"""Audited crash recovery with explicit human decisions.

When a run crashes mid-execution (phase="running" but process is gone), the
workspace is in an ambiguous state. This module provides TTY-gated recovery
commands that record the human decision in the hash-chained event log.

Recovery options:
- abandon: Mark the run as failed and allow a fresh start with a new run ID
- recover: Attempt to continue (only valid if outputs are intact)

Both require interactive TTY confirmation and record the decision.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from runspecimen.approve import require_interactive_tty
from runspecimen.atomic import atomic_write_json
from runspecimen.errors import ApprovalError, LeaseError, RecoveryError
from runspecimen.events import EventLog, utc_now_iso
from runspecimen.lease import hold_workspace_lease
from runspecimen.paths import ensure_dir, resolve_workspace, run_state_dir
from runspecimen.state import load_state, update_state

# Confirmation phrases for recovery actions
ABANDON_PHRASE = "ABANDON"
RECOVER_PHRASE = "RECOVER"


def is_recoverable(state: dict) -> tuple[bool, str]:
    """Check if a run is in a recoverable (crashed) state.
    
    A run is recoverable if:
    - Phase is "running" (process was executing)
    - There's no active process holding the lease for this run
    
    Returns (is_recoverable, reason).
    """
    phase = state.get("phase")
    
    if phase == "none":
        return False, "no run has started"
    if phase == "approved":
        return False, "run not started (still in approved phase)"
    if phase == "completed":
        return False, "run completed successfully; use postflight"
    if phase == "failed":
        return False, "run already marked as failed"
    if phase == "postflighted":
        return False, "run already postflighted"
    if phase == "abandoned":
        return False, "run already abandoned"
    if phase == "running":
        return True, "run interrupted (phase=running, no active process)"
    
    return False, f"unknown phase: {phase}"


def abandon_run(
    *,
    workspace: Path,
    campaign_id: str,
    run_id: str,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    skip_tty_check: bool = False,
    reason: str = "",
) -> dict:
    """Abandon a crashed run after TTY confirmation.
    
    This marks the run as failed/abandoned and prevents any future use of this
    run ID. A new run with a different ID can then proceed.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    
    if not skip_tty_check:
        require_interactive_tty(stdin, stdout)
    
    workspace = resolve_workspace(workspace)
    state_dir = run_state_dir(workspace, campaign_id, run_id)
    
    try:
        with hold_workspace_lease(workspace, holder="abandon"):
            return _abandon_under_lease(
                state_dir=state_dir,
                campaign_id=campaign_id,
                run_id=run_id,
                stdin=stdin,
                stdout=stdout,
                reason=reason,
            )
    except LeaseError as exc:
        raise RecoveryError(str(exc)) from exc


def _abandon_under_lease(
    *,
    state_dir: Path,
    campaign_id: str,
    run_id: str,
    stdin: TextIO,
    stdout: TextIO,
    reason: str,
) -> dict:
    state = load_state(state_dir)
    recoverable, msg = is_recoverable(state)
    
    if not recoverable:
        raise RecoveryError(f"run is not in a recoverable state: {msg}")
    
    stdout.write(
        f"Abandon crashed run?\n"
        f"  campaign: {campaign_id}\n"
        f"  run_id:   {run_id}\n"
        f"  phase:    {state.get('phase')}\n"
        f"  started:  {state.get('run_started_at', 'unknown')}\n"
        f"\n"
        f"WARNING: This will mark the run as failed/abandoned.\n"
        f"         The run ID cannot be reused after this.\n"
        f"         A new run with a different ID can proceed.\n"
        f"\n"
        f"Type {ABANDON_PHRASE!r} to confirm abandonment: "
    )
    stdout.flush()
    
    line = stdin.readline()
    if line is None:
        raise RecoveryError("no input for abandon confirmation")
    if line.strip() != ABANDON_PHRASE:
        raise RecoveryError("abandon aborted (confirmation phrase mismatch)")
    
    # Re-check state after interactive pause
    state = load_state(state_dir)
    recoverable, msg = is_recoverable(state)
    if not recoverable:
        raise RecoveryError(f"run state changed during confirmation: {msg}")
    
    ts = utc_now_iso()
    log = EventLog.for_state_dir(state_dir)
    log.append(
        "recovery_abandon",
        {
            "decision": "abandon",
            "reason": reason or "human decision via TTY",
            "previous_phase": state.get("phase"),
            "decided_at": ts,
        },
    )
    
    update_state(
        state_dir,
        phase="abandoned",
        run_result="abandoned",
        recovery_decision="abandon",
        recovery_reason=reason or "human decision via TTY",
        recovery_decided_at=ts,
    )
    
    return {
        "ok": True,
        "action": "abandon",
        "campaign_id": campaign_id,
        "run_id": run_id,
        "decided_at": ts,
        "message": "run abandoned; use a new run ID for the next attempt",
    }


def check_recovery_status(
    *,
    workspace: Path,
    campaign_id: str,
    run_id: str,
) -> dict:
    """Check if a run needs recovery and return status details."""
    workspace = resolve_workspace(workspace)
    state_dir = run_state_dir(workspace, campaign_id, run_id)
    state = load_state(state_dir)
    
    recoverable, reason = is_recoverable(state)
    
    return {
        "campaign_id": campaign_id,
        "run_id": run_id,
        "phase": state.get("phase"),
        "run_result": state.get("run_result"),
        "needs_recovery": recoverable,
        "recovery_reason": reason,
        "run_started_at": state.get("run_started_at"),
        "run_finished_at": state.get("run_finished_at"),
    }
