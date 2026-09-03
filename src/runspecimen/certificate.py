"""Tamper-evident run certificates and strict verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.contract import Contract
from runspecimen.errors import CertificateError
from runspecimen.events import EventLog, utc_now_iso
from runspecimen.hashutil import canonical_json_bytes, hash_source, sha256_bytes, sha256_file
from runspecimen.paths import CERTIFICATE_FILENAME, STATE_FILENAME, ensure_within, run_state_dir
from runspecimen.state import load_state
from runspecimen.runtime import runtime_provenance


def certificate_path(state_dir: Path) -> Path:
    return state_dir / CERTIFICATE_FILENAME


def load_certificate(state_dir: Path) -> dict[str, Any] | None:
    path = certificate_path(state_dir)
    if not path.exists():
        return None
    return read_json(path)


def write_certificate(state_dir: Path, cert: dict[str, Any]) -> None:
    atomic_write_json(certificate_path(state_dir), cert)


def build_certificate(
    *,
    contract: Contract,
    state: dict[str, Any],
    source_hash: str,
    output_digests: dict[str, str],
    event_head: str,
    approval: dict[str, Any] | None,
    runtime: dict[str, Any],
) -> dict[str, Any]:
    body = {
        "approval_expires_at_unix": (approval or {}).get("expires_at_unix"),
        "campaign_id": contract.campaign_id,
        "contract_hash": contract.contract_hash,
        "event_head": event_head,
        "exit_code": state.get("exit_code"),
        "issued_at": utc_now_iso(),
        "output_digests": dict(sorted(output_digests.items())),
        "run_id": contract.run_id,
        "run_result": state.get("run_result"),
        "source_hash": source_hash,
        "runtime": runtime,
    }
    certificate_id = sha256_bytes(canonical_json_bytes(body))
    return {"certificate_id": certificate_id, **body}


def _recompute_certificate_id(cert: dict[str, Any]) -> str:
    material = {
        "approval_expires_at_unix": cert.get("approval_expires_at_unix"),
        "campaign_id": cert["campaign_id"],
        "contract_hash": cert["contract_hash"],
        "event_head": cert["event_head"],
        "exit_code": cert.get("exit_code"),
        "issued_at": cert["issued_at"],
        "output_digests": cert["output_digests"],
        "run_id": cert["run_id"],
        "run_result": cert.get("run_result"),
        "source_hash": cert["source_hash"],
        "runtime": cert["runtime"],
    }
    return sha256_bytes(canonical_json_bytes(material))


def _verify_issuance_ordering(log: EventLog, cert: dict[str, Any]) -> None:
    records = log.read_all()
    if not records:
        raise CertificateError("event log empty; missing certificate issuance events")

    assertions_idx = None
    for i, rec in enumerate(records):
        if rec.type == "postflight_assertions_ok" and rec.event_hash == cert["event_head"]:
            assertions_idx = i
            break
    if assertions_idx is None:
        raise CertificateError(
            "certificate event_head does not match a postflight_assertions_ok event"
        )

    if assertions_idx + 1 >= len(records):
        raise CertificateError("missing certificate_issued event after postflight_assertions_ok")

    issued = records[assertions_idx + 1]
    if issued.type != "certificate_issued":
        raise CertificateError(
            f"expected certificate_issued immediately after assertions_ok, got {issued.type!r}"
        )
    if issued.body.get("certificate_id") != cert["certificate_id"]:
        raise CertificateError("certificate_issued event certificate_id mismatch")
    if issued.body.get("event_head") != cert["event_head"]:
        raise CertificateError("certificate_issued event event_head mismatch")

    final_issued = None
    for rec in records:
        if (
            rec.type == "certificate_issued"
            and rec.body.get("certificate_id") == cert["certificate_id"]
        ):
            final_issued = rec
    if final_issued is None:
        raise CertificateError("no matching certificate_issued event")
    if records[-1].event_hash != final_issued.event_hash:
        raise CertificateError("final event is not the matching certificate_issued event")
    if final_issued.event_hash != issued.event_hash:
        raise CertificateError("certificate issuance ordering fork detected")


def _verify_live_outputs(workspace: Path, cert: dict[str, Any]) -> None:
    digests = cert.get("output_digests")
    if not isinstance(digests, dict):
        raise CertificateError("certificate output_digests missing or invalid")
    for rel, expected in digests.items():
        if not isinstance(rel, str) or not isinstance(expected, str):
            raise CertificateError("invalid output_digests entry")
        path = ensure_within(workspace, Path(rel), label=f"output {rel!r}")
        if not path.is_file():
            raise CertificateError(f"recorded output missing on disk: {rel}")
        live = sha256_file(path)
        if live != expected:
            raise CertificateError(
                f"live output digest mismatch for {rel}: expected {expected}, got {live}"
            )


def verify_run_receipt(
    *,
    workspace: Path,
    campaign_id: str,
    run_id: str,
    contract: Contract | None = None,
    require_live_provenance: bool = False,
) -> dict[str, Any]:
    """Strict verification of a postflighted run receipt.

    Always checks: certificate integrity, state identity/phase, event chain,
    assertions_ok→certificate_issued ordering, and live output digests.

    When require_live_provenance is True, contract must be provided and current
    contract/source hashes are rehashed and compared to the certificate/state.
    """
    workspace = workspace.resolve()
    state_dir = run_state_dir(workspace, campaign_id, run_id)

    if not (state_dir / STATE_FILENAME).exists():
        raise CertificateError("state.json missing (deleted or never written)")

    cert = load_certificate(state_dir)
    if cert is None:
        raise CertificateError("certificate not found")

    required = [
        "certificate_id",
        "campaign_id",
        "run_id",
        "contract_hash",
        "source_hash",
        "event_head",
        "output_digests",
        "issued_at",
        "runtime",
    ]
    for key in required:
        if key not in cert:
            raise CertificateError(f"certificate missing field: {key}")

    if _recompute_certificate_id(cert) != cert["certificate_id"]:
        raise CertificateError("certificate_id mismatch (tampered certificate body)")

    if cert["campaign_id"] != campaign_id or cert["run_id"] != run_id:
        raise CertificateError("certificate campaign_id/run_id does not match requested identity")

    state = load_state(state_dir)
    if state.get("phase") != "postflighted":
        raise CertificateError(f"state phase must be postflighted, got {state.get('phase')!r}")

    for field in ("campaign_id", "run_id", "contract_hash", "source_hash", "certificate_id"):
        if state.get(field) != cert[field]:
            raise CertificateError(f"state {field} does not match certificate")

    if state.get("campaign_id") != campaign_id or state.get("run_id") != run_id:
        raise CertificateError("state campaign_id/run_id does not match requested identity")

    log = EventLog.for_state_dir(state_dir)
    ok, msg = log.verify_chain()
    if not ok:
        raise CertificateError(f"event log chain invalid: {msg}")

    _verify_issuance_ordering(log, cert)
    _verify_live_outputs(workspace, cert)

    if require_live_provenance:
        if contract is None:
            raise CertificateError("live provenance verification requires a contract")
        if contract.campaign_id != campaign_id or contract.run_id != run_id:
            raise CertificateError("contract identity does not match campaign_id/run_id")
        if contract.contract_hash != cert["contract_hash"]:
            raise CertificateError(
                f"current contract hash mismatch: live={contract.contract_hash} "
                f"cert={cert['contract_hash']}"
            )
        if state.get("contract_hash") != contract.contract_hash:
            raise CertificateError("state contract_hash does not match live contract")
        live_source, _ = hash_source(
            workspace, list(contract.source.roots), list(contract.source.excludes)
        )
        if live_source != cert["source_hash"]:
            raise CertificateError(
                f"current source hash mismatch: live={live_source} cert={cert['source_hash']}"
            )
        if state.get("source_hash") != live_source:
            raise CertificateError("state source_hash does not match live source")
        live_runtime = runtime_provenance(contract, workspace)
        if live_runtime.get("runtime_id") != cert["runtime"].get("runtime_id"):
            raise CertificateError("current runtime provenance does not match certificate")
        if state.get("runtime", {}).get("runtime_id") != live_runtime.get("runtime_id"):
            raise CertificateError("state runtime provenance does not match live runtime")

    return {
        "ok": True,
        "certificate_id": cert["certificate_id"],
        "event_chain": msg,
        "event_head": cert["event_head"],
        "campaign_id": campaign_id,
        "run_id": run_id,
    }


def verify_certificate(
    state_dir: Path,
    *,
    workspace: Path | None = None,
    contract: Contract | None = None,
    require_live_provenance: bool = False,
    campaign_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Wrapper around verify_run_receipt; infers workspace from state_dir when omitted."""
    state_dir = state_dir.resolve()
    if workspace is None:
        # state_dir = ws/.runspecimen/runs/{camp}/{run}
        if len(state_dir.parents) < 4 or state_dir.parents[2].name != ".runspecimen":
            raise CertificateError("cannot infer workspace from state_dir")
        workspace = state_dir.parents[3]

    state = load_state(state_dir)
    camp = campaign_id or state.get("campaign_id")
    rid = run_id or state.get("run_id")
    if not camp or not rid:
        cert = load_certificate(state_dir)
        if cert is None:
            raise CertificateError("certificate not found and state lacks identity")
        camp = camp or cert["campaign_id"]
        rid = rid or cert["run_id"]
    return verify_run_receipt(
        workspace=workspace,
        campaign_id=str(camp),
        run_id=str(rid),
        contract=contract,
        require_live_provenance=require_live_provenance,
    )
