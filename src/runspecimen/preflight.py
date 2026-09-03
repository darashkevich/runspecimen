"""Preflight checks before a bounded run."""

from __future__ import annotations

import time
from pathlib import Path

from runspecimen.approve import approval_is_valid, load_approval
from runspecimen.certificate import verify_run_receipt
from runspecimen.contract import (
    Contract,
    check_contract_paths,
    load_contract,
    validate_caps,
)
from runspecimen.errors import CertificateError, LeaseError, PreflightError
from runspecimen.events import EventLog
from runspecimen.hashutil import hash_source
from runspecimen.lease import hold_workspace_lease
from runspecimen.paths import ensure_within, resolve_workspace, run_state_dir
from runspecimen.state import load_state, update_state
from runspecimen.runtime import runtime_matches, runtime_provenance


def check_predecessor(workspace: Path, contract: Contract) -> None:
    pred = contract.predecessor
    if pred is None:
        return
    pred_dir = run_state_dir(workspace, pred.campaign_id, pred.run_id)
    if not (pred_dir / "state.json").exists():
        raise PreflightError(f"predecessor not found: {pred.campaign_id}/{pred.run_id}")
    state = load_state(pred_dir)
    phase = state.get("phase")
    if pred.refuse_if_failed and phase == "failed":
        raise PreflightError(f"predecessor failed: {pred.campaign_id}/{pred.run_id}")
    if pred.refuse_if_failed and state.get("run_result") in {"failed", "timeout"}:
        raise PreflightError(
            f"predecessor run_result={state.get('run_result')!r}: "
            f"{pred.campaign_id}/{pred.run_id}"
        )
    if pred.require_postflight:
        if phase != "postflighted":
            raise PreflightError(
                f"predecessor not postflighted (phase={phase!r}): "
                f"{pred.campaign_id}/{pred.run_id}"
            )
        try:
            verify_run_receipt(
                workspace=workspace,
                campaign_id=pred.campaign_id,
                run_id=pred.run_id,
                require_live_provenance=False,
            )
        except CertificateError as exc:
            raise PreflightError(
                f"predecessor receipt verification failed "
                f"({pred.campaign_id}/{pred.run_id}): {exc}"
            ) from exc


def check_outputs_absent(workspace: Path, contract: Contract) -> None:
    for rel in contract.asserted_output_paths:
        path = ensure_within(workspace, Path(rel), label=f"output {rel!r}")
        if path.exists():
            raise PreflightError(f"asserted output already exists (refuse overwrite): {rel}")


def preflight(
    *,
    contract_path: Path,
    workspace: Path,
    now: float | None = None,
) -> dict:
    """Refuse unsafe/stale conditions; record preflight_ok when clean."""
    workspace = resolve_workspace(workspace)
    contract = load_contract(contract_path)
    check_contract_paths(contract, workspace)
    validate_caps(contract.caps)

    try:
        with hold_workspace_lease(workspace, holder="preflight"):
            return _preflight_under_lease(contract=contract, workspace=workspace, now=now)
    except LeaseError as exc:
        raise PreflightError(str(exc)) from exc


def _preflight_under_lease(
    *,
    contract: Contract,
    workspace: Path,
    now: float | None,
) -> dict:
    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    ts = time.time() if now is None else now

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

    if contract.contract_hash != approval["contract_hash"]:
        raise PreflightError("changed provenance: contract hash drift")
    if source_hash != approval["source_hash"]:
        raise PreflightError("changed provenance: source hash drift")

    check_outputs_absent(workspace, contract)
    check_predecessor(workspace, contract)

    state = load_state(state_dir)
    phase = state.get("phase")
    if phase in {"running", "completed", "failed", "postflighted"}:
        raise PreflightError(f"run already in phase={phase!r}; refuse re-entry")

    result = {
        "ok": True,
        "campaign_id": contract.campaign_id,
        "run_id": contract.run_id,
        "contract_hash": contract.contract_hash,
        "source_hash": source_hash,
        "runtime": runtime,
        "approval_expires_at_unix": approval["expires_at_unix"],
    }
    log = EventLog.for_state_dir(state_dir)
    log.append("preflight_ok", result)
    update_state(
        state_dir,
        phase="preflighted",
        campaign_id=contract.campaign_id,
        run_id=contract.run_id,
        contract_hash=contract.contract_hash,
        source_hash=source_hash,
        runtime=runtime,
        preflight_at_unix=ts,
    )
    return result
