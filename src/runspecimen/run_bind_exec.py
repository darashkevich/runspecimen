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
import errno
import os
import signal
import subprocess
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


def _read_pid_state(pid: int) -> str | None:
    """Return the kernel state letter, or None when it cannot be read."""
    proc_stat = Path(f"/proc/{pid}/stat")
    try:
        content = proc_stat.read_text()
    except FileNotFoundError:
        if Path("/proc/self/stat").exists():
            return None
    except OSError:
        return None
    else:
        try:
            return content.rsplit(")", 1)[1].split()[0]
        except (IndexError, ValueError):
            return None
    try:
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "state="],
            capture_output=True,
            text=True,
            timeout=0.2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    state = result.stdout.strip()
    return state or None


def _pid_status(pid: int) -> str:
    """Return gone, zombie, live, or unknown."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "gone"
    except PermissionError:
        pass
    state = _read_pid_state(pid)
    if state is None:
        return "unknown"
    if state.startswith("Z"):
        return "zombie"
    return "live"


def _pid_alive(pid: int) -> bool:
    """True only for a process that is not gone and not a zombie.

    ``kill(pid, 0)`` succeeds on an unreaped zombie. The watchdog must not
    treat that as a live supervisor (PR80-P2-04).
    """
    return _pid_status(pid) in {"live", "unknown"}


def _payload_group_live_members(pgid: int) -> list[int] | None:
    """Non-zombie members of *pgid*, or None when membership is unknown."""
    if Path("/proc/self/stat").exists():
        try:
            entries = list(Path("/proc").iterdir())
        except OSError:
            return None
        members: list[int] = []
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                stat_content = (entry / "stat").read_text()
                tail = stat_content.rsplit(")", 1)[1].split()
                state = tail[0]
                pgrp = int(tail[2])
            except FileNotFoundError:
                continue
            except (IndexError, ValueError, ProcessLookupError):
                continue
            except OSError as exc:
                if getattr(exc, "errno", None) in {errno.ENOENT, errno.ESRCH}:
                    continue
                return None
            else:
                if pgrp == pgid and state != "Z":
                    members.append(int(entry.name))
        return members
    try:
        result = subprocess.run(
            ["/bin/ps", "-axo", "pid=,pgid=,state="],
            capture_output=True,
            text=True,
            timeout=0.2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    members = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            group = int(parts[1])
            state = parts[2]
        except ValueError:
            continue
        if group == pgid and not state.startswith("Z"):
            members.append(pid)
    return members


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
        status = _pid_status(parent)
        reparented = os.getppid() == 1
        if status == "live" and reparented:
            # Payload already exited; the supervisor still holds the lease.
            os._exit(0)
        if status in {"live", "unknown"} and not reparented:
            time.sleep(0.02)
            continue
        try:
            os.killpg(payload_pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        members = _payload_group_live_members(payload_pgid)
        if members == []:
            os._exit(1)
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
