"""Test-only unprivileged launch fault harness.

This file is not a root holder and it is not used by ``runspecimen run``.
The in-memory simulator is a different module. This harness uses real
pipes, real child processes, and fsynced durable files. A fault calls
``os._exit`` in the holder process so the kernel closes its pipes and the
child is not reaped by that holder.
"""

from __future__ import annotations

import os
import secrets
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

from runspecimen.holder_protocol import (
    ProtocolError,
    assess_durable,
    read_durable_record,
    write_durable_record,
)

# Kill points. "before_*" exits without that fsync. "after_*" exits after it.
FAULTS = (
    "before_consume",
    "after_consume",
    "before_intent",
    "after_intent",
    "before_spawn",
    "after_fork_before_armed",
    "after_armed_before_release",
    "after_armed",
    "before_go",
    "after_go",
    "after_ack",
    "before_acked_fsync",
    "after_acked",
    "before_commit",
    "after_commit",
    "before_running_fsync",
    "after_running",
    "wrapper_eof",
    "descendant",
)

EXIT_STOPPED = 0
EXIT_ERROR = 2
EXIT_LEASE = 3
EXIT_SPENT = 4


def os_start(pid: int) -> str | None:
    """Stable process start string. Not an exit status and not ``waitpid``."""

    try:
        out = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "lstart="],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    text = out.strip()
    return text or None


def liveness(recorded: str | None, current: str | None) -> str:
    if recorded and current and recorded != current:
        return "pid-reuse-not-adopted"
    if current:
        return "alive"
    return "dead"


def _spent_path(root: Path) -> Path:
    return root / "spent.json"


def _durable_path(root: Path) -> Path:
    return root / "durable.json"


def load_spent(root: Path) -> set[str]:
    path = _spent_path(root)
    if not path.exists():
        return set()
    try:
        data = read_durable_record(path)
    except ProtocolError:
        return set()
    nonces = data.get("nonces") if isinstance(data, dict) else None
    if not isinstance(nonces, list):
        return set()
    return {item for item in nonces if isinstance(item, str)}


def _remember(root: Path, nonce: str) -> None:
    spent = load_spent(root)
    spent.add(nonce)
    write_durable_record(_spent_path(root), {"nonces": sorted(spent)})


def _write_phase(root: Path, fields: dict[str, object]) -> None:
    record = {key: value for key, value in fields.items() if value is not None}
    write_durable_record(_durable_path(root), record)


def _markers(root: Path) -> list[dict[str, object]]:
    folder = root / "procs"
    if not folder.exists():
        return []
    found: list[dict[str, object]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = read_durable_record(path)
        except ProtocolError:
            continue
        if isinstance(data, dict):
            found.append(data)
    return found


def _pid_state(pid: object, recorded: object) -> str:
    if type(pid) is not int or pid <= 0:
        return "dead"
    return liveness(recorded if isinstance(recorded, str) else None, os_start(pid))


def recover(root: Path) -> dict[str, object]:
    """Read fsynced files from a process that is not the holder.

    ``wait`` is ``echild`` because this process must not treat ``waitpid``
    as an exit status. ``success`` is false. A live pid or a mismatched
    start string keeps the lease. A dead pid with no live descendant drops
    the lease and is still not success.
    """

    try:
        record = read_durable_record(_durable_path(root))
    except ProtocolError:
        record = {"phase": []}
    if record is None:
        base = assess_durable(None)
    elif isinstance(record, dict):
        base = assess_durable(record)
    else:
        base = assess_durable({"phase": []})
    states: list[str] = []
    if isinstance(record, dict):
        states.append(_pid_state(record.get("pid"), record.get("os_start")))
    for marker in _markers(root):
        states.append(_pid_state(marker.get("pid"), marker.get("os_start")))
    alive = "alive" in states
    reuse = "pid-reuse-not-adopted" in states
    decision = dict(base)
    decision["success"] = False
    decision["wait"] = "echild"
    decision["spawn"] = False
    if reuse:
        decision["lease"] = True
        decision["action"] = "pid-reuse-not-adopted"
        decision["phase"] = "unknown"
        return decision
    if alive:
        decision["lease"] = True
        decision["action"] = "supervise"
        return decision
    if base["action"] == "partial-record":
        decision["lease"] = True
        return decision
    if base["phase"] in {"armed", "acked", "running"}:
        decision["lease"] = False
        decision["action"] = "terminated-without-status"
        return decision
    return decision


def _note_reap(root: Path, pid: int) -> None:
    folder = root / "reap"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / str(pid)).write_text(str(pid), encoding="utf-8")


def reap(root: Path) -> None:
    """Kill harness children whose start string still matches. Skip pid reuse."""

    pids: set[int] = set()
    folder = root / "reap"
    if folder.exists():
        for path in folder.glob("*"):
            try:
                pids.add(int(path.name))
            except ValueError:
                continue
    recorded: dict[int, str] = {}
    durable = _durable_path(root)
    if durable.exists():
        try:
            data = read_durable_record(durable)
        except ProtocolError:
            data = None
        if isinstance(data, dict) and type(data.get("pid")) is int and isinstance(data.get("os_start"), str):
            recorded[data["pid"]] = data["os_start"]
    for marker in _markers(root):
        pid = marker.get("pid")
        start = marker.get("os_start")
        if type(pid) is int and isinstance(start, str):
            recorded[pid] = start
            pids.add(pid)
    for pid in pids:
        current = os_start(pid)
        known = recorded.get(pid)
        if known and current and known != current:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _read_line(fd: int, timeout: float = 5) -> str:
    buffer = b""
    deadline = time.time() + timeout
    while b"\n" not in buffer:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("wrapper produced no line")
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            raise TimeoutError("wrapper produced no line")
        chunk = os.read(fd, 1024)
        if not chunk:
            raise EOFError("wrapper closed its pipe")
        buffer += chunk
    line, _, _ = buffer.partition(b"\n")
    return line.decode("utf-8", "replace")


def _sleep_until_killed() -> None:
    time.sleep(30)
    os._exit(0)


def _write_marker(root: Path, nonce: str, start: int, image: str, pipe: str | None = None) -> None:
    pid = os.getpid()
    folder = root / "procs"
    folder.mkdir(parents=True, exist_ok=True)
    fields: dict[str, object] = {
        "pid": pid,
        "start": start,
        "os_start": os_start(pid),
        "image": image,
        "nonce": nonce,
    }
    if pipe is not None:
        fields["pipe"] = pipe
    write_durable_record(folder / f"{pid}.json", fields)


def _say(text: str) -> None:
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except BrokenPipeError:
        _sleep_until_killed()


def _wrapper(root: Path, nonce: str, start: int) -> None:
    _write_marker(root, nonce, start, "wrapper")
    _say("ready\n")
    while True:
        line = sys.stdin.readline()
        if line == "":
            _write_marker(root, nonce, start, "wrapper", pipe="eof")
            _say("eof\n")
            _sleep_until_killed()
        command = line.strip()
        if command == "go":
            _say("ack\n")
            continue
        if command in {"commit", "commit-descendant"}:
            _write_marker(root, nonce, start, "payload")
            if command == "commit-descendant":
                pid = os.fork()
                if pid == 0:
                    os.setsid()
                    null = os.open("/dev/null", os.O_RDWR)
                    os.dup2(null, 0)
                    os.dup2(null, 1)
                    os.dup2(null, 2)
                    _write_marker(root, nonce, start + 1, "descendant")
                    _sleep_until_killed()
                deadline = time.time() + 5
                while not (root / "procs" / f"{pid}.json").exists():
                    if time.time() > deadline:
                        os._exit(EXIT_ERROR)
                    time.sleep(0.01)
                _say("running\n")
                os._exit(0)
            _say("running\n")
            _sleep_until_killed()
        os._exit(EXIT_ERROR)


def _spawn(root: Path, nonce: str, start: int) -> tuple[int, int, int, int]:
    release_r, release_w = os.pipe()
    cmd_r, cmd_w = os.pipe()
    out_r, out_w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.dup2(cmd_r, 0)
        os.dup2(out_w, 1)
        null = os.open("/dev/null", os.O_RDWR)
        os.dup2(null, 2)
        for fd in (release_w, cmd_w, out_w, cmd_r, out_r):
            os.close(fd)
        try:
            got = os.read(release_r, 1)
            os.close(release_r)
            if got != b"x":
                _sleep_until_killed()
            _wrapper(root, nonce, start)
        except Exception:
            os._exit(EXIT_ERROR)
        os._exit(0)
    os.close(release_r)
    os.close(cmd_r)
    os.close(out_w)
    _note_reap(root, pid)
    return pid, release_w, cmd_w, out_r


def _clear_stale_tmp(root: Path) -> None:
    for path in root.glob("*.tmp"):
        path.unlink()
    procs = root / "procs"
    if procs.exists():
        for path in procs.glob("*.tmp"):
            path.unlink()


def holder_main(root: Path, nonce: str, fault: str) -> None:
    if fault not in FAULTS:
        os._exit(EXIT_ERROR)
    root.mkdir(parents=True, exist_ok=True)
    _clear_stale_tmp(root)
    decision = recover(root)
    if decision["lease"]:
        os._exit(EXIT_LEASE)
    if nonce in load_spent(root):
        os._exit(EXIT_SPENT)

    def stop(name: str) -> None:
        if fault == name:
            os._exit(EXIT_STOPPED)

    stop("before_consume")
    _remember(root, nonce)
    _write_phase(root, {"phase": "consumed", "nonce": nonce})
    stop("after_consume")
    stop("before_intent")
    _write_phase(root, {"phase": "intent", "nonce": nonce})
    stop("after_intent")
    stop("before_spawn")

    start = secrets.randbelow(1_000_000_000) + 1
    pid, release_w, cmd_w, out_r = _spawn(root, nonce, start)
    stop("after_fork_before_armed")
    identity = {
        "phase": "armed",
        "nonce": nonce,
        "pid": pid,
        "start": start,
        "os_start": os_start(pid),
    }
    _write_phase(root, identity)
    stop("after_armed_before_release")
    os.write(release_w, b"x")
    os.close(release_w)
    if _read_line(out_r) != "ready":
        os._exit(EXIT_ERROR)
    stop("after_armed")
    stop("before_go")
    if fault == "wrapper_eof":
        os.close(cmd_w)
        if _read_line(out_r) != "eof":
            os._exit(EXIT_ERROR)
        identity["handshake"] = "eof"
        _write_phase(root, identity)
        os._exit(EXIT_STOPPED)
    os.write(cmd_w, b"go\n")
    stop("after_go")
    if _read_line(out_r) != "ack":
        os._exit(EXIT_ERROR)
    stop("after_ack")
    stop("before_acked_fsync")
    identity["phase"] = "acked"
    _write_phase(root, identity)
    stop("after_acked")
    stop("before_commit")
    command = b"commit-descendant\n" if fault == "descendant" else b"commit\n"
    os.write(cmd_w, command)
    if _read_line(out_r) != "running":
        os._exit(EXIT_ERROR)
    stop("after_commit")
    stop("before_running_fsync")
    identity["phase"] = "running"
    _write_phase(root, identity)
    stop("after_running")
    if fault == "descendant":
        os._exit(EXIT_STOPPED)
    os._exit(EXIT_ERROR)


def run_fault(root: Path, fault: str, nonce: str, timeout: float = 15) -> subprocess.CompletedProcess[str]:
    root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1] / "src")
    previous = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not previous else src + os.pathsep + previous
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "holder", str(root), nonce, fault],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def main(argv: list[str]) -> None:
    if len(argv) != 5 or argv[1] != "holder":
        os._exit(EXIT_ERROR)
    holder_main(Path(argv[2]), argv[3], argv[4])


if __name__ == "__main__":
    main(sys.argv)
