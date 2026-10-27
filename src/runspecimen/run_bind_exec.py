#!/usr/bin/env python3
"""Bind a contract payload to the supervising parent.

The supervisor has a control-pipe thread, so it cannot use ``preexec_fn``.
This helper is a single-threaded exec wrapper:

- Linux ``PR_SET_PDEATHSIG`` so the payload dies if the supervisor dies
- A watchdog in its own session that ``killpg``s the payload group if the
  supervisor pid vanishes (portable, including macOS). It is not a
  process-group member, so a macOS ``killpg`` ESRCH after the leader
  exits cannot leave cleanup unconfirmed.
- The watchdog holds an inherited workspace-lease fd so SIGKILL of the
  supervisor cannot free the lease while the payload is still alive
- ``exec`` of the payload in the same pid (the ``Popen(start_new_session)``
  session leader)

A descendant that calls ``setsid()`` leaves this process group and is
outside ``cleanup_confirmed``.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path


def bind_argv(
    payload: list[str],
    *,
    parent_pid: int,
    lease_fd: int | None,
) -> list[str]:
    """Wrap *payload* so it dies with the supervising parent."""
    helper = str(Path(__file__).resolve())
    argv = [sys.executable, helper, "--parent-pid", str(parent_pid)]
    if lease_fd is not None:
        argv.extend(["--lease-fd", str(lease_fd)])
    argv.append("--")
    argv.extend(payload)
    return argv


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _set_pdeathsig(sig: int = signal.SIGKILL) -> bool:
    if sys.platform != "linux":
        return False
    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
        ]
        libc.prctl.restype = ctypes.c_int
        return libc.prctl(1, sig, 0, 0, 0) == 0
    except (OSError, AttributeError):
        return False


def _detach_stdio() -> None:
    null = os.open(os.devnull, os.O_RDWR)
    try:
        for fd in (0, 1, 2):
            os.dup2(null, fd)
    finally:
        if null > 2:
            os.close(null)


def _run_watchdog(parent: int, payload_pgid: int) -> None:
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_IGN)
    try:
        os.setsid()
    except OSError:
        pass
    _detach_stdio()
    while True:
        if not _pid_alive(parent):
            try:
                os.killpg(payload_pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            os._exit(1)
        if os.getppid() == 1:
            os._exit(0)
        time.sleep(0.02)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run-bind-exec")
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--lease-fd", type=int, default=-1)
    parser.add_argument("payload", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    payload = list(args.payload)
    if payload and payload[0] == "--":
        payload = payload[1:]
    if not payload:
        print("run-bind-exec: payload argv is missing", file=sys.stderr)
        return 2

    parent = int(args.parent_pid)
    lease_fd = int(args.lease_fd) if int(args.lease_fd) >= 0 else None

    _set_pdeathsig()
    if not _pid_alive(parent) or os.getppid() == 1:
        return 1

    payload_pgid = os.getpgrp()
    watch = os.fork()
    if watch == 0:
        _run_watchdog(parent, payload_pgid)
        os._exit(1)

    if lease_fd is not None:
        try:
            os.close(lease_fd)
        except OSError:
            pass

    try:
        os.execvp(payload[0], payload)
    except OSError as exc:
        print(f"run-bind-exec: exec failed: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
