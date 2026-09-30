"""Specification of snapshot binding and the launch handshake.

``runspecimen run`` does not call this module. Nothing here is a root
holder, a keychain call, or a biometric prompt. The tests drive it as an
unprivileged state machine plus ordinary files.

Copying an input and hashing the copy does not bind execution. Binding is
the rewritten argv, the snapshot inode, and a file descriptor opened on
that inode. The bytes read from that descriptor are the digest. A later
``stat`` of the original path is not that binding.

``HolderSim`` is an in-memory simulator. It does not fsync. Durable files
and ``assess_durable`` are the separate record a restarted process can read.
That process is not the parent and does not treat ``ECHILD`` as an exit.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


class ProtocolError(Exception):
    """The request cannot be bound or advanced."""


class NonceSpent(ProtocolError):
    """This nonce was already consumed."""


class LeaseHeld(ProtocolError):
    """Another launch still has live descendants or an unknown outcome."""


class PipeEOF(ProtocolError):
    """The wrapper pipe closed before a durable commit."""


DATA_MODE = 0o444
EXEC_MODE = 0o555


@dataclass(frozen=True)
class Snapshot:
    original: str
    path: str
    digest: str
    inode: int
    fd: int
    source_digest: str


@dataclass
class BoundExecution:
    """What the wrapper is allowed to exec. Paths are snapshot paths."""

    argv: tuple[str, ...]
    cwd: str
    outputs: tuple[str, ...]
    snapshots: tuple[Snapshot, ...]
    residuals: tuple[str, ...] = (
        "The dynamic linker and system libraries are not part of the snapshot.",
    )

    def close(self) -> None:
        for item in self.snapshots:
            try:
                os.close(item.fd)
            except OSError:
                pass

    def snapshot_for(self, original: str) -> Snapshot:
        for item in self.snapshots:
            if item.original == original:
                return item
        raise ProtocolError(f"no snapshot for {original}")


@dataclass(frozen=True)
class LaunchRequest:
    nonce: str
    argv: tuple[str, ...]
    executable: str
    inputs: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    script: str | None = None
    outputs: tuple[str, ...] = ()
    cwd_mode: str = "snapshot"
    fingerprints: dict[str, str] = field(default_factory=dict)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _read_all(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        block = os.read(fd, 1024 * 1024)
        if not block:
            break
        chunks.append(block)
    return b"".join(chunks)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise ProtocolError("short write while copying a snapshot")
        view = view[written:]


def _abort_partial(fd: int, dest: Path, exc: BaseException) -> None:
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.unlink(dest)
    except OSError as cleanup:
        raise ProtocolError(f"snapshot write failed ({exc}); cleanup failed ({cleanup})") from exc
    raise ProtocolError(f"snapshot write failed ({exc})") from exc


def _load_source(src: Path, expected: str) -> bytes:
    if not _is_sha256(expected):
        raise ProtocolError("signed fingerprint is not a sha256 hex digest")
    try:
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise ProtocolError(f"cannot open a regular file without following a link: {src}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProtocolError(f"not a regular file: {src}")
        data = _read_all(fd)
    finally:
        os.close(fd)
    if _sha256_hex(data) != expected:
        raise ProtocolError("snapshot bytes do not match the signed fingerprint")
    return data


def _reuse(dest: Path, digest: str, mode: int) -> int:
    """Open ``dest`` and trust it only when the fd is a regular file of ``digest``."""

    try:
        fd = os.open(dest, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise ProtocolError(f"cannot open snapshot without following a link: {dest}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProtocolError(f"snapshot destination is not a regular file: {dest}")
        if _sha256_hex(_read_all(fd)) != digest:
            raise ProtocolError("reused snapshot does not match the signed fingerprint")
        os.lseek(fd, 0, os.SEEK_SET)
        current = stat.S_IMODE(info.st_mode)
        if mode & 0o111 and (current & 0o111) != (mode & 0o111):
            os.fchmod(fd, mode)
    except Exception:
        os.close(fd)
        raise
    return fd


def _store(
    dest_dir: Path,
    digest: str,
    data: bytes,
    mode: int,
    source_digest: str,
    original: str,
) -> Snapshot:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / digest
    try:
        out = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode)
    except FileExistsError:
        fd = _reuse(dest, digest, mode)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise ProtocolError(f"cannot create snapshot: {dest}") from exc
        fd = _reuse(dest, digest, mode)
    else:
        try:
            _write_all(out, data)
            os.fsync(out)
        except Exception as exc:
            _abort_partial(out, dest, exc)
        os.close(out)
        fd = _reuse(dest, digest, mode)
    return Snapshot(original, str(dest), digest, os.fstat(fd).st_ino, fd, source_digest)


def _required_fingerprints(request: LaunchRequest) -> dict[str, str]:
    paths = [request.executable, *request.inputs, *request.dependencies]
    if request.script is not None:
        paths.append(request.script)
    if any(path not in request.fingerprints for path in paths):
        raise ProtocolError("signed fingerprints are required for every bound file")
    selected: dict[str, str] = {}
    for path in paths:
        value = request.fingerprints[path]
        if not _is_sha256(value):
            raise ProtocolError("signed fingerprint is not a sha256 hex digest")
        selected[path] = value
    return selected


def _shebang_interpreter(data: bytes) -> str | None:
    if not data.startswith(b"#!"):
        return None
    line = data.splitlines()[0][2:].decode("utf-8", "replace").strip()
    parts = line.split()
    if not parts:
        return None
    if Path(parts[0]).name == "env":
        raise ProtocolError("an env shebang does not name one bound interpreter")
    return parts[0]


def _rebind_shebang(data: bytes, interpreter_path: str) -> bytes:
    """Point the script at the snapshot interpreter. The body stays the signed body."""

    if not data.startswith(b"#!"):
        return data
    newline = data.find(b"\n")
    head = data if newline < 0 else data[:newline]
    tail = b"" if newline < 0 else data[newline + 1 :]
    parts = head[2:].decode("utf-8", "replace").strip().split()
    if not parts:
        return data
    if Path(parts[0]).name == "env":
        raise ProtocolError("an env shebang does not name one bound interpreter")
    args = (" " + " ".join(parts[1:])) if len(parts) > 1 else ""
    return f"#!{interpreter_path}{args}\n".encode("utf-8") + tail


def _close_open(snapshots: Mapping[str, Snapshot]) -> None:
    for item in snapshots.values():
        try:
            os.close(item.fd)
        except OSError:
            pass


def bind_execution(request: LaunchRequest, snapshot_root: Path) -> BoundExecution:
    """Rewrite the command so exec names snapshot inodes, not the live tree.

    Every executable, script, input, and dependency needs a sha256 fingerprint.
    A destination is used only after its opened fd is a regular file whose
    bytes hash to that destination's digest. ``cwd_mode`` other than
    ``snapshot`` fails closed. A final stat of the original path is not the
    binding.
    """

    if request.cwd_mode != "snapshot":
        raise ProtocolError("a bound run does not use the live workspace as its cwd")
    fingerprints = _required_fingerprints(request)
    files = snapshot_root / "files"
    by_original: dict[str, Snapshot] = {}
    loaded: dict[str, bytes] = {}

    def take(path: str, *, executable: bool) -> Snapshot:
        if path in by_original:
            snap = by_original[path]
            if executable:
                os.fchmod(snap.fd, EXEC_MODE)
            return snap
        data = _load_source(Path(path), fingerprints[path])
        loaded[path] = data
        snap = _store(
            files,
            fingerprints[path],
            data,
            EXEC_MODE if executable else DATA_MODE,
            fingerprints[path],
            path,
        )
        by_original[path] = snap
        return snap

    try:
        take(request.executable, executable=True)
        for path in (*request.inputs, *request.dependencies):
            take(path, executable=False)
        if request.script is not None:
            if request.script not in request.argv:
                raise ProtocolError("script path is not in argv")
            if request.script not in loaded:
                take(request.script, executable=False)
            interpreter = _shebang_interpreter(loaded[request.script])
            if interpreter is not None:
                if interpreter not in by_original:
                    raise ProtocolError("the script interpreter is not in the signed dependency set")
                interp = by_original[interpreter]
                os.fchmod(interp.fd, EXEC_MODE)
                rebound = _rebind_shebang(loaded[request.script], interp.path)
                digest = _sha256_hex(rebound)
                current = by_original[request.script]
                if digest != current.digest:
                    os.close(current.fd)
                    by_original[request.script] = _store(
                        files,
                        digest,
                        rebound,
                        EXEC_MODE,
                        current.source_digest,
                        request.script,
                    )
                else:
                    os.fchmod(current.fd, EXEC_MODE)
        for original in request.inputs:
            if original not in request.argv:
                raise ProtocolError("declared input is not an argv token")
        rewritten: list[str] = []
        originals = set(by_original)
        for token in request.argv:
            if token in by_original:
                rewritten.append(by_original[token].path)
            elif token in originals:
                raise ProtocolError("argv still names a live input")
            else:
                rewritten.append(token)
        if not rewritten or rewritten[0] != by_original[request.executable].path:
            raise ProtocolError("argv0 is not the snapshotted executable")
        for original in request.inputs:
            if original in rewritten:
                raise ProtocolError("executed argv still contains a live input path")
        cwd = snapshot_root / "cwd"
        cwd.mkdir(parents=True, exist_ok=True)
        if cwd.is_symlink():
            raise ProtocolError("snapshot cwd must not be a symlink")
        out_dir = snapshot_root / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[str] = []
        for name in request.outputs:
            if name != Path(name).name or name in {"", ".", ".."}:
                raise ProtocolError("output names are single path components")
            dest = out_dir / name
            fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)
            os.close(fd)
            outputs.append(str(dest))
        return BoundExecution(tuple(rewritten), str(cwd), tuple(outputs), tuple(by_original.values()))
    except Exception:
        _close_open(by_original)
        raise


def write_durable_record(path: Path, record: Mapping[str, object]) -> None:
    """Write a launch record and fsync it. This is not ``HolderSim``."""

    if not isinstance(record, dict):
        raise ProtocolError("durable record must be an object")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        out = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    except OSError as exc:
        raise ProtocolError(f"cannot create durable record: {tmp}") from exc
    try:
        _write_all(out, data)
        os.fsync(out)
    except Exception as exc:
        _abort_partial(out, tmp, exc)
    os.close(out)
    os.replace(tmp, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def read_durable_record(path: Path) -> dict[str, object] | None:
    """Read a durable record. Missing is ``None``. A partial file fails closed."""

    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ProtocolError(f"cannot open durable record: {path}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProtocolError("durable record is not a regular file")
        data = _read_all(fd)
    finally:
        os.close(fd)
    if not data:
        raise ProtocolError("partial durable record")
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("partial durable record") from exc
    if not isinstance(parsed, dict):
        raise ProtocolError("partial durable record")
    return parsed


def assess_durable(record: Mapping[str, object] | None) -> dict[str, object]:
    """Decide what a restarted process may do. It is not the parent.

    ``spawn`` is always false. ``wait`` is ``echild`` because this process
    cannot ``waitpid`` an orphan. A partial record keeps the lease. A missing
    record is not a supervised launch and is not an exit status.
    """

    if record is None:
        return {
            "action": "missing-record",
            "spawn": False,
            "lease": False,
            "wait": "echild",
            "phase": "absent",
        }
    phase = record.get("phase")
    nonce = record.get("nonce")
    pid = record.get("pid")
    start = record.get("start")
    launch_phases = {"armed", "acked", "running"}
    if phase in launch_phases:
        complete = isinstance(nonce, str) and bool(nonce) and isinstance(pid, int) and isinstance(start, int)
        if not complete:
            return {
                "action": "partial-record",
                "spawn": False,
                "lease": True,
                "wait": "echild",
                "phase": "unknown",
            }
        action = {
            "armed": "not-parent-do-not-commit",
            "acked": "not-parent-do-not-spawn",
            "running": "not-parent-supervise",
        }[str(phase)]
        return {"action": action, "spawn": False, "lease": True, "wait": "echild", "phase": phase}
    if phase in {"consumed", "intent"} and isinstance(nonce, str) and nonce:
        return {
            "action": "spent-without-spawn",
            "spawn": False,
            "lease": False,
            "wait": "echild",
            "phase": phase,
        }
    return {
        "action": "partial-record",
        "spawn": False,
        "lease": True,
        "wait": "echild",
        "phase": "unknown",
    }


def restat_agrees_with_snapshot(original: Path, snap: Snapshot) -> bool:
    """A passing restat is not how execution is bound. Callers must not use it as one."""

    try:
        info = original.stat()
    except OSError:
        return False
    return info.st_ino == snap.inode and original.read_bytes() == Path(snap.path).read_bytes()


@dataclass
class _Proc:
    pid: int
    start: int
    image: str
    alive: bool = True
    children: list[int] = field(default_factory=list)


class HolderSim:
    """In-memory holder. A crash drops unsynced flags and parenthood.

    ``persists`` is false. Nothing in this class fsyncs a record or reaps a
    real child. ``write_durable_record`` and ``assess_durable`` are the file
    path. The wrapper execs only after a durable Acked record and a commit
    byte. Sending go is not itself the Running state. Recovery never calls
    ``waitpid`` on a process it does not parent, and it never launches twice.
    """

    persists = False
    ORDER = (
        "consume",
        "write_intent",
        "spawn",
        "send_go",
        "recv_ack",
        "fsync_acked",
        "send_commit",
        "fsync_running",
    )

    def __init__(self) -> None:
        self.durable: dict[str, object] = {
            "phase": "empty",
            "nonce": None,
            "pid": None,
            "start": None,
            "lease": False,
        }
        self.spent: set[str] = set()
        self.procs: dict[int, _Proc] = {}
        self.spawned = 0
        self.commits = 0
        self.kills: list[int] = []
        self.is_parent = True
        self.ack = False
        self.pipe_open = True
        self._next_pid = 100
        self._next_start = 1

    def apply(self, step: str, nonce: str = "n1") -> None:
        if step == "consume":
            self._consume(nonce)
        elif step == "write_intent":
            self._require_phase("consumed")
            self.durable["phase"] = "intent"
        elif step == "spawn":
            self._require_phase("intent")
            self._spawn()
        elif step == "send_go":
            self._require_phase("armed")
            if not self.pipe_open:
                raise PipeEOF("go pipe closed")
            # Volatile. Durable phase stays armed.
        elif step == "recv_ack":
            if not self.pipe_open:
                raise PipeEOF("ack pipe closed")
            self.ack = True
        elif step == "fsync_acked":
            if not self.ack:
                raise ProtocolError("no ack to persist")
            self.durable["phase"] = "acked"
        elif step == "send_commit":
            if self.durable["phase"] != "acked":
                raise ProtocolError("commit requires a durable ack")
            if not self.pipe_open:
                raise PipeEOF("commit pipe closed")
            self.commits += 1
            proc = self._proc()
            proc.image = "payload"
            # Durable phase stays acked until fsync_running.
        elif step == "fsync_running":
            if self.durable["phase"] != "acked" or self.commits < 1:
                raise ProtocolError("running requires a commit")
            self.durable["phase"] = "running"
        else:
            raise ProtocolError(f"unknown step {step}")

    def run_through(self, step: str, nonce: str = "n1") -> None:
        for name in self.ORDER:
            self.apply(name, nonce)
            if name == step:
                return
        raise ProtocolError(f"unknown step {step}")

    def crash(self) -> None:
        """Parent exits. Children remain. Unsynced ack memory is gone."""

        self.is_parent = False
        if self.durable["phase"] not in {"acked", "running", "reaped", "unknown"}:
            self.ack = False

    def break_pipe(self) -> None:
        self.pipe_open = False

    def payload_forks(self) -> int:
        parent = self._proc()
        if parent.image != "payload":
            raise ProtocolError("only the payload forks a descendant")
        self._next_pid += 1
        child = _Proc(self._next_pid, parent.start, "descendant")
        self.procs[child.pid] = child
        parent.children.append(child.pid)
        return child.pid

    def mark_dead(self, pid: int) -> None:
        self.procs[pid].alive = False

    def reuse_pid(self) -> None:
        proc = self._proc()
        proc.start = proc.start + 1000
        proc.image = "unrelated"
        proc.alive = True
        proc.children.clear()

    def recover(self) -> dict[str, object]:
        if self.is_parent:
            raise ProtocolError("recovery is for a process that is not the parent")
        if not self._durable_complete():
            self.durable["phase"] = "unknown"
            self.durable["lease"] = True
            return {
                "wait": "echild",
                "action": "partial-record",
                "spawned": self.spawned,
                "commits": self.commits,
                "lease": True,
                "phase": "unknown",
                "kills": tuple(self.kills),
            }
        wait = "echild"
        phase = self.durable["phase"]
        proc = self.procs.get(self.durable["pid"]) if self.durable["pid"] else None
        action = "none"
        if proc is not None and proc.start != self.durable["start"]:
            self.durable["phase"] = "unknown"
            action = "pid-reuse-not-adopted"
        elif phase in {"consumed", "intent"}:
            action = "spent-without-spawn"
        elif phase == "armed":
            action = self._stop_wrapper_or_note(proc, "kill-waiting-wrapper")
        elif phase == "acked":
            if proc and proc.alive and proc.image == "payload" and proc.start == self.durable["start"]:
                self.durable["phase"] = "running"
                action = "adopt-payload"
            else:
                action = self._stop_wrapper_or_note(proc, "kill-uncommitted-wrapper")
        elif phase == "running":
            if self._live():
                action = "supervise"
            else:
                action = "terminated-without-status"
        spawned_now = self.spawned
        commits_now = self.commits
        self._refresh_lease()
        return {
            "wait": wait,
            "action": action,
            "spawned": spawned_now,
            "commits": commits_now,
            "lease": self.durable["lease"],
            "phase": self.durable["phase"],
            "kills": tuple(self.kills),
        }

    def begin_other(self, nonce: str) -> None:
        """A different nonce. The spent nonce cannot be reused by calling this."""

        self._consume(nonce)
        self.durable["phase"] = "intent"
        self._spawn()

    def _consume(self, nonce: str) -> None:
        if nonce in self.spent:
            raise NonceSpent(nonce)
        if self.durable["lease"]:
            raise LeaseHeld(nonce)
        self.spent.add(nonce)
        self.durable["nonce"] = nonce
        self.durable["phase"] = "consumed"
        self.durable["lease"] = True
        self.durable["pid"] = None
        self.durable["start"] = None
        self.ack = False
        self.pipe_open = True

    def _spawn(self) -> None:
        if self.spawned:
            raise ProtocolError("duplicate launch")
        self._next_pid += 1
        self._next_start += 1
        proc = _Proc(self._next_pid, self._next_start, "wrapper")
        self.procs[proc.pid] = proc
        self.spawned += 1
        self.durable["pid"] = proc.pid
        self.durable["start"] = proc.start
        self.durable["phase"] = "armed"

    def _proc(self) -> _Proc:
        pid = self.durable["pid"]
        if not isinstance(pid, int) or pid not in self.procs:
            raise ProtocolError("no wrapper")
        return self.procs[pid]

    def _durable_complete(self) -> bool:
        phase = self.durable.get("phase")
        nonce = self.durable.get("nonce")
        if phase in {"consumed", "intent"}:
            return isinstance(nonce, str) and bool(nonce)
        if phase in {"armed", "acked", "running"}:
            return (
                isinstance(nonce, str)
                and bool(nonce)
                and isinstance(self.durable.get("pid"), int)
                and isinstance(self.durable.get("start"), int)
            )
        return phase in {"unknown", "reaped", "spent", "empty"}

    def _require_phase(self, phase: str) -> None:
        if self.durable["phase"] != phase:
            raise ProtocolError(f"expected {phase}, have {self.durable['phase']}")

    def _stop_wrapper_or_note(self, proc: _Proc | None, kill_action: str) -> str:
        if (
            proc
            and proc.alive
            and proc.image == "wrapper"
            and proc.start == self.durable["start"]
        ):
            proc.alive = False
            self.kills.append(proc.pid)
            return kill_action
        if proc and proc.alive and proc.image == "payload":
            self.durable["phase"] = "running"
            return "adopt-payload"
        return "no-live-wrapper"

    def _live(self) -> bool:
        start = self.durable["start"]
        return any(proc.alive and proc.start == start for proc in self.procs.values())

    def _refresh_lease(self) -> None:
        if self.durable["phase"] == "unknown" or self._live():
            self.durable["lease"] = True
            return
        self.durable["lease"] = False
        if self.durable["phase"] not in {"empty", "unknown"}:
            self.durable["phase"] = "reaped" if self.spawned else "spent"
        self.spawned = 0
        self.commits = 0


def foreign_wait(pid: int) -> str:
    """``waitpid`` on a process this process does not parent.

    ``ECHILD`` is not an exit status and is not a reason to launch again.
    """

    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return "echild"
    return "waited"
