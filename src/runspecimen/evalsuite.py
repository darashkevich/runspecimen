"""Workflow regression evaluation (reproducible local suite + provider interface).

Separates deterministic checks from model judgments. One stochastic run is never
conclusive. Local suite works without external agent credentials. Does not
fabricate authorization with internal helpers.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Protocol

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
from runspecimen.hashutil import sha256_file, sha256_bytes, canonical_json_bytes
from runspecimen.paths import ensure_dir, resolve_workspace, validate_id, workspace_state_root
from runspecimen.requirements import (
    OUTCOME_FAILED,
    OUTCOME_PASSED,
    OUTCOME_UNVERIFIED,
    load_task_manifest,
    run_requirements,
)
from runspecimen.contract import load_contract


class EvalError(RunSpecimenError):
    """Eval suite validation or execution failed."""


class EvalProvider(Protocol):
    name: str

    def run_task(self, *, workspace: Path, task: dict[str, Any]) -> dict[str, Any]:
        ...


class LocalDeterministicEvalProvider:
    """Runs requirement checks in a disposable copy of a fixture workspace."""

    name = "local_deterministic"

    def run_task(self, *, workspace: Path, task: dict[str, Any]) -> dict[str, Any]:
        fixture = task.get("fixture_dir")
        contract_rel = task.get("contract")
        manifest_rel = task.get("manifest")
        if not isinstance(fixture, str) or not isinstance(contract_rel, str):
            return {
                "outcome": OUTCOME_FAILED,
                "error": "task requires fixture_dir and contract",
                "deterministic": True,
            }
        src = Path(fixture)
        if not src.is_dir():
            # Allow fixture relative to suite workspace
            src = workspace / fixture
        if not src.is_dir():
            return {
                "outcome": OUTCOME_FAILED,
                "error": f"fixture_dir missing: {fixture}",
                "deterministic": True,
            }
        with tempfile.TemporaryDirectory(prefix="rs-eval-") as tmp:
            dest = Path(tmp) / "ws"
            shutil.copytree(
                src,
                dest,
                ignore=shutil.ignore_patterns(".runspecimen", ".git", "__pycache__"),
            )
            contract = load_contract(dest / contract_rel)
            manifest = None
            if isinstance(manifest_rel, str):
                from runspecimen.requirements import AuthorizationError

                manifest = load_task_manifest(dest / manifest_rel)
                try:
                    report = run_requirements(
                        workspace=dest, contract=contract, manifest=manifest
                    )
                except AuthorizationError as exc:
                    return {
                        "outcome": OUTCOME_UNVERIFIED,
                        "deterministic": True,
                        "error": str(exc),
                        "note": (
                            "execution-gated without human APPROVE; "
                            "local suite does not fabricate approval"
                        ),
                    }
                return {
                    "outcome": report.get("aggregate_outcome"),
                    "deterministic": True,
                    "evidence_report_digest": report.get("artifact_digest"),
                    "summary": report.get("summary"),
                    "final_state_certifiable": report.get("final_state_certifiable"),
                    "fixture_version": task.get("fixture_version"),
                    "note": "local deterministic checks only; no model judgment",
                }
            return {
                "outcome": OUTCOME_UNVERIFIED,
                "deterministic": True,
                "error": "manifest required for local_deterministic provider",
            }


_PROVIDERS: dict[str, EvalProvider] = {
    LocalDeterministicEvalProvider.name: LocalDeterministicEvalProvider(),
}


def get_eval_provider(name: str) -> EvalProvider:
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise EvalError(f"eval provider unavailable: {name!r}")
    return provider


_SUITE_FIELDS = {
    "schema_kind",
    "schema_version",
    "id",
    "description",
    "tasks",
    "artifact_digest",
}

_TASK_FIELDS = {
    "id",
    "provider",
    "fixture_dir",
    "fixture_version",
    "contract",
    "manifest",
    "rules_hash",
    "skills_hash",
    "policy_hash",
    "expected_outcome",
    "judgment",  # deterministic | model — model never conclusive alone
}


def parse_eval_suite(data: dict[str, Any]) -> dict[str, Any]:
    data = _require_dict(data, "eval_suite")
    _reject_unknown(data, _SUITE_FIELDS, "eval_suite")
    assert_schema_kind(data.get("schema_kind"), expected="eval_suite")
    assert_artifact_version(data.get("schema_version"))
    validate_id(_require_str(data.get("id"), "eval_suite.id"))
    _require_str(data.get("description"), "eval_suite.description")
    tasks = _require_list(data.get("tasks"), "eval_suite.tasks")
    if not tasks:
        raise EvalError("eval_suite.tasks must be non-empty")
    for i, task in enumerate(tasks):
        label = f"tasks[{i}]"
        obj = _require_dict(task, label)
        _reject_unknown(obj, _TASK_FIELDS, label)
        validate_id(_require_str(obj.get("id"), f"{label}.id"))
        _require_str(obj.get("provider"), f"{label}.provider")
        judgment = obj.get("judgment", "deterministic")
        if judgment not in {"deterministic", "model"}:
            raise EvalError(f"{label}.judgment must be deterministic|model")
    if "artifact_digest" in data:
        verify_artifact_digest(data)
    return data


def load_eval_suite(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    data = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_object_without_duplicates,
    )
    return parse_eval_suite(data)


def run_eval_suite(*, workspace: Path, suite: dict[str, Any]) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    suite = parse_eval_suite(suite)
    started = time.time()
    task_results: list[dict[str, Any]] = []
    for task in suite["tasks"]:
        provider = get_eval_provider(task["provider"])
        t0 = time.time()
        raw = provider.run_task(workspace=workspace, task=task)
        elapsed = time.time() - t0
        expected = task.get("expected_outcome")
        matched = expected is None or raw.get("outcome") == expected
        judgment = task.get("judgment", "deterministic")
        task_results.append(
            {
                "task_id": task["id"],
                "provider": task["provider"],
                "fixture_version": task.get("fixture_version"),
                "rules_hash": task.get("rules_hash"),
                "skills_hash": task.get("skills_hash"),
                "policy_hash": task.get("policy_hash"),
                "judgment": judgment,
                "expected_outcome": expected,
                "actual_outcome": raw.get("outcome"),
                "matched_expected": matched,
                "deterministic": bool(raw.get("deterministic")),
                "elapsed_sec": round(elapsed, 3),
                "provider_result": raw,
                "conclusive": judgment == "deterministic" and matched,
                "note": (
                    None
                    if judgment == "deterministic"
                    else "model judgment is not conclusive from a single run"
                ),
            }
        )

    deterministic = [t for t in task_results if t["judgment"] == "deterministic"]
    regressions = [
        t["task_id"]
        for t in deterministic
        if t["expected_outcome"] is not None and not t["matched_expected"]
    ]
    result = {
        "schema_kind": "eval_result",
        "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
        "suite_id": suite["id"],
        "suite_digest": suite.get("artifact_digest")
        or sha256_bytes(canonical_json_bytes({k: v for k, v in suite.items() if k != "artifact_digest"})),
        "started_at": utc_now_iso(),
        "elapsed_sec": round(time.time() - started, 3),
        "tasks": task_results,
        "regressions": regressions,
        "passed_deterministic": not regressions and bool(deterministic),
        "limitations": [
            "One stochastic/model run is never conclusive.",
            "Local suite does not fabricate APPROVE; execution-gated tasks stay unverified without human auth.",
            "External agents may need credentials; this provider path does not.",
        ],
    }
    return bind_artifact_digest(result)


def compare_eval_results(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    assert_schema_kind(baseline.get("schema_kind"), expected="eval_result")
    assert_schema_kind(candidate.get("schema_kind"), expected="eval_result")
    verify_artifact_digest(baseline)
    verify_artifact_digest(candidate)
    if baseline.get("suite_id") != candidate.get("suite_id"):
        raise EvalError("cannot compare eval results from different suite ids")
    if baseline.get("suite_digest") != candidate.get("suite_digest"):
        # Still allow compare but flag fixture/config drift.
        suite_mismatch = True
    else:
        suite_mismatch = False

    base_map = {t["task_id"]: t for t in baseline.get("tasks") or []}
    cand_map = {t["task_id"]: t for t in candidate.get("tasks") or []}
    deltas: list[dict[str, Any]] = []
    for tid in sorted(set(base_map) | set(cand_map)):
        b = base_map.get(tid)
        c = cand_map.get(tid)
        if b is None or c is None:
            deltas.append({"task_id": tid, "change": "task_added_or_removed"})
            continue
        if b.get("fixture_version") != c.get("fixture_version"):
            deltas.append(
                {
                    "task_id": tid,
                    "change": "fixture_version",
                    "baseline": b.get("fixture_version"),
                    "candidate": c.get("fixture_version"),
                }
            )
        for key in ("rules_hash", "skills_hash", "policy_hash"):
            if b.get(key) != c.get(key):
                deltas.append(
                    {
                        "task_id": tid,
                        "change": key,
                        "baseline": b.get(key),
                        "candidate": c.get(key),
                    }
                )
        if b.get("actual_outcome") != c.get("actual_outcome"):
            deltas.append(
                {
                    "task_id": tid,
                    "change": "outcome",
                    "baseline": b.get("actual_outcome"),
                    "candidate": c.get("actual_outcome"),
                    "regression_candidate": (
                        b.get("actual_outcome") == OUTCOME_PASSED
                        and c.get("actual_outcome") != OUTCOME_PASSED
                    ),
                }
            )
    return {
        "suite_id": baseline.get("suite_id"),
        "suite_digest_mismatch": suite_mismatch,
        "baseline_digest": baseline.get("artifact_digest"),
        "candidate_digest": candidate.get("artifact_digest"),
        "deltas": deltas,
        "note": (
            "Compare uses recorded fixture/config versions. "
            "Model-judgment tasks remain non-conclusive."
        ),
    }


def eval_results_dir(workspace: Path) -> Path:
    return workspace_state_root(workspace) / "eval"


def write_eval_result(workspace: Path, result: dict[str, Any]) -> Path:
    ensure_dir(eval_results_dir(workspace))
    path = eval_results_dir(workspace) / f"{result['suite_id']}-{result['artifact_digest'][:12]}.json"
    verify_artifact_digest(result)
    atomic_write_json(path, result)
    return path
