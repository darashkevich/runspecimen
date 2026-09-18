"""Mac-armed remote human confirm (ADR-004).

Arming happens on an interactive Mac TTY. The one-shot challenge is shown only
locally. A paired iOS companion may settle that pending approval by typing the
challenge plus APPROVE. This is not equivalent to local TTY APPROVE evidence,
and agents/plugins must not drive it.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from runspecimen.approve import (
    CONFIRM_PHRASE,
    complete_approval_document,
    require_interactive_tty,
)
from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.contract import Contract, check_contract_paths, load_contract
from runspecimen.errors import ApprovalError, LeaseError, RunSpecimenError
from runspecimen.hashutil import hash_source
from runspecimen.lease import hold_workspace_lease
from runspecimen.paths import ensure_dir, resolve_workspace, run_state_dir
from runspecimen.runtime import runtime_provenance
from runspecimen.state import load_state

PENDING_FILENAME = "remote_confirm_pending.json"
LOCAL_CHALLENGE_FILENAME = "remote_confirm_challenge.local"
DEFAULT_CHALLENGE_TTL_SEC = 300
MAX_FAILED_ATTEMPTS = 5
CONFIRM_CHANNEL = "remote_human_confirm"
NOT_EQUIVALENT_TO = "local_tty_approve"
CLAIM_TEXT = (
    "Remote human confirm of a Mac-armed pending approval; "
    "distinct from interactive TTY APPROVE."
)
MAX_REFUSE_REASON_CHARS = 240
QUIET_HOURS_ENV = "RUNSPECIMEN_QUIET_HOURS"

_TERMINAL_PHASES = frozenset({"running", "completed", "failed", "postflighted", "abandoned"})


def pending_path(state_dir: Path) -> Path:
    return state_dir / PENDING_FILENAME


def local_challenge_path(state_dir: Path) -> Path:
    return state_dir / LOCAL_CHALLENGE_FILENAME


def _challenge_digest(challenge: str) -> str:
    return hashlib.sha256(challenge.encode("utf-8")).hexdigest()


def generate_challenge() -> str:
    """Short, human-typable one-shot code (hex, uppercase for display clarity)."""
    return secrets.token_hex(4).upper()


def _clear_local_challenge(state_dir: Path) -> None:
    path = local_challenge_path(state_dir)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _write_local_challenge(state_dir: Path, challenge: str) -> None:
    path = local_challenge_path(state_dir)
    path.write_text(challenge + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_pending(state_dir: Path) -> dict[str, Any] | None:
    path = pending_path(state_dir)
    if not path.exists():
        return None
    try:
        doc = read_json(path)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(doc, dict):
        return None
    return doc


def clear_pending(state_dir: Path) -> None:
    path = pending_path(state_dir)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    _clear_local_challenge(state_dir)


def pending_is_live(pending: dict[str, Any] | None, *, now: float | None = None) -> bool:
    if not pending or pending.get("consumed"):
        return False
    ts = time.time() if now is None else now
    expires = pending.get("expires_at_unix")
    if not isinstance(expires, (int, float)):
        return False
    if ts >= float(expires):
        return False
    failures = pending.get("failed_attempts", 0)
    if isinstance(failures, int) and failures >= int(pending.get("max_attempts") or MAX_FAILED_ATTEMPTS):
        return False
    return True


def public_pending_view(pending: dict[str, Any] | None, *, now: float | None = None) -> dict[str, Any]:
    """Metadata safe to show to a paired companion — never includes the challenge secret."""
    if not pending_is_live(pending, now=now) or pending is None:
        return {
            "pending": False,
            "can_remote_confirm": False,
        }
    return {
        "pending": True,
        "can_remote_confirm": True,
        "challenge_id": pending.get("challenge_id"),
        "expires_at_unix": pending.get("expires_at_unix"),
        "campaign_id": pending.get("campaign_id"),
        "run_id": pending.get("run_id"),
        "contract_hash": pending.get("contract_hash"),
        "confirm_channel": CONFIRM_CHANNEL,
        "not_equivalent_to": NOT_EQUIVALENT_TO,
        "claim": CLAIM_TEXT,
        "instruction": (
            "Type the Mac-displayed challenge and the word APPROVE. "
            "Refuse requires the same challenge plus a reason."
        ),
        "who": "operator · workspace",
        "what": (
            f"{pending.get('campaign_id')}/{pending.get('run_id')}"
            + (f" · {str(pending.get('contract_hash'))[:12]}" if pending.get("contract_hash") else "")
        ),
    }


def arm_remote_confirm(
    *,
    contract_path: Path,
    workspace: Path,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    ttl_sec: int = DEFAULT_CHALLENGE_TTL_SEC,
    now: float | None = None,
    skip_tty_check: bool = False,
) -> dict[str, Any]:
    """Create a Mac-originated pending remote confirm and print the challenge locally."""
    import sys

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if not skip_tty_check:
        require_interactive_tty(stdin, stdout)

    if ttl_sec < 30 or ttl_sec > 3600:
        raise RunSpecimenError("remote-confirm ttl_sec must be between 30 and 3600")
    if quiet_hours_blocks_arm(now=now):
        raise RunSpecimenError(
            f"refuse remote-confirm arm: {QUIET_HOURS_ENV} is active "
            "(quiet hours never auto-APPROVE; wait or unset the env)"
        )

    workspace = resolve_workspace(workspace)
    contract = load_contract(contract_path)
    check_contract_paths(contract, workspace)

    try:
        with hold_workspace_lease(workspace, holder="remote-confirm-arm"):
            return _arm_under_lease(
                contract=contract,
                workspace=workspace,
                stdout=stdout,
                ttl_sec=ttl_sec,
                now=now,
            )
    except LeaseError as exc:
        raise ApprovalError(str(exc)) from exc


def _arm_under_lease(
    *,
    contract: Contract,
    workspace: Path,
    stdout: TextIO,
    ttl_sec: int,
    now: float | None,
) -> dict[str, Any]:
    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    ensure_dir(state_dir)
    state = load_state(state_dir)
    phase = state.get("phase")
    if phase in _TERMINAL_PHASES:
        raise ApprovalError(
            f"refuse remote-confirm arm: run already in phase={phase!r} "
            f"({contract.campaign_id}/{contract.run_id})"
        )

    source_hash, _manifest = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    runtime = runtime_provenance(contract, workspace)
    ts = time.time() if now is None else now
    challenge = generate_challenge()
    challenge_id = secrets.token_urlsafe(12)
    pending = {
        "version": 1,
        "kind": "remote_human_confirm_pending",
        "challenge_id": challenge_id,
        "challenge_sha256": _challenge_digest(challenge),
        "created_at_unix": ts,
        "expires_at_unix": ts + ttl_sec,
        "ttl_sec": ttl_sec,
        "campaign_id": contract.campaign_id,
        "run_id": contract.run_id,
        "contract_path": str(contract.path),
        "contract_hash": contract.contract_hash,
        "source_hash": source_hash,
        "runtime": runtime,
        "failed_attempts": 0,
        "max_attempts": MAX_FAILED_ATTEMPTS,
        "consumed": False,
        "confirm_channel": CONFIRM_CHANNEL,
        "not_equivalent_to": NOT_EQUIVALENT_TO,
        "adr": "docs/ADR-004-remote-human-confirm.md",
    }
    atomic_write_json(pending_path(state_dir), pending)
    _write_local_challenge(state_dir, challenge)

    stdout.write(
        "Remote human confirm ARMED (ADR-004).\n"
        "Show this challenge only on this Mac. Do not paste it into agent chat.\n"
        f"  campaign:    {contract.campaign_id}\n"
        f"  run_id:      {contract.run_id}\n"
        f"  challenge:   {challenge}\n"
        f"  challenge_id:{challenge_id}\n"
        f"  expires_in:  {ttl_sec}s\n"
        f"On the paired phone, type: {challenge} APPROVE\n"
        "This is remote human confirm — not equivalent to local TTY APPROVE.\n"
    )
    stdout.flush()

    from runspecimen.companion_attention import notify_remote_confirm_armed

    attention = notify_remote_confirm_armed(
        campaign_id=contract.campaign_id,
        run_id=contract.run_id,
        ttl_sec=ttl_sec,
    )

    return {
        "ok": True,
        "armed": True,
        "challenge_id": challenge_id,
        "expires_at_unix": pending["expires_at_unix"],
        "ttl_sec": ttl_sec,
        "campaign_id": contract.campaign_id,
        "run_id": contract.run_id,
        "contract_hash": contract.contract_hash,
        "local_challenge_file": str(local_challenge_path(state_dir)),
        "confirm_channel": CONFIRM_CHANNEL,
        "not_equivalent_to": NOT_EQUIVALENT_TO,
        "attention_notification": attention,
        "adr": "docs/ADR-004-remote-human-confirm.md",
    }


def quiet_hours_blocks_arm(*, now: float | None = None) -> bool:
    """Refuse arming when RUNSPECIMEN_QUIET_HOURS=HH-HH is set and local hour is inside the window."""
    raw = os.environ.get(QUIET_HOURS_ENV, "").strip()
    if not raw:
        return False
    parts = raw.replace("–", "-").split("-")
    if len(parts) != 2:
        raise RunSpecimenError(f"{QUIET_HOURS_ENV} must look like 22-07")
    try:
        start = int(parts[0])
        end = int(parts[1])
    except ValueError as exc:
        raise RunSpecimenError(f"{QUIET_HOURS_ENV} must look like 22-07") from exc
    if not (0 <= start <= 23 and 0 <= end <= 23):
        raise RunSpecimenError(f"{QUIET_HOURS_ENV} hours must be 0-23")
    if start == end:
        return False
    if now is None:
        hour = datetime.now().hour
    else:
        hour = datetime.fromtimestamp(now).hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def run_ontology_chips(
    *,
    contract: Contract,
    workspace: Path,
    pending: dict[str, Any] | None,
    now: float | None = None,
) -> dict[str, Any]:
    """Blast-radius stand-ins for runs (not money/audience)."""
    from runspecimen.lease import Lease

    ts = time.time() if now is None else now
    expiry = "—"
    expires = None if pending is None else pending.get("expires_at_unix")
    if isinstance(expires, (int, float)):
        remaining = max(0, int(float(expires) - ts))
        expiry = f"{remaining}s"
    lease = Lease.for_workspace(workspace, holder="status")
    pred = "none"
    if contract.predecessor is not None:
        pred = f"{contract.predecessor.campaign_id}/{contract.predecessor.run_id}"
    return {
        "expiry": expiry,
        "lease": "held" if lease.is_locked_by_other() else "free",
        "isolation": "native-unspecified",
        "predecessor": pred,
        "wall_timeout_sec": contract.caps.wall_timeout_sec,
    }


def refuse_remote_confirm(
    *,
    contract_path: Path,
    workspace: Path,
    challenge: str,
    reason: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Consume a live pending confirm with a typed reason. Does not write approval."""
    cleaned = (reason or "").strip()
    if not cleaned or len(cleaned) > MAX_REFUSE_REASON_CHARS:
        raise ApprovalError(
            f"refuse reason required (1-{MAX_REFUSE_REASON_CHARS} characters)"
        )
    workspace = resolve_workspace(workspace)
    contract = load_contract(contract_path)
    try:
        with hold_workspace_lease(workspace, holder="remote-confirm-refuse"):
            return _refuse_under_lease(
                contract=contract,
                workspace=workspace,
                challenge=challenge,
                reason=cleaned,
                now=now,
            )
    except LeaseError as exc:
        raise ApprovalError(str(exc)) from exc


def _refuse_under_lease(
    *,
    contract: Contract,
    workspace: Path,
    challenge: str,
    reason: str,
    now: float | None,
) -> dict[str, Any]:
    from runspecimen.events import EventLog

    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    ensure_dir(state_dir)
    pending = load_pending(state_dir)
    if not pending_is_live(pending, now=now) or pending is None:
        raise ApprovalError("no live Mac-armed remote confirm pending")
    if pending.get("contract_hash") != contract.contract_hash:
        raise ApprovalError("remote-confirm pending contract_hash mismatch")

    provided = (challenge or "").strip().upper()
    expected_digest = str(pending.get("challenge_sha256") or "")
    if not provided or not hmac.compare_digest(_challenge_digest(provided), expected_digest):
        _record_failure(state_dir, pending)
        raise ApprovalError("remote-confirm refuse aborted (challenge mismatch)")

    pending = dict(pending)
    pending["consumed"] = True
    pending["refused"] = True
    pending["refuse_reason"] = reason
    atomic_write_json(pending_path(state_dir), pending)
    _clear_local_challenge(state_dir)

    log = EventLog.for_state_dir(state_dir)
    log.ensure()
    record = log.append(
        "remote_confirm_refused",
        {
            "reason": reason,
            "challenge_id": pending.get("challenge_id"),
            "confirm_channel": CONFIRM_CHANNEL,
            "not_equivalent_to": NOT_EQUIVALENT_TO,
            "campaign_id": contract.campaign_id,
            "run_id": contract.run_id,
            "contract_hash": contract.contract_hash,
        },
    )
    clear_pending(state_dir)
    return {
        "ok": True,
        "refused": True,
        "reason": reason,
        "confirm_channel": CONFIRM_CHANNEL,
        "event_hash": record.event_hash,
        "not_equivalent_to": NOT_EQUIVALENT_TO,
        "note": "Pending consumed. Re-arm or use local TTY APPROVE. Not an agent amend chat.",
    }


def cancel_remote_confirm(*, contract_path: Path, workspace: Path) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    contract = load_contract(contract_path)
    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    existed = pending_path(state_dir).exists()
    clear_pending(state_dir)
    return {"ok": True, "cancelled": existed}


def read_local_challenge_for_display(state_dir: Path) -> str | None:
    """Mac-local helper only — never expose via companion HTTP."""
    path = local_challenge_path(state_dir)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def _record_failure(state_dir: Path, pending: dict[str, Any]) -> None:
    pending = dict(pending)
    pending["failed_attempts"] = int(pending.get("failed_attempts") or 0) + 1
    if pending["failed_attempts"] >= int(pending.get("max_attempts") or MAX_FAILED_ATTEMPTS):
        pending["consumed"] = True
        atomic_write_json(pending_path(state_dir), pending)
        _clear_local_challenge(state_dir)
    else:
        atomic_write_json(pending_path(state_dir), pending)


def settle_remote_confirm(
    *,
    contract_path: Path,
    workspace: Path,
    challenge: str,
    phrase: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Consume a live pending challenge and write a remote_human_confirm approval."""
    workspace = resolve_workspace(workspace)
    contract = load_contract(contract_path)
    check_contract_paths(contract, workspace)

    try:
        with hold_workspace_lease(workspace, holder="remote-confirm-settle"):
            return _settle_under_lease(
                contract=contract,
                workspace=workspace,
                challenge=challenge,
                phrase=phrase,
                now=now,
            )
    except LeaseError as exc:
        raise ApprovalError(str(exc)) from exc


def _settle_under_lease(
    *,
    contract: Contract,
    workspace: Path,
    challenge: str,
    phrase: str,
    now: float | None,
) -> dict[str, Any]:
    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    ensure_dir(state_dir)
    pending = load_pending(state_dir)
    if not pending_is_live(pending, now=now) or pending is None:
        raise ApprovalError("no live Mac-armed remote confirm pending")

    if pending.get("contract_hash") != contract.contract_hash:
        raise ApprovalError("remote-confirm pending contract_hash mismatch")
    if pending.get("campaign_id") != contract.campaign_id or pending.get("run_id") != contract.run_id:
        raise ApprovalError("remote-confirm pending run identity mismatch")

    if phrase.strip() != CONFIRM_PHRASE:
        _record_failure(state_dir, pending)
        raise ApprovalError("remote-confirm aborted (confirmation phrase mismatch)")

    provided = (challenge or "").strip().upper()
    expected_digest = str(pending.get("challenge_sha256") or "")
    if not provided or not hmac.compare_digest(_challenge_digest(provided), expected_digest):
        _record_failure(state_dir, pending)
        raise ApprovalError("remote-confirm aborted (challenge mismatch)")

    pending = dict(pending)
    pending["consumed"] = True
    atomic_write_json(pending_path(state_dir), pending)
    _clear_local_challenge(state_dir)

    evidence = {
        "kind": "mac_armed_challenge_plus_approve_phrase",
        "challenge_id": pending.get("challenge_id"),
        "not_equivalent_to": NOT_EQUIVALENT_TO,
        "claim": CLAIM_TEXT,
        "adr": "docs/ADR-004-remote-human-confirm.md",
    }
    doc = complete_approval_document(
        contract=contract,
        workspace=workspace,
        now=now,
        confirm_channel=CONFIRM_CHANNEL,
        confirm_evidence=evidence,
        expected_source_hash=str(pending.get("source_hash") or ""),
    )
    clear_pending(state_dir)
    return doc
