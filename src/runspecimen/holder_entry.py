#!/usr/bin/env python3
"""Isolated holder daemon entrypoint.

This file is executed by path (``python -I /…/holder_entry.py``), never via
``python -m runspecimen…``. It inserts its own directory onto ``sys.path``
*before* importing ``runspecimen``, so discovery does not depend on
``RS_HOLDER_MODULE_ROOT`` being processed after module import.

Unprivileged tests do not prove installed protection. This is source only;
applying it to the live /Applications install requires later Yahor approval.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

# Checked with the standard library before any runspecimen import.
_BEFORE_IMPORT = (
    "holder_daemon.py",
    "holder_entry.py",
    "holder_runtime.py",
    "execution_holder.py",
    "holder_asymmetric.py",
    "native_bridge.py",
)


def _walk_existing(path: Path) -> None:
    if not path.is_absolute():
        raise SystemExit(f"runtime path must be absolute: {path}")
    # macOS /var is a symlink to /private/var. Follow that system alias, then
    # refuse a symlink that remains on the resolved chain.
    real = Path(os.path.realpath(path))
    cursor = Path("/")
    for part in real.parts[1:]:
        cursor = cursor / part
        if not cursor.exists():
            raise SystemExit(f"runtime path missing before import: {cursor}")
        st = os.lstat(cursor)
        if stat.S_ISLNK(st.st_mode):
            raise SystemExit(f"runtime path contains a symlink: {cursor}")
        mode = stat.S_IMODE(st.st_mode)
        if mode & stat.S_IWOTH:
            sticky = bool(st.st_mode & stat.S_ISVTX) and stat.S_ISDIR(st.st_mode)
            if not sticky:
                raise SystemExit(f"runtime path is world-writable: {cursor}")


def validate_before_import(module_root: Path) -> None:
    """Refuse a hostile tree before importing holder code or reading a secret.

    Supported installed layout is a root-owned app under /Applications. The
    Store app is a different bundle and is not this runtime. This check does
    not claim a reproduced exploit against the live holder.
    """

    root = Path(module_root)
    _walk_existing(root)
    package = root / "runspecimen"
    for name in _BEFORE_IMPORT:
        path = package / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"runtime file is missing or a symlink: {path}")
        st = os.lstat(path)
        if stat.S_IMODE(st.st_mode) & 0o022:
            raise SystemExit(f"runtime file is group or world writable: {path}")


def _bootstrap() -> None:
    # Refuse user-selected interpreters / module injection before any import.
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "RS_HOLDER_PYTHON"):
        if os.environ.get(key):
            raise SystemExit(f"{key} is refused for protected holder runtime")
    here = Path(__file__).resolve().parent
    # holder_entry.py lives inside the runspecimen package OR as a sibling of it.
    # Supported layouts:
    #   <moduleRoot>/runspecimen/holder_entry.py  -> insert <moduleRoot>
    #   <moduleRoot>/holder_entry.py              -> insert <moduleRoot>
    if here.name == "runspecimen" and (here / "holder_daemon.py").is_file():
        module_root = here.parent
    else:
        module_root = here
    # Put the trusted module root first; do not inherit a caller PYTHONPATH.
    sys.path = [str(module_root), *[p for p in sys.path if p not in {"", str(module_root)}]]
    # Drop the env hint if present; import path is already correct.
    os.environ.pop("RS_HOLDER_MODULE_ROOT", None)


def main(argv: list[str] | None = None) -> int:
    _bootstrap()
    module_root = Path(__file__).resolve().parent
    if module_root.name == "runspecimen":
        module_root = module_root.parent
    validate_before_import(module_root)
    from runspecimen.holder_runtime import (
        RuntimeTrustError,
        assert_module_root,
        assert_shipped_runtime_chain,
        refuse_user_python_injection,
    )

    try:
        refuse_user_python_injection()
        module_root = Path(__file__).resolve().parent
        if module_root.name == "runspecimen":
            module_root = module_root.parent
        assert_module_root(module_root)
        assert_shipped_runtime_chain(module_root, entry=Path(__file__).resolve())
    except RuntimeTrustError as exc:
        raise SystemExit(str(exc)) from exc
    from runspecimen.holder_daemon import main as daemon_main

    return int(daemon_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
