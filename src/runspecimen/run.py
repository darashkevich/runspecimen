"""Execute exactly one approved bounded run under workspace lease."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from runspecimen.approve import approval_is_valid, load_approval
from runspecimen.atomic import atomic_write_bytes
from runspecimen.contract import check_contract_paths, load_contract, validate_caps
from runspecimen.errors import LeaseError, PreflightError, RunError
from runspecimen.events import EventLog, utc_now_iso
from runspecimen.hashutil import hash_source
from runspecimen.lease import hold_workspace_lease
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
from runspecimen.runtime import runtime_matches, runtime_provenance


def _kill_process_group(proc: subprocess.Popen[bytes]) -> None:
    if proc.pid is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


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
        return False
    finally:
        selector.close()


def _stop_process(proc) -> None:
    _kill_process_group(proc)
    proc.wait(timeout=5)


def run_contract(
    *,
    contract_path: Path,
    workspace: Path,
    now: float | None = None,
) -> dict:
    workspace = resolve_workspace(workspace)
    contract = load_contract(contract_path)
    check_contract_paths(contract, workspace)
    validate_caps(contract.caps)

    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    ensure_dir(state_dir)
    try:
        with hold_workspace_lease(workspace, holder="run"):
            return _run_under_lease(
                contract=contract,
                workspace=workspace,
                state_dir=state_dir,
                now=now,
            )
    except LeaseError as exc:
        raise RunError(str(exc)) from exc


def _run_under_lease(*, contract, workspace: Path, state_dir: Path, now: float | None) -> dict:
    approval = load_approval(state_dir)
    if approval is None:
        raise PreflightError("no approval present; run approve first")
    source_hash, _ = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    ok, reason = approval_is_valid(approval, contract, source_hash, now=now)
    if not ok:
        raise PreflightError(reason)
    runtime = runtime_provenance(contract, workspace)
    ok, reason = runtime_matches(approval, runtime)
    if not ok:
        raise PreflightError(reason)
    check_outputs_absent(workspace, contract)
    check_predecessor(workspace, contract)

    state = load_state(state_dir)
    phase = state.get("phase")
    if phase in {"running", "completed", "failed", "postflighted"}:
        raise PreflightError(f"run already in phase={phase!r}; refuse re-entry")

    cwd = ensure_within(workspace, Path(contract.cwd), label="cwd")
    if not cwd.is_dir():
        raise RunError(f"cwd does not exist or is not a directory: {contract.cwd}")

    # Source/runtime hashing and predecessor verification can outlast a short
    # approval. Check the clock again at the actual launch boundary.
    ts = time.time() if now is None else now
    ok, reason = approval_is_valid(approval, contract, source_hash, now=ts)
    if not ok:
        raise PreflightError(reason)

    log = EventLog.for_state_dir(state_dir)
    log.append(
        "run_start",
        {
            "argv": list(contract.argv),
            "contract_hash": contract.contract_hash,
            "source_hash": source_hash,
            "runtime_id": runtime["runtime_id"],
            "wall_timeout_sec": contract.caps.wall_timeout_sec,
        },
    )
    update_state(
        state_dir,
        phase="running",
        campaign_id=contract.campaign_id,
        run_id=contract.run_id,
        run_started_at=utc_now_iso(),
        run_started_at_unix=ts,
        contract_hash=contract.contract_hash,
        source_hash=source_hash,
        runtime=runtime,
    )

    deadline = time.monotonic() + contract.caps.wall_timeout_sec
    try:
        # Launch the exact absolute executable that was just hashed instead of
        # asking PATH to resolve argv[0] a second time.
        launch_argv = [str(runtime["resolved_executable"]), *contract.argv[1:]]
        proc = subprocess.Popen(  # noqa: S603
            launch_argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            shell=False,
            start_new_session=True,
        )
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
        _stop_process(proc)
        result = "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed"
        atomic_write_bytes(state_dir / STDOUT_FILENAME, bytes(stdout.data))
        atomic_write_bytes(state_dir / STDERR_FILENAME, bytes(stderr.data))
        update_state(
            state_dir,
            phase="failed",
            run_result=result,
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
