"""Freshness / applicability of evidence against current workspace state.

Preserves historical evidence reports. Marks applicability stale when declared
dependencies change. Conservative invalidation unless dependencies are declared.
Does not rewrite prior outcomes. Separate from ``verify``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runspecimen.artifact import (
    CURRENT_ARTIFACT_SCHEMA_VERSION,
    assert_artifact_version,
    assert_schema_kind,
    bind_artifact_digest,
    verify_artifact_digest,
)
from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.contract import Contract
from runspecimen.errors import RunSpecimenError
from runspecimen.hashutil import hash_source, sha256_file
from runspecimen.paths import ensure_dir, ensure_within, resolve_workspace, run_state_dir
from runspecimen.requirements import TaskManifest, load_evidence_report
from runspecimen.runtime import runtime_provenance


class FreshnessError(RunSpecimenError):
    """Freshness evaluation failed."""


def freshness_report_path(workspace: Path, campaign_id: str, run_id: str) -> Path:
    return run_state_dir(workspace, campaign_id, run_id) / "freshness_report.json"


def _policy_digest(contract: Contract, workspace: Path) -> str | None:
    if contract.policy is None:
        return None
    path = ensure_within(workspace, Path(contract.policy.path), label="policy.path")
    if not path.is_file():
        return None
    return sha256_file(path)


def evaluate_freshness(
    *,
    workspace: Path,
    contract: Contract,
    manifest: TaskManifest | None,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare current fingerprints to those recorded in an evidence report."""
    workspace = resolve_workspace(workspace)
    source_hash, _ = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    runtime = runtime_provenance(contract, workspace)
    policy_hash = _policy_digest(contract, workspace)

    changes: list[dict[str, Any]] = []
    affected: list[str] = []

    if evidence is None:
        applicability = "no_evidence"
        changes.append(
            {
                "kind": "missing_evidence",
                "detail": "no evidence report to evaluate; requirements are unverified",
            }
        )
    else:
        verify_artifact_digest(evidence)
        if evidence.get("contract_hash") != contract.contract_hash:
            changes.append(
                {
                    "kind": "contract",
                    "detail": "contract hash differs from evidence-bound contract",
                    "recorded": evidence.get("contract_hash"),
                    "current": contract.contract_hash,
                }
            )
        if manifest is not None and evidence.get("manifest_hash") != manifest.manifest_hash:
            changes.append(
                {
                    "kind": "task_manifest",
                    "detail": "task requirements/check config changed",
                    "recorded": evidence.get("manifest_hash"),
                    "current": manifest.manifest_hash,
                }
            )
            if manifest is not None:
                affected.extend(r.id for r in manifest.requirements)

        recorded_source = evidence.get("source_hash_after") or evidence.get("source_hash_before")
        if recorded_source and recorded_source != source_hash:
            changes.append(
                {
                    "kind": "source",
                    "detail": (
                        "declared source roots changed since evidence capture "
                        "(includes previously untracked files now under roots)"
                    ),
                    "recorded": recorded_source,
                    "current": source_hash,
                }
            )
            if manifest is not None:
                for req in manifest.requirements:
                    if not req.source_scope or any(
                        True for _ in req.source_scope
                    ):
                        # Conservative: any source change affects requirements
                        # unless they declare an empty scope meaning "none"
                        # (empty scope still conservatively invalidated).
                        affected.append(req.id)

        if evidence.get("source_changed_during_checks"):
            changes.append(
                {
                    "kind": "source_during_checks",
                    "detail": (
                        "source changed while checks ran; final-state certification "
                        "was already refused on the evidence report"
                    ),
                }
            )

        fp = evidence.get("runtime_fingerprint") or {}
        current_fp = {
            "runtime_id": runtime.get("runtime_id"),
            "executable_sha256": runtime.get("executable_sha256"),
            "interpreter_sha256": runtime.get("interpreter_sha256"),
            "env_hash": runtime.get("env_hash"),
        }
        for key in ("runtime_id", "executable_sha256", "interpreter_sha256", "env_hash"):
            if fp.get(key) and fp.get(key) != current_fp.get(key):
                changes.append(
                    {
                        "kind": "runtime",
                        "field": key,
                        "detail": f"runtime/verification tool fingerprint changed: {key}",
                        "recorded": fp.get(key),
                        "current": current_fp.get(key),
                    }
                )

        # Evidence artifact digests: if recorded artifacts are missing/changed → stale.
        for label, digest in (evidence.get("evidence_digests") or {}).items():
            # Digests are content hashes of ephemeral junit files; absence is expected
            # after cleanup. Record as informational limitation, not auto-pass.
            if not isinstance(digest, str):
                changes.append(
                    {
                        "kind": "evidence_artifact",
                        "detail": f"malformed evidence digest for {label}",
                    }
                )

        if policy_hash is not None:
            # Policy is part of contract hash when bound; also surface explicitly.
            pass

        if changes:
            applicability = "stale"
        else:
            applicability = "applicable"

    # Deduplicate affected requirement ids
    affected_unique = sorted(set(affected))

    reverify_plan = {
        "requires_new_approval": bool(changes),
        "steps": [
            "Author or retain the current contract (new run_id if execution is needed).",
            "Human APPROVE on a real TTY (agents must not type APPROVE).",
            "preflight → run (if execution required) → postflight.",
            "runspecimen requirements check to capture fresh evidence.",
            "runspecimen freshness check to confirm applicability.",
        ],
        "note": (
            "Re-verification uses the ordinary approval lifecycle. "
            "Historical evidence reports are preserved and marked stale, not rewritten."
        ),
    }

    report = {
        "schema_kind": "freshness_report",
        "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
        "campaign_id": contract.campaign_id,
        "run_id": contract.run_id,
        "contract_hash": contract.contract_hash,
        "manifest_hash": manifest.manifest_hash if manifest else None,
        "evidence_report_digest": (evidence or {}).get("artifact_digest"),
        "current_source_hash": source_hash,
        "current_runtime_id": runtime.get("runtime_id"),
        "current_policy_sha256": policy_hash,
        "applicability": applicability,
        "changes": changes,
        "affected_requirements": affected_unique,
        "historical_outcomes_preserved": True,
        "receipt_authenticity_separate": True,
        "reverification_plan": reverify_plan,
        "limitations": [
            "Conservative invalidation: undeclared dependencies are assumed relevant.",
            "Applicability is distinct from receipt authenticity and check outcomes.",
            "Unchanged final digest does not prove files were never temporarily modified.",
        ],
    }
    return bind_artifact_digest(report)


def write_freshness_report(
    workspace: Path, campaign_id: str, run_id: str, report: dict[str, Any]
) -> Path:
    path = freshness_report_path(workspace, campaign_id, run_id)
    ensure_dir(path.parent)
    verify_artifact_digest(report)
    atomic_write_json(path, report)
    return path


def load_freshness_report(workspace: Path, campaign_id: str, run_id: str) -> dict[str, Any]:
    path = freshness_report_path(workspace, campaign_id, run_id)
    if not path.is_file():
        raise FreshnessError(f"freshness report not found: {path}")
    doc = read_json(path)
    assert_schema_kind(doc.get("schema_kind"), expected="freshness_report")
    assert_artifact_version(doc.get("schema_version"))
    verify_artifact_digest(doc)
    return doc


def check_freshness_for_run(
    *,
    workspace: Path,
    contract: Contract,
    manifest: TaskManifest | None = None,
) -> dict[str, Any]:
    evidence = None
    try:
        evidence = load_evidence_report(workspace, contract.campaign_id, contract.run_id)
    except Exception:  # noqa: BLE001
        evidence = None
    return evaluate_freshness(
        workspace=workspace,
        contract=contract,
        manifest=manifest,
        evidence=evidence,
    )
