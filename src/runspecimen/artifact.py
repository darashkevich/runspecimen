"""Shared versioned artifact digests for evidence-layer documents.

Every expansion artifact (manifest, evidence report, freshness report, …) carries
``schema_kind``, ``schema_version``, and an ``artifact_digest`` over canonical
JSON of the body excluding the digest field itself. Unsupported versions fail
closed. See docs/ADR-005-evidence-expansion.md.
"""

from __future__ import annotations

from typing import Any

from runspecimen.errors import ContractError
from runspecimen.hashutil import canonical_json_bytes, sha256_bytes

CURRENT_ARTIFACT_SCHEMA_VERSION = 1
SUPPORTED_ARTIFACT_SCHEMA_VERSIONS = frozenset({1})

SCHEMA_KINDS = frozenset(
    {
        "task_manifest",
        "evidence_report",
        "freshness_report",
        "config_bundle",
        "decision",
        "snapshot_record",
        "usage_ledger",
        "coordination_plan",
        "eval_suite",
        "eval_result",
        "evidence_attestation",
    }
)

_COMPAT_DOC = "docs/SCHEMA_COMPATIBILITY.md"


def assert_artifact_version(version: Any, *, label: str = "schema_version") -> int:
    if isinstance(version, bool) or not isinstance(version, int):
        raise ContractError(
            f"{label} must be a JSON integer (see {_COMPAT_DOC})"
        )
    if version not in SUPPORTED_ARTIFACT_SCHEMA_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_ARTIFACT_SCHEMA_VERSIONS))
        raise ContractError(
            f"unsupported {label}: {version} (supported: {supported}; see {_COMPAT_DOC})"
        )
    return version


def assert_schema_kind(kind: Any, *, expected: str | None = None) -> str:
    if not isinstance(kind, str) or not kind:
        raise ContractError("schema_kind must be a non-empty string")
    if kind not in SCHEMA_KINDS:
        raise ContractError(f"unsupported schema_kind: {kind!r}")
    if expected is not None and kind != expected:
        raise ContractError(f"expected schema_kind {expected!r}, got {kind!r}")
    return kind


def material_without_digest(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "artifact_digest"}


def compute_artifact_digest(doc: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(material_without_digest(doc)))


def bind_artifact_digest(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out.pop("artifact_digest", None)
    out["artifact_digest"] = compute_artifact_digest(out)
    return out


def verify_artifact_digest(doc: dict[str, Any]) -> str:
    if "artifact_digest" not in doc:
        raise ContractError("artifact_digest missing")
    recorded = doc["artifact_digest"]
    if not isinstance(recorded, str) or len(recorded) != 64:
        raise ContractError("artifact_digest must be a 64-character SHA-256 hex digest")
    expected = compute_artifact_digest(doc)
    if recorded.lower() != expected:
        raise ContractError(
            f"artifact_digest mismatch: recorded {recorded.lower()}, computed {expected}"
        )
    return expected
