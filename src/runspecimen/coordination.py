"""Bounded cross-repo coordination (first slice: two repos, producer/consumer).

Preserves per-workspace approval. No auto-deploy, unrestricted parallel exec,
auto-merge, or blanket approval. Aggregate readiness from explicit checks and
current evidence only — never agent narrative.
"""

from __future__ import annotations

import json
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
from runspecimen.contract import (
    _object_without_duplicates,
    _reject_unknown,
    _require_dict,
    _require_list,
    _require_str,
    load_contract,
)
from runspecimen.errors import RunSpecimenError
from runspecimen.hashutil import hash_source, sha256_file
from runspecimen.paths import ensure_dir, resolve_workspace, validate_id, workspace_state_root
from runspecimen.freshness import check_freshness_for_run
from runspecimen.requirements import load_evidence_report, load_task_manifest


class CoordinationError(RunSpecimenError):
    """Coordination plan validation or readiness failed."""


_PLAN_FIELDS = {
    "schema_kind",
    "schema_version",
    "id",
    "description",
    "repos",
    "dependencies",
    "compatibility_checks",
    "artifact_digest",
}

_REPO_FIELDS = {
    "id",
    "workspace",
    "contract",
    "manifest",
    "role",  # producer | consumer | peer
}

_DEP_FIELDS = {
    "id",
    "from_repo",
    "to_repo",
    "requires_evidence_outcome",
    "artifact_path",
    "artifact_sha256_field",
}


def coordination_path(workspace: Path, plan_id: str) -> Path:
    return workspace_state_root(workspace) / "coordination" / f"{validate_id(plan_id)}.json"


def parse_coordination_plan(data: dict[str, Any]) -> dict[str, Any]:
    data = _require_dict(data, "coordination_plan")
    _reject_unknown(data, _PLAN_FIELDS, "coordination_plan")
    assert_schema_kind(data.get("schema_kind"), expected="coordination_plan")
    assert_artifact_version(data.get("schema_version"))
    validate_id(_require_str(data.get("id"), "coordination_plan.id"))
    _require_str(data.get("description"), "coordination_plan.description")
    repos = _require_list(data.get("repos"), "coordination_plan.repos")
    if len(repos) < 2:
        raise CoordinationError("coordination_plan.repos must list at least two repos")
    if len(repos) > 2:
        # First slice: two repos only.
        raise CoordinationError(
            "first coordination slice supports exactly two repos "
            "(producer/consumer); refuse larger plans"
        )
    seen: set[str] = set()
    for i, repo in enumerate(repos):
        label = f"repos[{i}]"
        obj = _require_dict(repo, label)
        _reject_unknown(obj, _REPO_FIELDS, label)
        rid = validate_id(_require_str(obj.get("id"), f"{label}.id"))
        if rid in seen:
            raise CoordinationError(f"duplicate repo id: {rid}")
        seen.add(rid)
        _require_str(obj.get("workspace"), f"{label}.workspace")
        _require_str(obj.get("contract"), f"{label}.contract")
        role = _require_str(obj.get("role"), f"{label}.role")
        if role not in {"producer", "consumer", "peer"}:
            raise CoordinationError(f"{label}.role must be producer|consumer|peer")
    deps = _require_list(data.get("dependencies", []), "coordination_plan.dependencies")
    for i, dep in enumerate(deps):
        label = f"dependencies[{i}]"
        obj = _require_dict(dep, label)
        _reject_unknown(obj, _DEP_FIELDS, label)
        validate_id(_require_str(obj.get("id"), f"{label}.id"))
        fr = _require_str(obj.get("from_repo"), f"{label}.from_repo")
        to = _require_str(obj.get("to_repo"), f"{label}.to_repo")
        if fr not in seen or to not in seen:
            raise CoordinationError(f"{label} references unknown repo id")
    if "artifact_digest" in data:
        verify_artifact_digest(data)
    return data


def load_coordination_plan(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise CoordinationError(f"coordination plan not found: {path}")
    data = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_object_without_duplicates,
    )
    plan = parse_coordination_plan(data)
    if "artifact_digest" in plan:
        verify_artifact_digest(plan)
    return plan


def save_coordination_plan(workspace: Path, plan: dict[str, Any]) -> Path:
    plan = bind_artifact_digest(parse_coordination_plan(plan))
    path = coordination_path(workspace, plan["id"])
    ensure_dir(path.parent)
    atomic_write_json(path, plan)
    return path


def evaluate_readiness(plan: dict[str, Any]) -> dict[str, Any]:
    """Aggregate readiness from explicit checks + current evidence (not narrative)."""
    parse_coordination_plan(plan)
    verify_artifact_digest(plan) if "artifact_digest" in plan else None
    if "artifact_digest" not in plan:
        plan = bind_artifact_digest(plan)

    repo_status: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    contracts: dict[str, Any] = {}
    for repo in plan["repos"]:
        ws = resolve_workspace(Path(repo["workspace"]))
        cpath = (ws / repo["contract"]).resolve() if not Path(repo["contract"]).is_absolute() else Path(repo["contract"])
        try:
            contract = load_contract(cpath)
            contracts[repo["id"]] = contract
            evidence = None
            freshness = None
            try:
                evidence = load_evidence_report(ws, contract.campaign_id, contract.run_id)
            except Exception as exc:  # noqa: BLE001
                blockers.append(
                    {
                        "repo": repo["id"],
                        "reason": "missing_or_invalid_evidence",
                        "detail": str(exc),
                    }
                )
            manifest = None
            if repo.get("manifest"):
                mpath = (ws / repo["manifest"]).resolve()
                try:
                    manifest = load_task_manifest(mpath)
                except Exception as exc:  # noqa: BLE001
                    blockers.append(
                        {
                            "repo": repo["id"],
                            "reason": "manifest_error",
                            "detail": str(exc),
                        }
                    )
            if evidence is not None:
                freshness = check_freshness_for_run(
                    workspace=ws, contract=contract, manifest=manifest
                )
                if freshness.get("applicability") != "applicable":
                    blockers.append(
                        {
                            "repo": repo["id"],
                            "reason": "evidence_stale_or_missing",
                            "applicability": freshness.get("applicability"),
                            "changes": freshness.get("changes"),
                        }
                    )
                if evidence.get("aggregate_outcome") != "passed":
                    blockers.append(
                        {
                            "repo": repo["id"],
                            "reason": "requirements_not_passed",
                            "aggregate_outcome": evidence.get("aggregate_outcome"),
                        }
                    )
            repo_status.append(
                {
                    "repo": repo["id"],
                    "role": repo["role"],
                    "workspace": str(ws),
                    "campaign_id": contract.campaign_id,
                    "run_id": contract.run_id,
                    "contract_hash": contract.contract_hash,
                    "evidence_digest": (evidence or {}).get("artifact_digest"),
                    "applicability": (freshness or {}).get("applicability"),
                    "aggregate_outcome": (evidence or {}).get("aggregate_outcome"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            blockers.append(
                {
                    "repo": repo["id"],
                    "reason": "contract_load_failed",
                    "detail": str(exc),
                }
            )
            repo_status.append({"repo": repo["id"], "error": str(exc)})

    # Producer/consumer artifact compatibility
    for dep in plan.get("dependencies") or []:
        producer = next(r for r in plan["repos"] if r["id"] == dep["from_repo"])
        consumer = next(r for r in plan["repos"] if r["id"] == dep["to_repo"])
        p_ws = resolve_workspace(Path(producer["workspace"]))
        artifact_rel = dep.get("artifact_path")
        if not artifact_rel:
            continue
        artifact = p_ws / artifact_rel
        if not artifact.is_file():
            blockers.append(
                {
                    "dependency": dep["id"],
                    "reason": "producer_artifact_missing",
                    "path": artifact_rel,
                }
            )
            continue
        # If consumer evidence referenced producer hash, check invalidation.
        c_contract = contracts.get(consumer["id"])
        if c_contract is None:
            blockers.append(
                {
                    "dependency": dep["id"],
                    "reason": "consumer_contract_unavailable",
                    "path": artifact_rel,
                }
            )
            continue
        try:
            c_ws = resolve_workspace(Path(consumer["workspace"]))
            evidence = load_evidence_report(
                c_ws, c_contract.campaign_id, c_contract.run_id
            )
            # Invalidate consumer readiness when producer artifact changed vs
            # any digest recorded under evidence_digests or a dedicated field.
            live = sha256_file(artifact)
            recorded = None
            for key, digest in (evidence.get("evidence_digests") or {}).items():
                if artifact_rel in key or key.endswith(artifact_rel):
                    recorded = digest
                    break
            expected_outcome = dep.get("requires_evidence_outcome", "passed")
            if evidence.get("aggregate_outcome") != expected_outcome:
                blockers.append(
                    {
                        "dependency": dep["id"],
                        "reason": "consumer_evidence_outcome",
                        "expected": expected_outcome,
                        "actual": evidence.get("aggregate_outcome"),
                    }
                )
            if recorded is None:
                blockers.append(
                    {
                        "dependency": dep["id"],
                        "reason": "producer_artifact_digest_missing",
                        "path": artifact_rel,
                        "detail": (
                            "declared artifact_path has no recorded digest in "
                            "consumer evidence; readiness must not pass silently"
                        ),
                        "current": live,
                    }
                )
            elif recorded != live:
                blockers.append(
                    {
                        "dependency": dep["id"],
                        "reason": "producer_artifact_changed_invalidates_consumer",
                        "recorded": recorded,
                        "current": live,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            blockers.append(
                {
                    "dependency": dep["id"],
                    "reason": "producer_artifact_check_failed",
                    "path": artifact_rel,
                    "detail": str(exc),
                }
            )

    ready = not blockers
    return {
        "plan_id": plan["id"],
        "ready": ready,
        "repos": repo_status,
        "blockers": blockers,
        "prerequisites": [
            "Each participating workspace requires its own human approval before execution.",
            "No auto-deploy, auto-merge, or blanket multi-repo approval.",
        ],
        "note": (
            "Readiness is aggregated from explicit checks and current evidence only. "
            "Agent narrative is ignored."
        ),
    }
