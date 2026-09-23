"""Interactive approval binding contract + source hashes with expiry."""

from __future__ import annotations

import getpass
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, TextIO

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.contract import Contract, check_contract_paths, load_contract
from runspecimen.errors import ApprovalError, LeaseError
from runspecimen.isolation import plans_match
from runspecimen.policy import execution_constraints
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


def local_approver() -> dict[str, Any]:
    """The OS account that settled approval on this machine. Not an SSO identity.

    On POSIX, resolve the username from the real UID via ``pwd`` so ``LOGNAME`` /
    ``USER`` environment spoofing cannot falsify the recorded identity. This does
    not affect TTY APPROVE gates — only the display/receipt name.
    """
    uid = os.getuid() if hasattr(os, "getuid") else None
    try:
        user = _local_os_username(uid)
    except ApprovalError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ApprovalError(f"cannot record the local OS user: {exc}") from exc
    if not user or any(ch.isspace() for ch in user):
        raise ApprovalError("refusing to record a blank local OS user")
    return {"kind": "local_os_user", "uid": uid, "user": user}


def _local_os_username(uid: int | None) -> str:
    """Resolve the login name for *uid* without trusting LOGNAME/USER."""
    if os.name == "posix" and uid is not None:
        try:
            import pwd
        except ImportError as exc:  # pragma: no cover - exotic POSIX without pwd
            raise ApprovalError("cannot resolve local OS user: pwd module unavailable") from exc
        try:
            return pwd.getpwuid(uid).pw_name
        except KeyError as exc:
            raise ApprovalError(f"cannot resolve local OS user for uid={uid}") from exc
    # Non-POSIX fallback (e.g. Windows): getpass is the practical source.
    return getpass.getuser()
_TERMINAL_PHASES = frozenset({"running", "completed", "failed", "postflighted", "abandoned"})


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
    isolation, policy = execution_constraints(contract, workspace)
    approver = local_approver()
    policy_line = "none" if policy is None else f"{policy['id']} ({policy['sha256'][:12]})"

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
        f"  isolation: {isolation['claim']}\n"
        f"  policy:   {policy_line}\n"
        f"  approver: {approver['user']} (local OS user)\n"
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

    return complete_approval_document(
        contract=contract,
        workspace=workspace,
        now=now,
        confirm_channel="local_tty_approve",
        confirm_evidence={
            "kind": "interactive_tty_phrase",
            "phrase": confirm_phrase,
            "claim": "Interactive local TTY APPROVE on the Mac.",
        },
        expected_source_hash=source_hash,
        expected_runtime=runtime,
        expected_isolation=isolation,
        expected_policy=policy,
    )


def complete_approval_document(
    *,
    contract: Contract,
    workspace: Path,
    now: float | None = None,
    confirm_channel: str = "local_tty_approve",
    confirm_evidence: dict | None = None,
    expected_source_hash: str | None = None,
    expected_runtime: dict | None = None,
    expected_isolation: dict | None = None,
    expected_policy: dict | None = None,
) -> dict:
    """Write approval + events after human confirmation (TTY or remote-confirm settle).

    Caller must already hold the workspace lease. Re-checks phase and provenance.
    """
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
    if expected_source_hash is not None and expected_source_hash != source_hash:
        raise ApprovalError("approval aborted (source hash changed since confirm was armed)")
    runtime = expected_runtime if expected_runtime is not None else runtime_provenance(contract, workspace)
    isolation, policy = execution_constraints(contract, workspace)
    if expected_isolation is not None and not plans_match(expected_isolation, isolation):
        raise ApprovalError("approval aborted (isolation backend changed since the prompt)")
    if expected_policy is not None and expected_policy != policy:
        raise ApprovalError("approval aborted (policy binding changed since the prompt)")
    approver = local_approver()

    ts = time.time() if now is None else now
    expires_at = ts + contract.approval.ttl_sec
    evidence = dict(confirm_evidence or {})
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
        "confirm_channel": confirm_channel,
        "confirm_evidence": evidence,
        "approver": approver,
        "isolation": isolation,
    }
    if policy is not None:
        doc["policy"] = policy

    atomic_write_json(approval_path(state_dir), doc)
    log = EventLog.for_state_dir(state_dir)
    log.append(
        "approval",
        {
            "contract_hash": contract.contract_hash,
            "source_hash": source_hash,
            "runtime_id": runtime["runtime_id"],
            "expires_at_unix": expires_at,
            "confirm_channel": confirm_channel,
            "approver": approver,
            "isolation_backend": isolation.get("backend"),
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
    if isinstance(expires, bool) or not isinstance(expires, (int, float)):
        return False, "approval missing or invalid expires_at_unix"
    try:
        finite_expiry = math.isfinite(expires)
    except OverflowError:
        finite_expiry = False
    if not finite_expiry:
        return False, "approval invalid expires_at_unix (must be finite)"
    if ts >= expires:
        return False, "approval expired (stale)"
    return True, "ok"
