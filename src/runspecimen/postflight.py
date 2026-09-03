"""Postflight assertions and certificate issuance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runspecimen.approve import load_approval
from runspecimen.certificate import build_certificate, write_certificate
from runspecimen.contract import check_contract_paths, load_contract
from runspecimen.errors import LeaseError, PostflightError
from runspecimen.events import EventLog
from runspecimen.hashutil import hash_source, sha256_file
from runspecimen.lease import hold_workspace_lease
from runspecimen.paths import ensure_within, resolve_workspace, run_state_dir
from runspecimen.state import load_state, update_state
from runspecimen.runtime import runtime_matches, runtime_provenance


def _dig_field(data: Any, dotted: str) -> Any:
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def postflight(
    *,
    contract_path: Path,
    workspace: Path,
) -> dict:
    workspace = resolve_workspace(workspace)
    contract = load_contract(contract_path)
    check_contract_paths(contract, workspace)

    try:
        with hold_workspace_lease(workspace, holder="postflight"):
            return _postflight_under_lease(contract=contract, workspace=workspace)
    except LeaseError as exc:
        raise PostflightError(str(exc)) from exc


def _postflight_under_lease(*, contract, workspace: Path) -> dict:
    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    state = load_state(state_dir)
    approval = load_approval(state_dir)

    if state.get("phase") not in {"completed", "failed"}:
        raise PostflightError(
            f"postflight requires completed/failed run; phase={state.get('phase')!r}"
        )
    if "exit_code" not in state:
        raise PostflightError("run state missing exit_code")
    if state.get("run_result") != "completed":
        raise PostflightError(
            f"cannot certify orchestration result={state.get('run_result')!r}; "
            "only completed executions are eligible"
        )

    # Exact provenance gate before any outcome assertions.
    if approval is None:
        raise PostflightError("no approval present; cannot verify contract provenance")
    if contract.contract_hash != approval.get("contract_hash"):
        raise PostflightError(
            "current contract hash differs from approval "
            f"(live={contract.contract_hash}, approval={approval.get('contract_hash')})"
        )
    if contract.contract_hash != state.get("contract_hash"):
        raise PostflightError(
            "current contract hash differs from run state "
            f"(live={contract.contract_hash}, state={state.get('contract_hash')})"
        )
    if state.get("campaign_id") != contract.campaign_id or state.get("run_id") != contract.run_id:
        raise PostflightError("run state identity differs from current contract")

    runtime = runtime_provenance(contract, workspace)
    runtime_ok, runtime_reason = runtime_matches(approval, runtime)
    if not runtime_ok:
        raise PostflightError(runtime_reason)
    if state.get("runtime", {}).get("runtime_id") != runtime["runtime_id"]:
        raise PostflightError("runtime provenance differs from run state")

    failures: list[str] = []
    pf = contract.postflight

    actual_exit = state.get("exit_code")
    if actual_exit != pf.exit_code:
        failures.append(f"exit_code: expected {pf.exit_code}, got {actual_exit}")

    output_digests: dict[str, str] = {}
    if pf.require_outputs:
        for rel in contract.outputs_required:
            path = ensure_within(workspace, Path(rel), label=f"output {rel!r}")
            if not path.is_file():
                failures.append(f"required output missing: {rel}")
            else:
                output_digests[rel] = sha256_file(path)

    for rel, expected in pf.output_sha256.items():
        path = ensure_within(workspace, Path(rel), label=f"output_sha256 {rel!r}")
        if not path.is_file():
            failures.append(f"output_sha256 target missing: {rel}")
            continue
        digest = sha256_file(path)
        output_digests[rel] = digest
        if digest != expected:
            failures.append(f"output sha256 mismatch for {rel}: expected {expected}, got {digest}")

    for assertion in pf.json_equals:
        path = ensure_within(
            workspace, Path(assertion.path), label=f"json_equals {assertion.path!r}"
        )
        if not path.is_file():
            failures.append(f"json_equals target missing: {assertion.path}")
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            actual = _dig_field(data, assertion.field)
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            failures.append(f"json_equals {assertion.path}:{assertion.field}: {exc}")
            continue
        if actual != assertion.equals:
            failures.append(
                f"json_equals {assertion.path}:{assertion.field}: "
                f"expected {assertion.equals!r}, got {actual!r}"
            )
        else:
            output_digests[assertion.path] = sha256_file(path)

    source_hash, _ = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    # source_unchanged is required true by contract validation.
    expected_source = approval.get("source_hash")
    if expected_source is None:
        failures.append("source_unchanged: no baseline source_hash in approval")
    elif source_hash != expected_source:
        failures.append(
            f"source changed since approval: expected {expected_source}, got {source_hash}"
        )
    if source_hash != state.get("source_hash"):
        failures.append(
            f"source changed since run: expected {state.get('source_hash')}, got {source_hash}"
        )

    log = EventLog.for_state_dir(state_dir)
    if failures:
        log.append("postflight_failed", {"failures": failures})
        update_state(state_dir, phase="failed", postflight_ok=False, postflight_failures=failures)
        raise PostflightError("; ".join(failures))

    chain_ok, chain_msg = log.verify_chain()
    if not chain_ok:
        raise PostflightError(f"event log chain invalid before certificate: {chain_msg}")

    assertions_body = {
        "contract_hash": contract.contract_hash,
        "exit_code": actual_exit,
        "output_digests": dict(sorted(output_digests.items())),
        "source_hash": source_hash,
        "runtime": runtime,
    }
    assertions_rec = log.append("postflight_assertions_ok", assertions_body)
    cert = build_certificate(
        contract=contract,
        state=state,
        source_hash=source_hash,
        output_digests=output_digests,
        event_head=assertions_rec.event_hash,
        approval=approval,
        runtime=runtime,
    )
    write_certificate(state_dir, cert)
    log.append(
        "certificate_issued",
        {
            "certificate_id": cert["certificate_id"],
            "event_head": cert["event_head"],
            "output_digests": output_digests,
        },
    )
    update_state(
        state_dir,
        phase="postflighted",
        postflight_ok=True,
        campaign_id=contract.campaign_id,
        run_id=contract.run_id,
        contract_hash=contract.contract_hash,
        source_hash=source_hash,
        certificate_id=cert["certificate_id"],
        output_digests=output_digests,
        runtime=runtime,
    )
    return cert
