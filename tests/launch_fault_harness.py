"""Test-only unprivileged launch fault harness.

This file is not a root holder and it is not used by ``runspecimen run``.
The in-memory simulator is a different module. This harness uses real
pipes, real child processes, and fsynced durable files. A fault calls
``os._exit`` in the holder process so the kernel closes its pipes and the
child is not reaped by that holder.

Cleanup may signal a pid only after a stored high-resolution start token
matches a fresh lookup. A pid file, a ``ps`` ``lstart`` string, a missing
token, or a failed lookup is not authorization. ``lstart`` is second
resolution and is not that token. Corrupt spent history is lost state, not
an empty nonce set. A missing spent file is new state.
"""

from __future__ import annotations

import ctypes
import errno
import os
import re
import secrets
import select
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

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
EXIT_LOST = 5

# Microseconds since the epoch, or Linux start ticks. Not a wall-clock second.
_TOKEN_RE = re.compile(r"^(?:us:[1-9][0-9]*\.[0-9]{6}|ticks:[0-9]+)$")

Identify = Callable[[int], "ProcessView"]
Kill = Callable[[int, int], None]


class IdentityError(Exception):
    """The lookup did not produce a comparable identity.

    This is not proof that the process is dead and not authorization to signal.
    """


class ProcessView:
    """One lookup. ``absent`` means the pid is not there. It is not a signal."""

    __slots__ = ("state", "pid", "start_token")

    def __init__(self, state: str, pid: int, start_token: str | None) -> None:
        if state not in {"alive", "absent"}:
            raise IdentityError("identity state is unknown")
        if type(pid) is not int or pid <= 0:
            raise IdentityError("pid is not a positive int")
        self.state = state
        self.pid = pid
        self.start_token = start_token


class SpentState:
    """``new`` has no file. ``recorded`` was parsed. ``lost`` must not be replayed as empty."""

    __slots__ = ("status", "nonces")

    def __init__(self, status: str, nonces: set[str]) -> None:
        if status not in {"new", "recorded", "lost"}:
            raise ValueError(status)
        self.status = status
        self.nonces = set(nonces)


class _Scan:
    __slots__ = ("pairs", "bad", "unreadable")

    def __init__(self, pairs: dict[int, str], bad: bool, unreadable: bool) -> None:
        self.pairs = pairs
        self.bad = bad
        self.unreadable = unreadable


def os_start(pid: int) -> str | None:
    """``ps`` ``lstart``. Second resolution. Not an identity token and not a signal."""

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
    """Compare two ``lstart`` strings. A match is not authorization to signal."""

    if recorded and current and recorded != current:
        return "pid-reuse-not-adopted"
    if current:
        return "alive"
    return "dead"


def linux_start_token(text: str, pid: int) -> str:
    """Field 22 of ``/proc/<pid>/stat``, after the command in parentheses."""

    if type(pid) is not int or pid <= 0:
        raise IdentityError("pid is not a positive int")
    open_at = text.find(" (")
    end = text.rfind(")")
    if open_at < 1 or end < open_at:
        raise IdentityError("stat has no command field")
    try:
        stated = int(text[:open_at])
    except ValueError as exc:
        raise IdentityError("stat pid is not an int") from exc
    if stated != pid:
        raise IdentityError("stat pid mismatch")
    fields = text[end + 1 :].split()
    if len(fields) < 20 or not fields[19].isdigit():
        raise IdentityError("stat starttime is missing")
    return f"ticks:{fields[19]}"


def _darwin_identity(pid: int) -> ProcessView:
    class _ProcBsdInfo(ctypes.Structure):
        _fields_ = [
            ("pbi_flags", ctypes.c_uint32),
            ("pbi_status", ctypes.c_uint32),
            ("pbi_xstatus", ctypes.c_uint32),
            ("pbi_pid", ctypes.c_uint32),
            ("pbi_ppid", ctypes.c_uint32),
            ("pbi_uid", ctypes.c_uint32),
            ("pbi_gid", ctypes.c_uint32),
            ("pbi_ruid", ctypes.c_uint32),
            ("pbi_rgid", ctypes.c_uint32),
            ("pbi_svuid", ctypes.c_uint32),
            ("pbi_svgid", ctypes.c_uint32),
            ("rfu_1", ctypes.c_uint32),
            ("pbi_comm", ctypes.c_char * 16),
            ("pbi_name", ctypes.c_char * 32),
            ("pbi_nfiles", ctypes.c_uint32),
            ("pbi_pgid", ctypes.c_uint32),
            ("pbi_pjobc", ctypes.c_uint32),
            ("e_tdev", ctypes.c_uint32),
            ("e_tpgid", ctypes.c_uint32),
            ("pbi_nice", ctypes.c_int32),
            ("pbi_start_tvsec", ctypes.c_uint64),
            ("pbi_start_tvusec", ctypes.c_uint64),
        ]

    info = _ProcBsdInfo()
    libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    libproc.proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    libproc.proc_pidinfo.restype = ctypes.c_int
    ctypes.set_errno(0)
    size = ctypes.sizeof(info)
    ret = libproc.proc_pidinfo(pid, 3, 0, ctypes.byref(info), size)
    err = ctypes.get_errno()
    if ret <= 0:
        if err == errno.ESRCH:
            return ProcessView("absent", pid, None)
        raise IdentityError("proc_pidinfo failed")
    if ret < size or int(info.pbi_pid) != pid:
        raise IdentityError("proc_bsdinfo is not this pid")
    sec = int(info.pbi_start_tvsec)
    usec = int(info.pbi_start_tvusec)
    if sec <= 0 or usec < 0 or usec > 999999:
        raise IdentityError("proc_bsdinfo start time is not usable")
    return ProcessView("alive", pid, f"us:{sec}.{usec:06d}")


def _linux_identity(pid: int) -> ProcessView:
    path = Path(f"/proc/{pid}/stat")
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ProcessView("absent", pid, None)
    except OSError as exc:
        raise IdentityError("cannot read process stat") from exc
    return ProcessView("alive", pid, linux_start_token(text, pid))


def process_identity(pid: int) -> ProcessView:
    """High-resolution start identity for a pid this user can see.

    A failure raises ``IdentityError``. It does not mean the pid is dead.
    """

    if type(pid) is not int or pid <= 0:
        raise IdentityError("pid is not a positive int")
    if sys.platform == "darwin":
        return _darwin_identity(pid)
    if sys.platform.startswith("linux"):
        return _linux_identity(pid)
    raise IdentityError("process identity is unavailable")


def _complete_identity(record: object) -> tuple[int, str] | None:
    if not isinstance(record, dict):
        return None
    pid = record.get("pid")
    token = record.get("start_token")
    if type(pid) is not int or pid <= 0:
        return None
    if not isinstance(token, str) or _TOKEN_RE.fullmatch(token) is None:
        return None
    return pid, token


def _scan(root: Path) -> _Scan:
    tokens: dict[int, set[str]] = {}
    bad = False
    unreadable = False
    files: list[Path] = []
    durable = _durable_path(root)
    if durable.exists() or durable.is_symlink():
        files.append(durable)
    for name in ("identity", "procs"):
        folder = root / name
        if not folder.exists() and not folder.is_symlink():
            continue
        if not folder.is_dir() or folder.is_symlink():
            unreadable = True
            continue
        files.extend(sorted(folder.glob("*.json")))
    for path in files:
        try:
            data = read_durable_record(path)
        except ProtocolError:
            unreadable = True
            continue
        if data is None:
            unreadable = True
            continue
        if "pid" not in data and "start_token" not in data:
            continue
        parsed = _complete_identity(data)
        if parsed is None:
            bad = True
            continue
        pid, token = parsed
        tokens.setdefault(pid, set()).add(token)
    pairs: dict[int, str] = {}
    for pid, values in tokens.items():
        if len(values) != 1:
            bad = True
            continue
        pairs[pid] = next(iter(values))
    return _Scan(pairs, bad, unreadable)


def _require_live(identify: Identify, pid: int) -> ProcessView:
    if type(pid) is not int or pid <= 0:
        raise IdentityError("pid is not a positive int")
    try:
        view = identify(pid)
    except IdentityError:
        raise
    except Exception as exc:
        raise IdentityError("identity lookup failed") from exc
    if (
        not isinstance(view, ProcessView)
        or view.state != "alive"
        or view.pid != pid
        or not isinstance(view.start_token, str)
        or _TOKEN_RE.fullmatch(view.start_token) is None
    ):
        raise IdentityError("child identity is not alive")
    return view


def record_child_identity(root: Path, pid: int, identify: Identify = process_identity) -> dict[str, object]:
    """Fsync the child's token, then read it back and look the pid up again.

    A mismatch deletes the file. The deleted file is not authorization.
    """

    first = _require_live(identify, pid)
    payload: dict[str, object] = {"pid": pid, "start_token": first.start_token}
    path = root / "identity" / f"{pid}.json"
    write_durable_record(path, payload)
    try:
        stored = read_durable_record(path)
        second = _require_live(identify, pid)
        if stored != payload or second.start_token != first.start_token:
            raise IdentityError("identity changed while recording")
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    return payload


def _spent_path(root: Path) -> Path:
    return root / "spent.json"


def _durable_path(root: Path) -> Path:
    return root / "durable.json"


def _spent_from_object(data: dict[str, object]) -> SpentState:
    nonces = data.get("nonces")
    if not isinstance(nonces, list) or any(type(item) is not str or item == "" for item in nonces):
        return SpentState("lost", set())
    return SpentState("recorded", set(nonces))


def load_spent(root: Path) -> SpentState:
    """Missing file is new. Any other unreadable or malformed file is lost.

    Lost history does not return the nonces that happened to parse.
    """

    path = _spent_path(root)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return SpentState("new", set())
    except OSError:
        return SpentState("lost", set())
    if not stat.S_ISREG(info.st_mode):
        return SpentState("lost", set())
    try:
        data = read_durable_record(path)
    except ProtocolError:
        return SpentState("lost", set())
    if not isinstance(data, dict):
        return SpentState("lost", set())
    return _spent_from_object(data)


def _remember(root: Path, nonce: str) -> None:
    state = load_spent(root)
    if state.status == "lost":
        os._exit(EXIT_LOST)
    nonces = set(state.nonces)
    nonces.add(nonce)
    write_durable_record(_spent_path(root), {"nonces": sorted(nonces)})


def _write_phase(root: Path, fields: dict[str, object]) -> None:
    record = {key: value for key, value in fields.items() if value is not None}
    write_durable_record(_durable_path(root), record)


def _apply_children(
    decision: dict[str, object],
    record: object,
    scan: _Scan,
    identify: Identify,
) -> dict[str, object]:
    uncertain = isinstance(record, dict) and record.get("child") == "uncertain"
    if scan.unreadable or scan.bad or (uncertain and not scan.pairs):
        decision["lease"] = True
        decision["action"] = "uncertain-child"
        return decision
    flags: list[str] = []
    for pid, token in scan.pairs.items():
        try:
            view = identify(pid)
        except IdentityError:
            flags.append("error")
            continue
        if not isinstance(view, ProcessView) or view.pid != pid:
            flags.append("error")
            continue
        if view.state == "absent":
            flags.append("dead")
            continue
        if view.state == "alive" and view.start_token == token:
            flags.append("alive")
            continue
        if view.state == "alive":
            flags.append("reused")
            continue
        flags.append("error")
    if "reused" in flags or "error" in flags:
        decision["lease"] = True
        if "reused" in flags:
            decision["action"] = "pid-reuse-not-adopted"
            decision["phase"] = "unknown"
        else:
            decision["action"] = "uncertain-child"
        return decision
    if "alive" in flags:
        decision["lease"] = True
        decision["action"] = "supervise"
        return decision
    proven_dead = bool(scan.pairs) and flags and all(flag == "dead" for flag in flags)
    if proven_dead and (decision.get("phase") in {"armed", "acked", "running"} or uncertain):
        decision["lease"] = False
        decision["action"] = "terminated-without-status"
        return decision
    if uncertain:
        decision["lease"] = True
        decision["action"] = "uncertain-child"
    return decision


def recover(root: Path, identify: Identify = process_identity) -> dict[str, object]:
    """Read fsynced files from a process that is not the holder.

    ``wait`` is ``echild``. ``success`` is false. A live or unverified child
    keeps the lease. Lost spent history keeps the lease and is not an empty
    nonce set. A matching start token that is now absent is the only proof
    that a recorded child is gone. That proof is not a signal.
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
    history = load_spent(root)
    decision = dict(base)
    decision["success"] = False
    decision["wait"] = "echild"
    decision["spawn"] = False
    decision["history"] = history.status
    if history.status == "lost":
        decision["lease"] = True
        decision["action"] = "spent-history-lost"
        return decision
    return _apply_children(decision, record, _scan(root), identify)


def reap(
    root: Path,
    *,
    kill: Kill = os.kill,
    identify: Identify = process_identity,
) -> list[int]:
    """Signal a pid only when its stored token still matches a fresh lookup.

    The stored record is read again immediately before that lookup. Unknown,
    missing, conflicting, and failed identities are not signaled. ``absent``
    is not signaled.
    """

    scan = _scan(root)
    if scan.unreadable:
        return []
    signaled: list[int] = []
    for pid, token in sorted(scan.pairs.items()):
        fresh = _scan(root)
        if fresh.unreadable or fresh.pairs.get(pid) != token:
            continue
        try:
            view = identify(pid)
        except IdentityError:
            continue
        if (
            not isinstance(view, ProcessView)
            or view.state != "alive"
            or view.pid != pid
            or view.start_token != token
        ):
            continue
        kill(pid, signal.SIGKILL)
        signaled.append(pid)
    return signaled


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
    try:
        recorded = record_child_identity(root, os.getpid())
    except (IdentityError, ProtocolError):
        os._exit(EXIT_ERROR)
    folder = root / "procs"
    folder.mkdir(parents=True, exist_ok=True)
    fields: dict[str, object] = {
        "pid": recorded["pid"],
        "start": start,
        "start_token": recorded["start_token"],
        "image": image,
        "nonce": nonce,
    }
    if pipe is not None:
        fields["pipe"] = pipe
    write_durable_record(folder / f"{recorded['pid']}.json", fields)


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


def _spawn(root: Path, nonce: str, start: int) -> tuple[int, int, int, int, str]:
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
    try:
        recorded = record_child_identity(root, pid)
    except (IdentityError, ProtocolError):
        os._exit(EXIT_ERROR)
    return pid, release_w, cmd_w, out_r, str(recorded["start_token"])


def _clear_stale_tmp(root: Path) -> None:
    for folder in (root, root / "procs", root / "identity"):
        if folder.exists():
            for path in folder.glob("*.tmp"):
                path.unlink()


def holder_main(root: Path, nonce: str, fault: str) -> None:
    if fault not in FAULTS:
        os._exit(EXIT_ERROR)
    root.mkdir(parents=True, exist_ok=True)
    _clear_stale_tmp(root)
    history = load_spent(root)
    if history.status == "lost":
        os._exit(EXIT_LOST)
    decision = recover(root)
    if decision["lease"]:
        os._exit(EXIT_LEASE)
    if nonce in history.nonces:
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
    _write_phase(root, {"phase": "intent", "nonce": nonce, "child": "uncertain"})

    start = secrets.randbelow(1_000_000_000) + 1
    pid, release_w, cmd_w, out_r, start_token = _spawn(root, nonce, start)
    stop("after_fork_before_armed")
    identity = {
        "phase": "armed",
        "nonce": nonce,
        "pid": pid,
        "start": start,
        "start_token": start_token,
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
