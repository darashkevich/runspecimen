"""Execute exactly one approved bounded run under workspace lease."""

from __future__ import annotations

import os
import contextlib
import contextvars
import selectors
import signal
import subprocess
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runspecimen.approve import approval_is_valid, load_approval
from runspecimen.atomic import atomic_write_bytes
from runspecimen.contract import check_contract_paths, load_contract, validate_caps
from runspecimen.errors import LeaseError, PreflightError, RunError
from runspecimen.events import EventLog, utc_now_iso
from runspecimen.hashutil import hash_source
from runspecimen.isolation import assert_tool_unchanged, confinement_argv, plans_match
from runspecimen.lease import hold_workspace_lease
from runspecimen.policy import execution_constraints
from runspecimen.paths import (
    STDERR_FILENAME,
    STDOUT_FILENAME,
    ensure_dir,
    ensure_within,
    resolve_workspace,
    run_state_dir,
)
from runspecimen.preflight import check_outputs_absent, check_predecessor
from runspecimen.state import load_state, update_state
from runspecimen.runtime import job_environment, runtime_matches, runtime_provenance


# Hooks for supervisor mode - set only in the detached supervisor process
_external_interrupt: threading.Event | None = None
_cleanup_notification: Any = None


class _CleanupUnconfirmed(RunError):
    """Raised when process group cleanup cannot be confirmed."""

    def __init__(self, proc: subprocess.Popen, reason: str) -> None:
        super().__init__(reason)
        self.proc = proc
        self.interrupted = False


class _RunInterrupted(KeyboardInterrupt):
    """An ordinary run received a termination request while holding its lease."""

    def __init__(self, signum: int) -> None:
        super().__init__(signal.Signals(signum).name)
        self.signum = signum


_pending_signal: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar(
    "runspecimen_run_pending_signal", default=None
)


@contextlib.contextmanager
def _termination_signals():
    # Python only permits installing handlers in the main thread. Library calls
    # from worker threads retain their existing exception-based cancellation.
    pending: list[int] = []
    token = _pending_signal.set(pending)
    previous = {}

    def request_stop(signum, _frame):
        # Never raise asynchronously in Popen, state persistence or cleanup.
        # A second signal cannot unwind the lease while cleanup is in progress.
        if not pending:
            pending.append(signum)

    try:
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                previous[signum] = signal.getsignal(signum)
                signal.signal(signum, request_stop)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        _pending_signal.reset(token)


def _check_termination_signal() -> None:
    # Check external interrupt (supervisor mode: CLI death or stop request)
    if _external_interrupt is not None and _external_interrupt.is_set():
        raise _RunInterrupted(signal.SIGTERM)
    # Check signal-based termination (normal CLI mode)
    pending = _pending_signal.get()
    if pending:
        raise _RunInterrupted(pending[0])


def _kill_process_group(proc: subprocess.Popen[bytes]) -> None:
    """Send SIGKILL to the process group. Raises _CleanupUnconfirmed on EPERM."""
    if proc.pid is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        # EPERM: we cannot confirm the group is stopped. Never fall back to
        # killing only the leader, as that leaves descendants alive.
        raise _CleanupUnconfirmed(
            proc, f"process-group stop denied/unconfirmed: {exc}"
        ) from exc


@dataclass
class _Capture:
    limit: int
    data: bytearray = field(default_factory=bytearray)
    truncated: bool = False

    def append(self, chunk: bytes) -> None:
        remaining = self.limit - len(self.data)
        self.data.extend(chunk[:remaining])
        self.truncated = self.truncated or len(chunk) > remaining


def _supervise_process(proc, stdout: _Capture, stderr: _Capture, deadline: float) -> bool:
    """Drain both pipes without allowing inherited descriptors to block cleanup."""
    assert proc.stdout is not None and proc.stderr is not None
    selector = selectors.DefaultSelector()
    try:
        for stream, capture in ((proc.stdout, stdout), (proc.stderr, stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, capture)
        group_cleaned = False
        while selector.get_map() or proc.poll() is None:
            _check_termination_signal()
            if proc.poll() is not None and not group_cleaned:
                # A successful launcher can leave workers holding the pipes
                # open. End its process group before releasing the lease.
                _kill_process_group(proc)
                group_cleaned = True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            if selector.get_map():
                for key, _ in selector.select(timeout=min(0.1, remaining)):
                    try:
                        chunk = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if chunk:
                        key.data.append(chunk)
                    else:
                        selector.unregister(key.fileobj)
            else:
                try:
                    proc.wait(timeout=min(0.1, remaining))
                except subprocess.TimeoutExpired:
                    pass
        _check_termination_signal()
        return False
    finally:
        selector.close()


def _live_group_members(pgid: int, timeout: float) -> list[int]:
    """Return PIDs of non-zombie processes in the given process group.

    Uses /proc on Linux, /bin/ps on other systems.
    """
    if Path("/proc/self/stat").exists():
        # Linux: read /proc directly
        members = []
        try:
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    stat_content = (entry / "stat").read_text()
                    # Format: pid (comm) state ppid pgrp ...
                    # comm can contain spaces/parens, so split from the right
                    tail = stat_content.rsplit(")", 1)[1].split()
                    state = tail[0]
                    pgrp = int(tail[2])
                    if pgrp == pgid and state != "Z":
                        members.append(int(entry.name))
                except (FileNotFoundError, ProcessLookupError, IndexError, ValueError):
                    continue
        except (FileNotFoundError, PermissionError):
            pass
        return members

    # Fallback: use /bin/ps
    result = subprocess.run(
        ["/bin/ps", "-axo", "pid=,pgid=,stat="],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        return []
    members = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            try:
                pid = int(parts[0])
                group = int(parts[1])
                state = parts[2]
                if group == pgid and not state.startswith("Z"):
                    members.append(pid)
            except (ValueError, IndexError):
                continue
    return members


def _stop_process(proc: subprocess.Popen) -> None:
    """Kill process group and confirm all members are dead.

    Raises _CleanupUnconfirmed if:
    - os.killpg fails with EPERM
    - Group members remain alive after the cleanup budget

    Never re-signals a reaped PID.
    """
    if proc.returncode is not None:
        return  # Already reaped, idempotent

    deadline = time.monotonic() + 5  # Existing cleanup budget

    _kill_process_group(proc)

    try:
        # Wait for all group members to exit
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("live group members remain after cleanup budget")
            members = _live_group_members(proc.pid, remaining)
            if not members:
                break
            time.sleep(min(0.02, remaining))

        # Reap the leader
        proc.wait(timeout=max(0.01, deadline - time.monotonic()))

    except (OSError, subprocess.SubprocessError, ValueError, TimeoutError) as exc:
        raise _CleanupUnconfirmed(
            proc, f"process-group death could not be confirmed: {exc}"
        ) from exc


def _retain_cleanup(exc: _CleanupUnconfirmed, state_dir: Path) -> None:
    """Handle cleanup_pending: retain lease and retry cleanup until confirmed.

    This function blocks until cleanup succeeds, keeping the lease held.
    It never returns normally - after cleanup succeeds, it raises RunError.
    """
    result = "interrupted" if exc.interrupted else "failed"
    message = f"Cleanup unresolved; supervisor pid={os.getpid()}; lease retained. {exc}"

    update_state(
        state_dir,
        phase="cleanup_pending",
        run_result=result,
        cleanup_confirmed=False,
        supervisor_pid=os.getpid(),
        process_group=exc.proc.pid,
        error=message,
    )

    log = EventLog.for_state_dir(state_dir)
    log.append("cleanup_pending", {"error": message})

    # Notify the CLI (in supervisor mode)
    if _cleanup_notification is not None:
        _cleanup_notification(message)

    # Retry cleanup until it succeeds. The original child stays unreaped,
    # so its PID cannot be reused as signal authority during retry.
    while True:
        try:
            _stop_process(exc.proc)
        except _CleanupUnconfirmed:
            time.sleep(0.1)
        else:
            break

    # Cleanup confirmed
    update_state(
        state_dir,
        phase="failed",
        run_result=result,
        cleanup_confirmed=True,
        run_finished_at=utc_now_iso(),
        error="Cleanup confirmed after unresolved stop",
    )
    log.append("cleanup_confirmed", {"exit_code": exc.proc.returncode})
    raise RunError("Run failed; deferred cleanup is now confirmed")


def run_contract(
    *,
    contract_path: Path,
    workspace: Path,
    now: float | None = None,
    holder: Any = None,
    guard_parent: bool = False,
) -> dict:
    workspace = resolve_workspace(workspace)
    contract = load_contract(contract_path)
    check_contract_paths(contract, workspace)
    validate_caps(contract.caps)

    # For phrase-approved contracts (no execution_approval), use the supervisor
    # when guard_parent=True. This survives SIGKILL of the CLI.
    if guard_parent and contract.execution_approval is None:
        from runspecimen.run_supervisor import guarded_run
        return guarded_run(contract_path=contract_path, workspace=workspace, now=now)

    if holder is None and contract.execution_approval is not None:
        holder = _resolve_installed_holder(str(contract.execution_approval))

    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    ensure_dir(state_dir)
    signals = _termination_signals() if contract.execution_approval is None else contextlib.nullcontext()
    try:
        with signals, hold_workspace_lease(workspace, holder="run"):
            try:
                return _run_under_lease(
                    contract=contract,
                    workspace=workspace,
                    state_dir=state_dir,
                    now=now,
                    holder=holder,
                )
            except _CleanupUnconfirmed as exc:
                _retain_cleanup(exc, state_dir)
    except LeaseError as exc:
        raise RunError(str(exc)) from exc


def _resolve_installed_holder(policy: str) -> Any:
    """Refuse an installed-holder run from this CLI.

    Never falls back to a typed phrase. Does not prompt for Touch ID, Face ID,
    or a paired phone, does not set hardware true, and does not call consume.
    This path cannot collect a verified device signature.
    """
    from runspecimen.holder_adapter import installed_socket_path

    sock = installed_socket_path()
    if not sock.exists() and not _is_socket(sock):
        raise PreflightError(
            f"execution policy {policy} requires the holder; "
            "installed daemon socket is missing and there is no typed-phrase fallback"
        )
    caller_id = os.environ.get("RS_HOLDER_CALLER_ID", "").strip()
    caller_secret = os.environ.get("RS_HOLDER_CALLER_SECRET", "").strip()
    if not caller_id or not caller_secret:
        raise PreflightError(
            f"execution policy {policy} requires the holder at the installed socket but "
            "RS_HOLDER_CALLER_ID/RS_HOLDER_CALLER_SECRET are unset; "
            "enroll a caller first. There is no typed-phrase fallback"
        )
    # Credentials only prove a caller name. This CLI does not collect an
    # exact-run or device signature and does not prompt. Fail before any
    # holder call so a missing signature is not labeled hardware.
    # Do not call consume from this entry point.
    raise PreflightError(
        f"execution policy {policy} requires the holder; "
        "this CLI cannot collect an exact-run or device signature, "
        "so it will not claim a hardware human. "
        "Authorize that run from the holder. This command does not prompt "
        "and there is no typed-phrase fallback"
    )


def _is_socket(path: Path) -> bool:
    try:
        return path.is_socket()
    except OSError:
        return False


def _run_under_lease(*, contract, workspace: Path, state_dir: Path, now: float | None, holder: Any) -> dict:
    # Check phase first - terminal phases must be rejected immediately
    state = load_state(state_dir)
    phase = state.get("phase")
    if phase in {"running", "cleanup_pending", "completed", "failed", "postflighted", "abandoned"}:
        raise PreflightError(f"run already in phase={phase!r}; refuse re-entry")

    approval = load_approval(state_dir)
    holder_receipt: dict | None = None
    if contract.execution_approval is not None:
        if approval is not None:
            raise PreflightError("a workspace approval cannot replace the execution holder")
        from runspecimen.holder_adapter import HolderRefusal, authorize_held_execution

        if holder is None:
            raise PreflightError(
                f"execution policy {contract.execution_approval} requires the holder; "
                "there is no typed-phrase fallback"
            )
        try:
            holder_receipt = authorize_held_execution(contract, workspace, holder)
        except HolderRefusal as exc:
            raise PreflightError(str(exc)) from exc
        if holder_receipt.get("policy") != contract.execution_approval:
            raise PreflightError("holder policy does not match the contract")
        installed = bool(holder_receipt.get("installed_protection"))
        expect_installed = bool(getattr(holder, "expect_installed", False))
        if expect_installed:
            if not installed:
                raise PreflightError("installed holder did not claim installed protection")
        elif installed:
            raise PreflightError("unprivileged holder must not claim installed protection")
    elif approval is None:
        raise PreflightError("no approval present; run approve first")
    source_hash, _ = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    runtime = runtime_provenance(contract, workspace)
    check_outputs_absent(workspace, contract)
    check_predecessor(workspace, contract)

    cwd = ensure_within(workspace, Path(contract.cwd), label="cwd")
    if not cwd.is_dir():
        raise RunError(f"cwd does not exist or is not a directory: {contract.cwd}")

    isolation, policy = execution_constraints(contract, workspace)
    ts = time.time() if now is None else now
    if holder_receipt is None:
        ok, reason = approval_is_valid(
            approval, contract, source_hash, now=now, state_dir=state_dir
        )
        if not ok:
            raise PreflightError(reason)
        ok, reason = runtime_matches(approval, runtime)
        if not ok:
            raise PreflightError(reason)
        if not plans_match(approval.get("isolation"), isolation):
            raise PreflightError(
                "isolation backend does not match the approval "
                f"(approved {approval.get('isolation')!r}, live {isolation!r})"
            )
        if approval.get("policy") != policy:
            raise PreflightError("shared policy does not match the approval")
        # Source/runtime hashing and predecessor verification can outlast a short
        # approval. Check the clock again at the actual launch boundary.
        ok, reason = approval_is_valid(
            approval, contract, source_hash, now=ts, state_dir=state_dir
        )
        if not ok:
            raise PreflightError(reason)
    elif holder_receipt.get("holder_id") == source_hash:
        raise PreflightError("holder identity is not distinct from the payload")

    _check_termination_signal()
    log = EventLog.for_state_dir(state_dir)
    log.append(
        "run_start",
        {
            "argv": list(contract.argv),
            "contract_hash": contract.contract_hash,
            "source_hash": source_hash,
            "runtime_id": runtime["runtime_id"],
            "wall_timeout_sec": contract.caps.wall_timeout_sec,
            "isolation_backend": isolation.get("backend"),
            "isolation_enforced": isolation.get("enforced"),
        },
    )
    running_fields: dict = {
        "phase": "running",
        "campaign_id": contract.campaign_id,
        "run_id": contract.run_id,
        "run_started_at": utc_now_iso(),
        "run_started_at_unix": ts,
        "contract_hash": contract.contract_hash,
        "source_hash": source_hash,
        "runtime": runtime,
        "isolation": isolation,
    }
    if policy is not None:
        running_fields["policy"] = policy
    if holder_receipt is not None:
        running_fields["execution_holder"] = {
            "holder_id": holder_receipt.get("holder_id"),
            "payload_digest": holder_receipt.get("payload_digest"),
            "policy": holder_receipt.get("policy"),
            "snapshot_root": holder_receipt.get("snapshot_root"),
            "residuals": list(holder_receipt.get("residuals") or []),
            "installed_protection": False,
        }
    update_state(state_dir, **running_fields)

    deadline = time.monotonic() + contract.caps.wall_timeout_sec
    try:
        # Held policies are supervised inside the holder after preflight checks.
        # The client must not Popen that path. Ordinary phrase-approved runs still spawn here.
        if holder_receipt is not None:
            from runspecimen.holder_adapter import HolderRefusal, execute_held_execution

            try:
                holder_receipt = execute_held_execution(contract, workspace, holder, holder_receipt)
            except HolderRefusal as exc:
                raise PreflightError(str(exc)) from exc
            if holder_receipt.get("supervisor") != "holder" or holder_receipt.get("executed") is not True:
                raise PreflightError("held execution requires holder-owned spawn and completion")
            import base64

            stdout_data = base64.b64decode(str(holder_receipt.get("stdout_b64") or ""))
            stderr_data = base64.b64decode(str(holder_receipt.get("stderr_b64") or ""))
            stdout_trunc = bool(holder_receipt.get("stdout_truncated"))
            stderr_trunc = bool(holder_receipt.get("stderr_truncated"))
            exit_code = holder_receipt.get("exit_code")
            timed_out = bool(holder_receipt.get("timed_out"))
            if not isinstance(exit_code, int):
                raise PreflightError("holder execute did not return an exit code")
            atomic_write_bytes(state_dir / STDOUT_FILENAME, stdout_data)
            atomic_write_bytes(state_dir / STDERR_FILENAME, stderr_data)
            finished = utc_now_iso()
            if timed_out:
                result = {
                    "run_result": "timeout",
                    "exit_code": exit_code,
                    "timed_out": True,
                    "stdout_bytes": len(stdout_data),
                    "stderr_bytes": len(stderr_data),
                    "stdout_truncated": stdout_trunc,
                    "stderr_truncated": stderr_trunc,
                }
                update_state(
                    state_dir,
                    phase="failed",
                    run_result="timeout",
                    exit_code=exit_code,
                    timed_out=True,
                    run_finished_at=finished,
                    stdout_truncated=stdout_trunc,
                    stderr_truncated=stderr_trunc,
                )
                log.append("run_timeout", result)
                raise RunError(
                    f"wall timeout after {contract.caps.wall_timeout_sec}s; process group killed"
                )
            result = {
                "run_result": "completed",
                "exit_code": exit_code,
                "timed_out": False,
                "stdout_bytes": len(stdout_data),
                "stderr_bytes": len(stderr_data),
                "stdout_truncated": stdout_trunc,
                "stderr_truncated": stderr_trunc,
            }
            update_state(
                state_dir,
                phase="completed",
                run_result="completed",
                exit_code=exit_code,
                timed_out=False,
                run_finished_at=finished,
                stdout_truncated=stdout_trunc,
                stderr_truncated=stderr_trunc,
            )
            log.append("run_completed", result)
            return {
                "campaign_id": contract.campaign_id,
                "run_id": contract.run_id,
                **result,
            }

        # Build launch vector using approved interpreter if present
        if runtime.get("interpreter"):
            interpreter_args = runtime.get("interpreter_args", [])
            launch_argv = [
                str(runtime["interpreter"]),
                *interpreter_args,
                str(runtime["resolved_executable"]),
                *contract.argv[1:],
            ]
        else:
            launch_argv = [str(runtime["resolved_executable"]), *contract.argv[1:]]

        launch_argv = confinement_argv(
            isolation,
            launch_argv,
            workspace=workspace,
            cwd=cwd,
            profile_path=state_dir / "isolation.sb",
        )
        assert_tool_unchanged(isolation)

        bound_runtime = approval.get("runtime") if isinstance(approval, dict) else runtime
        try:
            job_env = job_environment(
                contract,
                bound_runtime if isinstance(bound_runtime, dict) else runtime,
            )
        except RunError as exc:
            raise PreflightError(str(exc)) from exc
        _check_termination_signal()
        proc = subprocess.Popen(  # noqa: S603
            launch_argv,
            cwd=str(cwd),
            env=job_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            shell=False,
            start_new_session=True,
        )
    except _RunInterrupted as exc:
        update_state(
            state_dir, phase="failed", run_result="interrupted",
            error=f"run interrupted: {exc}", run_finished_at=utc_now_iso(),
        )
        log.append("run_interrupted", {"signal": exc.signum, "error": str(exc)})
        raise
    except PreflightError as exc:
        update_state(
            state_dir,
            phase="failed",
            run_result="failed",
            error=str(exc),
            run_finished_at=utc_now_iso(),
        )
        log.append("run_failed", {"error": str(exc)})
        raise
    except OSError as exc:
        update_state(
            state_dir,
            phase="failed",
            run_result="failed",
            error=f"spawn failed: {exc}",
            run_finished_at=utc_now_iso(),
        )
        log.append("run_failed", {"error": f"spawn failed: {exc}"})
        raise RunError(f"failed to spawn process: {exc}") from exc

    stdout = _Capture(contract.caps.stdout_max_bytes)
    stderr = _Capture(contract.caps.stderr_max_bytes)
    try:
        timed_out = _supervise_process(proc, stdout, stderr, deadline)
        _stop_process(proc)
    except BaseException as exc:
        try:
            _stop_process(proc)
        except _CleanupUnconfirmed as pending:
            # Mark interrupted status and save outputs before re-raising
            pending.interrupted = isinstance(exc, (KeyboardInterrupt, SystemExit, _RunInterrupted))
            atomic_write_bytes(state_dir / STDOUT_FILENAME, bytes(stdout.data))
            atomic_write_bytes(state_dir / STDERR_FILENAME, bytes(stderr.data))
            raise pending from exc
        result = "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit, _RunInterrupted)) else "failed"
        atomic_write_bytes(state_dir / STDOUT_FILENAME, bytes(stdout.data))
        atomic_write_bytes(state_dir / STDERR_FILENAME, bytes(stderr.data))
        update_state(
            state_dir,
            phase="failed",
            run_result=result,
            cleanup_confirmed=True,
            exit_code=proc.returncode,
            error=f"run {result}: {type(exc).__name__}",
            run_finished_at=utc_now_iso(),
            stdout_truncated=stdout.truncated,
            stderr_truncated=stderr.truncated,
        )
        log.append(f"run_{result}", {"exit_code": proc.returncode, "error": type(exc).__name__})
        raise
    finally:
        proc.stdout.close()
        proc.stderr.close()

    stdout_data, stdout_trunc = bytes(stdout.data), stdout.truncated
    stderr_data, stderr_trunc = bytes(stderr.data), stderr.truncated
    atomic_write_bytes(state_dir / STDOUT_FILENAME, stdout_data)
    atomic_write_bytes(state_dir / STDERR_FILENAME, stderr_data)

    exit_code = proc.returncode
    finished = utc_now_iso()
    if timed_out:
        result = {
            "run_result": "timeout",
            "exit_code": exit_code,
            "timed_out": True,
            "stdout_bytes": len(stdout_data),
            "stderr_bytes": len(stderr_data),
            "stdout_truncated": stdout_trunc,
            "stderr_truncated": stderr_trunc,
        }
        update_state(
            state_dir,
            phase="failed",
            run_result="timeout",
            cleanup_confirmed=True,
            exit_code=exit_code,
            timed_out=True,
            run_finished_at=finished,
            stdout_truncated=stdout_trunc,
            stderr_truncated=stderr_trunc,
        )
        log.append("run_timeout", result)
        raise RunError(
            f"wall timeout after {contract.caps.wall_timeout_sec}s; process group killed"
        )

    result = {
        "run_result": "completed",
        "exit_code": exit_code,
        "timed_out": False,
        "stdout_bytes": len(stdout_data),
        "stderr_bytes": len(stderr_data),
        "stdout_truncated": stdout_trunc,
        "stderr_truncated": stderr_trunc,
    }
    update_state(
        state_dir,
        phase="completed",
        run_result="completed",
        cleanup_confirmed=True,
        exit_code=exit_code,
        timed_out=False,
        run_finished_at=finished,
        stdout_truncated=stdout_trunc,
        stderr_truncated=stderr_trunc,
    )
    log.append("run_completed", result)
    return {
        "campaign_id": contract.campaign_id,
        "run_id": contract.run_id,
        **result,
    }
