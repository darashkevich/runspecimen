"""Protected runtime trust checks for the holder daemon source.

This module is the development-time implementation of the isolated runtime
chain. It does not prove that a live installed Holder.app is protected.
Unprivileged tests do not prove installed protection. Applying this to the
live /Applications install requires Yahor's explicit later approval.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Iterable

# Modules that must be present and trusted before the daemon serves.
_REQUIRED_RELATIVE = (
    "runspecimen/__init__.py",
    "runspecimen/holder_daemon.py",
    "runspecimen/holder_entry.py",
    "runspecimen/holder_drop_exec.py",
    "runspecimen/holder_runtime.py",
    "runspecimen/holder_io.py",
    "runspecimen/holder_adapter.py",
    "runspecimen/execution_holder.py",
    "runspecimen/holder_asymmetric.py",
    "runspecimen/holder_protocol.py",
)


class RuntimeTrustError(Exception):
    """The runtime path is not acceptable for privileged holder execution."""


def _lstat(path: Path) -> os.stat_result:
    try:
        return os.lstat(path)
    except OSError as exc:
        raise RuntimeTrustError(f"cannot lstat runtime path: {path}") from exc


def assert_path_chain(
    path: Path,
    *,
    require_uid: int = 0,
    allow_group_write: bool = False,
    allow_world_write: bool = False,
) -> Path:
    """Refuse symlinks and writable ownership along path and parents."""
    current = Path(path)
    if not current.is_absolute():
        raise RuntimeTrustError(f"runtime path must be absolute: {path}")
    parts = current.parts
    if parts[0] == "/":
        cursor = Path("/")
        start = 1
    else:
        cursor = Path(parts[0])
        start = 1
    for part in parts[start:]:
        cursor = cursor / part
        st = _lstat(cursor)
        if stat.S_ISLNK(st.st_mode):
            raise RuntimeTrustError(f"runtime path contains a symlink: {cursor}")
        if require_uid == 0 and os.geteuid() == 0 and st.st_uid != 0:
            raise RuntimeTrustError(f"runtime path is not root-owned: {cursor}")
        if require_uid != 0 and st.st_uid != require_uid and os.geteuid() == 0:
            raise RuntimeTrustError(f"runtime path uid mismatch: {cursor}")
        mode = stat.S_IMODE(st.st_mode)
        if not allow_world_write and mode & stat.S_IWOTH:
            raise RuntimeTrustError(f"runtime path is world-writable: {cursor}")
        if not allow_group_write and mode & stat.S_IWGRP:
            raise RuntimeTrustError(f"runtime path is group-writable: {cursor}")
    return cursor


def refuse_user_python_injection(env: dict[str, str] | None = None) -> None:
    """Refuse caller-selected interpreters and PYTHONPATH module injection."""
    source = env if env is not None else os.environ
    if source.get("RS_HOLDER_PYTHON"):
        raise RuntimeTrustError("RS_HOLDER_PYTHON is refused for protected holder runtime")
    if source.get("PYTHONPATH"):
        raise RuntimeTrustError("PYTHONPATH is refused for protected holder runtime")
    for key in ("PYTHONHOME", "PYTHONUSERBASE"):
        if source.get(key):
            raise RuntimeTrustError(f"{key} is refused for protected holder runtime")


def choose_protected_interpreter(
    *,
    embedded: Path | None,
    system_candidates: Iterable[Path] = (Path("/usr/bin/python3"),),
    require_root_owned: bool | None = None,
) -> Path:
    """Select an interpreter after ownership/mode/symlink checks.

    Prefers an embedded runtime under the app Resources tree when present.
    Homebrew and user-selected paths are never accepted.
    """
    refuse_user_python_injection()
    require_uid = 0 if (require_root_owned if require_root_owned is not None else os.geteuid() == 0) else os.geteuid()
    if embedded is not None and embedded.exists():
        chosen = assert_path_chain(embedded, require_uid=require_uid)
        if not os.access(chosen, os.X_OK):
            raise RuntimeTrustError(f"embedded interpreter is not executable: {chosen}")
        return chosen
    for candidate in system_candidates:
        text = str(candidate)
        if "homebrew" in text or "/opt/homebrew/" in text or text.startswith("/Users/"):
            continue
        if not candidate.exists():
            continue
        chosen = assert_path_chain(
            candidate,
            require_uid=require_uid if require_uid == 0 else os.stat(candidate).st_uid,
        )
        if not os.access(chosen, os.X_OK):
            continue
        return chosen
    raise RuntimeTrustError("no protected interpreter available")


def assert_module_root(module_root: Path, *, require_uid: int | None = None) -> Path:
    """Validate the holder Python package root before import."""
    uid = 0 if require_uid is None and os.geteuid() == 0 else (
        require_uid if require_uid is not None else os.geteuid()
    )
    root = assert_path_chain(module_root, require_uid=uid)
    marker = root / "runspecimen" / "holder_daemon.py"
    assert_path_chain(marker, require_uid=uid)
    return root


def assert_shipped_runtime_chain(
    module_root: Path,
    *,
    entry: Path | None = None,
    interpreter: Path | None = None,
    require_uid: int | None = None,
) -> None:
    """Verify the shipped module/entry/interpreter trust chain before load."""
    refuse_user_python_injection()
    uid = 0 if require_uid is None and os.geteuid() == 0 else (
        require_uid if require_uid is not None else os.geteuid()
    )
    root = assert_module_root(module_root, require_uid=uid)
    for rel in _REQUIRED_RELATIVE:
        assert_path_chain(root / rel, require_uid=uid)
    if entry is not None:
        assert_path_chain(entry, require_uid=uid)
        if entry.name != "holder_entry.py":
            raise RuntimeTrustError("holder entrypoint must be holder_entry.py")
    if interpreter is not None:
        text = str(interpreter)
        if "homebrew" in text or "/opt/homebrew/" in text or text.startswith("/Users/"):
            raise RuntimeTrustError("interpreter path is not in the protected chain")
        assert_path_chain(interpreter, require_uid=uid if uid == 0 else os.stat(interpreter).st_uid)
    # When running as root, the executing interpreter must not be Homebrew or
    # under /Users. Unprivileged harnesses may use a venv for isolated tests;
    # those tests do not prove installed protection.
    if os.geteuid() == 0:
        exe = Path(sys.executable).resolve()
        exe_text = str(exe)
        if "homebrew" in exe_text or "/opt/homebrew/" in exe_text:
            raise RuntimeTrustError("running interpreter is Homebrew and refused")
        if exe_text.startswith("/Users/"):
            raise RuntimeTrustError("running interpreter is user-writable and refused")
