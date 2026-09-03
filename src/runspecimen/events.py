"""Append-only SHA-256 hash-chained event log with fcntl append serialization."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from runspecimen.hashutil import canonical_json_bytes, sha256_bytes
from runspecimen.paths import EVENTS_APPEND_LOCK_FILENAME, EVENTS_FILENAME

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

    def ensure(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _read_all_unlocked(self) -> list[EventRecord]:
        if not self.path.exists():
            return []
        records: list[EventRecord] = []
        with self.path.open("r", encoding="utf-8") as fh:
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
        return records

    def read_all(self) -> list[EventRecord]:
        """Read a stable snapshot while excluding an in-progress append."""
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
        self.ensure()
        self.append_lock_path.touch(exist_ok=True)
        fd = os.open(str(self.append_lock_path), os.O_RDWR)

        class _Guard:
            def __enter__(self_inner):
                fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
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
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
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
