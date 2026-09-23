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

# Measurable expectations only. Unknown keys fail closed at validation.
_SUPPORTED_EXPECTED = frozenset({"minimum_tests"})


class AuthorizationError(EvidenceError):
    """Requirement checks refused because the run is not human-approved."""


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
    unknown_expected = sorted(set(expected) - _SUPPORTED_EXPECTED)
    if unknown_expected:
        raise EvidenceError(
            f"{label}.expected contains unsupported key(s): {', '.join(unknown_expected)}; "
            f"supported: {', '.join(sorted(_SUPPORTED_EXPECTED)) or '(none)'}"
        )
    if "minimum_tests" in expected:
        mt = expected["minimum_tests"]
        if isinstance(mt, bool) or not isinstance(mt, int) or mt < 1:
            raise EvidenceError(
                f"{label}.expected.minimum_tests must be a positive integer"
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
            elif completed.returncode not in (0, 1):
                # pytest uses 1 for test failures; other nonzero is runner/collection error.
                outcome = OUTCOME_ERROR
                collection_errors.append(
                    f"pytest exited with returncode={completed.returncode}"
                )
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
                # Passing XML is insufficient if the process still failed.
                if completed.returncode != 0:
                    outcome = OUTCOME_FAILED
                    collection_errors.append(
                        f"pytest returned nonzero ({completed.returncode}) after XML collection"
                    )
                else:
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
                "runtime_provenance": {
                    "executable": sys.executable,
                    "executable_sha256": sha256_file(Path(sys.executable))
                    if Path(sys.executable).is_file()
                    else None,
                },
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
    """Run stdlib unittest in a fresh subprocess. No third-party dependency."""

    name = "unittest"

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
            workspace = workspace.resolve()
            start = ensure_within(workspace, Path(start_dir), label="unittest.start_dir")
            start = start.resolve()
        except Exception as exc:  # noqa: BLE001
            return {
                "outcome": OUTCOME_ERROR,
                "provider": self.name,
                "check_id": check_id,
                "error": str(exc),
                "tests": [],
                "artifacts": {},
            }

        runner_src = r"""
import json
import sys
import unittest
from pathlib import Path

workspace = Path(sys.argv[1]).resolve()
start_dir = Path(sys.argv[2])
if not start_dir.is_absolute():
    start_dir = (workspace / start_dir).resolve()
else:
    start_dir = start_dir.resolve()
pattern = sys.argv[3]
out_path = Path(sys.argv[4])

# Keep discovery paths under the same resolved workspace root (macOS /var vs /private/var).
try:
    start_dir.relative_to(workspace)
except ValueError:
    # Fall back to relative path from argv when roots differ only by symlink alias.
    start_dir = (workspace / start_dir.name).resolve() if start_dir.name else workspace

sys.path.insert(0, str(workspace))
init_py = start_dir / "__init__.py"
created_init = False
if start_dir.is_dir() and not init_py.exists():
    init_py.write_text("", encoding="utf-8")
    created_init = True

class _Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ordered = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.ordered.append({"name": str(test), "outcome": "passed"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.ordered.append({"name": str(test), "outcome": "failed"})

    def addError(self, test, err):
        super().addError(test, err)
        self.ordered.append({"name": str(test), "outcome": "error"})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.ordered.append({"name": str(test), "outcome": "skipped", "reason": reason})

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.ordered.append({"name": str(test), "outcome": "expected_failure"})

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.ordered.append({"name": str(test), "outcome": "unexpected_success"})

try:
    loader = unittest.defaultTestLoader
    suite = loader.discover(
        start_dir=str(start_dir), pattern=pattern, top_level_dir=str(workspace)
    )
    import io
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=_Result)
    result = runner.run(suite)
    payload = {
        "tests": list(result.ordered),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(getattr(result, "skipped", [])),
        "expected_failures": len(getattr(result, "expectedFailures", [])),
        "unexpected_successes": len(getattr(result, "unexpectedSuccesses", [])),
        "stream": stream.getvalue(),
        "collection_error": None,
    }
except Exception as exc:
    payload = {
        "tests": [],
        "tests_run": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "expected_failures": 0,
        "unexpected_successes": 0,
        "stream": "",
        "collection_error": str(exc),
    }
finally:
    if created_init:
        try:
            init_py.unlink()
        except OSError:
            pass

out_path.write_text(json.dumps(payload), encoding="utf-8")
"""
        with tempfile.TemporaryDirectory(prefix="rs-unittest-") as tmp:
            runner_path = Path(tmp) / "rs_unittest_runner.py"
            result_path = Path(tmp) / "result.json"
            runner_path.write_text(runner_src, encoding="utf-8")
            cmd = [
                sys.executable,
                str(runner_path),
                str(workspace),
                str(start.relative_to(workspace)),
                pattern,
                str(result_path),
            ]
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
                    "error": f"unittest timed out: {exc}",
                    "tests": [],
                    "artifacts": {},
                    "exit_code": None,
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "outcome": OUTCOME_ERROR,
                    "provider": self.name,
                    "check_id": check_id,
                    "error": f"unittest subprocess failed: {exc}",
                    "tests": [],
                    "artifacts": {},
                }

            if not result_path.is_file():
                return {
                    "outcome": OUTCOME_ERROR,
                    "provider": self.name,
                    "check_id": check_id,
                    "error": (
                        "unittest subprocess produced no result file; "
                        f"exit={completed.returncode} stderr={(completed.stderr or '')[-1000:]}"
                    ),
                    "tests": [],
                    "artifacts": {},
                    "exit_code": completed.returncode,
                }
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                return {
                    "outcome": OUTCOME_ERROR,
                    "provider": self.name,
                    "check_id": check_id,
                    "error": f"malformed unittest result payload: {exc}",
                    "tests": [],
                    "artifacts": {},
                    "exit_code": completed.returncode,
                }

        tests = list(payload.get("tests") or [])
        collection_errors: list[str] = []
        if payload.get("collection_error"):
            collection_errors.append(str(payload["collection_error"]))

        expected_fail_n = int(payload.get("expected_failures") or 0)
        unexpected_ok_n = int(payload.get("unexpected_successes") or 0)
        tests_run = int(payload.get("tests_run") or 0)
        stream_text = str(payload.get("stream") or "")

        if collection_errors:
            outcome = OUTCOME_ERROR
        elif tests_run == 0 or not tests:
            outcome = OUTCOME_ERROR
            collection_errors.append("no tests collected; filename match is not coverage")
        elif any(t.get("outcome") == OUTCOME_ERROR for t in tests):
            outcome = OUTCOME_ERROR
        elif any(t.get("outcome") == OUTCOME_FAILED for t in tests):
            outcome = OUTCOME_FAILED
        elif unexpected_ok_n or any(t.get("outcome") == "unexpected_success" for t in tests):
            # Unexpected success is not a certified pass for a requirement.
            outcome = OUTCOME_UNVERIFIED
            collection_errors.append(
                "unexpectedSuccesses present; incomplete verification cannot certify passed"
            )
        elif expected_fail_n or any(t.get("outcome") == "expected_failure" for t in tests):
            # Expected failures are not requirement success.
            outcome = OUTCOME_UNVERIFIED
            collection_errors.append(
                "expectedFailures present; incomplete verification cannot certify passed"
            )
        elif any(t.get("outcome") == OUTCOME_SKIPPED for t in tests):
            if all(t.get("outcome") == OUTCOME_SKIPPED for t in tests):
                outcome = OUTCOME_SKIPPED
            else:
                outcome = OUTCOME_UNVERIFIED
        elif all(t.get("outcome") == OUTCOME_PASSED for t in tests) and completed.returncode == 0:
            outcome = OUTCOME_PASSED
        else:
            outcome = OUTCOME_UNVERIFIED
            if completed.returncode != 0:
                collection_errors.append(
                    f"unittest subprocess returncode={completed.returncode}"
                )

        return {
            "outcome": outcome,
            "provider": self.name,
            "check_id": check_id,
            "tests": tests,
            "collection_errors": collection_errors,
            "tests_run": tests_run,
            "expected_failures": expected_fail_n,
            "unexpected_successes": unexpected_ok_n,
            "exit_code": completed.returncode,
            "artifacts": {
                "unittest_stream_sha256": sha256_bytes(stream_text.encode("utf-8"))
            },
            "stdout_tail": stream_text[-4000:],
            "stderr_tail": (completed.stderr or "")[-2000:],
            "command": cmd,
            "runtime_provenance": {
                "executable": sys.executable,
                "executable_sha256": sha256_file(Path(sys.executable))
                if Path(sys.executable).is_file()
                else None,
                "subprocess": True,
            },
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

    artifacts = result.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        return OUTCOME_ERROR
    missing_evidence = [
        key for key in requirement.required_evidence if key not in artifacts
    ]
    if missing_evidence:
        result.setdefault("expectation_errors", []).append(
            f"missing required_evidence: {missing_evidence}"
        )
        return OUTCOME_FAILED if outcome == OUTCOME_PASSED else str(outcome)

    if "minimum_tests" in requirement.expected:
        tests = result.get("tests") or []
        if not isinstance(tests, list):
            result.setdefault("expectation_errors", []).append("tests list missing")
            return OUTCOME_ERROR
        passed_n = sum(1 for t in tests if isinstance(t, dict) and t.get("outcome") == OUTCOME_PASSED)
        need = int(requirement.expected["minimum_tests"])
        if passed_n < need:
            result.setdefault("expectation_errors", []).append(
                f"minimum_tests={need} not met (passed={passed_n})"
            )
            if outcome == OUTCOME_PASSED:
                return OUTCOME_FAILED
            return str(outcome)

    return str(outcome)


def _fingerprint_requirement_inputs(
    workspace: Path, requirement: Requirement
) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel in requirement.inputs:
        try:
            path = ensure_within(workspace, Path(rel), label=f"requirement.inputs:{rel}")
        except Exception:
            digests[rel] = "missing"
            continue
        if not path.is_file():
            digests[rel] = "missing"
        else:
            digests[rel] = sha256_file(path)
    for rel in requirement.source_scope:
        try:
            path = ensure_within(workspace, Path(rel), label=f"requirement.source_scope:{rel}")
        except Exception:
            digests[f"scope:{rel}"] = "missing"
            continue
        if path.is_file():
            digests[f"scope:{rel}"] = sha256_file(path)
        elif path.is_dir():
            # Directory fingerprint via contained file hashes (sorted).
            entries: list[tuple[str, str]] = []
            for child in sorted(path.rglob("*")):
                if child.is_file() and not child.is_symlink():
                    rel_child = child.relative_to(workspace).as_posix()
                    entries.append((rel_child, sha256_file(child)))
            digests[f"scope:{rel}"] = sha256_bytes(
                canonical_json_bytes({"files": entries})
            )
        else:
            digests[f"scope:{rel}"] = "missing"
    return digests


def assert_checks_authorized(
    *,
    workspace: Path,
    contract: Contract,
    manifest: TaskManifest,
) -> dict[str, Any]:
    """Refuse check execution unless this run was human-approved with bound manifest."""
    from runspecimen.approve import approval_is_valid, load_approval
    from runspecimen.hashutil import hash_source
    from runspecimen.state import load_state

    if contract.task_manifest is None:
        raise AuthorizationError(
            "requirements check refused: contract has no task_manifest binding. "
            "Bind task_manifest {id,path,sha256} in the contract before human APPROVE, "
            "then use the ordinary approve → preflight → run path. "
            "Agents must not type APPROVE."
        )
    if contract.task_manifest.sha256 != manifest.manifest_hash:
        raise AuthorizationError(
            "requirements check refused: live manifest hash does not match "
            "contract.task_manifest.sha256 (rebind before approval)"
        )
    if contract.task_manifest.id != manifest.id:
        raise AuthorizationError(
            "requirements check refused: manifest id does not match contract.task_manifest.id"
        )
    mpath = ensure_within(
        workspace, Path(contract.task_manifest.path), label="task_manifest.path"
    )
    if mpath.resolve() != manifest.path.resolve():
        # Allow same bytes via the bound path only.
        live = load_task_manifest(mpath)
        if live.manifest_hash != manifest.manifest_hash:
            raise AuthorizationError(
                "requirements check refused: manifest path must be the contract-bound file"
            )

    state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
    approval = load_approval(state_dir)
    if approval is None:
        raise AuthorizationError(
            "requirements check refused: no approval present for this campaign/run. "
            "Use the ordinary approve → preflight → run lifecycle on a real TTY; "
            "agents must not type APPROVE. Unapproved check commands never execute."
        )
    source_hash, _ = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    ok, reason = approval_is_valid(approval, contract, source_hash)
    if not ok:
        raise AuthorizationError(
            f"requirements check refused: approval not valid ({reason}). "
            "Re-approve on a real TTY after provenance is current."
        )
    bound = approval.get("task_manifest")
    if not isinstance(bound, dict) or bound.get("sha256") != manifest.manifest_hash:
        raise AuthorizationError(
            "requirements check refused: approval does not bind this task_manifest. "
            "Manifest/check commands must be bound before APPROVE."
        )
    state = load_state(state_dir)
    phase = state.get("phase")
    if phase in {None, "none", "abandoned"}:
        raise AuthorizationError(
            f"requirements check refused: run phase={phase!r} is not authorized"
        )
    return approval


def run_requirements(
    *,
    workspace: Path,
    contract: Contract,
    manifest: TaskManifest,
    capture_source_during: bool = True,
) -> dict[str, Any]:
    """Execute configured checks and build an evidence report.

    Check commands run only under an existing human-approved lifecycle for this
    campaign/run with a contract-bound task_manifest. When
    ``capture_source_during`` is true, source is hashed before and after
    checks; a mid-check source change marks final-state certification invalid.
    """
    from runspecimen.lease import hold_workspace_lease
    from runspecimen.errors import LeaseError

    workspace = resolve_workspace(workspace)
    approval = assert_checks_authorized(
        workspace=workspace, contract=contract, manifest=manifest
    )
    try:
        with hold_workspace_lease(workspace, holder="requirements-check"):
            return _run_requirements_under_lease(
                workspace=workspace,
                contract=contract,
                manifest=manifest,
                approval=approval,
                capture_source_during=capture_source_during,
            )
    except LeaseError as exc:
        raise AuthorizationError(f"requirements check refused: {exc}") from exc


def _run_requirements_under_lease(
    *,
    workspace: Path,
    contract: Contract,
    manifest: TaskManifest,
    approval: dict[str, Any],
    capture_source_during: bool,
) -> dict[str, Any]:
    source_before, _ = hash_source(
        workspace, list(contract.source.roots), list(contract.source.excludes)
    )
    runtime = runtime_provenance(contract, workspace)
    results: list[dict[str, Any]] = []
    evidence_digests: dict[str, str] = {}
    evidence_artifact_paths: dict[str, str] = {}
    input_fingerprints: dict[str, dict[str, str]] = {}

    for req in manifest.requirements:
        input_fingerprints[req.id] = _fingerprint_requirement_inputs(workspace, req)
        if any(v == "missing" for v in input_fingerprints[req.id].values()):
            results.append(
                {
                    "requirement_id": req.id,
                    "outcome": OUTCOME_ERROR,
                    "check": (
                        {"provider": req.check.provider, "id": req.check.id}
                        if req.check
                        else None
                    ),
                    "error": "declared inputs/source_scope paths missing; cannot certify",
                    "input_fingerprints": input_fingerprints[req.id],
                }
            )
            continue
        if req.manual_unverifiable:
            results.append(
                {
                    "requirement_id": req.id,
                    "outcome": OUTCOME_MANUAL,
                    "check": None,
                    "note": "explicitly manual/unverifiable; not success",
                    "input_fingerprints": input_fingerprints[req.id],
                }
            )
            continue
        assert req.check is not None
        # Caps: check timeout may not exceed contract wall timeout.
        cfg = dict(req.check.config)
        if "timeout_sec" in cfg:
            try:
                t = int(cfg["timeout_sec"])
            except (TypeError, ValueError):
                t = contract.caps.wall_timeout_sec
            cfg["timeout_sec"] = min(t, contract.caps.wall_timeout_sec)
        else:
            cfg["timeout_sec"] = min(120, contract.caps.wall_timeout_sec)

        # Approved check identity must match approval binding when present.
        approved_checks = (approval.get("task_manifest") or {}).get("checks") or []
        identity = sha256_bytes(
            canonical_json_bytes(
                {
                    "provider": req.check.provider,
                    "id": req.check.id,
                    "config": req.check.config,
                }
            )
        )
        if approved_checks:
            match = next(
                (
                    c
                    for c in approved_checks
                    if c.get("requirement_id") == req.id and c.get("identity") == identity
                ),
                None,
            )
            if match is None:
                results.append(
                    {
                        "requirement_id": req.id,
                        "outcome": OUTCOME_ERROR,
                        "check": {
                            "provider": req.check.provider,
                            "id": req.check.id,
                            "identity": identity,
                        },
                        "error": (
                            "check identity not present in approval binding; "
                            "manifest changed after APPROVE"
                        ),
                    }
                )
                continue

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
            config=cfg,
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
                "identity": identity,
            },
            "provider_result": raw,
            "input_fingerprints": input_fingerprints[req.id],
        }
        for key, digest in (raw.get("artifacts") or {}).items():
            if isinstance(digest, str) and len(digest) == 64:
                evidence_digests[f"{req.id}:{key}"] = digest.lower()
            path_val = (raw.get("artifact_paths") or {}).get(key)
            if isinstance(path_val, str):
                evidence_artifact_paths[f"{req.id}:{key}"] = path_val
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
        "manifest_path": (
            contract.task_manifest.path if contract.task_manifest is not None else None
        ),
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
        "policy_sha256": (
            (approval.get("policy") or {}).get("sha256")
            if isinstance(approval.get("policy"), dict)
            else None
        ),
        "input_fingerprints": input_fingerprints,
        "requirements": results,
        "evidence_digests": dict(sorted(evidence_digests.items())),
        "evidence_artifact_paths": dict(sorted(evidence_artifact_paths.items())),
        "summary": summary,
        "aggregate_outcome": aggregate,
        "aggregate_note": aggregate_note,
        "approval_contract_hash": approval.get("contract_hash"),
        "limitations": [
            "Passing configured checks is not universal correctness.",
            "Unchanged final digest does not prove files were never temporarily modified.",
            "Skipped tests and collection errors are visible and are not success.",
            "Artifact digest alone does not authenticate this report.",
        ],
    }
    report = bind_artifact_digest(report)
    return report


def evidence_captures_dir(workspace: Path, campaign_id: str, run_id: str) -> Path:
    return run_state_dir(workspace, campaign_id, run_id) / "evidence_captures"


def write_evidence_report(
    workspace: Path, campaign_id: str, run_id: str, report: dict[str, Any]
) -> Path:
    """Write an immutable capture; never overwrite a prior distinct report."""
    verify_artifact_digest(report)
    digest = report["artifact_digest"]
    captures = evidence_captures_dir(workspace, campaign_id, run_id)
    ensure_dir(captures)
    capture_path = captures / f"evidence_report-{digest[:16]}.json"
    if capture_path.is_file():
        existing = read_json(capture_path)
        if existing.get("artifact_digest") == digest:
            # Identical capture already preserved.
            _update_evidence_pointer(workspace, campaign_id, run_id, capture_path, report)
            return capture_path
        raise EvidenceError(
            "evidence capture path collision with different contents; refusing overwrite"
        )
    atomic_write_json(capture_path, report)
    _update_evidence_pointer(workspace, campaign_id, run_id, capture_path, report)
    return capture_path


def _update_evidence_pointer(
    workspace: Path,
    campaign_id: str,
    run_id: str,
    capture_path: Path,
    report: dict[str, Any],
) -> None:
    """Maintain latest pointer without destroying historical captures."""
    pointer = evidence_report_path(workspace, campaign_id, run_id)
    ensure_dir(pointer.parent)
    meta = {
        "schema_kind": "evidence_report_pointer",
        "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "run_id": run_id,
        "capture_path": str(capture_path.name),
        "evidence_report_digest": report["artifact_digest"],
        "aggregate_outcome": report.get("aggregate_outcome"),
        "note": "Pointer to an immutable capture; historical captures are preserved.",
    }
    atomic_write_json(pointer, bind_artifact_digest(meta))


def load_evidence_report(workspace: Path, campaign_id: str, run_id: str) -> dict[str, Any]:
    path = evidence_report_path(workspace, campaign_id, run_id)
    if not path.is_file():
        raise EvidenceError(f"evidence report not found: {path}")
    doc = read_json(path)
    if not isinstance(doc, dict):
        raise EvidenceError("evidence report must be a JSON object")
    # New layout: pointer → capture. Legacy: direct evidence_report document.
    if doc.get("schema_kind") == "evidence_report_pointer":
        assert_artifact_version(doc.get("schema_version"))
        verify_artifact_digest(doc)
        capture = evidence_captures_dir(workspace, campaign_id, run_id) / str(
            doc.get("capture_path")
        )
        if not capture.is_file():
            raise EvidenceError(f"evidence capture missing: {capture}")
        report = read_json(capture)
    else:
        report = doc
    if not isinstance(report, dict):
        raise EvidenceError("evidence report must be a JSON object")
    assert_schema_kind(report.get("schema_kind"), expected="evidence_report")
    assert_artifact_version(report.get("schema_version"))
    verify_artifact_digest(report)
    return annotate_evidence_authenticity(workspace, campaign_id, run_id, report)


def annotate_evidence_authenticity(
    workspace: Path, campaign_id: str, run_id: str, report: dict[str, Any]
) -> dict[str, Any]:
    """Mark whether the report is bound through a receipt/attestation path."""
    from runspecimen.certificate import load_certificate
    from runspecimen.approve import load_approval

    state_dir = run_state_dir(workspace, campaign_id, run_id)
    cert = load_certificate(state_dir)
    att_path = attestation_path(workspace, campaign_id, run_id)
    attestation = read_json(att_path) if att_path.is_file() else None
    authentic = False
    binding = None
    if isinstance(cert, dict):
        ea = cert.get("evidence_attestation")
        if isinstance(ea, dict) and ea.get("evidence_report_digest") == report.get(
            "artifact_digest"
        ):
            authentic = True
            binding = "certificate.evidence_attestation"
    if not authentic and isinstance(attestation, dict):
        try:
            verify_artifact_digest(attestation)
        except Exception:  # noqa: BLE001
            attestation = None
        if (
            isinstance(attestation, dict)
            and attestation.get("evidence_report_digest") == report.get("artifact_digest")
        ):
            # Sidecar attestation alone is still self-hashed — not receipt-authentic.
            binding = "unanchored_attestation"
    out = dict(report)
    if authentic:
        out["authenticity"] = "receipt_bound"
        out["authenticity_binding"] = binding
        out["authenticity_note"] = (
            "Evidence report digest is bound into the run receipt."
        )
    else:
        out["authenticity"] = "unauthenticated"
        out["authenticity_binding"] = binding
        out["authenticity_note"] = (
            "Checksum/self-digest is internal consistency only, not authenticity. "
            "Bind via postflight receipt evidence_attestation (or signed receipt)."
        )
    # Approval presence is separate from receipt authenticity.
    approval = load_approval(state_dir)
    out["approval_present"] = approval is not None
    return out


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
            "Attestation authenticates the evidence report bytes only when this "
            "digest is bound into a receipt/event/signature. A self-hash alone is "
            "not authenticity."
        ),
    }
    return bind_artifact_digest(att)


def write_evidence_attestation(
    workspace: Path, campaign_id: str, run_id: str, attestation: dict[str, Any]
) -> Path:
    path = attestation_path(workspace, campaign_id, run_id)
    ensure_dir(path.parent)
    verify_artifact_digest(attestation)
    # Preserve prior attestations immutably.
    captures = evidence_captures_dir(workspace, campaign_id, run_id)
    ensure_dir(captures)
    digest = attestation["artifact_digest"]
    capture = captures / f"evidence_attestation-{digest[:16]}.json"
    if not capture.is_file():
        atomic_write_json(capture, attestation)
    atomic_write_json(path, attestation)
    return path


def ci_machine_report(report: dict[str, Any]) -> dict[str, Any]:
    """Compact machine-readable CI output (exit semantics left to caller)."""
    authenticity = report.get("authenticity")
    authentic = authenticity == "receipt_bound"
    return {
        "ok": report.get("aggregate_outcome") == OUTCOME_PASSED
        and report.get("final_state_certifiable") is True
        and authentic,
        "aggregate_outcome": report.get("aggregate_outcome"),
        "final_state_certifiable": report.get("final_state_certifiable"),
        "authenticity": authenticity or "unauthenticated",
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
        "authenticity_note": report.get("authenticity_note"),
    }
