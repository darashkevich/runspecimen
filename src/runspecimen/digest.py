"""Read-only receipt digest and field diff.

Neither command rechecks the event chain, live provenance, or signatures.
Use ``verify`` for that. A diff that finds differences still exits 0: the
report is the result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runspecimen.certificate import load_certificate
from runspecimen.errors import CertificateError
from runspecimen.hashutil import sha256_file
from runspecimen.paths import ensure_within, resolve_workspace, run_state_dir
from runspecimen.schema import assert_supported_receipt_schema

_META_KEYS = frozenset({"kind", "note", "live_verification"})


def load_recorded_receipt(workspace: Path, campaign_id: str, run_id: str) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    state_dir = run_state_dir(workspace, campaign_id, run_id)
    cert = load_certificate(state_dir)
    if cert is None:
        raise CertificateError(f"certificate not found for {campaign_id}/{run_id}")
    assert_supported_receipt_schema(cert)
    return cert


def summarize_receipt(cert: dict[str, Any]) -> dict[str, Any]:
    runtime = cert.get("runtime")
    runtime_id = runtime.get("runtime_id") if isinstance(runtime, dict) else None
    summary: dict[str, Any] = {
        "kind": "receipt_digest",
        "live_verification": False,
        "note": "Recorded certificate fields only. This is not runspecimen verify.",
        "campaign_id": cert.get("campaign_id"),
        "certificate_id": cert.get("certificate_id"),
        "contract_hash": cert.get("contract_hash"),
        "event_head": cert.get("event_head"),
        "exit_code": cert.get("exit_code"),
        "issued_at": cert.get("issued_at"),
        "output_digests": cert.get("output_digests") if isinstance(cert.get("output_digests"), dict) else {},
        "run_id": cert.get("run_id"),
        "run_result": cert.get("run_result"),
        "runtime_id": runtime_id,
        "schema_version": cert.get("schema_version", 1),
        "source_hash": cert.get("source_hash"),
    }
    for key in ("approver", "isolation", "policy"):
        if key in cert:
            summary[key] = cert[key]
    return summary


def live_output_rows(workspace: Path, cert: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare recorded output digests to files currently in the workspace."""
    workspace = resolve_workspace(workspace)
    digests = cert.get("output_digests")
    if not isinstance(digests, dict):
        raise CertificateError("certificate output_digests missing or invalid")
    rows: list[dict[str, Any]] = []
    for rel, expected in sorted(digests.items()):
        if not isinstance(rel, str) or not isinstance(expected, str):
            raise CertificateError("invalid output_digests entry")
        path = ensure_within(workspace, Path(rel), label=f"output {rel!r}")
        if not path.is_file():
            rows.append({"live": None, "path": rel, "recorded": expected, "status": "missing"})
            continue
        live = sha256_file(path)
        rows.append(
            {
                "live": live,
                "path": rel,
                "recorded": expected,
                "status": "match" if live == expected else "differs",
            }
        )
    return rows


def diff_summaries(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    keys = sorted((set(left) | set(right)) - _META_KEYS)
    changed = []
    for key in keys:
        if left.get(key) != right.get(key):
            changed.append({"field": key, "left": left.get(key), "right": right.get(key)})
    return {
        "kind": "receipt_diff",
        "live_verification": False,
        "note": "Field diff of two recorded digests. This is not runspecimen verify.",
        "identical": not changed,
        "changed": changed,
        "left": {"campaign_id": left.get("campaign_id"), "run_id": left.get("run_id")},
        "right": {"campaign_id": right.get("campaign_id"), "run_id": right.get("run_id")},
    }
