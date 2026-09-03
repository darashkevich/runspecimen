"""Execute exactly one approved bounded run under workspace lease."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
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


def _drain_bounded(stream, max_bytes: int, sink: list) -> None:
    """Background reader: keep at most max_bytes; drop the rest."""
    buf = bytearray()
    truncated = False
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            if truncated:
                continue
            remaining = max_bytes - len(buf)
            if remaining <= 0:
                truncated = True
                continue
            if len(chunk) > remaining:
                buf.extend(chunk[:remaining])
                truncated = True
            else:
                buf.extend(chunk)
    finally:
        sink.append((bytes(buf), truncated))


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
    ts = time.time() if now is None else now

    try:
        with hold_workspace_lease(workspace, holder="run"):
            return _run_under_lease(
                contract=contract,
                workspace=workspace,
                state_dir=state_dir,
                ts=ts,
            )
    except LeaseError as exc:
        raise RunError(str(exc)) from exc


def _run_under_lease(*, contract, workspace: Path, state_dir: Path, ts: float) -> dict:
    approval = load_approval(state_dir)
    if approval is None:
        raise PreflightError("no approval present; run approve first")
    source_hash, _ = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    ok, reason = approval_is_valid(approval, contract, source_hash, now=ts)
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

    try:
        # Launch the exact absolute executable that was just hashed instead of
        # asking PATH to resolve argv[0] a second time.
        launch_argv = [str(runtime["resolved_executable"]), *contract.argv[1:]]
        proc = subprocess.Popen(  # noqa: S603
            launch_argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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

    assert proc.stdout is not None and proc.stderr is not None
    stdout_sink: list = []
    stderr_sink: list = []
    t_out = threading.Thread(
        target=_drain_bounded,
        args=(proc.stdout, contract.caps.stdout_max_bytes, stdout_sink),
        daemon=True,
    )
    t_err = threading.Thread(
        target=_drain_bounded,
        args=(proc.stderr, contract.caps.stderr_max_bytes, stderr_sink),
        daemon=True,
    )
    t_out.start()
    t_err.start()

    timed_out = False
    deadline = time.monotonic() + contract.caps.wall_timeout_sec
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                _kill_process_group(proc)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _kill_process_group(proc)
                    proc.wait(timeout=5)
                break
            try:
                proc.wait(timeout=min(0.2, max(remaining, 0.01)))
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        t_out.join(timeout=5)
        t_err.join(timeout=5)
        try:
            proc.stdout.close()
        except OSError:
            pass
        try:
            proc.stderr.close()
        except OSError:
            pass

    stdout_data, stdout_trunc = stdout_sink[0] if stdout_sink else (b"", False)
    stderr_data, stderr_trunc = stderr_sink[0] if stderr_sink else (b"", False)
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
