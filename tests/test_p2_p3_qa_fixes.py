"""Regression tests for remaining P2/P3 QA findings on evidence-expansion PR."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PYTHON, RunSpecimenTestCase, approve, base_contract, write_contract

from runspecimen.artifact import bind_artifact_digest, verify_artifact_digest
from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.certificate import CertificateError, verify_run_receipt
from runspecimen.cli import main
from runspecimen.configsync import (
    active_bundle_path,
    apply_bundle,
    export_bundle,
)
from runspecimen.contract import load_contract
from runspecimen.coordination import evaluate_readiness, parse_coordination_plan
from runspecimen.errors import PreflightError
from runspecimen.evalsuite import compare_eval_results
from runspecimen.events import utc_now_iso
from runspecimen.freshness import evaluate_freshness
from runspecimen.hashutil import hash_source
from runspecimen.paths import resolve_workspace
from runspecimen.policy import execution_constraints
from runspecimen.preflight import preflight
from runspecimen.postflight import postflight
from runspecimen.requirements import Requirement, _fingerprint_requirement_inputs
from runspecimen.run import run_contract
from runspecimen.snapshot import SnapshotError, get_snapshot_provider


def _policy_blob(doc: dict) -> tuple[bytes, str]:
    blob = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return blob, hashlib.sha256(blob).hexdigest()


class ConfigSecretStripTests(RunSpecimenTestCase):
    def test_p2_apply_and_export_strip_secret_like_keys(self) -> None:
        # Digest-bound bundle that includes keys build_bundle would strip.
        leaky = bind_artifact_digest(
            {
                "schema_kind": "config_bundle",
                "schema_version": 1,
                "id": "leaky",
                "created_at": utc_now_iso(),
                "settings": {
                    "theme": "dark",
                    "api_key": "SHOULD-NOT-PERSIST",
                    "retry_limit": 3,
                },
                "env": {
                    "RUNSPECIMEN_TOKEN": "tok-secret",
                    "RUNSPECIMEN_FOO": "keep-me",
                },
                "secret_keys_excluded": [],
                "precedence": [
                    "explicit CLI flags",
                    "active config bundle",
                    "environment",
                    "defaults",
                ],
                "note": "adversarial secret-bearing bundle",
            }
        )
        verify_artifact_digest(leaky)
        applied = apply_bundle(self.ws, leaky)
        self.assertTrue(applied["ok"])
        active = read_json(active_bundle_path(self.ws))
        verify_artifact_digest(active)
        self.assertEqual(active["settings"].get("theme"), "dark")
        self.assertEqual(active["settings"].get("retry_limit"), 3)
        self.assertNotIn("api_key", active["settings"])
        self.assertEqual(active["env"].get("RUNSPECIMEN_FOO"), "keep-me")
        self.assertNotIn("RUNSPECIMEN_TOKEN", active["env"])
        self.assertIn("api_key", active["secret_keys_excluded"])
        self.assertIn("RUNSPECIMEN_TOKEN", active["secret_keys_excluded"])

        out = Path(tempfile.mkdtemp(prefix="rs-cfg-export-")) / "export.json"
        exported = export_bundle(self.ws, out)
        self.assertTrue(exported["ok"])
        doc = read_json(out)
        verify_artifact_digest(doc)
        self.assertNotIn("api_key", doc.get("settings") or {})
        self.assertNotIn("RUNSPECIMEN_TOKEN", doc.get("env") or {})
        self.assertEqual(doc["settings"]["theme"], "dark")
        self.assertEqual(doc["env"]["RUNSPECIMEN_FOO"], "keep-me")


class FreshnessAuthenticityTests(RunSpecimenTestCase):
    def test_p2_evaluate_freshness_raw_missing_authenticity_not_applicable(self) -> None:
        cpath = write_contract(self.ws, "c.json", base_contract())
        contract = load_contract(cpath)
        source_hash, _ = hash_source(
            self.ws, list(contract.source.roots), list(contract.source.excludes)
        )
        # Digest-valid report that skipped annotate_evidence_authenticity.
        evidence = bind_artifact_digest(
            {
                "schema_kind": "evidence_report",
                "schema_version": 1,
                "campaign_id": contract.campaign_id,
                "run_id": contract.run_id,
                "contract_hash": contract.contract_hash,
                "manifest_id": None,
                "manifest_hash": None,
                "source_hash_before": source_hash,
                "source_hash_after": source_hash,
                "source_changed_during_checks": False,
                "final_state_certifiable": True,
                "runtime_fingerprint": {},
                "input_fingerprints": {},
                "requirements": [],
                "evidence_digests": {},
                "summary": {
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "error": 0,
                    "unverified": 0,
                    "manual_unverifiable": 0,
                    "total": 0,
                },
                "aggregate_outcome": "passed",
                "aggregate_note": "raw api stub",
            }
        )
        verify_artifact_digest(evidence)
        self.assertNotIn("authenticity", evidence)
        fresh = evaluate_freshness(
            workspace=self.ws, contract=contract, manifest=None, evidence=evidence
        )
        self.assertNotEqual(fresh["applicability"], "applicable")
        self.assertTrue(
            any(c.get("kind") == "authenticity" for c in fresh.get("changes") or [])
        )


class RequiredVerificationTests(RunSpecimenTestCase):
    def test_p2_unsupported_verification_step_fails_validation(self) -> None:
        policy = {
            "version": 1,
            "id": "p-bad",
            "required_verification": ["not_a_real_step"],
        }
        blob, digest = _policy_blob(policy)
        (self.ws / "policy.json").write_bytes(blob)
        doc = base_contract(
            policy={"id": "p-bad", "path": "policy.json", "sha256": digest}
        )
        cpath = write_contract(self.ws, "c.json", doc)
        with self.assertRaises(PreflightError) as ctx:
            execution_constraints(load_contract(cpath), self.ws)
        self.assertIn("unsupported step", str(ctx.exception))

    def test_p2_required_verification_refuses_verify_without_evidence(self) -> None:
        policy = {
            "version": 1,
            "id": "p-req",
            "required_verification": ["requirements_check", "freshness_applicable"],
        }
        blob, digest = _policy_blob(policy)
        (self.ws / "policy.json").write_bytes(blob)
        doc = base_contract(
            policy={"id": "p-req", "path": "policy.json", "sha256": digest},
            argv=[PYTHON, "work/job.py"],
        )
        cpath = write_contract(self.ws, "c.json", doc)
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        # Postflight succeeds (certificate issued) — completion gate is verify.
        postflight(contract_path=cpath, workspace=self.ws)
        contract = load_contract(cpath)
        with self.assertRaises(CertificateError) as ctx:
            verify_run_receipt(
                workspace=self.ws,
                campaign_id=contract.campaign_id,
                run_id=contract.run_id,
                contract=contract,
                require_live_provenance=True,
            )
        msg = str(ctx.exception)
        self.assertIn("required_verification", msg)
        self.assertIn("requirements_check", msg)


class CoordinationArtifactTests(RunSpecimenTestCase):
    def test_p2_declared_artifact_missing_digest_blocks_readiness(self) -> None:
        producer = Path(tempfile.mkdtemp(prefix="rs-prod-"))
        consumer = Path(tempfile.mkdtemp(prefix="rs-cons-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(producer, ignore_errors=True))
        self.addCleanup(lambda: __import__("shutil").rmtree(consumer, ignore_errors=True))
        for root in (producer, consumer):
            (root / "work").mkdir()
            (root / "outputs").mkdir()
            (root / "work" / "job.py").write_text(
                "from pathlib import Path\n"
                "import json\n"
                "Path('outputs/out.json').write_text(json.dumps({'status':'ok'})+'\\n')\n",
                encoding="utf-8",
            )
            write_contract(root, "contract.json", base_contract(run_id="run-1"))
        (producer / "outputs" / "api.json").write_text(
            json.dumps({"api_version": 1}) + "\n", encoding="utf-8"
        )
        # Consumer evidence exists and is "passed" but records no producer digest.
        c_contract = load_contract(consumer / "contract.json")
        evidence = bind_artifact_digest(
            {
                "schema_kind": "evidence_report",
                "schema_version": 1,
                "campaign_id": c_contract.campaign_id,
                "run_id": c_contract.run_id,
                "contract_hash": c_contract.contract_hash,
                "manifest_id": "m",
                "manifest_hash": "a" * 64,
                "source_hash_before": "b" * 64,
                "source_hash_after": "b" * 64,
                "source_changed_during_checks": False,
                "final_state_certifiable": True,
                "runtime_fingerprint": {},
                "input_fingerprints": {},
                "requirements": [{"requirement_id": "r1", "outcome": "passed"}],
                "evidence_digests": {},
                "summary": {
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                    "error": 0,
                    "unverified": 0,
                    "manual_unverifiable": 0,
                    "total": 1,
                },
                "aggregate_outcome": "passed",
                "aggregate_note": "no producer digest",
            }
        )
        from runspecimen.requirements import write_evidence_report

        write_evidence_report(
            consumer, c_contract.campaign_id, c_contract.run_id, evidence
        )
        # Producer also needs some evidence so repo-level blockers do not dominate.
        p_contract = load_contract(producer / "contract.json")
        write_evidence_report(
            producer,
            p_contract.campaign_id,
            p_contract.run_id,
            bind_artifact_digest(
                {
                    **{k: v for k, v in evidence.items() if k != "artifact_digest"},
                    "campaign_id": p_contract.campaign_id,
                    "run_id": p_contract.run_id,
                    "contract_hash": p_contract.contract_hash,
                }
            ),
        )

        plan = bind_artifact_digest(
            parse_coordination_plan(
                {
                    "schema_kind": "coordination_plan",
                    "schema_version": 1,
                    "id": "qa-artifact",
                    "description": "missing digest must block",
                    "repos": [
                        {
                            "id": "producer",
                            "workspace": str(producer),
                            "contract": "contract.json",
                            "role": "producer",
                        },
                        {
                            "id": "consumer",
                            "workspace": str(consumer),
                            "contract": "contract.json",
                            "role": "consumer",
                        },
                    ],
                    "dependencies": [
                        {
                            "id": "api",
                            "from_repo": "producer",
                            "to_repo": "consumer",
                            "requires_evidence_outcome": "passed",
                            "artifact_path": "outputs/api.json",
                        }
                    ],
                    "compatibility_checks": [],
                }
            )
        )
        readiness = evaluate_readiness(plan)
        self.assertFalse(readiness["ready"])
        reasons = {b.get("reason") for b in readiness["blockers"]}
        self.assertIn("producer_artifact_digest_missing", reasons)


class EvalCompareExitTests(RunSpecimenTestCase):
    def _result(self, *, suite_digest: str, rules_hash: str) -> dict:
        return bind_artifact_digest(
            {
                "schema_kind": "eval_result",
                "schema_version": 1,
                "suite_id": "suite-a",
                "suite_digest": suite_digest,
                "tasks": [
                    {
                        "task_id": "t1",
                        "fixture_version": "1",
                        "rules_hash": rules_hash,
                        "skills_hash": "s" * 64,
                        "policy_hash": "p" * 64,
                        "actual_outcome": "passed",
                    }
                ],
                "passed_deterministic": True,
            }
        )

    def test_p3_compare_nonzero_on_drift_zero_on_match(self) -> None:
        match_a = self._result(suite_digest="d" * 64, rules_hash="r" * 64)
        match_b = self._result(suite_digest="d" * 64, rules_hash="r" * 64)
        drift = self._result(suite_digest="e" * 64, rules_hash="z" * 64)
        base = self.ws / "base.json"
        cand_ok = self.ws / "cand_ok.json"
        cand_bad = self.ws / "cand_bad.json"
        atomic_write_json(base, match_a)
        atomic_write_json(cand_ok, match_b)
        atomic_write_json(cand_bad, drift)

        same = compare_eval_results(match_a, match_b)
        self.assertFalse(same["suite_digest_mismatch"])
        self.assertEqual(same["deltas"], [])
        drifted = compare_eval_results(match_a, drift)
        self.assertTrue(drifted["suite_digest_mismatch"] or drifted["deltas"])

        rc_ok = main(
            [
                "eval",
                "compare",
                "--baseline",
                str(base),
                "--candidate",
                str(cand_ok),
            ]
        )
        rc_bad = main(
            [
                "eval",
                "compare",
                "--baseline",
                str(base),
                "--candidate",
                str(cand_bad),
            ]
        )
        self.assertEqual(rc_ok, 0)
        self.assertEqual(rc_bad, 1)


class SnapshotRestoreDestTests(RunSpecimenTestCase):
    def test_p3_restore_to_parent_refused_no_sibling_work(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        contract = load_contract(cpath)
        provider = get_snapshot_provider("local_tar")
        record = provider.create(
            workspace=self.ws,
            snapshot_id="s-parent",
            roots=list(contract.source.roots),
            excludes=list(contract.source.excludes),
        )
        parent = self.ws.parent
        sibling_work = parent / "work"
        existed_before = sibling_work.exists()
        with self.assertRaises(SnapshotError) as ctx:
            provider.restore(workspace=self.ws, record=record, dest=parent)
        self.assertIn("ancestor", str(ctx.exception).lower())
        if not existed_before:
            self.assertFalse(
                sibling_work.exists(),
                "restore to parent must not materialize parent/work beside the live tree",
            )
        # Explicit dest clearly outside still works.
        dest = Path(tempfile.mkdtemp(prefix="rs-restore-ok-"))
        provider.restore(workspace=self.ws, record=record, dest=dest)
        self.assertTrue((dest / "work").is_dir() or any(dest.iterdir()))


class FingerprintResolveTests(RunSpecimenTestCase):
    def test_p3_fingerprint_resolves_unresolved_workspace(self) -> None:
        (self.ws / "work" / "dep.txt").write_text("hello\n", encoding="utf-8")
        req = Requirement(
            id="r1",
            description="fp",
            check=None,
            inputs=(),
            source_scope=("work",),
            required_evidence=(),
            expected={},
            rationale=None,
            manual_unverifiable=True,
        )
        resolved = resolve_workspace(self.ws)
        # Unresolved path that still points at the same tree (trailing junk via Path).
        unresolved = Path(str(self.ws))
        self.assertEqual(
            _fingerprint_requirement_inputs(resolved, req),
            _fingerprint_requirement_inputs(unresolved, req),
        )
        # Symlink-style alias when practical (macOS /var vs resolved).
        if sys.platform == "darwin":
            # Force an unresolved form that resolve() would normalize.
            aliased = Path(str(self.ws)).absolute()
            self.assertEqual(
                _fingerprint_requirement_inputs(aliased, req),
                _fingerprint_requirement_inputs(resolved, req),
            )


if __name__ == "__main__":
    unittest.main()
