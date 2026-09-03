"""Human-readable status for a run (read-only; does not take the execution lease)."""

from __future__ import annotations

import json
from pathlib import Path

from runspecimen.approve import load_approval
from runspecimen.certificate import load_certificate
from runspecimen.contract import load_contract
from runspecimen.events import EventLog
from runspecimen.lease import Lease
from runspecimen.paths import resolve_workspace, run_state_dir
from runspecimen.state import load_state


def status_for(
    *,
    workspace: Path,
    campaign_id: str,
    run_id: str,
    contract_path: Path | None = None,
) -> dict:
    workspace = resolve_workspace(workspace)
    state_dir = run_state_dir(workspace, campaign_id, run_id)
    state = load_state(state_dir)
    approval = load_approval(state_dir)
    cert = load_certificate(state_dir)
    log = EventLog.for_state_dir(state_dir)
    chain_ok, chain_msg = (True, "empty") if not log.path.exists() else log.verify_chain()
    lease = Lease.for_workspace(workspace, holder="status")
    lease_held = lease.is_locked_by_other()
    lease_meta = lease.read_meta() if lease_held else None

    contract_info = None
    if contract_path is not None:
        c = load_contract(contract_path)
        contract_info = {
            "path": str(c.path),
            "hash": c.contract_hash,
            "argv": list(c.argv),
        }

    return {
        "workspace": str(workspace),
        "campaign_id": campaign_id,
        "run_id": run_id,
        "state_dir": str(state_dir),
        "phase": state.get("phase"),
        "state": state,
        "approval": approval,
        "certificate": (
            {"certificate_id": cert["certificate_id"], "event_head": cert["event_head"]}
            if cert
            else None
        ),
        "event_chain_ok": chain_ok,
        "event_chain_msg": chain_msg,
        "event_count": len(log.read_all()) if log.path.exists() else 0,
        "workspace_lease_held_by_other": lease_held,
        "lease_held_by_other": lease_held,
        "lease_meta": lease_meta.to_dict() if lease_meta else None,
        "contract": contract_info,
    }


def format_status(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, default=str)
