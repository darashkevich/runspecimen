"""Evidence expansion coverage (ADR-005)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PYTHON, RunSpecimenTestCase, approve, base_contract, write_contract

from runspecimen.artifact import bind_artifact_digest, verify_artifact_digest
from runspecimen.atomic import atomic_write_json
from runspecimen.cli import main
from runspecimen.configsync import apply_bundle, build_bundle, preview_apply, rollback_bundle
from runspecimen.contract import load_contract
from runspecimen.decisions import capture_decision, review_flags, search_decisions
from runspecimen.freshness import check_freshness_for_run
from runspecimen.hashutil import sha256_file
from runspecimen.policy import execution_constraints
from runspecimen.requirements import (
    OUTCOME_FAILED,
    OUTCOME_PASSED,
    AuthorizationError,
    EvidenceError,
    load_task_manifest,
    run_requirements,
    write_evidence_report,
)
from runspecimen.snapshot import get_snapshot_provider
from runspecimen.usage import import_usage, summarize_usage
from runspecimen.errors import PreflightError
from runspecimen.certificate import verify_run_receipt
from runspecimen.scenes import run_scenes


def _manifest(req_id: str, provider_config: dict, *, manual: bool = False, mid: str = "m1") -> dict:
    req: dict = {
        "id": req_id,
        "description": "demo requirement",
        "inputs": [],
        "source_scope": ["work"],
        "required_evidence": [],
        "expected": {},
    }
    if manual:
        req["manual_unverifiable"] = True
    else:
        req["check"] = provider_config
    doc = {
        "schema_kind": "task_manifest",
        "schema_version": 1,
        "id": mid,
        "description": "test manifest",
        "requirements": [req],
    }
    return bind_artifact_digest(doc)


def _approved_contract(
    ws: Path, mpath: Path, *, run_id: str = "run-a", mid: str = "m1", **overrides
) -> tuple[Path, object]:
    doc = base_contract(run_id=run_id, **overrides)
    doc["task_manifest"] = {
        "id": mid,
        "path": str(mpath.relative_to(ws)),
        "sha256": sha256_file(mpath),
    }
    cpath = write_contract(ws, f"contract-{run_id}.json", doc)
    approve(ws, cpath)
    return cpath, load_contract(cpath)


class EvidenceExpansionTests(RunSpecimenTestCase):
    def _write_unittest_pass(self) -> Path:
        tests = self.ws / "tests_local"
        tests.mkdir()
        (tests / "test_ok.py").write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        return tests

    def test_existing_showcase_certificate_still_loads(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cert = (
            root
            / "examples"
            / "showcase"
            / ".runspecimen"
            / "runs"
            / "showcase-campaign"
            / "run-001"
            / "certificate.json"
        )
        self.assertTrue(cert.is_file())
        doc = json.loads(cert.read_text(encoding="utf-8"))
        self.assertIn("certificate_id", doc)

    def test_tampered_manifest_digest_detected(self) -> None:
        path = self.ws / "manifest.json"
        doc = _manifest(
            "r1",
            {"provider": "command_status", "id": "c", "config": {"argv": [PYTHON, "-c", "pass"]}},
        )
        atomic_write_json(path, doc)
        raw = json.loads(path.read_text())
        raw["description"] = "tampered"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(Exception):
            load_task_manifest(path)

    def test_agent_passed_field_rejected_in_config(self) -> None:
        path = self.ws / "manifest.json"
        doc = _manifest(
            "r1",
            {
                "provider": "command_status",
                "id": "c",
                "config": {"argv": [PYTHON, "-c", "pass"], "passed": True},
            },
        )
        # bind digest after smuggling would fail parse
        doc.pop("artifact_digest", None)
        doc = bind_artifact_digest(doc)
        atomic_write_json(path, doc)
        with self.assertRaises(EvidenceError):
            load_task_manifest(path)

    def test_missing_failed_skipped_not_success(self) -> None:
        # fail via command_status
        m_fail = self.ws / "m_fail.json"
        atomic_write_json(
            m_fail,
            _manifest(
                "r-fail",
                {
                    "provider": "command_status",
                    "id": "c",
                    "config": {"argv": [PYTHON, "-c", "raise SystemExit(2)"], "exit_code": 0},
                },
                mid="m-fail",
            ),
        )
        _, contract = _approved_contract(self.ws, m_fail, run_id="run-fail", mid="m-fail")
        fail_report = run_requirements(
            workspace=self.ws, contract=contract, manifest=load_task_manifest(m_fail)
        )
        self.assertEqual(fail_report["aggregate_outcome"], OUTCOME_FAILED)

        # manual + empty collection via unittest with no tests
        empty = self.ws / "empty_tests"
        empty.mkdir()
        m_skip = self.ws / "m_skip.json"
        atomic_write_json(
            m_skip,
            bind_artifact_digest(
                {
                    "schema_kind": "task_manifest",
                    "schema_version": 1,
                    "id": "m-skip",
                    "description": "skip/manual",
                    "requirements": [
                        {
                            "id": "manual",
                            "description": "manual",
                            "manual_unverifiable": True,
                            "inputs": [],
                            "source_scope": [],
                            "required_evidence": [],
                            "expected": {},
                        },
                        {
                            "id": "empty",
                            "description": "empty suite",
                            "check": {
                                "provider": "unittest",
                                "id": "u",
                                "config": {"start_dir": "empty_tests", "pattern": "test*.py"},
                            },
                            "inputs": [],
                            "source_scope": [],
                            "required_evidence": [],
                            "expected": {},
                        },
                    ],
                }
            ),
        )
        _, contract2 = _approved_contract(self.ws, m_skip, run_id="run-skip", mid="m-skip")
        skip_report = run_requirements(
            workspace=self.ws, contract=contract2, manifest=load_task_manifest(m_skip)
        )
        self.assertNotEqual(skip_report["aggregate_outcome"], OUTCOME_PASSED)

    def test_source_change_during_checks_invalidates_final_cert(self) -> None:
        from runspecimen import requirements as reqmod

        class MutatingProvider:
            name = "mutating"

            def run(self, *, workspace, check_id, config, requirement):
                (workspace / "work" / "job.py").write_text("# mutated\n", encoding="utf-8")
                return {
                    "outcome": OUTCOME_PASSED,
                    "provider": self.name,
                    "check_id": check_id,
                    "artifacts": {},
                }

        reqmod.register_provider(MutatingProvider())
        mpath = self.ws / "m.json"
        atomic_write_json(
            mpath,
            _manifest("r1", {"provider": "mutating", "id": "m", "config": {}}, mid="m-mut"),
        )
        _, contract = _approved_contract(self.ws, mpath, run_id="run-mut", mid="m-mut")
        report = run_requirements(
            workspace=self.ws, contract=contract, manifest=load_task_manifest(mpath)
        )
        self.assertTrue(report["source_changed_during_checks"])
        self.assertFalse(report["final_state_certifiable"])
        self.assertNotEqual(report["aggregate_outcome"], OUTCOME_PASSED)

    def test_requirement_edit_invalidates_applicability(self) -> None:
        mpath = self.ws / "m.json"
        atomic_write_json(
            mpath,
            _manifest(
                "r1",
                {
                    "provider": "command_status",
                    "id": "c",
                    "config": {"argv": [PYTHON, "-c", "pass"]},
                },
                mid="m-edit",
            ),
        )
        _, contract = _approved_contract(self.ws, mpath, run_id="run-edit", mid="m-edit")
        report = run_requirements(
            workspace=self.ws, contract=contract, manifest=load_task_manifest(mpath)
        )
        write_evidence_report(self.ws, contract.campaign_id, contract.run_id, report)
        # Edit manifest
        new_doc = _manifest(
            "r1",
            {
                "provider": "command_status",
                "id": "c",
                "config": {"argv": [PYTHON, "-c", "pass"], "timeout_sec": 5},
            },
            mid="m-edit",
        )
        atomic_write_json(mpath, new_doc)
        fresh = check_freshness_for_run(
            workspace=self.ws,
            contract=contract,
            manifest=load_task_manifest(mpath),
        )
        self.assertEqual(fresh["applicability"], "stale")

    def test_unapproved_run_requirements_refuses(self) -> None:
        mpath = self.ws / "m.json"
        atomic_write_json(
            mpath,
            _manifest(
                "r1",
                {
                    "provider": "command_status",
                    "id": "c",
                    "config": {"argv": [PYTHON, "-c", "pass"]},
                },
            ),
        )
        cpath = write_contract(self.ws, "contract.json", base_contract())
        with self.assertRaises(AuthorizationError):
            run_requirements(
                workspace=self.ws,
                contract=load_contract(cpath),
                manifest=load_task_manifest(mpath),
            )

    def test_policy_refusal_actionable(self) -> None:
        policy = self.ws / "policy.json"
        atomic_write_json(
            policy,
            {
                "version": 1,
                "id": "p1",
                "protected_paths": ["work/job.py"],
                "expected_outputs": ["outputs/out.json"],
            },
        )
        doc = base_contract()
        doc["outputs"]["required"] = ["work/job.py"]
        doc["postflight"]["json_equals"] = []
        doc["policy"] = {
            "id": "p1",
            "path": "policy.json",
            "sha256": sha256_file(policy),
        }
        cpath = write_contract(self.ws, "c.json", doc)
        with self.assertRaises(PreflightError) as ctx:
            execution_constraints(load_contract(cpath), self.ws)
        self.assertIn("policy refusal", str(ctx.exception))

    def test_config_conflict_and_rollback(self) -> None:
        a = build_bundle(bundle_id="a", settings={"x": 1})
        b = build_bundle(bundle_id="b", settings={"x": 2})
        apply_bundle(self.ws, a)
        preview = preview_apply(self.ws, b)
        self.assertIn("x", preview["conflicts"])
        applied = apply_bundle(self.ws, b)
        self.assertTrue(applied["backup"])
        rolled = rollback_bundle(self.ws, Path(applied["backup"]))
        self.assertEqual(rolled["bundle_id"], "a")

    def test_snapshot_preview_preserves_user_changes(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        contract = load_contract(cpath)
        provider = get_snapshot_provider("local_tar")
        record = provider.create(
            workspace=self.ws,
            snapshot_id="s1",
            roots=list(contract.source.roots),
            excludes=list(contract.source.excludes),
        )
        (self.ws / "work" / "user.txt").write_text("keep\n", encoding="utf-8")
        dest = Path(tempfile.mkdtemp(prefix="rs-restore-"))
        preview = provider.preview_restore(workspace=self.ws, record=record, dest=dest)
        self.assertTrue(preview["ok"])
        with self.assertRaises(Exception):
            provider.restore(workspace=self.ws, record=record, dest=self.ws)
        provider.restore(workspace=self.ws, record=record, dest=dest)
        self.assertTrue((self.ws / "work" / "user.txt").is_file())

    def test_usage_duplicate_and_unknown(self) -> None:
        export = self.ws / "usage.json"
        atomic_write_json(
            export,
            {
                "events": [
                    {
                        "import_key": "k1",
                        "provider": "p",
                        "amount_kind": "unknown",
                        "confidence": "unknown",
                    },
                    {
                        "import_key": "k2",
                        "provider": "p",
                        "amount_kind": "billed",
                        "amount": 3,
                        "currency": "USD",
                        "task_id": "t1",
                        "confidence": "high",
                    },
                ]
            },
        )
        first = import_usage(workspace=self.ws, provider_name="local_json", export_path=export)
        second = import_usage(workspace=self.ws, provider_name="local_json", export_path=export)
        self.assertEqual(first["added"], 2)
        self.assertEqual(second["duplicates"], 2)
        summary = summarize_usage(self.ws)
        self.assertGreaterEqual(summary["unknown_amount_events"], 1)
        self.assertGreaterEqual(summary["unallocated_events"], 1)

    def test_decision_search_and_stale_flag(self) -> None:
        target = self.ws / "work" / "job.py"
        digest = sha256_file(target)
        capture_decision(
            workspace=self.ws,
            decision_id="d1",
            rationale="retries disabled because not idempotent",
            classification="human",
            stale_when=[{"path": "work/job.py", "sha256": digest}],
        )
        hits = search_decisions(self.ws, "idempotent")
        self.assertEqual(len(hits), 1)
        target.write_text("# changed\n", encoding="utf-8")
        flags = review_flags(self.ws)
        self.assertTrue(any(f.get("reason") == "referenced_input_changed" for f in flags))

    def test_tampered_evidence_report_detected(self) -> None:
        mpath = self.ws / "m.json"
        atomic_write_json(
            mpath,
            _manifest(
                "r1",
                {
                    "provider": "command_status",
                    "id": "c",
                    "config": {"argv": [PYTHON, "-c", "pass"]},
                },
                mid="m-tamp",
            ),
        )
        _, contract = _approved_contract(self.ws, mpath, run_id="run-tamp", mid="m-tamp")
        report = run_requirements(
            workspace=self.ws, contract=contract, manifest=load_task_manifest(mpath)
        )
        path = write_evidence_report(self.ws, contract.campaign_id, contract.run_id, report)
        raw = json.loads(path.read_text())
        raw["aggregate_outcome"] = "failed" if raw.get("aggregate_outcome") == "passed" else "passed"
        path.write_text(json.dumps(raw), encoding="utf-8")
        from runspecimen.requirements import load_evidence_report

        with self.assertRaises(Exception):
            load_evidence_report(self.ws, contract.campaign_id, contract.run_id)

    def test_scenes_demo_runs(self) -> None:
        result = run_scenes(workspace=self.ws, prepare_only=False)
        self.assertTrue(result["ok"], msg=json.dumps(result, indent=2, default=str))
        self.assertEqual(len(result["scenes"]), 10)
        self.assertIn("APPROVE", result["human_approve_instructions"])
        self.assertNotIn("\nAPPROVE\n", json.dumps(result))

    def test_cli_requirements_and_doctor(self) -> None:
        mpath = self.ws / "m.json"
        atomic_write_json(
            mpath,
            _manifest(
                "r1",
                {
                    "provider": "command_status",
                    "id": "c",
                    "config": {"argv": [PYTHON, "-c", "pass"]},
                },
                mid="m-cli",
            ),
        )
        cpath = write_contract(self.ws, "contract.json", base_contract())
        # Unapproved check must refuse (not execute).
        self.assertEqual(
            main(
                [
                    "requirements",
                    "check",
                    "--workspace",
                    str(self.ws),
                    "--contract",
                    str(cpath),
                    "--manifest",
                    str(mpath),
                ]
            ),
            2,
        )
        self.assertEqual(main(["doctor", "--workspace", str(self.ws)]), 0)
        self.assertEqual(
            main(["requirements", "validate", "--manifest", str(mpath)]),
            0,
        )


if __name__ == "__main__":
    unittest.main()
