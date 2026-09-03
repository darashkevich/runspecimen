"""Cross-process exclusive workspace execution lease via fcntl with PID metadata."""

from __future__ import annotations

import contextlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.errors import LeaseError
from runspecimen.paths import (
    LEASE_FILENAME,
    LEASE_META_FILENAME,
    ensure_dir,
    resolve_workspace,
    workspace_state_root,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]


@dataclass
class LeaseMeta:
    pid: int
    created_ts: float
    holder: str

    def to_dict(self) -> dict[str, object]:
        return {
            "created_ts": self.created_ts,
            "holder": self.holder,
            "pid": self.pid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LeaseMeta:
        return cls(
            pid=int(data["pid"]),
            created_ts=float(data["created_ts"]),
            holder=str(data["holder"]),
        )


class Lease:
    """Exclusive advisory lock held for the lifetime of the open lock file fd."""

    def __init__(self, lock_dir: Path, *, holder: str) -> None:
        if fcntl is None:
            raise LeaseError("fcntl leases require a POSIX platform")
        self.lock_dir = ensure_dir(lock_dir)
        self.lock_path = self.lock_dir / LEASE_FILENAME
        self.meta_path = self.lock_dir / LEASE_META_FILENAME
        self.holder = holder
        self._fd: int | None = None
        self.meta: LeaseMeta | None = None

    @classmethod
    def for_workspace(cls, workspace: Path, *, holder: str) -> Lease:
        ws = resolve_workspace(workspace)
        return cls(workspace_state_root(ws), holder=holder)

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self, *, blocking: bool = False) -> None:
        if self._fd is not None:
            return
        self.lock_path.touch(exist_ok=True)
        fd = os.open(str(self.lock_path), os.O_RDWR)
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except OSError as exc:
            os.close(fd)
            existing = self.read_meta()
            detail = ""
            if existing is not None:
                detail = f" (held by pid={existing.pid} holder={existing.holder!r})"
            raise LeaseError(f"workspace execution lease unavailable{detail}") from exc
        self._fd = fd
        self.meta = LeaseMeta(pid=os.getpid(), created_ts=time.time(), holder=self.holder)
        atomic_write_json(self.meta_path, self.meta.to_dict())

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            try:
                self.meta_path.unlink()
            except FileNotFoundError:
                pass
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None
            self.meta = None

    def read_meta(self) -> LeaseMeta | None:
        if not self.meta_path.exists():
            return None
        try:
            return LeaseMeta.from_dict(read_json(self.meta_path))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def is_locked_by_other(self) -> bool:
        """Non-destructive probe: True if another process holds the lease."""
        if self._fd is not None:
            return False
        ensure_dir(self.lock_dir)
        self.lock_path.touch(exist_ok=True)
        fd = os.open(str(self.lock_path), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        finally:
            os.close(fd)


@contextlib.contextmanager
def hold_lease(lock_dir: Path, *, holder: str, blocking: bool = False) -> Iterator[Lease]:
    lease = Lease(lock_dir, holder=holder)
    lease.acquire(blocking=blocking)
    try:
        yield lease
    finally:
        lease.release()


@contextlib.contextmanager
def hold_workspace_lease(
    workspace: Path, *, holder: str, blocking: bool = False
) -> Iterator[Lease]:
    """Exclusive workspace-wide lease for lifecycle mutations."""
    lease = Lease.for_workspace(workspace, holder=holder)
    lease.acquire(blocking=blocking)
    try:
        yield lease
    finally:
        lease.release()
