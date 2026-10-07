"""Bounded AF_UNIX framing for the unprivileged holder adapter and daemon source.

These helpers do not prove installed protection. Absolute read/write deadlines
prevent slow clients from retaining admission slots indefinitely. Tests must
drive the unprivileged adapter only; they must not point at a live root socket.
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Final

MAX_FRAME_BYTES: Final[int] = 1_048_576
DEFAULT_DEADLINE_SEC: Final[float] = 5.0
DEFAULT_READ_TIMEOUT_SEC: Final[float] = DEFAULT_DEADLINE_SEC
DEFAULT_ACCEPT_BACKLOG: Final[int] = 8
DEFAULT_MAX_IN_FLIGHT: Final[int] = 4


class FrameError(Exception):
    """Framing, timeout, or admission failure on the holder socket."""


class AdmissionGate:
    """Limit concurrent in-flight connections. Excess clients are refused."""

    def __init__(self, limit: int = DEFAULT_MAX_IN_FLIGHT) -> None:
        if limit < 1:
            raise ValueError("admission limit must be at least 1")
        self._sem = threading.BoundedSemaphore(limit)

    def try_enter(self) -> bool:
        return self._sem.acquire(blocking=False)

    def leave(self) -> None:
        self._sem.release()


def read_frame(
    conn: socket.socket,
    *,
    max_bytes: int = MAX_FRAME_BYTES,
    deadline_sec: float = DEFAULT_DEADLINE_SEC,
    timeout_sec: float | None = None,
) -> str:
    """Read one newline-terminated frame under an absolute monotonic deadline."""
    if max_bytes < 1:
        raise FrameError("holder frame limit is invalid")
    # Backward-compatible alias: timeout_sec means the same absolute budget.
    budget = float(deadline_sec if timeout_sec is None else timeout_sec)
    if budget <= 0:
        raise FrameError("holder read deadline is invalid")
    end = time.monotonic() + budget
    previous = conn.gettimeout()
    try:
        buf = bytearray()
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise FrameError("holder read deadline exceeded")
            conn.settimeout(remaining)
            try:
                piece = conn.recv(min(65536, max_bytes - len(buf) + 1))
            except TimeoutError as exc:
                raise FrameError("holder read deadline exceeded") from exc
            except socket.timeout as exc:
                raise FrameError("holder read deadline exceeded") from exc
            if not piece:
                break
            buf.extend(piece)
            if len(buf) > max_bytes:
                raise FrameError("holder message exceeds frame limit")
            if b"\n" in piece:
                break
        if not buf.endswith(b"\n"):
            raise FrameError("holder connection closed before a message")
        try:
            return buf.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FrameError("holder message is not utf-8") from exc
    finally:
        try:
            conn.settimeout(previous)
        except OSError:
            pass


def write_frame(
    conn: socket.socket,
    text: str,
    *,
    deadline_sec: float = DEFAULT_DEADLINE_SEC,
) -> None:
    """Write one frame under an absolute monotonic deadline."""
    if "\n" in text:
        raise FrameError("holder response must be a single frame")
    if deadline_sec <= 0:
        raise FrameError("holder write deadline is invalid")
    payload = text.encode("utf-8") + b"\n"
    end = time.monotonic() + float(deadline_sec)
    previous = conn.gettimeout()
    try:
        view = memoryview(payload)
        offset = 0
        while offset < len(payload):
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise FrameError("holder write deadline exceeded")
            conn.settimeout(remaining)
            try:
                sent = conn.send(view[offset:])
            except TimeoutError as exc:
                raise FrameError("holder write deadline exceeded") from exc
            except socket.timeout as exc:
                raise FrameError("holder write deadline exceeded") from exc
            if sent == 0:
                raise FrameError("holder write closed")
            offset += sent
    finally:
        try:
            conn.settimeout(previous)
        except OSError:
            pass
