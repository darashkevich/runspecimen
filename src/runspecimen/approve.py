"""Interactive approval binding contract + source hashes with expiry."""

from __future__ import annotations

import getpass
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, TextIO

from runspecimen.atomic import atomic_write_json, read_json_nofollow
from runspecimen.contract import Contract, check_contract_paths, load_contract
from runspecimen.errors import ApprovalError, LeaseError, PathEscapeError
from runspecimen.isolation import plans_match
from runspecimen.policy import execution_constraints
from runspecimen.events import EventLog, utc_now_iso
from runspecimen.hashutil import canonical_json_bytes, hash_source, sha256_bytes
from runspecimen.lease import hold_workspace_lease
from runspecimen.paths import (
    APPROVAL_FILENAME,
    assert_control_plane_not_symlinked,
    ensure_dir,
    resolve_workspace,
    run_state_dir,
)
from runspecimen.present import format_approve_prompt
from runspecimen.state import load_state, update_state
from runspecimen.runtime import runtime_provenance

CONFIRM_PHRASE = "APPROVE"

# Only values real approve / remote-confirm settle paths write.
ALLOWED_CONFIRM_CHANNELS = frozenset({"local_tty_approve", "remote_human_confirm"})

PLANTED_OR_EDITED_APPROVAL = (
    "This run has no chained approval event that matches approval.json. "
    "Planted or edited approval files cannot launch."
)
APPROVAL_EVENT_MISMATCH = (
    "approval.json does not match the latest chained approval event. "
    "Planted or edited approval files cannot launch."
)
UNKNOWN_CONFIRM_CHANNEL = (
    "approval confirm_channel is not a value this program writes"
)
TTL_REFRESH_REQUIRES_TTY = (
    "TTL refresh requires a real TTY approve "
    "(remote confirm cannot extend an existing approval)"
)


def typed_phrase_fallback_refusal(policy: str) -> str:
    """Plain-English refusal when a holder policy has no TTY APPROVE path.

    Used by approve, preflight, and postflight so piped and interactive
    callers see the same sentence. N10 pins this exact text. This is not a
    holder-receipt path.
    """
    return f"execution policy {policy} has no typed-phrase fallback"


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
    assert_control_plane_not_symlinked(path)
    if path.is_symlink():
        raise PathEscapeError(
            f"control-plane path must not be a symlink (or contain a symlinked component): {path}"
        )
    if not path.exists():
        return None
    return read_json_nofollow(path)


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

    workspace = resolve_workspace(workspace)
    contract = load_contract(contract_path)
    if contract.execution_approval is not None:
        raise ApprovalError(typed_phrase_fallback_refusal(contract.execution_approval))
    if not skip_tty_check:
        require_interactive_tty(stdin, stdout)

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
    manifest_line = "none"
    check_lines: list[str] = []
    if contract.task_manifest is not None:
        from runspecimen.hashutil import sha256_file
        from runspecimen.paths import ensure_within
        from runspecimen.requirements import load_task_manifest

        mpath = ensure_within(
            workspace, Path(contract.task_manifest.path), label="task_manifest.path"
        )
        live = sha256_file(mpath)
        if live != contract.task_manifest.sha256:
            raise ApprovalError(
                "task_manifest.sha256 does not match file bytes; "
                "rebind the contract before approval"
            )
        manifest = load_task_manifest(mpath)
        if manifest.id != contract.task_manifest.id:
            raise ApprovalError(
                f"task_manifest.id mismatch: contract={contract.task_manifest.id!r} "
                f"file={manifest.id!r}"
            )
        manifest_line = (
            f"{contract.task_manifest.id} ({contract.task_manifest.sha256[:12]}) "
            f"path={contract.task_manifest.path}"
        )
        for req in manifest.requirements:
            if req.check is None:
                check_lines.append(f"    - {req.id}: manual_unverifiable")
            else:
                check_lines.append(
                    f"    - {req.id}: {req.check.provider}/{req.check.id} "
                    f"config={req.check.config!r}"
                )

    stdout.write(
        format_approve_prompt(
            campaign_id=contract.campaign_id,
            run_id=contract.run_id,
            argv=list(contract.argv),
            cwd=str(contract.cwd),
            sources=list(contract.source.roots),
            excludes=list(contract.source.excludes),
            outputs=list(contract.asserted_output_paths),
            timeout_sec=int(contract.caps.wall_timeout_sec),
            stdout_max_bytes=int(contract.caps.stdout_max_bytes),
            stderr_max_bytes=int(contract.caps.stderr_max_bytes),
            predecessor=contract.predecessor,
            isolation_claim=str(isolation["claim"]),
            policy_line=policy_line,
            manifest_line=manifest_line,
            check_lines=check_lines,
            approver_user=str(approver["user"]),
            contract_hash=contract.contract_hash,
            source_hash=source_hash,
            runtime_path=str(runtime["resolved_executable"]),
            runtime_id=str(runtime["runtime_id"]),
            ttl_sec=int(contract.approval.ttl_sec),
            confirm_phrase=confirm_phrase,
        )
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
            "claim": "Interactive local TTY APPROVE on this computer.",
        },
        expected_source_hash=source_hash,
        expected_runtime=runtime,
        expected_isolation=isolation,
        expected_policy=policy,
        allow_ttl_refresh=True,
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
    allow_ttl_refresh: bool = False,
) -> dict:
    """Write approval + events after human confirmation (TTY or remote-confirm settle).

    Caller must already hold the workspace lease. Re-checks phase and provenance.
    TTY approve may refresh TTL while phase is ``approved`` or ``preflighted``;
    each refresh appends a new approval event and the latest event governs.
    Remote confirm cannot refresh an existing approval.
    """
    if contract.execution_approval is not None:
        raise ApprovalError(typed_phrase_fallback_refusal(contract.execution_approval))
    if confirm_channel not in ALLOWED_CONFIRM_CHANNELS:
        raise ApprovalError(UNKNOWN_CONFIRM_CHANNEL)
    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    ensure_dir(state_dir)
    state = load_state(state_dir)
    phase = state.get("phase")
    if phase in _TERMINAL_PHASES:
        raise ApprovalError(
            f"refuse re-approval: run already in phase={phase!r} "
            f"({contract.campaign_id}/{contract.run_id})"
        )
    if phase in {"approved", "preflighted"} and not allow_ttl_refresh:
        raise ApprovalError(TTL_REFRESH_REQUIRES_TTY)

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
    if contract.task_manifest is not None:
        from runspecimen.hashutil import sha256_bytes, canonical_json_bytes
        from runspecimen.paths import ensure_within
        from runspecimen.requirements import load_task_manifest

        mpath = ensure_within(
            workspace, Path(contract.task_manifest.path), label="task_manifest.path"
        )
        manifest = load_task_manifest(mpath)
        checks = []
        for req in manifest.requirements:
            if req.check is None:
                checks.append({"requirement_id": req.id, "manual_unverifiable": True})
            else:
                checks.append(
                    {
                        "requirement_id": req.id,
                        "provider": req.check.provider,
                        "id": req.check.id,
                        "identity": sha256_bytes(
                            canonical_json_bytes(
                                {
                                    "provider": req.check.provider,
                                    "id": req.check.id,
                                    "config": req.check.config,
                                }
                            )
                        ),
                        "config": req.check.config,
                    }
                )
        doc["task_manifest"] = {
            "id": contract.task_manifest.id,
            "path": contract.task_manifest.path,
            "sha256": contract.task_manifest.sha256,
            "manifest_hash": manifest.manifest_hash,
            "checks": checks,
        }

    atomic_write_json(approval_path(state_dir), doc)
    document_hash = approval_document_hash(doc)
    log = EventLog.for_state_dir(state_dir)
    log.append(
        "approval",
        {
            "approval_document_hash": document_hash,
            "contract_hash": contract.contract_hash,
            "source_hash": source_hash,
            "runtime_id": runtime["runtime_id"],
            "expires_at_unix": expires_at,
            "confirm_channel": confirm_channel,
            "confirm_evidence": evidence,
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


def approval_document_hash(approval: dict) -> str:
    """Canonical SHA-256 of the approval document.

    Covers every field ``approval_is_valid`` trusts plus ``confirm_channel``,
    ``confirm_evidence``, and ``expires_at_unix``. Hashing the full document
    means any edit after approve fails the chained-event check.
    """
    if not isinstance(approval, dict):
        raise ApprovalError("approval document is not an object")
    return sha256_bytes(canonical_json_bytes(approval))


def latest_approval_event(state_dir: Path):
    """Return the latest chained ``approval`` event, or None."""
    log = EventLog.for_state_dir(state_dir)
    if not log.path.exists():
        return None
    ok, _msg = log.verify_chain()
    if not ok:
        return None
    for rec in reversed(log.read_all()):
        if rec.type == "approval":
            return rec
    return None


def approval_matches_latest_event(
    approval: dict,
    state_dir: Path,
) -> tuple[bool, str]:
    """Refuse unless approval.json equals the latest chained approval event."""
    channel = approval.get("confirm_channel")
    if channel not in ALLOWED_CONFIRM_CHANNELS:
        return False, UNKNOWN_CONFIRM_CHANNEL
    try:
        digest = approval_document_hash(approval)
    except ApprovalError as exc:
        return False, str(exc)
    rec = latest_approval_event(state_dir)
    if rec is None:
        return False, PLANTED_OR_EDITED_APPROVAL
    event_hash = rec.body.get("approval_document_hash")
    if not isinstance(event_hash, str) or not event_hash:
        return False, PLANTED_OR_EDITED_APPROVAL
    if event_hash != digest:
        return False, APPROVAL_EVENT_MISMATCH
    if rec.body.get("confirm_channel") != channel:
        return False, APPROVAL_EVENT_MISMATCH
    return True, "ok"


def _expires_at_unix_is_valid(expires: object) -> tuple[bool, str]:
    if isinstance(expires, bool) or not isinstance(expires, (int, float)):
        return False, "approval missing or invalid expires_at_unix"
    try:
        finite_expiry = math.isfinite(expires)
    except OverflowError:
        finite_expiry = False
    if not finite_expiry:
        return False, "approval invalid expires_at_unix (must be finite)"
    return True, "ok"


def approval_is_valid(
    approval: dict,
    contract: Contract,
    source_hash: str,
    *,
    now: float | None = None,
    state_dir: Path | None = None,
) -> tuple[bool, str]:
    ts = time.time() if now is None else now
    if approval.get("contract_hash") != contract.contract_hash:
        return False, "approval contract_hash mismatch (stale or wrong contract)"
    if approval.get("source_hash") != source_hash:
        return False, "approval source_hash mismatch (provenance changed)"
    if approval.get("campaign_id") != contract.campaign_id or approval.get("run_id") != contract.run_id:
        return False, "approval run identity mismatch"
    file_expires = approval.get("expires_at_unix")
    ok, reason = _expires_at_unix_is_valid(file_expires)
    if not ok:
        return False, reason
    if state_dir is not None:
        bound_ok, bound_reason = approval_matches_latest_event(approval, state_dir)
        if not bound_ok:
            return False, bound_reason
        rec = latest_approval_event(state_dir)
        if rec is None:
            return False, PLANTED_OR_EDITED_APPROVAL
        expires = rec.body.get("expires_at_unix")
        ok, reason = _expires_at_unix_is_valid(expires)
        if not ok:
            return False, reason
    else:
        expires = file_expires
    if ts >= expires:
        return False, "approval expired (stale)"
    return True, "ok"
