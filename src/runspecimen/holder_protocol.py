"""Specification of snapshot binding and the launch handshake.

``runspecimen run`` does not call this module. Nothing here is a root
holder, a keychain call, or a biometric prompt. The tests drive it as an
unprivileged state machine plus ordinary files.

Copying an input and hashing the copy does not bind execution. Binding is
the rewritten argv, the snapshot inode, and a file descriptor opened on
that inode. A later ``stat`` of the original path is not that binding.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path


class ProtocolError(Exception):
    """The request cannot be bound or advanced."""


class NonceSpent(ProtocolError):
    """This nonce was already consumed."""


class LeaseHeld(ProtocolError):
    """Another launch still has live descendants or an unknown outcome."""


class PipeEOF(ProtocolError):
    """The wrapper pipe closed before a durable commit."""


@dataclass(frozen=True)
class Snapshot:
    original: str
    path: str
    digest: str
    inode: int
    fd: int


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


def _snapshot_file(src: Path, dest_dir: Path, expected: str | None) -> Snapshot:
    try:
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise ProtocolError(f"cannot open a regular file without following a link: {src}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ProtocolError(f"not a regular file: {src}")
        chunks: list[bytes] = []
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        data = b"".join(chunks)
    finally:
        os.close(fd)
    digest = hashlib.sha256(data).hexdigest()
    if expected is not None and digest != expected:
        raise ProtocolError("snapshot bytes do not match the signed fingerprint")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / digest
    if not dest.exists():
        out = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o444)
        try:
            os.write(out, data)
            os.fsync(out)
        finally:
            os.close(out)
        os.chmod(dest, 0o444)
    snap_fd = os.open(dest, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    inode = os.fstat(snap_fd).st_ino
    return Snapshot(str(src), str(dest), digest, inode, snap_fd)


def _shebang(data: bytes) -> str | None:
    if not data.startswith(b"#!"):
        return None
    line = data.splitlines()[0][2:].decode("utf-8", "replace").strip()
    parts = line.split()
    if not parts:
        return None
    if Path(parts[0]).name == "env":
        raise ProtocolError("an env shebang does not name one bound interpreter")
    return parts[0]


def bind_execution(request: LaunchRequest, snapshot_root: Path) -> BoundExecution:
    """Rewrite the command so exec names snapshot inodes, not the live tree.

    ``cwd_mode`` other than ``snapshot`` fails closed. A final stat of the
    original path is not consulted after the snapshot fd is opened.
    """

    if request.cwd_mode != "snapshot":
        raise ProtocolError("a bound run does not use the live workspace as its cwd")
    files = dest_dir = snapshot_root / "files"
    by_original: dict[str, Snapshot] = {}

    def take(path: str) -> Snapshot:
        if path in by_original:
            return by_original[path]
        snap = _snapshot_file(Path(path), files, request.fingerprints.get(path))
        by_original[path] = snap
        return snap

    for path in (request.executable, *request.inputs, *request.dependencies):
        take(path)
    if request.script is not None:
        if request.script not in request.argv:
            raise ProtocolError("script path is not in argv")
        script = take(request.script)
        interpreter = _shebang(Path(script.path).read_bytes())
        if interpreter is not None and interpreter not in by_original:
            raise ProtocolError("the script interpreter is not in the signed dependency set")
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

    The wrapper execs only after a durable Acked record and a commit byte.
    Sending go is not itself the Running state. Recovery never calls
    ``waitpid`` on a process it does not parent, and it never launches twice.
    """

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
