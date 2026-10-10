"""Append-only SHA-256 hash-chained event log with fcntl append serialization."""

from __future__ import annotations

import errno
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from runspecimen.errors import PathEscapeError
from runspecimen.hashutil import canonical_json_bytes, sha256_bytes
from runspecimen.paths import (
    EVENTS_APPEND_LOCK_FILENAME,
    EVENTS_FILENAME,
    assert_control_plane_not_symlinked,
    ensure_dir,
    open_regular_nofollow,
)

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

GENESIS_HASH = "0" * 64


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class EventRecord:
    seq: int
    prev_hash: str
    event_hash: str
    ts: str
    type: str
    body: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "prev_hash": self.prev_hash,
            "event_hash": self.event_hash,
            "ts": self.ts,
            "type": self.type,
            "body": self.body,
        }


def _line_hash(prev_hash: str, seq: int, ts: str, event_type: str, body: dict[str, Any]) -> str:
    material = {
        "body": body,
        "prev_hash": prev_hash,
        "seq": seq,
        "ts": ts,
        "type": event_type,
    }
    return sha256_bytes(canonical_json_bytes(material))


class EventLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.append_lock_path = path.parent / EVENTS_APPEND_LOCK_FILENAME

    @classmethod
    def for_state_dir(cls, state_dir: Path) -> EventLog:
        return cls(state_dir / EVENTS_FILENAME)

    def _prepare_log_parent(self) -> None:
        assert_control_plane_not_symlinked(self.path)
        ensure_dir(self.path.parent)
        if self.path.is_symlink():
            raise PathEscapeError(
                f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
            )

    def _ensure_file_unlocked(self) -> None:
        """Create the log if needed. Caller holds the append lock."""
        if self.path.is_symlink():
            raise PathEscapeError(
                f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
            )
        try:
            info = os.lstat(self.path)
        except FileNotFoundError:
            info = None
        else:
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise PathEscapeError(
                    f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
                )
            return
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(str(self.path), flags, 0o644)
        except FileExistsError:
            try:
                info = os.lstat(self.path)
            except OSError as exc:
                raise PathEscapeError(
                    f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
                ) from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise PathEscapeError(
                    f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
                )
            return
        except OSError as exc:
            if getattr(exc, "errno", None) in {errno.ELOOP, errno.EPERM}:
                raise PathEscapeError(
                    f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
                ) from exc
            raise
        else:
            os.close(fd)

    def ensure(self) -> None:
        self._prepare_log_parent()
        with self._with_lock(exclusive=True):
            return

    def _read_all_unlocked(self) -> list[EventRecord]:
        if self.path.is_symlink():
            raise PathEscapeError(
                f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
            )
        if not self.path.exists():
            return []
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(str(self.path), flags)
        except OSError as exc:
            if getattr(exc, "errno", None) in {errno.ELOOP, errno.EPERM} or self.path.is_symlink():
                raise PathEscapeError(
                    f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
                ) from exc
            raise
        records: list[EventRecord] = []
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise PathEscapeError(
                    f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
                )
            with os.fdopen(fd, "r", encoding="utf-8") as fh:
                fd = -1
                for line_no, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        records.append(
                            EventRecord(
                                seq=int(obj["seq"]),
                                prev_hash=str(obj["prev_hash"]),
                                event_hash=str(obj["event_hash"]),
                                ts=str(obj["ts"]),
                                type=str(obj["type"]),
                                body=dict(obj["body"]),
                            )
                        )
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise ValueError(f"corrupt event log at line {line_no}: {exc}") from exc
        finally:
            if fd >= 0:
                os.close(fd)
        return records

    def read_all(self) -> list[EventRecord]:
        """Read a stable snapshot while excluding an in-progress append."""
        if self.path.is_symlink():
            raise PathEscapeError(
                f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
            )
        if not self.path.exists():
            return []
        with self._with_lock(exclusive=False):
            return self._read_all_unlocked()

    def head_hash(self) -> str:
        records = self.read_all()
        if not records:
            return GENESIS_HASH
        return records[-1].event_hash

    def last(self) -> EventRecord | None:
        records = self.read_all()
        return records[-1] if records else None

    def _with_lock(self, *, exclusive: bool):
        if fcntl is None:
            raise RuntimeError("fcntl event lock requires a POSIX platform")
        self._prepare_log_parent()
        fd = open_regular_nofollow(self.append_lock_path, os.O_RDWR | os.O_CREAT, 0o644)

        class _Guard:
            def __enter__(self_inner):
                fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                if exclusive:
                    self._ensure_file_unlocked()
                return fd

            def __exit__(self_inner, exc_type, exc, tb):
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
                return False

        return _Guard()

    def append(self, event_type: str, body: dict[str, Any], *, ts: str | None = None) -> EventRecord:
        """Serialize read-then-append under an exclusive fcntl lock."""
        with self._with_lock(exclusive=True):
            records = self._read_all_unlocked()
            seq = (records[-1].seq + 1) if records else 1
            prev = records[-1].event_hash if records else GENESIS_HASH
            stamp = ts or utc_now_iso()
            event_hash = _line_hash(prev, seq, stamp, event_type, body)
            record = EventRecord(
                seq=seq,
                prev_hash=prev,
                event_hash=event_hash,
                ts=stamp,
                type=event_type,
                body=body,
            )
            line = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
            if self.path.is_symlink():
                raise PathEscapeError(
                    f"control-plane path must not be a symlink (or contain a symlinked component): {self.path}"
                )
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(str(self.path), flags, 0o644)
            try:
                with os.fdopen(fd, "a", encoding="utf-8") as fh:
                    fd = -1
                    fh.write(line)
                    fh.flush()
                    os.fsync(fh.fileno())
            except Exception:
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                raise
            return record

    def verify_chain(self) -> tuple[bool, str]:
        records = self.read_all()
        prev = GENESIS_HASH
        expected_seq = 1
        for rec in records:
            if rec.seq != expected_seq:
                return False, f"seq gap: expected {expected_seq}, got {rec.seq}"
            if rec.prev_hash != prev:
                return False, f"prev_hash mismatch at seq {rec.seq}"
            recomputed = _line_hash(rec.prev_hash, rec.seq, rec.ts, rec.type, rec.body)
            if recomputed != rec.event_hash:
                return False, f"event_hash mismatch at seq {rec.seq}"
            prev = rec.event_hash
            expected_seq += 1
        return True, "ok"

    def iter_types(self, event_type: str) -> Iterator[EventRecord]:
        for rec in self.read_all():
            if rec.type == event_type:
                yield rec
