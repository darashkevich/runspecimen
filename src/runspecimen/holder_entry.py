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
import sys
from pathlib import Path


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
