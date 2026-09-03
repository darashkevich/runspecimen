"""Interactive approval binding contract + source hashes with expiry."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TextIO

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.contract import Contract, check_contract_paths, load_contract
from runspecimen.errors import ApprovalError, LeaseError
from runspecimen.events import EventLog, utc_now_iso
from runspecimen.hashutil import hash_source
from runspecimen.lease import hold_workspace_lease
from runspecimen.paths import (
    APPROVAL_FILENAME,
    ensure_dir,
    resolve_workspace,
    run_state_dir,
)
from runspecimen.state import load_state, update_state
from runspecimen.runtime import runtime_provenance

CONFIRM_PHRASE = "APPROVE"
_TERMINAL_PHASES = frozenset({"running", "completed", "failed", "postflighted"})


def approval_path(state_dir: Path) -> Path:
    return state_dir / APPROVAL_FILENAME


def load_approval(state_dir: Path) -> dict | None:
    path = approval_path(state_dir)
    if not path.exists():
        return None
    return read_json(path)


def require_interactive_tty(
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if not (
        hasattr(stdin, "isatty")
        and stdin.isatty()
        and hasattr(stdout, "isatty")
        and stdout.isatty()
    ):
        raise ApprovalError(
            "approval requires an interactive TTY on stdin and stdout "
            "(refuse unattended / piped approval)"
        )


def approve_contract(
    *,
    contract_path: Path,
    workspace: Path,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    confirm_phrase: str = CONFIRM_PHRASE,
    now: float | None = None,
    skip_tty_check: bool = False,
) -> dict:
    """Prompt on a TTY and write a binding approval document under workspace lease."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if not skip_tty_check:
        require_interactive_tty(stdin, stdout)

    workspace = resolve_workspace(workspace)
    contract = load_contract(contract_path)
    check_contract_paths(contract, workspace)

    try:
        with hold_workspace_lease(workspace, holder="approve"):
            return _approve_under_lease(
                contract=contract,
                workspace=workspace,
                stdin=stdin,
                stdout=stdout,
                confirm_phrase=confirm_phrase,
                now=now,
            )
    except LeaseError as exc:
        raise ApprovalError(str(exc)) from exc


def _approve_under_lease(
    *,
    contract: Contract,
    workspace: Path,
    stdin: TextIO,
    stdout: TextIO,
    confirm_phrase: str,
    now: float | None,
) -> dict:
    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    ensure_dir(state_dir)
    state = load_state(state_dir)
    phase = state.get("phase")
    if phase in _TERMINAL_PHASES:
        raise ApprovalError(
            f"refuse re-approval: run already in phase={phase!r} "
            f"({contract.campaign_id}/{contract.run_id})"
        )

    source_hash, _manifest = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    runtime = runtime_provenance(contract, workspace)

    stdout.write(
        f"Approve bounded run?\n"
        f"  campaign: {contract.campaign_id}\n"
        f"  run_id:   {contract.run_id}\n"
        f"  argv:     {list(contract.argv)!r}\n"
        f"  cwd:      {contract.cwd}\n"
        f"  sources:  {list(contract.source.roots)!r}\n"
        f"  excludes: {list(contract.source.excludes)!r}\n"
        f"  outputs:  {list(contract.asserted_output_paths)!r}\n"
        f"  timeout:  {contract.caps.wall_timeout_sec}s\n"
        f"  capture:  stdout={contract.caps.stdout_max_bytes}B "
        f"stderr={contract.caps.stderr_max_bytes}B\n"
        f"  prior:    {contract.predecessor!r}\n"
        f"  contract: {contract.contract_hash}\n"
        f"  source:   {source_hash}\n"
        f"  runtime:  {runtime['resolved_executable']}\n"
        f"  runtime#: {runtime['runtime_id']}\n"
        f"  ttl_sec:  {contract.approval.ttl_sec}\n"
        f"Type {confirm_phrase!r} to bind this approval: "
    )
    stdout.flush()
    line = stdin.readline()
    if line is None:
        raise ApprovalError("no input for approval confirmation")
    if line.strip() != confirm_phrase:
        raise ApprovalError("approval aborted (confirmation phrase mismatch)")

    # Re-check phase after interactive pause (still under lease).
    state = load_state(state_dir)
    phase = state.get("phase")
    if phase in _TERMINAL_PHASES:
        raise ApprovalError(
            f"refuse re-approval: run already in phase={phase!r} "
            f"({contract.campaign_id}/{contract.run_id})"
        )

    ts = time.time() if now is None else now
    expires_at = ts + contract.approval.ttl_sec
    doc = {
        "approved_at": utc_now_iso(),
        "approved_at_unix": ts,
        "expires_at_unix": expires_at,
        "campaign_id": contract.campaign_id,
        "run_id": contract.run_id,
        "contract_path": str(contract.path),
        "contract_hash": contract.contract_hash,
        "source_hash": source_hash,
        "runtime": runtime,
        "ttl_sec": contract.approval.ttl_sec,
        "argv": list(contract.argv),
    }

    atomic_write_json(approval_path(state_dir), doc)
    log = EventLog.for_state_dir(state_dir)
    log.append(
        "approval",
        {
            "contract_hash": contract.contract_hash,
            "source_hash": source_hash,
            "runtime_id": runtime["runtime_id"],
            "expires_at_unix": expires_at,
        },
    )
    update_state(
        state_dir,
        phase="approved",
        campaign_id=contract.campaign_id,
        run_id=contract.run_id,
        contract_hash=contract.contract_hash,
        source_hash=source_hash,
        runtime=runtime,
        approval_expires_at_unix=expires_at,
    )
    return doc


def approval_is_valid(
    approval: dict,
    contract: Contract,
    source_hash: str,
    *,
    now: float | None = None,
) -> tuple[bool, str]:
    ts = time.time() if now is None else now
    if approval.get("contract_hash") != contract.contract_hash:
        return False, "approval contract_hash mismatch (stale or wrong contract)"
    if approval.get("source_hash") != source_hash:
        return False, "approval source_hash mismatch (provenance changed)"
    if approval.get("campaign_id") != contract.campaign_id or approval.get("run_id") != contract.run_id:
        return False, "approval run identity mismatch"
    expires = approval.get("expires_at_unix")
    if not isinstance(expires, (int, float)):
        return False, "approval missing expires_at_unix"
    if ts > float(expires):
        return False, "approval expired (stale)"
    return True, "ok"
