"""Bounded AF_UNIX framing for the unprivileged holder adapter and daemon source.

These helpers do not prove installed protection. They exist so a stalled or
malformed client cannot block the server forever or grow memory without bound.
Tests must drive the unprivileged adapter only; they must not point at a live
root socket.
"""

from __future__ import annotations

import socket
import threading
from typing import Final

MAX_FRAME_BYTES: Final[int] = 1_048_576
DEFAULT_READ_TIMEOUT_SEC: Final[float] = 5.0
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
    timeout_sec: float = DEFAULT_READ_TIMEOUT_SEC,
) -> str:
    """Read one newline-terminated frame with a deadline and byte cap."""
    if max_bytes < 1:
        raise FrameError("holder frame limit is invalid")
    previous = conn.gettimeout()
    conn.settimeout(timeout_sec)
    try:
        buf = bytearray()
        while True:
            try:
                piece = conn.recv(min(65536, max_bytes - len(buf) + 1))
            except TimeoutError as exc:
                raise FrameError("holder read timed out") from exc
            except socket.timeout as exc:
                raise FrameError("holder read timed out") from exc
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


def write_frame(conn: socket.socket, text: str) -> None:
    if "\n" in text:
        raise FrameError("holder response must be a single frame")
    conn.sendall(text.encode("utf-8") + b"\n")
