"""Task manifests, requirement checks, and evidence reports.

Agents never supply a trusted ``passed`` field. Outcomes come only from
registered check providers that execute and capture structured results.
Missing, malformed, skipped, or collection-error results are never success.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from runspecimen.artifact import (
    CURRENT_ARTIFACT_SCHEMA_VERSION,
    assert_artifact_version,
    assert_schema_kind,
    bind_artifact_digest,
    verify_artifact_digest,
)
from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.contract import (
    Contract,
    _object_without_duplicates,
    _reject_unknown,
    _require_dict,
    _require_list,
    _require_sha256_hex,
    _require_str,
    load_contract,
)
from runspecimen.errors import ContractError, ProvenanceError, RunSpecimenError
from runspecimen.hashutil import hash_source, sha256_bytes, sha256_file, canonical_json_bytes
from runspecimen.paths import (
    ensure_dir,
    ensure_within,
    resolve_workspace,
    run_state_dir,
    validate_id,
    workspace_state_root,
)
from runspecimen.runtime import runtime_provenance


class EvidenceError(RunSpecimenError):
    """Requirements or evidence report failed validation or honesty rules."""


# Outcome vocabulary — never collapse skipped/error into passed.
OUTCOME_PASSED = "passed"
OUTCOME_FAILED = "failed"
OUTCOME_SKIPPED = "skipped"
OUTCOME_ERROR = "error"
OUTCOME_UNVERIFIED = "unverified"
OUTCOME_MANUAL = "manual_unverifiable"

SUCCESS_OUTCOMES = frozenset({OUTCOME_PASSED})
NON_SUCCESS = frozenset(
    {
        OUTCOME_FAILED,
        OUTCOME_SKIPPED,
        OUTCOME_ERROR,
        OUTCOME_UNVERIFIED,
        OUTCOME_MANUAL,
    }
)

_MANIFEST_FIELDS = {
    "schema_kind",
    "schema_version",
    "id",
    "description",
    "requirements",
    "artifact_digest",
}

_REQUIREMENT_FIELDS = {
    "id",
    "description",
    "check",
    "inputs",
    "source_scope",
    "required_evidence",
    "expected",
    "rationale",
    "manual_unverifiable",
}

_CHECK_FIELDS = {"provider", "id", "config"}


@dataclass(frozen=True)
class CheckRef:
    provider: str
    id: str
    config: dict[str, Any]


@dataclass(frozen=True)
class Requirement:
    id: str
    description: str
    check: CheckRef | None
    inputs: tuple[str, ...]
    source_scope: tuple[str, ...]
    required_evidence: tuple[str, ...]
    expected: dict[str, Any]
    rationale: str | None
    manual_unverifiable: bool


@dataclass(frozen=True)
class TaskManifest:
    schema_version: int
    id: str
    description: str
    requirements: tuple[Requirement, ...]
    path: Path
    manifest_hash: str
    raw: dict[str, Any]


class CheckProvider(Protocol):
    name: str

    def run(
        self,
        *,
        workspace: Path,
        check_id: str,
        config: dict[str, Any],
        requirement: Requirement,
    ) -> dict[str, Any]:
        """Return structured result; must not trust caller-supplied passed."""


def _parse_check(raw: Any, label: str) -> CheckRef:
    obj = _require_dict(raw, label)
    _reject_unknown(obj, _CHECK_FIELDS, label)
    provider = _require_str(obj.get("provider"), f"{label}.provider")
    check_id = _require_str(obj.get("id"), f"{label}.id")
    config = obj.get("config", {})
    if config is None:
        config = {}
    config_obj = _require_dict(config, f"{label}.config")
    # Reject agent outcome smuggling inside config.
    for banned in ("passed", "outcome", "status", "success"):
        if banned in config_obj:
            raise EvidenceError(
                f"{label}.config must not contain {banned!r}; "
                "outcomes are provider-collected only"
            )
    return CheckRef(provider=provider, id=check_id, config=dict(config_obj))


def _parse_requirement(raw: Any, index: int) -> Requirement:
    label = f"requirements[{index}]"
    obj = _require_dict(raw, label)
    _reject_unknown(obj, _REQUIREMENT_FIELDS, label)
    req_id = validate_id(_require_str(obj.get("id"), f"{label}.id"))
    description = _require_str(obj.get("description"), f"{label}.description")
    manual = bool(obj.get("manual_unverifiable", False))
    if "manual_unverifiable" in obj and not isinstance(obj["manual_unverifiable"], bool):
        raise ContractError(f"{label}.manual_unverifiable must be a JSON boolean")

    check_raw = obj.get("check")
    if manual:
        if check_raw is not None:
            raise EvidenceError(
                f"{label}: manual_unverifiable requirements must not declare a check"
            )
        check = None
    else:
        if check_raw is None:
            raise EvidenceError(f"{label}: check is required unless manual_unverifiable")
        check = _parse_check(check_raw, f"{label}.check")

    inputs = tuple(
        _require_str(x, f"{label}.inputs[{i}]")
        for i, x in enumerate(_require_list(obj.get("inputs", []), f"{label}.inputs"))
    )
    source_scope = tuple(
        _require_str(x, f"{label}.source_scope[{i}]")
        for i, x in enumerate(
            _require_list(obj.get("source_scope", []), f"{label}.source_scope")
        )
    )
    required_evidence = tuple(
        _require_str(x, f"{label}.required_evidence[{i}]")
        for i, x in enumerate(
            _require_list(obj.get("required_evidence", []), f"{label}.required_evidence")
        )
    )
    expected_raw = obj.get("expected", {})
    expected = dict(_require_dict(expected_raw if expected_raw is not None else {}, f"{label}.expected"))
    if "passed" in expected:
        raise EvidenceError(
            f"{label}.expected must not contain passed; declare measurable expectations only"
        )
    rationale = obj.get("rationale")
    if rationale is not None:
        rationale = _require_str(rationale, f"{label}.rationale")
    return Requirement(
        id=req_id,
        description=description,
        check=check,
        inputs=inputs,
        source_scope=source_scope,
        required_evidence=required_evidence,
        expected=expected,
        rationale=rationale,
        manual_unverifiable=manual,
    )


def parse_task_manifest(data: dict[str, Any], *, path: Path, payload: bytes) -> TaskManifest:
    data = _require_dict(data, "task_manifest")
    _reject_unknown(data, _MANIFEST_FIELDS, "task_manifest")
    assert_schema_kind(data.get("schema_kind"), expected="task_manifest")
    version = assert_artifact_version(data.get("schema_version"))
    manifest_id = validate_id(_require_str(data.get("id"), "task_manifest.id"))
    description = _require_str(data.get("description"), "task_manifest.description")
    reqs_raw = _require_list(data.get("requirements"), "task_manifest.requirements")
    if not reqs_raw:
        raise EvidenceError("task_manifest.requirements must be non-empty")
    requirements = tuple(_parse_requirement(item, i) for i, item in enumerate(reqs_raw))
    seen: set[str] = set()
    for req in requirements:
        if req.id in seen:
            raise EvidenceError(f"duplicate requirement id: {req.id!r}")
        seen.add(req.id)
    # Integrity: if digest present, verify; hash is always over file bytes for binding.
    if "artifact_digest" in data:
        verify_artifact_digest(data)
    manifest_hash = sha256_bytes(payload)
    return TaskManifest(
        schema_version=version,
        id=manifest_id,
        description=description,
        requirements=requirements,
        path=path.resolve(),
        manifest_hash=manifest_hash,
        raw=data,
    )


def load_task_manifest(path: Path) -> TaskManifest:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise EvidenceError(f"task manifest not found: {path}")
    payload = path.read_bytes()
    try:
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_object_without_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid task manifest JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceError("task manifest must be a JSON object")
    return parse_task_manifest(data, path=path, payload=payload)


def evidence_report_path(workspace: Path, campaign_id: str, run_id: str) -> Path:
    return run_state_dir(workspace, campaign_id, run_id) / "evidence_report.json"


def attestation_path(workspace: Path, campaign_id: str, run_id: str) -> Path:
    return run_state_dir(workspace, campaign_id, run_id) / "evidence_attestation.json"


# --- Providers -----------------------------------------------------------------


class PytestProvider:
    """Run pytest and parse JUnit XML. Never trusts a pre-written passed field."""

    name = "pytest"

    def run(
        self,
        *,
        workspace: Path,
        check_id: str,
        config: dict[str, Any],
        requirement: Requirement,
    ) -> dict[str, Any]:
        import subprocess
        import sys
        import tempfile

        target = config.get("target")
        if not isinstance(target, str) or not target:
            return {
                "outcome": OUTCOME_ERROR,
                "provider": self.name,
                "check_id": check_id,
                "error": "pytest config.target must be a non-empty relative path",
                "tests": [],
                "artifacts": {},
            }
        try:
            target_path = ensure_within(workspace, Path(target), label="pytest.target")
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": OUTCOME_ERROR,
                "provider": self.name,
                "check_id": check_id,
                "error": f"pytest target escapes workspace: {exc}",
                "tests": [],
                "artifacts": {},
            }
        if not target_path.exists():
            return {
                "outcome": OUTCOME_ERROR,
                "provider": self.name,
                "check_id": check_id,
                "error": f"pytest target missing: {target}",
                "tests": [],
                "artifacts": {},
            }

        node_ids = config.get("node_ids")
        if node_ids is None:
            node_ids_list: list[str] = []
        else:
            if not isinstance(node_ids, list) or not all(isinstance(x, str) for x in node_ids):
                return {
                    "outcome": OUTCOME_ERROR,
                    "provider": self.name,
                    "check_id": check_id,
                    "error": "pytest config.node_ids must be an array of strings",
                    "tests": [],
                    "artifacts": {},
                }
            node_ids_list = list(node_ids)

        with tempfile.TemporaryDirectory(prefix="rs-pytest-") as tmp:
            junit = Path(tmp) / "junit.xml"
            cmd = [
                sys.executable,
                "-m",
                "pytest",
                str(target_path),
                "--junitxml",
                str(junit),
                "-q",
            ]
            for node in node_ids_list:
                cmd.append(node)
            try:
                completed = subprocess.run(
                    cmd,
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                    timeout=int(config.get("timeout_sec", 120)),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                return {
                    "outcome": OUTCOME_ERROR,
                    "provider": self.name,
                    "check_id": check_id,
                    "error": f"pytest timed out: {exc}",
                    "tests": [],
                    "artifacts": {},
                    "exit_code": None,
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "outcome": OUTCOME_ERROR,
                    "provider": self.name,
                    "check_id": check_id,
                    "error": f"pytest collection/execution failed: {exc}",
                    "tests": [],
                    "artifacts": {},
                }

            tests, collection_errors = _parse_junit(junit if junit.is_file() else None)
            artifacts: dict[str, str] = {}
            if junit.is_file():
                artifacts["junit_xml_sha256"] = sha256_file(junit)

            if collection_errors:
                outcome = OUTCOME_ERROR
            elif not tests:
                # No tests collected → not coverage, not success.
                outcome = OUTCOME_ERROR
                collection_errors.append("no tests collected; filename match is not coverage")
            elif any(t["outcome"] == OUTCOME_FAILED for t in tests):
                outcome = OUTCOME_FAILED
            elif any(t["outcome"] == OUTCOME_ERROR for t in tests):
                outcome = OUTCOME_ERROR
            elif all(t["outcome"] == OUTCOME_SKIPPED for t in tests):
                outcome = OUTCOME_SKIPPED
            elif any(t["outcome"] == OUTCOME_SKIPPED for t in tests):
                # Mixed skip + pass → incomplete, not universal pass.
                outcome = OUTCOME_UNVERIFIED
            elif all(t["outcome"] == OUTCOME_PASSED for t in tests):
                outcome = OUTCOME_PASSED
            else:
                outcome = OUTCOME_UNVERIFIED

            return {
                "outcome": outcome,
                "provider": self.name,
                "check_id": check_id,
                "exit_code": completed.returncode,
                "stdout_tail": (completed.stdout or "")[-4000:],
                "stderr_tail": (completed.stderr or "")[-4000:],
                "tests": tests,
                "collection_errors": collection_errors,
                "artifacts": artifacts,
                "command": cmd,
            }


def _parse_junit(path: Path | None) -> tuple[list[dict[str, Any]], list[str]]:
    if path is None or not path.is_file():
        return [], ["junit xml missing (collection or runner failure)"]
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [], [f"malformed junit xml: {exc}"]

    tests: list[dict[str, Any]] = []
    errors: list[str] = []
    suites = root.findall(".//testsuite") or ([root] if root.tag == "testsuite" else [])
    for suite in suites:
        for case in suite.findall("testcase"):
            name = case.get("name") or ""
            classname = case.get("classname") or ""
            if case.find("failure") is not None:
                outcome = OUTCOME_FAILED
            elif case.find("error") is not None:
                outcome = OUTCOME_ERROR
            elif case.find("skipped") is not None:
                outcome = OUTCOME_SKIPPED
            else:
                outcome = OUTCOME_PASSED
            tests.append(
                {
                    "name": name,
                    "classname": classname,
                    "outcome": outcome,
                }
            )
    # pytest may encode collection errors as a property or empty suite with errors attr
    for suite in suites:
        err_count = suite.get("errors")
        if err_count and err_count.isdigit() and int(err_count) > 0 and not tests:
            errors.append(f"junit reports errors={err_count} with no testcases")
    return tests, errors


class CommandStatusProvider:
    """Capture exit status of a declared argv relative to workspace (no shell)."""

    name = "command_status"

    def run(
        self,
        *,
        workspace: Path,
        check_id: str,
        config: dict[str, Any],
        requirement: Requirement,
    ) -> dict[str, Any]:
        import subprocess

        argv = config.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            return {
                "outcome": OUTCOME_ERROR,
                "provider": self.name,
                "check_id": check_id,
                "error": "command_status config.argv must be a non-empty string array",
                "artifacts": {},
            }
        expected_exit = config.get("exit_code", 0)
        if isinstance(expected_exit, bool) or not isinstance(expected_exit, int):
            return {
                "outcome": OUTCOME_ERROR,
                "provider": self.name,
                "check_id": check_id,
                "error": "command_status config.exit_code must be an integer",
                "artifacts": {},
            }
        try:
            completed = subprocess.run(
                list(argv),
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=int(config.get("timeout_sec", 60)),
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": OUTCOME_ERROR,
                "provider": self.name,
                "check_id": check_id,
                "error": str(exc),
                "artifacts": {},
            }
        outcome = OUTCOME_PASSED if completed.returncode == expected_exit else OUTCOME_FAILED
        return {
            "outcome": outcome,
            "provider": self.name,
            "check_id": check_id,
            "exit_code": completed.returncode,
            "expected_exit_code": expected_exit,
            "stdout_tail": (completed.stdout or "")[-2000:],
            "stderr_tail": (completed.stderr or "")[-2000:],
            "artifacts": {},
            "command": list(argv),
        }


class UnittestProvider:
    """Run stdlib unittest and capture results. No third-party dependency."""

    name = "unittest"

    def run(
        self,
        *,
        workspace: Path,
        check_id: str,
        config: dict[str, Any],
        requirement: Requirement,
    ) -> dict[str, Any]:
        import io
        import sys
        import unittest

        pattern = config.get("pattern", "test*.py")
        start_dir = config.get("start_dir", ".")
        if not isinstance(pattern, str) or not isinstance(start_dir, str):
            return {
                "outcome": OUTCOME_ERROR,
                "provider": self.name,
                "check_id": check_id,
                "error": "unittest config.pattern/start_dir must be strings",
                "tests": [],
                "artifacts": {},
            }
        try:
            start = ensure_within(workspace, Path(start_dir), label="unittest.start_dir")
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": OUTCOME_ERROR,
                "provider": self.name,
                "check_id": check_id,
                "error": str(exc),
                "tests": [],
                "artifacts": {},
            }
        # Ensure the workspace root is importable for fixture packages.
        inserted = False
        ws_str = str(workspace)
        if ws_str not in sys.path:
            sys.path.insert(0, ws_str)
            inserted = True
        # Make start_dir a package if needed so discover can import it.
        init_py = start / "__init__.py"
        created_init = False
        if start.is_dir() and not init_py.exists():
            init_py.write_text("", encoding="utf-8")
            created_init = True
        loader = unittest.defaultTestLoader
        suite = None
        try:
            try:
                suite = loader.discover(
                    start_dir=str(start), pattern=pattern, top_level_dir=str(workspace)
                )
            except Exception as exc:  # noqa: BLE001
                return {
                    "outcome": OUTCOME_ERROR,
                    "provider": self.name,
                    "check_id": check_id,
                    "error": f"unittest collection failed: {exc}",
                    "tests": [],
                    "collection_errors": [str(exc)],
                    "artifacts": {},
                }

            stream = io.StringIO()
            runner = unittest.TextTestRunner(stream=stream, verbosity=2)
            result = runner.run(suite)
        finally:
            if created_init:
                try:
                    init_py.unlink()
                except OSError:
                    pass
            if inserted:
                try:
                    sys.path.remove(ws_str)
                except ValueError:
                    pass

        tests: list[dict[str, Any]] = []
        for test, _ in result.failures:
            tests.append({"name": str(test), "outcome": OUTCOME_FAILED})
        for test, _ in result.errors:
            tests.append({"name": str(test), "outcome": OUTCOME_ERROR})
        for test, _ in getattr(result, "skipped", []):
            tests.append({"name": str(test), "outcome": OUTCOME_SKIPPED})
        # Estimate passes: total - failures - errors - skipped
        skipped_n = len(getattr(result, "skipped", []))
        passed_n = result.testsRun - len(result.failures) - len(result.errors) - skipped_n
        for i in range(max(0, passed_n)):
            tests.append({"name": f"passed[{i}]", "outcome": OUTCOME_PASSED})

        if result.testsRun == 0:
            outcome = OUTCOME_ERROR
            collection_errors = ["no tests collected; filename match is not coverage"]
        elif result.failures or result.errors:
            outcome = OUTCOME_FAILED if result.failures else OUTCOME_ERROR
            collection_errors = []
        elif skipped_n and passed_n == 0:
            outcome = OUTCOME_SKIPPED
            collection_errors = []
        elif skipped_n:
            outcome = OUTCOME_UNVERIFIED
            collection_errors = []
        else:
            outcome = OUTCOME_PASSED
            collection_errors = []

        return {
            "outcome": outcome,
            "provider": self.name,
            "check_id": check_id,
            "tests": tests,
            "collection_errors": collection_errors,
            "tests_run": result.testsRun,
            "artifacts": {
                "unittest_stream_sha256": sha256_bytes(stream.getvalue().encode("utf-8"))
            },
            "stdout_tail": stream.getvalue()[-4000:],
        }


_PROVIDERS: dict[str, CheckProvider] = {
    PytestProvider.name: PytestProvider(),
    UnittestProvider.name: UnittestProvider(),
    CommandStatusProvider.name: CommandStatusProvider(),
}


def register_provider(provider: CheckProvider) -> None:
    _PROVIDERS[provider.name] = provider


def get_provider(name: str) -> CheckProvider | None:
    return _PROVIDERS.get(name)


def list_providers() -> list[str]:
    return sorted(_PROVIDERS)


def _requirement_outcome(result: dict[str, Any], requirement: Requirement) -> str:
    if requirement.manual_unverifiable:
        return OUTCOME_MANUAL
    outcome = result.get("outcome")
    if outcome not in SUCCESS_OUTCOMES | NON_SUCCESS:
        return OUTCOME_ERROR
    return str(outcome)


def run_requirements(
    *,
    workspace: Path,
    contract: Contract,
    manifest: TaskManifest,
    capture_source_during: bool = True,
) -> dict[str, Any]:
    """Execute configured checks and build an evidence report.

    When ``capture_source_during`` is true, source is hashed before and after
    checks; a mid-check source change marks final-state certification invalid.
    """
    workspace = resolve_workspace(workspace)
    source_before, _ = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    runtime = runtime_provenance(contract, workspace)
    results: list[dict[str, Any]] = []
    evidence_digests: dict[str, str] = {}

    for req in manifest.requirements:
        if req.manual_unverifiable:
            results.append(
                {
                    "requirement_id": req.id,
                    "outcome": OUTCOME_MANUAL,
                    "check": None,
                    "note": "explicitly manual/unverifiable; not success",
                }
            )
            continue
        assert req.check is not None
        provider = get_provider(req.check.provider)
        if provider is None:
            results.append(
                {
                    "requirement_id": req.id,
                    "outcome": OUTCOME_ERROR,
                    "check": {"provider": req.check.provider, "id": req.check.id},
                    "error": f"unknown check provider: {req.check.provider!r}",
                }
            )
            continue
        raw = provider.run(
            workspace=workspace,
            check_id=req.check.id,
            config=req.check.config,
            requirement=req,
        )
        # Defensive: strip any smuggled passed field from provider output.
        raw = {k: v for k, v in raw.items() if k != "passed"}
        outcome = _requirement_outcome(raw, req)
        entry = {
            "requirement_id": req.id,
            "outcome": outcome,
            "check": {
                "provider": req.check.provider,
                "id": req.check.id,
                "identity": sha256_bytes(
                    canonical_json_bytes(
                        {
                            "provider": req.check.provider,
                            "id": req.check.id,
                            "config": req.check.config,
                        }
                    )
                ),
            },
            "provider_result": raw,
        }
        for key, digest in (raw.get("artifacts") or {}).items():
            if isinstance(digest, str) and len(digest) == 64:
                evidence_digests[f"{req.id}:{key}"] = digest.lower()
        results.append(entry)

    source_after, entries = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    source_changed_during = source_before != source_after
    final_state_certifiable = not source_changed_during

    summary = {
        "passed": sum(1 for r in results if r["outcome"] == OUTCOME_PASSED),
        "failed": sum(1 for r in results if r["outcome"] == OUTCOME_FAILED),
        "skipped": sum(1 for r in results if r["outcome"] == OUTCOME_SKIPPED),
        "error": sum(1 for r in results if r["outcome"] == OUTCOME_ERROR),
        "unverified": sum(1 for r in results if r["outcome"] == OUTCOME_UNVERIFIED),
        "manual_unverifiable": sum(1 for r in results if r["outcome"] == OUTCOME_MANUAL),
        "total": len(results),
    }
    # Aggregate status: only all-passed (and no mid-check source change) is "passed".
    if source_changed_during:
        aggregate = OUTCOME_UNVERIFIED
        aggregate_note = (
            "source changed during verification; final workspace state is not certifiable "
            "from this evidence report"
        )
    elif summary["failed"] or summary["error"]:
        aggregate = OUTCOME_FAILED
        aggregate_note = "one or more requirements failed or errored"
    elif summary["skipped"] or summary["unverified"] or summary["manual_unverifiable"]:
        aggregate = OUTCOME_UNVERIFIED
        aggregate_note = "incomplete: skipped, unverified, or manual requirements present"
    elif summary["passed"] == summary["total"] and summary["total"] > 0:
        aggregate = OUTCOME_PASSED
        aggregate_note = (
            "configured checks passed; this is not universal correctness"
        )
    else:
        aggregate = OUTCOME_UNVERIFIED
        aggregate_note = "no successful requirement outcomes"

    report = {
        "schema_kind": "evidence_report",
        "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
        "campaign_id": contract.campaign_id,
        "run_id": contract.run_id,
        "contract_hash": contract.contract_hash,
        "manifest_id": manifest.id,
        "manifest_hash": manifest.manifest_hash,
        "source_hash_before": source_before,
        "source_hash_after": source_after,
        "source_changed_during_checks": source_changed_during,
        "final_state_certifiable": final_state_certifiable,
        "runtime_fingerprint": {
            "runtime_id": runtime.get("runtime_id"),
            "executable_sha256": runtime.get("executable_sha256"),
            "interpreter_sha256": runtime.get("interpreter_sha256"),
            "env_hash": runtime.get("env_hash"),
        },
        "requirements": results,
        "evidence_digests": dict(sorted(evidence_digests.items())),
        "summary": summary,
        "aggregate_outcome": aggregate,
        "aggregate_note": aggregate_note,
        "limitations": [
            "Passing configured checks is not universal correctness.",
            "Unchanged final digest does not prove files were never temporarily modified.",
            "Skipped tests and collection errors are visible and are not success.",
        ],
    }
    report = bind_artifact_digest(report)
    return report


def write_evidence_report(
    workspace: Path, campaign_id: str, run_id: str, report: dict[str, Any]
) -> Path:
    path = evidence_report_path(workspace, campaign_id, run_id)
    ensure_dir(path.parent)
    verify_artifact_digest(report)
    atomic_write_json(path, report)
    return path


def load_evidence_report(workspace: Path, campaign_id: str, run_id: str) -> dict[str, Any]:
    path = evidence_report_path(workspace, campaign_id, run_id)
    if not path.is_file():
        raise EvidenceError(f"evidence report not found: {path}")
    doc = read_json(path)
    if not isinstance(doc, dict):
        raise EvidenceError("evidence report must be a JSON object")
    assert_schema_kind(doc.get("schema_kind"), expected="evidence_report")
    assert_artifact_version(doc.get("schema_version"))
    verify_artifact_digest(doc)
    return doc


def build_evidence_attestation(report: dict[str, Any]) -> dict[str, Any]:
    """Linked attestation binding the evidence report digest for optional receipt use."""
    verify_artifact_digest(report)
    att = {
        "schema_kind": "evidence_attestation",
        "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
        "campaign_id": report["campaign_id"],
        "run_id": report["run_id"],
        "contract_hash": report["contract_hash"],
        "manifest_hash": report["manifest_hash"],
        "evidence_report_digest": report["artifact_digest"],
        "aggregate_outcome": report["aggregate_outcome"],
        "final_state_certifiable": report["final_state_certifiable"],
        "note": (
            "Attestation authenticates the evidence report bytes. "
            "It does not rewrite check outcomes or imply current applicability."
        ),
    }
    return bind_artifact_digest(att)


def write_evidence_attestation(
    workspace: Path, campaign_id: str, run_id: str, attestation: dict[str, Any]
) -> Path:
    path = attestation_path(workspace, campaign_id, run_id)
    ensure_dir(path.parent)
    verify_artifact_digest(attestation)
    atomic_write_json(path, attestation)
    return path


def ci_machine_report(report: dict[str, Any]) -> dict[str, Any]:
    """Compact machine-readable CI output (exit semantics left to caller)."""
    return {
        "ok": report.get("aggregate_outcome") == OUTCOME_PASSED
        and report.get("final_state_certifiable") is True,
        "aggregate_outcome": report.get("aggregate_outcome"),
        "final_state_certifiable": report.get("final_state_certifiable"),
        "summary": report.get("summary"),
        "manifest_hash": report.get("manifest_hash"),
        "contract_hash": report.get("contract_hash"),
        "campaign_id": report.get("campaign_id"),
        "run_id": report.get("run_id"),
        "artifact_digest": report.get("artifact_digest"),
        "requirements": [
            {"id": r["requirement_id"], "outcome": r["outcome"]}
            for r in report.get("requirements", [])
        ],
        "note": report.get("aggregate_note"),
    }
