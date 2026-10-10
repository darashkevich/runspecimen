"""Contract and receipt schema version constants and checks."""

from __future__ import annotations

from typing import Any

from runspecimen.errors import CertificateError, ContractError

CURRENT_CONTRACT_VERSION = 1
SUPPORTED_CONTRACT_VERSIONS = frozenset({1})

CURRENT_RECEIPT_SCHEMA_VERSION = 2
SUPPORTED_RECEIPT_SCHEMA_VERSIONS = frozenset({1, 2})

# Top-level certificate.json keys. Unknown extras fail verify (BH-05).
CERTIFICATE_KNOWN_KEYS = frozenset(
    {
        "approval_expires_at_unix",
        "approver",
        "campaign_id",
        "certificate_id",
        "confirm_channel",
        "contract_hash",
        "event_head",
        "evidence_attestation",
        "exit_code",
        "isolation",
        "issued_at",
        "output_digests",
        "policy",
        "run_id",
        "run_result",
        "runtime",
        "schema_version",
        "source_hash",
    }
)

_COMPAT_DOC = "docs/SCHEMA_COMPATIBILITY.md"


def assert_supported_contract_version(version: int) -> None:
    """Fail closed on unsupported contract versions."""
    if version not in SUPPORTED_CONTRACT_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_CONTRACT_VERSIONS))
        raise ContractError(
            f"unsupported contract version: {version} "
            f"(supported: {supported}; see {_COMPAT_DOC} for migration rules)"
        )


def normalize_receipt_schema_version(cert: dict[str, Any]) -> int:
    """Return the effective receipt schema version (absent → legacy 1)."""
    if "schema_version" not in cert:
        return 1
    raw = cert["schema_version"]
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise CertificateError(
            "certificate schema_version must be a JSON integer "
            f"(see {_COMPAT_DOC} for migration rules)"
        )
    return raw


def assert_supported_receipt_schema(cert: dict[str, Any]) -> int:
    """Fail closed on unsupported receipt schema versions. Returns effective version."""
    version = normalize_receipt_schema_version(cert)
    if version not in SUPPORTED_RECEIPT_SCHEMA_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_RECEIPT_SCHEMA_VERSIONS))
        raise CertificateError(
            f"unsupported receipt schema_version: {version} "
            f"(supported: {supported}; legacy certificates omit the field and "
            f"are treated as 1; see {_COMPAT_DOC} for migration rules)"
        )
    return version


def certificate_id_material(cert: dict[str, Any]) -> dict[str, Any]:
    """Fields bound into certificate_id (schema_version only when present)."""
    material: dict[str, Any] = {
        "approval_expires_at_unix": cert.get("approval_expires_at_unix"),
        "campaign_id": cert["campaign_id"],
        "contract_hash": cert["contract_hash"],
        "event_head": cert["event_head"],
        "exit_code": cert.get("exit_code"),
        "issued_at": cert["issued_at"],
        "output_digests": cert["output_digests"],
        "run_id": cert["run_id"],
        "run_result": cert.get("run_result"),
        "runtime": cert["runtime"],
        "source_hash": cert["source_hash"],
    }
    if "schema_version" in cert:
        material["schema_version"] = cert["schema_version"]
    # Optional Phase 2–5 fields plus confirm_channel. Omitted keys stay out of
    # the hash so historical receipts that never recorded them still recompute
    # certificate_id; verify still refuses those receipts unless a bound
    # approval event or holder receipt is present.
    for key in ("approver", "isolation", "policy", "evidence_attestation", "confirm_channel"):
        if key in cert:
            material[key] = cert[key]
    return material


def assert_certificate_known_keys(cert: dict[str, Any]) -> None:
    """Fail closed on unknown top-level certificate.json fields."""
    extra = sorted(set(cert) - CERTIFICATE_KNOWN_KEYS)
    if extra:
        raise CertificateError(
            "certificate contains unknown field(s): " + ", ".join(extra)
        )
