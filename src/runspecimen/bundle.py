"""Local incident bundle export (Community). Team sharing/retention is out of band."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runspecimen.approve import load_approval
from runspecimen.certificate import load_certificate, verify_run_receipt
from runspecimen.contract import load_contract
from runspecimen.errors import CertificateError, RunSpecimenError
from runspecimen.events import EventLog
from runspecimen.paths import (
    APPROVAL_FILENAME,
    CERTIFICATE_FILENAME,
    EVENTS_FILENAME,
    STATE_FILENAME,
    ensure_dir,
    resolve_workspace,
    run_state_dir,
)
from runspecimen.state import load_state


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _copy_if_present(src: Path, dest: Path) -> bool:
    if not src.is_file():
        return False
    shutil.copy2(src, dest)
    return True


def _refusal_extract(state_dir: Path) -> list[dict[str, Any]]:
    log = EventLog.for_state_dir(state_dir)
    if not log.path.exists():
        return []
    out: list[dict[str, Any]] = []
    for rec in log.read_all():
        if rec.type in {"remote_confirm_refused", "launch_refused", "preflight_refused"}:
            out.append(rec.to_dict())
        elif rec.type.endswith("_refused") or rec.type == "refusal":
            out.append(rec.to_dict())
    return out


def confirm_channel_from_state_dir(state_dir: Path) -> str | None:
    approval = load_approval(state_dir)
    if isinstance(approval, dict) and approval.get("confirm_channel"):
        return str(approval["confirm_channel"])
    log = EventLog.for_state_dir(state_dir)
    if not log.path.exists():
        return None
    for rec in reversed(log.read_all()):
        if rec.type == "approval" and rec.body.get("confirm_channel"):
            return str(rec.body["confirm_channel"])
    return None


def assert_retention_destination(workspace: Path, out_dir: Path) -> Path:
    """Refuse a destination that resolves inside the workspace."""
    workspace = resolve_workspace(workspace)
    dest = Path(out_dir).expanduser()
    if not dest.is_absolute():
        dest = (Path.cwd() / dest).resolve()
    else:
        dest = dest.resolve()
    if dest == workspace or _is_inside(dest, workspace):
        raise RunSpecimenError(
            "retain destination must be outside the workspace; "
            "use bundle for a pack inside the workspace"
        )
    return dest


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def retain_incident_bundle(
    *,
    workspace: Path,
    campaign_id: str,
    run_id: str,
    out_dir: Path,
    contract_path: Path | None = None,
    include_chain: bool = False,
) -> dict[str, Any]:
    dest = assert_retention_destination(workspace, out_dir)
    manifest = write_incident_bundle(
        workspace=workspace,
        campaign_id=campaign_id,
        run_id=run_id,
        out_dir=dest,
        contract_path=contract_path,
        include_chain=include_chain,
    )
    manifest["kind"] = "retained_incident_bundle"
    manifest["retention"] = "local_directory"
    manifest["note"] = (
        "Local copy outside the workspace. No upload and no retention service."
    )
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def write_incident_bundle(
    *,
    workspace: Path,
    campaign_id: str,
    run_id: str,
    out_dir: Path,
    contract_path: Path | None = None,
    include_chain: bool = False,
    _seen: frozenset[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    state_dir = run_state_dir(workspace, campaign_id, run_id)
    has_state = (state_dir / STATE_FILENAME).exists()
    has_events = (state_dir / EVENTS_FILENAME).exists()
    if not has_state and not has_events:
        raise RunSpecimenError(f"no run state for {campaign_id}/{run_id}")

    dest = Path(out_dir)
    ensure_dir(dest)
    files: list[str] = []
    for name in (STATE_FILENAME, EVENTS_FILENAME, APPROVAL_FILENAME, CERTIFICATE_FILENAME):
        if _copy_if_present(state_dir / name, dest / name):
            files.append(name)

    refusals = _refusal_extract(state_dir)
    if refusals:
        (dest / "refusals.json").write_text(
            json.dumps(refusals, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        files.append("refusals.json")

    channel = confirm_channel_from_state_dir(state_dir)
    verify_doc: dict[str, Any] | None = None
    state = load_state(state_dir)
    if state.get("phase") == "postflighted":
        contract = load_contract(contract_path) if contract_path is not None else None
        try:
            verify_doc = verify_run_receipt(
                workspace=workspace,
                campaign_id=campaign_id,
                run_id=run_id,
                contract=contract,
                require_live_provenance=contract is not None,
            )
        except CertificateError as exc:
            verify_doc = {"ok": False, "error": str(exc)}
        (dest / "verify.json").write_text(
            json.dumps(verify_doc, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        files.append("verify.json")

    if include_chain:
        seen = set(_seen or ())
        seen.add((campaign_id, run_id))
        pred_campaign = None
        pred_run = None
        if contract_path is not None:
            contract = load_contract(contract_path)
            if contract.predecessor is not None:
                pred_campaign = contract.predecessor.campaign_id
                pred_run = contract.predecessor.run_id
        pred = state.get("predecessor")
        if isinstance(pred, dict):
            pred_campaign = pred.get("campaign_id") or pred_campaign
            pred_run = pred.get("run_id") or pred_run
        if pred_campaign and pred_run and (pred_campaign, pred_run) not in seen:
            pred_dir = dest / "predecessors" / str(pred_campaign) / str(pred_run)
            write_incident_bundle(
                workspace=workspace,
                campaign_id=str(pred_campaign),
                run_id=str(pred_run),
                out_dir=pred_dir,
                contract_path=None,
                include_chain=True,
                _seen=frozenset(seen),
            )
            files.append(f"predecessors/{pred_campaign}/{pred_run}/")

    cert = load_certificate(state_dir)
    manifest = {
        "product": "RunSpecimen",
        "kind": "incident_bundle",
        "schema_version": 1,
        "campaign_id": campaign_id,
        "run_id": run_id,
        "created_at": _utc_now(),
        "phase": state.get("phase"),
        "confirm_channel": channel,
        "certificate_id": cert.get("certificate_id") if cert else None,
        "not_a_compliance_product": True,
        "files": files,
        "note": "Local evidence pack. History on disk stays free. Not a Veto vault.",
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest
