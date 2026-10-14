"""Atomic file writes for crash-safe state."""

from __future__ import annotations

import errno
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from runspecimen.errors import PathEscapeError
from runspecimen.paths import assert_control_plane_not_symlinked, ensure_dir


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    assert_control_plane_not_symlinked(path)
    if path.is_symlink():
        raise PathEscapeError(
            f"refusing to write through a symlink: {path} -> {path.resolve()}"
        )
    ensure_dir(path.parent)
    if path.parent.is_symlink():
        raise PathEscapeError(
            f"refusing to write through a symlink directory: {path.parent}"
        )
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        # Best-effort directory fsync for durability on crash.
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, obj: Any, *, sort_keys: bool = True) -> None:
    payload = json.dumps(obj, indent=2, sort_keys=sort_keys, separators=(",", ": ")) + "\n"
    atomic_write_text(path, payload)


def read_text_nofollow(path: Path, *, encoding: str = "utf-8") -> str:
    """Read a regular file without following a symlink."""
    if path.is_symlink():
        raise PathEscapeError(f"refusing to follow a symlink: {path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        if getattr(exc, "errno", None) in {errno.ELOOP, errno.EPERM} or path.is_symlink():
            raise PathEscapeError(f"refusing to follow a symlink: {path}") from exc
        raise
    try:
        info = os.fstat(fd)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise PathEscapeError(f"refusing to follow a symlink: {path}")
        with os.fdopen(fd, "r", encoding=encoding) as fh:
            fd = -1
            return fh.read()
    finally:
        if fd >= 0:
            os.close(fd)


def read_json_nofollow(path: Path) -> Any:
    return json.loads(read_text_nofollow(path))


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
