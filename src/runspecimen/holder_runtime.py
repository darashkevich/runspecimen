"""Protected runtime trust checks for the holder daemon source.

This module is the development-time implementation of the isolated runtime
chain. It does not prove that a live installed Holder.app is protected.
Unprivileged tests do not prove installed protection. Applying this to the
live /Applications install requires Yahor's explicit later approval.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Iterable


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
    resolved_parts: list[Path] = []
    current = Path(path)
    # Walk from root down using the lexical path, lstat each component.
    if not current.is_absolute():
        raise RuntimeTrustError(f"runtime path must be absolute: {path}")
    parts = current.parts
    cursor = Path(parts[0]) if parts[0] == "/" else Path(parts[0])
    if parts[0] == "/":
        cursor = Path("/")
        start = 1
    else:
        start = 0
    for part in parts[start:]:
        cursor = cursor / part
        st = _lstat(cursor)
        if stat.S_ISLNK(st.st_mode):
            raise RuntimeTrustError(f"runtime path contains a symlink: {cursor}")
        if st.st_uid != require_uid and require_uid == 0 and os.geteuid() == 0:
            raise RuntimeTrustError(f"runtime path is not root-owned: {cursor}")
        mode = stat.S_IMODE(st.st_mode)
        if not allow_world_write and mode & stat.S_IWOTH:
            raise RuntimeTrustError(f"runtime path is world-writable: {cursor}")
        if not allow_group_write and mode & stat.S_IWGRP:
            raise RuntimeTrustError(f"runtime path is group-writable: {cursor}")
        resolved_parts.append(cursor)
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
        chosen = assert_path_chain(candidate, require_uid=require_uid if require_uid == 0 else os.stat(candidate).st_uid)
        if not os.access(chosen, os.X_OK):
            continue
        return chosen
    raise RuntimeTrustError("no protected interpreter available")


def assert_module_root(module_root: Path, *, require_uid: int | None = None) -> Path:
    """Validate the holder Python package root before import."""
    uid = 0 if require_uid is None and os.geteuid() == 0 else (require_uid if require_uid is not None else os.geteuid())
    root = assert_path_chain(module_root, require_uid=uid)
    marker = root / "runspecimen" / "holder_daemon.py"
    assert_path_chain(marker, require_uid=uid)
    return root
