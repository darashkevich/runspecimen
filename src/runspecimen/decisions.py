"""Decision provenance registry (explicit capture only).

Not execution authority. Does not harvest chats or sync secrets. Flag for review
when referenced inputs change. History is append-only with supersession links.
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
)
from runspecimen.errors import RunSpecimenError
from runspecimen.events import utc_now_iso
from runspecimen.hashutil import sha256_file
from runspecimen.paths import ensure_dir, ensure_within, resolve_workspace, validate_id, workspace_state_root


class DecisionError(RunSpecimenError):
    """Decision registry validation failed."""


_DECISION_FIELDS = {
    "schema_kind",
    "schema_version",
    "id",
    "rationale",
    "source_refs",
    "affected_requirements",
    "affected_files",
    "affected_policies",
    "affected_contracts",
    "classification",  # human | agent
    "captured_at",
    "captured_by",
    "stale_when",
    "supersedes",
    "artifact_digest",
}

_CLASSIFICATIONS = frozenset({"human", "agent"})


def decisions_dir(workspace: Path) -> Path:
    return workspace_state_root(workspace) / "decisions"


def decision_path(workspace: Path, decision_id: str) -> Path:
    return decisions_dir(workspace) / f"{validate_id(decision_id)}.json"


def parse_decision(data: dict[str, Any]) -> dict[str, Any]:
    data = _require_dict(data, "decision")
    _reject_unknown(data, _DECISION_FIELDS, "decision")
    assert_schema_kind(data.get("schema_kind"), expected="decision")
    assert_artifact_version(data.get("schema_version"))
    did = validate_id(_require_str(data.get("id"), "decision.id"))
    rationale = _require_str(data.get("rationale"), "decision.rationale")
    classification = _require_str(data.get("classification"), "decision.classification")
    if classification not in _CLASSIFICATIONS:
        raise DecisionError("decision.classification must be 'human' or 'agent'")
    for key in (
        "source_refs",
        "affected_requirements",
        "affected_files",
        "affected_policies",
        "affected_contracts",
    ):
        raw = data.get(key, [])
        _require_list(raw if raw is not None else [], f"decision.{key}")
    stale_when = data.get("stale_when", [])
    _require_list(stale_when if stale_when is not None else [], "decision.stale_when")
    if data.get("supersedes") is not None:
        validate_id(_require_str(data.get("supersedes"), "decision.supersedes"))
    if "artifact_digest" in data:
        verify_artifact_digest(data)
    # Secrets must not appear in rationale/source_refs (heuristic refuse).
    blob = json.dumps(data, sort_keys=True).lower()
    for needle in ("begin private key", "api_key=", "secret=", "password="):
        if needle in blob:
            raise DecisionError(
                "decision appears to contain a secret-like token; refuse capture"
            )
    return data


def capture_decision(
    *,
    workspace: Path,
    decision_id: str,
    rationale: str,
    classification: str,
    source_refs: list[str] | None = None,
    affected_requirements: list[str] | None = None,
    affected_files: list[str] | None = None,
    affected_policies: list[str] | None = None,
    affected_contracts: list[str] | None = None,
    stale_when: list[dict[str, Any]] | None = None,
    supersedes: str | None = None,
    captured_by: str = "cli",
) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    did = validate_id(decision_id)
    path = decision_path(workspace, did)
    if path.exists():
        raise DecisionError(
            f"decision {did!r} already exists; capture a new id or supersede explicitly"
        )
    doc = {
        "schema_kind": "decision",
        "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
        "id": did,
        "rationale": rationale,
        "source_refs": list(source_refs or []),
        "affected_requirements": list(affected_requirements or []),
        "affected_files": list(affected_files or []),
        "affected_policies": list(affected_policies or []),
        "affected_contracts": list(affected_contracts or []),
        "classification": classification,
        "captured_at": utc_now_iso(),
        "captured_by": captured_by,
        "stale_when": list(stale_when or []),
        "supersedes": supersedes,
    }
    doc = bind_artifact_digest(parse_decision(doc))
    ensure_dir(path.parent)
    atomic_write_json(path, doc)
    return doc


def load_decision(workspace: Path, decision_id: str) -> dict[str, Any]:
    path = decision_path(workspace, decision_id)
    if not path.is_file():
        raise DecisionError(f"decision not found: {decision_id}")
    doc = read_json(path)
    parse_decision(doc)
    verify_artifact_digest(doc)
    return doc


def list_decisions(workspace: Path) -> list[dict[str, Any]]:
    workspace = resolve_workspace(workspace)
    root = decisions_dir(workspace)
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            doc = read_json(path)
            parse_decision(doc)
            verify_artifact_digest(doc)
            out.append(doc)
        except Exception:  # noqa: BLE001
            out.append(
                {
                    "id": path.stem,
                    "error": "malformed_or_tampered",
                    "path": str(path),
                }
            )
    return out


def search_decisions(workspace: Path, query: str) -> list[dict[str, Any]]:
    q = query.lower().strip()
    if not q:
        return list_decisions(workspace)
    hits: list[dict[str, Any]] = []
    for doc in list_decisions(workspace):
        if doc.get("error"):
            continue
        blob = json.dumps(doc, sort_keys=True).lower()
        if q in blob:
            hits.append(doc)
    return hits


def review_flags(workspace: Path) -> list[dict[str, Any]]:
    """Flag decisions whose stale_when conditions match current file digests."""
    workspace = resolve_workspace(workspace)
    flags: list[dict[str, Any]] = []
    for doc in list_decisions(workspace):
        if doc.get("error"):
            flags.append({"decision_id": doc.get("id"), "reason": "malformed_or_tampered"})
            continue
        for cond in doc.get("stale_when") or []:
            if not isinstance(cond, dict):
                continue
            path_rel = cond.get("path")
            expected = cond.get("sha256")
            if not isinstance(path_rel, str) or not isinstance(expected, str):
                continue
            try:
                path = ensure_within(workspace, Path(path_rel), label="decision.stale_when.path")
            except Exception:  # noqa: BLE001
                flags.append(
                    {
                        "decision_id": doc["id"],
                        "reason": "stale_path_invalid",
                        "path": path_rel,
                    }
                )
                continue
            if not path.is_file():
                flags.append(
                    {
                        "decision_id": doc["id"],
                        "reason": "referenced_input_missing",
                        "path": path_rel,
                    }
                )
                continue
            live = sha256_file(path)
            if live != expected.lower():
                flags.append(
                    {
                        "decision_id": doc["id"],
                        "reason": "referenced_input_changed",
                        "path": path_rel,
                        "recorded_sha256": expected.lower(),
                        "current_sha256": live,
                    }
                )
    return flags
