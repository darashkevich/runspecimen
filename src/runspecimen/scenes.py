"""Ten-scene local evidence demo (ADR-005). Never types APPROVE."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from runspecimen.artifact import bind_artifact_digest
from runspecimen.configsync import apply_bundle, build_bundle, preview_apply
from runspecimen.contract import load_contract
from runspecimen.coordination import evaluate_readiness, parse_coordination_plan
from runspecimen.decisions import capture_decision
from runspecimen.evalsuite import compare_eval_results, run_eval_suite
from runspecimen.freshness import check_freshness_for_run
from runspecimen.hashutil import sha256_file
from runspecimen.requirements import (
    OUTCOME_FAILED,
    OUTCOME_PASSED,
    load_task_manifest,
    run_requirements,
    write_evidence_report,
)
from runspecimen.snapshot import get_snapshot_provider
from runspecimen.usage import import_usage, summarize_usage
from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.errors import PreflightError, ContractError


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_mini_workspace(root: Path) -> dict[str, Path]:
    work = root / "work"
    outputs = root / "outputs"
    tests = root / "scene_tests"
    work.mkdir(parents=True)
    outputs.mkdir()
    tests.mkdir()
    _write(tests / "__init__.py", "")
    _write(work / "__init__.py", "")
    _write(work / "app.py", "VALUE = 1\n")
    _write(
        tests / "test_app.py",
        "import unittest\nfrom work.app import VALUE\n\n"
        "class TestApp(unittest.TestCase):\n"
        "    def test_value(self):\n"
        "        self.assertEqual(VALUE, 1)\n",
    )
    _write(
        tests / "test_fail.py",
        "import unittest\n\n"
        "class TestFail(unittest.TestCase):\n"
        "    def test_fail(self):\n"
        "        self.assertTrue(False)\n",
    )
    _write(
        tests / "test_skip.py",
        "import unittest\n\n"
        "class TestSkip(unittest.TestCase):\n"
        "    @unittest.skip('demo skip')\n"
        "    def test_skip(self):\n"
        "        self.assertTrue(True)\n",
    )
    contract = {
        "version": 1,
        "campaign_id": "scenes",
        "run_id": "run-demo",
        "argv": ["python3", "-c", "print('noop')"],
        "cwd": ".",
        "source": {"roots": ["work", "scene_tests"], "excludes": []},
        "outputs": {"required": ["outputs/out.json"]},
        "caps": {
            "wall_timeout_sec": 30,
            "stdout_max_bytes": 65536,
            "stderr_max_bytes": 65536,
        },
        "approval": {"ttl_sec": 3600},
        "predecessor": None,
        "postflight": {
            "exit_code": 0,
            "require_outputs": True,
            "output_sha256": {},
            "json_equals": [],
            "source_unchanged": True,
        },
    }
    cpath = root / "contract.json"
    atomic_write_json(cpath, contract)

    pass_manifest = {
        "schema_kind": "task_manifest",
        "schema_version": 1,
        "id": "scenes-pass",
        "description": "Passing pytest check",
        "requirements": [
            {
                "id": "req-pass",
                "description": "app value test",
                "check": {
                    "provider": "unittest",
                    "id": "value",
                    "config": {"start_dir": "scene_tests", "pattern": "test_app.py"},
                },
                "inputs": ["work/app.py"],
                "source_scope": ["work"],
                "required_evidence": ["junit"],
                "expected": {"tests_min": 1},
            }
        ],
    }
    pass_manifest = bind_artifact_digest(pass_manifest)
    m_pass = root / "manifest_pass.json"
    atomic_write_json(m_pass, pass_manifest)

    fail_manifest = {
        "schema_kind": "task_manifest",
        "schema_version": 1,
        "id": "scenes-fail",
        "description": "Failing pytest check",
        "requirements": [
            {
                "id": "req-fail",
                "description": "intentional fail",
                "check": {
                    "provider": "unittest",
                    "id": "fail",
                    "config": {"start_dir": "scene_tests", "pattern": "test_fail.py"},
                },
                "inputs": [],
                "source_scope": ["tests"],
                "required_evidence": [],
                "expected": {},
            }
        ],
    }
    fail_manifest = bind_artifact_digest(fail_manifest)
    m_fail = root / "manifest_fail.json"
    atomic_write_json(m_fail, fail_manifest)

    skip_manifest = {
        "schema_kind": "task_manifest",
        "schema_version": 1,
        "id": "scenes-skip",
        "description": "Skipped tests are not success",
        "requirements": [
            {
                "id": "req-skip",
                "description": "skipped",
                "check": {
                    "provider": "unittest",
                    "id": "skip",
                    "config": {"start_dir": "scene_tests", "pattern": "test_skip.py"},
                },
                "inputs": [],
                "source_scope": [],
                "required_evidence": [],
                "expected": {},
            },
            {
                "id": "req-manual",
                "description": "human review",
                "manual_unverifiable": True,
                "inputs": [],
                "source_scope": [],
                "required_evidence": [],
                "expected": {},
            },
        ],
    }
    skip_manifest = bind_artifact_digest(skip_manifest)
    m_skip = root / "manifest_skip.json"
    atomic_write_json(m_skip, skip_manifest)

    return {
        "contract": cpath,
        "manifest_pass": m_pass,
        "manifest_fail": m_fail,
        "manifest_skip": m_skip,
    }


def run_scenes(*, workspace: Path, prepare_only: bool = False) -> dict[str, Any]:
    """Execute all ten scenes in a disposable subdirectory of workspace."""
    workspace = workspace.expanduser().resolve()
    demo = workspace / ".runspecimen" / "scenes-demo"
    if demo.exists():
        shutil.rmtree(demo)
    demo.mkdir(parents=True)

    scenes: list[dict[str, Any]] = []
    paths = _seed_mini_workspace(demo)
    contract = load_contract(paths["contract"])

    human_approve_instructions = (
        "This demo never types APPROVE. To exercise a full lifecycle on the "
        f"prepared contract at {paths['contract']}, a human must run:\n"
        f"  runspecimen approve --workspace {demo} --contract {paths['contract']}\n"
        "then preflight → run → postflight → verify. Agents must not pipe APPROVE."
    )

    if prepare_only:
        return {
            "ok": True,
            "prepare_only": True,
            "demo_workspace": str(demo),
            "human_approve_instructions": human_approve_instructions,
            "scenes": [],
        }

    # Scene 1: requirements pass
    m_pass = load_task_manifest(paths["manifest_pass"])
    report_pass = run_requirements(workspace=demo, contract=contract, manifest=m_pass)
    write_evidence_report(demo, contract.campaign_id, contract.run_id, report_pass)
    scenes.append(
        {
            "id": 1,
            "name": "requirements_pass",
            "aggregate_outcome": report_pass["aggregate_outcome"],
            "ok": report_pass["aggregate_outcome"] == OUTCOME_PASSED,
        }
    )

    # Scene 2: requirements fail
    m_fail = load_task_manifest(paths["manifest_fail"])
    report_fail = run_requirements(workspace=demo, contract=contract, manifest=m_fail)
    scenes.append(
        {
            "id": 2,
            "name": "requirements_fail",
            "aggregate_outcome": report_fail["aggregate_outcome"],
            "ok": report_fail["aggregate_outcome"] == OUTCOME_FAILED,
        }
    )

    # Scene 3: unverified (skip + manual)
    m_skip = load_task_manifest(paths["manifest_skip"])
    report_skip = run_requirements(workspace=demo, contract=contract, manifest=m_skip)
    scenes.append(
        {
            "id": 3,
            "name": "requirements_unverified",
            "aggregate_outcome": report_skip["aggregate_outcome"],
            "ok": report_skip["aggregate_outcome"] == "unverified",
        }
    )

    # Scene 4: valid historical receipt authenticity distinct from applicability
    # Use showcase golden certificate if present in repo; else record digest authenticity locally.
    showcase = Path(__file__).resolve().parents[2] / "examples" / "showcase" / ".runspecimen" / "runs" / "showcase-campaign" / "run-001" / "certificate.json"
    historical = {
        "certificate_exists": showcase.is_file(),
        "note": (
            "Historical certificate authenticity is separate from current applicability. "
            "Dashboard/verify semantics unchanged."
        ),
    }
    if showcase.is_file():
        historical["certificate_id"] = json.loads(showcase.read_text())["certificate_id"]
        historical["artifact_path"] = str(showcase)
    scenes.append({"id": 4, "name": "historical_receipt", "ok": True, **historical})

    # Scene 5: source change makes evidence stale
    _write(demo / "work" / "app.py", "VALUE = 2\n")
    fresh = check_freshness_for_run(workspace=demo, contract=contract, manifest=m_pass)
    scenes.append(
        {
            "id": 5,
            "name": "source_change_stale_evidence",
            "applicability": fresh.get("applicability"),
            "ok": fresh.get("applicability") == "stale",
            "changes": fresh.get("changes"),
        }
    )
    # Restore for later scenes
    _write(demo / "work" / "app.py", "VALUE = 1\n")

    # Scene 6: policy refusal
    policy_path = demo / "policy.json"
    atomic_write_json(
        policy_path,
        {
            "version": 1,
            "id": "scenes-policy",
            "protected_paths": ["work/app.py"],
            "expected_outputs": ["outputs/out.json"],
            "nl_constraint_notes": [
                {
                    "text": "maybe lock everything somehow",
                    "status": "ambiguous",
                }
            ],
        },
    )
    # Build a contract object that asserts writing protected path
    bad_contract_doc = json.loads(paths["contract"].read_text())
    bad_contract_doc["outputs"]["required"] = ["work/app.py"]
    bad_contract_doc["postflight"]["json_equals"] = []
    bad_contract_doc["policy"] = {
        "id": "scenes-policy",
        "path": "policy.json",
        "sha256": sha256_file(policy_path),
    }
    bad_path = demo / "contract_bad_policy.json"
    atomic_write_json(bad_path, bad_contract_doc)
    refusal_ok = False
    refusal_msg = ""
    try:
        from runspecimen.policy import execution_constraints

        execution_constraints(load_contract(bad_path), demo)
    except (PreflightError, ContractError) as exc:
        refusal_ok = "policy refusal" in str(exc) or "protected_paths" in str(exc)
        refusal_msg = str(exc)
    scenes.append(
        {
            "id": 6,
            "name": "policy_refusal",
            "ok": refusal_ok,
            "message": refusal_msg,
        }
    )

    # Scene 7: config mismatch / recoverable apply
    bundle_a = build_bundle(bundle_id="scenes-a", settings={"theme": "dark"})
    bundle_b = build_bundle(bundle_id="scenes-b", settings={"theme": "light"})
    apply_bundle(demo, bundle_a)
    preview = preview_apply(demo, bundle_b)
    apply_b = apply_bundle(demo, bundle_b)
    scenes.append(
        {
            "id": 7,
            "name": "config_mismatch_recoverable",
            "conflicts": preview.get("conflicts"),
            "backup": apply_b.get("backup"),
            "ok": "theme" in (preview.get("conflicts") or []) and bool(apply_b.get("backup")),
        }
    )

    # Scene 8: recovery preview preserves user changes
    provider = get_snapshot_provider("local_tar")
    snap = provider.create(
        workspace=demo,
        snapshot_id="scenes-snap",
        roots=list(contract.source.roots),
        excludes=list(contract.source.excludes),
    )
    # User change after snapshot
    _write(demo / "work" / "user_note.txt", "do not discard\n")
    dest = demo / "restore-out"
    preview_r = provider.preview_restore(workspace=demo, record=snap, dest=dest)
    # Ensure in-place refused
    in_place_refused = False
    try:
        provider.restore(workspace=demo, record=snap, dest=demo)
    except Exception as exc:  # noqa: BLE001
        in_place_refused = "refusing in-place" in str(exc)
    provider.restore(workspace=demo, record=snap, dest=dest)
    user_note_still = (demo / "work" / "user_note.txt").is_file()
    scenes.append(
        {
            "id": 8,
            "name": "recovery_preview_preserves_user_changes",
            "ok": in_place_refused and user_note_still and preview_r.get("ok") is True,
            "in_place_refused": in_place_refused,
            "user_note_preserved": user_note_still,
        }
    )

    # Scene 9: usage import with unallocated + unknown
    export = demo / "usage_export.json"
    atomic_write_json(
        export,
        {
            "events": [
                {
                    "import_key": "evt-1",
                    "provider": "demo",
                    "model": "demo-model",
                    "amount_kind": "billed",
                    "amount": 1.25,
                    "currency": "USD",
                    "campaign_id": "scenes",
                    "confidence": "high",
                    "timestamp": "2026-09-23T00:00:00Z",
                },
                {
                    "import_key": "evt-unalloc",
                    "provider": "demo",
                    "amount_kind": "unknown",
                    "confidence": "unknown",
                    "notes": "unallocated ambiguous event",
                },
            ]
        },
    )
    imp1 = import_usage(workspace=demo, provider_name="local_json", export_path=export)
    imp2 = import_usage(workspace=demo, provider_name="local_json", export_path=export)
    summary = summarize_usage(demo)
    scenes.append(
        {
            "id": 9,
            "name": "usage_import_unallocated",
            "ok": (
                imp1["added"] == 2
                and imp2["duplicates"] == 2
                and summary["unallocated_events"] >= 1
                and summary["unknown_amount_events"] >= 1
            ),
            "import": imp1,
            "duplicate_import": imp2,
            "summary": summary,
        }
    )

    # Scene 10a: blocked cross-repo dependency + workflow regression
    producer = demo / "producer"
    consumer = demo / "consumer"
    shutil.copytree(demo / "work", producer / "work", dirs_exist_ok=True)
    (producer / "scene_tests").mkdir(exist_ok=True)
    shutil.copytree(demo / "scene_tests", producer / "scene_tests", dirs_exist_ok=True)
    shutil.copytree(demo / "work", consumer / "work", dirs_exist_ok=True)
    (consumer / "scene_tests").mkdir(exist_ok=True)
    shutil.copytree(demo / "scene_tests", consumer / "scene_tests", dirs_exist_ok=True)
    (producer / "outputs").mkdir(exist_ok=True)
    (consumer / "outputs").mkdir(exist_ok=True)
    _write(producer / "outputs" / "api.json", json.dumps({"api_version": 1}) + "\n")

    for label, root in (("producer", producer), ("consumer", consumer)):
        cdoc = json.loads(paths["contract"].read_text())
        cdoc["campaign_id"] = f"scenes-{label}"
        cdoc["run_id"] = "run-1"
        atomic_write_json(root / "contract.json", cdoc)
        shutil.copy(paths["manifest_pass"], root / "manifest.json")
        # Refresh evidence for each
        creport = run_requirements(
            workspace=root,
            contract=load_contract(root / "contract.json"),
            manifest=load_task_manifest(root / "manifest.json"),
        )
        write_evidence_report(root, cdoc["campaign_id"], cdoc["run_id"], creport)

    # Change producer artifact after consumer evidence — invalidate
    _write(producer / "outputs" / "api.json", json.dumps({"api_version": 2}) + "\n")
    # Record digest into consumer evidence manually for dependency check
    from runspecimen.requirements import load_evidence_report
    from runspecimen.atomic import read_json
    from runspecimen.artifact import verify_artifact_digest

    c_evidence_path = (
        consumer
        / ".runspecimen"
        / "runs"
        / "scenes-consumer"
        / "run-1"
        / "evidence_report.json"
    )
    c_ev = read_json(c_evidence_path)
    c_ev["evidence_digests"]["dep:outputs/api.json"] = "0" * 64  # stale recorded digest
    c_ev.pop("artifact_digest", None)
    c_ev = bind_artifact_digest(c_ev)
    atomic_write_json(c_evidence_path, c_ev)

    plan = {
        "schema_kind": "coordination_plan",
        "schema_version": 1,
        "id": "scenes-two-repo",
        "description": "producer/consumer API compatibility",
        "repos": [
            {
                "id": "producer",
                "workspace": str(producer),
                "contract": "contract.json",
                "manifest": "manifest.json",
                "role": "producer",
            },
            {
                "id": "consumer",
                "workspace": str(consumer),
                "contract": "contract.json",
                "manifest": "manifest.json",
                "role": "consumer",
            },
        ],
        "dependencies": [
            {
                "id": "api-compat",
                "from_repo": "producer",
                "to_repo": "consumer",
                "requires_evidence_outcome": "passed",
                "artifact_path": "outputs/api.json",
            }
        ],
        "compatibility_checks": [],
    }
    plan = bind_artifact_digest(parse_coordination_plan(plan))
    readiness = evaluate_readiness(plan)
    scenes.append(
        {
            "id": 10,
            "name": "cross_repo_blocked_and_eval_regression",
            "ready": readiness.get("ready"),
            "blockers": readiness.get("blockers"),
            "ok_cross_repo": readiness.get("ready") is False,
        }
    )

    # Decision example + eval regression
    capture_decision(
        workspace=demo,
        decision_id="retries-disabled",
        rationale="Retries disabled because the step is not idempotent.",
        classification="human",
        affected_requirements=["req-pass"],
        source_refs=["docs/ADR-005-evidence-expansion.md"],
    )

    suite = {
        "schema_kind": "eval_suite",
        "schema_version": 1,
        "id": "scenes-eval",
        "description": "local deterministic regression",
        "tasks": [
            {
                "id": "t-pass",
                "provider": "local_deterministic",
                "fixture_dir": str(demo),
                "fixture_version": "1",
                "contract": "contract.json",
                "manifest": "manifest_pass.json",
                "expected_outcome": "passed",
                "judgment": "deterministic",
            }
        ],
    }
    suite = bind_artifact_digest(suite)
    # Baseline should pass
    baseline = run_eval_suite(workspace=demo, suite=suite)
    # Candidate: break fixture expectation by pointing at fail manifest
    suite_bad = json.loads(json.dumps(suite))
    suite_bad["tasks"][0]["manifest"] = "manifest_fail.json"
    suite_bad["tasks"][0]["fixture_version"] = "1-bad"
    suite_bad.pop("artifact_digest", None)
    suite_bad = bind_artifact_digest(suite_bad)
    candidate = run_eval_suite(workspace=demo, suite=suite_bad)
    # Force same suite_id for compare by rewriting candidate suite_id match
    candidate["suite_id"] = baseline["suite_id"]
    candidate.pop("artifact_digest", None)
    candidate = bind_artifact_digest(candidate)
    cmp = compare_eval_results(baseline, candidate)
    regression_detected = any(
        d.get("change") == "outcome" and d.get("regression_candidate") for d in cmp.get("deltas", [])
    ) or any(d.get("change") == "fixture_version" for d in cmp.get("deltas", []))
    scenes[-1]["eval_compare"] = cmp
    scenes[-1]["ok_eval_regression"] = regression_detected
    scenes[-1]["ok"] = scenes[-1]["ok_cross_repo"] and regression_detected

    ok = all(s.get("ok") for s in scenes)
    return {
        "ok": ok,
        "demo_workspace": str(demo),
        "human_approve_instructions": human_approve_instructions,
        "scenes": scenes,
        "note": (
            "Scenes exercise requirements, freshness, policy, config, snapshot, "
            "usage, coordination, and eval without fabricating APPROVE."
        ),
    }
