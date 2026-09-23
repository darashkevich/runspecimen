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
from runspecimen.requirements import TaskManifest, load_evidence_report, load_task_manifest
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


def _resolve_bound_manifest(
    workspace: Path, contract: Contract, manifest: TaskManifest | None
) -> tuple[TaskManifest | None, list[dict[str, Any]]]:
    """Resolve the contract-bound manifest; missing binding is a freshness failure."""
    changes: list[dict[str, Any]] = []
    if contract.task_manifest is None:
        if manifest is None:
            changes.append(
                {
                    "kind": "task_manifest",
                    "detail": (
                        "no task_manifest bound on contract and none supplied; "
                        "missing manifests must not yield applicable"
                    ),
                }
            )
            return None, changes
        return manifest, changes

    try:
        bound_path = ensure_within(
            workspace, Path(contract.task_manifest.path), label="task_manifest.path"
        )
        live = load_task_manifest(bound_path)
    except Exception as exc:  # noqa: BLE001
        changes.append(
            {
                "kind": "task_manifest",
                "detail": f"bound task_manifest could not be loaded: {exc}",
            }
        )
        return None, changes

    if live.manifest_hash != contract.task_manifest.sha256:
        changes.append(
            {
                "kind": "task_manifest",
                "detail": "bound task_manifest bytes differ from contract.task_manifest.sha256",
                "recorded": contract.task_manifest.sha256,
                "current": live.manifest_hash,
            }
        )
    if manifest is not None and manifest.manifest_hash != live.manifest_hash:
        changes.append(
            {
                "kind": "task_manifest",
                "detail": "caller-supplied manifest differs from contract-bound manifest",
                "recorded": live.manifest_hash,
                "current": manifest.manifest_hash,
            }
        )
    return live, changes


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

    resolved_manifest, manifest_changes = _resolve_bound_manifest(
        workspace, contract, manifest
    )
    changes.extend(manifest_changes)

    if evidence is None:
        applicability = "no_evidence"
        changes.append(
            {
                "kind": "missing_evidence",
                "detail": "no evidence report to evaluate; requirements are unverified",
            }
        )
    else:
        # Strip load-time authenticity annotations (not part of stored digest).
        verify_artifact_digest(
            {
                k: v
                for k, v in evidence.items()
                if k
                not in {
                    "authenticity",
                    "authenticity_binding",
                    "authenticity_note",
                    "approval_present",
                }
            }
        )
        authenticity = evidence.get("authenticity")
        if authenticity and authenticity != "receipt_bound":
            # Unauthenticated historical docs can still be freshness-evaluated,
            # but never reported as currently applicable without authenticity.
            changes.append(
                {
                    "kind": "authenticity",
                    "detail": (
                        "evidence report is unauthenticated "
                        "(checksum is not receipt authenticity)"
                    ),
                    "authenticity": authenticity,
                }
            )

        if evidence.get("contract_hash") != contract.contract_hash:
            changes.append(
                {
                    "kind": "contract",
                    "detail": "contract hash differs from evidence-bound contract",
                    "recorded": evidence.get("contract_hash"),
                    "current": contract.contract_hash,
                }
            )

        if resolved_manifest is None:
            changes.append(
                {
                    "kind": "task_manifest",
                    "detail": "manifest unavailable for freshness comparison",
                }
            )
        else:
            if evidence.get("manifest_hash") != resolved_manifest.manifest_hash:
                changes.append(
                    {
                        "kind": "task_manifest",
                        "detail": "task requirements/check config changed",
                        "recorded": evidence.get("manifest_hash"),
                        "current": resolved_manifest.manifest_hash,
                    }
                )
                affected.extend(r.id for r in resolved_manifest.requirements)

            recorded_inputs = evidence.get("input_fingerprints") or {}
            for req in resolved_manifest.requirements:
                from runspecimen.requirements import _fingerprint_requirement_inputs

                current_fp = _fingerprint_requirement_inputs(workspace, req)
                recorded_fp = recorded_inputs.get(req.id) or {}
                if not recorded_fp:
                    changes.append(
                        {
                            "kind": "inputs",
                            "requirement_id": req.id,
                            "detail": (
                                "evidence lacks input/source_scope fingerprints; "
                                "missing inputs must not yield applicable"
                            ),
                        }
                    )
                    affected.append(req.id)
                    continue
                if current_fp != recorded_fp:
                    changes.append(
                        {
                            "kind": "inputs",
                            "requirement_id": req.id,
                            "detail": "declared inputs or source_scope changed",
                            "recorded": recorded_fp,
                            "current": current_fp,
                        }
                    )
                    affected.append(req.id)
                if any(v == "missing" for v in current_fp.values()):
                    changes.append(
                        {
                            "kind": "inputs",
                            "requirement_id": req.id,
                            "detail": "declared input/source_scope path missing on disk",
                            "current": current_fp,
                        }
                    )
                    affected.append(req.id)

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
            if resolved_manifest is not None:
                affected.extend(r.id for r in resolved_manifest.requirements)

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

        # Rehash durable evidence artifacts when paths were recorded.
        artifact_paths = evidence.get("evidence_artifact_paths") or {}
        for label, digest in (evidence.get("evidence_digests") or {}).items():
            if not isinstance(digest, str):
                changes.append(
                    {
                        "kind": "evidence_artifact",
                        "detail": f"malformed evidence digest for {label}",
                    }
                )
                continue
            rel = artifact_paths.get(label)
            if not isinstance(rel, str) or not rel:
                # Ephemeral provider digests (temp junit/stream) cannot be rehashed;
                # recorded in limitations, not treated as proof of freshness.
                continue
            try:
                path = ensure_within(workspace, Path(rel), label=f"evidence:{label}")
            except Exception as exc:  # noqa: BLE001
                changes.append(
                    {
                        "kind": "evidence_artifact",
                        "detail": f"evidence artifact path invalid for {label}: {exc}",
                    }
                )
                continue
            if not path.is_file():
                changes.append(
                    {
                        "kind": "evidence_artifact",
                        "detail": f"evidence artifact missing for {label}",
                        "path": rel,
                        "recorded": digest,
                    }
                )
                continue
            live = sha256_file(path)
            if live != digest.lower():
                changes.append(
                    {
                        "kind": "evidence_artifact",
                        "detail": f"evidence artifact changed for {label}",
                        "path": rel,
                        "recorded": digest,
                        "current": live,
                    }
                )

        recorded_policy = evidence.get("policy_sha256")
        if contract.policy is not None:
            if policy_hash is None:
                changes.append(
                    {
                        "kind": "policy",
                        "detail": "policy file missing; cannot confirm policy freshness",
                    }
                )
            else:
                if recorded_policy and recorded_policy != policy_hash:
                    changes.append(
                        {
                            "kind": "policy",
                            "detail": "policy file bytes changed since evidence capture",
                            "recorded": recorded_policy,
                            "current": policy_hash,
                        }
                    )
                elif contract.policy.sha256 != policy_hash:
                    changes.append(
                        {
                            "kind": "policy",
                            "detail": "live policy file does not match contract.policy.sha256",
                            "recorded": contract.policy.sha256,
                            "current": policy_hash,
                        }
                    )
        elif recorded_policy:
            changes.append(
                {
                    "kind": "policy",
                    "detail": "evidence recorded a policy hash but contract has no policy",
                    "recorded": recorded_policy,
                }
            )

        if changes:
            applicability = "stale"
        else:
            applicability = "applicable"

    # Deduplicate affected requirement ids
    affected_unique = sorted(set(affected))

    reverify_plan = {
        "requires_new_approval": bool(changes),
        "steps": [
            "Author or retain the current contract with task_manifest bound (new run_id if execution is needed).",
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
        "manifest_hash": resolved_manifest.manifest_hash if resolved_manifest else None,
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
            "Missing inputs or manifests never yield applicable.",
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
