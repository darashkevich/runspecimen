"""Adversarial verify, event-append, re-approval, and predecessor tamper tests."""

from __future__ import annotations

import json
import multiprocessing
import sys
import unittest
from pathlib import Path

from tests.helpers import SRC, RunSpecimenTestCase, approve, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.certificate import verify_run_receipt
from runspecimen.contract import load_contract
from runspecimen.errors import (
    ApprovalError,
    CertificateError,
    PostflightError,
    PreflightError,
    RunError,
)
from runspecimen.events import EventLog
from runspecimen.paths import run_state_dir
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.run import run_contract
from runspecimen.state import load_state


def _append_many(state_dir: str, prefix: str, n: int, ready, go, done) -> None:
    src = str(Path(__file__).resolve().parents[1] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from pathlib import Path as P

    from runspecimen.events import EventLog

    log = EventLog.for_state_dir(P(state_dir))
    ready.set()
    go.wait(timeout=30)
    for i in range(n):
        log.append("stress", {"who": prefix, "i": i})
    done.set()


class TestEventAppendConcurrency(RunSpecimenTestCase):
    def test_concurrent_append_integrity(self) -> None:
        state_dir = run_state_dir(self.ws, "camp", "run-log")
        state_dir.mkdir(parents=True)
        log = EventLog.for_state_dir(state_dir)
        log.ensure()

        ctx = multiprocessing.get_context("spawn")
        n = 40
        procs = []
        readies = []
        dones = []
        go = ctx.Event()
        for name in ("a", "b", "c", "d"):
            ready = ctx.Event()
            done = ctx.Event()
            p = ctx.Process(
                target=_append_many,
                args=(str(state_dir), name, n, ready, go, done),
            )
            procs.append(p)
            readies.append(ready)
            dones.append(done)
            p.start()
        for r in readies:
            self.assertTrue(r.wait(timeout=10))
        go.set()
        for d in dones:
            self.assertTrue(d.wait(timeout=30))
        for p in procs:
            p.join(timeout=10)
            self.assertEqual(p.exitcode, 0)

        ok, msg = log.verify_chain()
        self.assertTrue(ok, msg)
        records = log.read_all()
        self.assertEqual(len(records), 4 * n)
        self.assertEqual([r.seq for r in records], list(range(1, 4 * n + 1)))


class TestStrictVerifyAdversarial(RunSpecimenTestCase):
    def _complete(self) -> Path:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        postflight(contract_path=cpath, workspace=self.ws)
        return cpath

    def test_output_tamper_fails_verify(self) -> None:
        cpath = self._complete()
        out = self.ws / "outputs" / "out.json"
        out.write_text(json.dumps({"status": "ok", "tampered": True}) + "\n", encoding="utf-8")
        with self.assertRaises(CertificateError) as ctx:
            verify_run_receipt(
                workspace=self.ws,
                campaign_id="camp",
                run_id="run-a",
                contract=load_contract(cpath),
                require_live_provenance=True,
            )
        self.assertIn("output", str(ctx.exception).lower())

    def test_json_only_assertion_is_absent_before_run_and_hashed_in_receipt(self) -> None:
        doc = base_contract(outputs={"required": []})
        cpath = write_contract(self.ws, "json-only.json", doc)
        stale = self.ws / "outputs" / "out.json"
        stale.write_text(json.dumps({"status": "ok", "stale": True}) + "\n", encoding="utf-8")
        approve(self.ws, cpath)
        with self.assertRaises(PreflightError) as ctx:
            preflight(contract_path=cpath, workspace=self.ws)
        self.assertIn("asserted output", str(ctx.exception).lower())

        stale.unlink()
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        cert = postflight(contract_path=cpath, workspace=self.ws)
        self.assertIn("outputs/out.json", cert["output_digests"])

        stale.write_text(json.dumps({"status": "ok", "tampered": True}) + "\n", encoding="utf-8")
        with self.assertRaises(CertificateError):
            verify_run_receipt(
                workspace=self.ws,
                campaign_id="camp",
                run_id="run-a",
                contract=load_contract(cpath),
                require_live_provenance=True,
            )

    def test_deleted_state_fails_verify(self) -> None:
        cpath = self._complete()
        state_path = run_state_dir(self.ws, "camp", "run-a") / "state.json"
        state_path.unlink()
        with self.assertRaises(CertificateError) as ctx:
            verify_run_receipt(
                workspace=self.ws,
                campaign_id="camp",
                run_id="run-a",
                contract=load_contract(cpath),
                require_live_provenance=True,
            )
        self.assertIn("state", str(ctx.exception).lower())

    def test_current_source_tamper_fails_verify(self) -> None:
        cpath = self._complete()
        (self.ws / "work" / "job.py").write_text(
            (self.ws / "work" / "job.py").read_text(encoding="utf-8") + "# tamper\n",
            encoding="utf-8",
        )
        with self.assertRaises(CertificateError) as ctx:
            verify_run_receipt(
                workspace=self.ws,
                campaign_id="camp",
                run_id="run-a",
                contract=load_contract(cpath),
                require_live_provenance=True,
            )
        self.assertIn("source", str(ctx.exception).lower())

    def test_current_contract_tamper_fails_verify(self) -> None:
        cpath = self._complete()
        doc = json.loads(cpath.read_text(encoding="utf-8"))
        doc["caps"]["wall_timeout_sec"] = doc["caps"]["wall_timeout_sec"] + 1
        cpath.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        with self.assertRaises(CertificateError) as ctx:
            verify_run_receipt(
                workspace=self.ws,
                campaign_id="camp",
                run_id="run-a",
                contract=load_contract(cpath),
                require_live_provenance=True,
            )
        self.assertIn("contract", str(ctx.exception).lower())


class TestReapprovalAndPostflightProvenance(RunSpecimenTestCase):
    def test_refuse_reapproval_after_completed(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        self.assertEqual(load_state(run_state_dir(self.ws, "camp", "run-a"))["phase"], "completed")
        with self.assertRaises(ApprovalError) as ctx:
            approve(self.ws, cpath)
        self.assertIn("re-approval", str(ctx.exception).lower())

    def test_postflight_fails_on_contract_hash_drift_before_assertions(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        doc = json.loads(cpath.read_text(encoding="utf-8"))
        doc["caps"]["stdout_max_bytes"] = doc["caps"]["stdout_max_bytes"] + 1
        cpath.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        with self.assertRaises(PostflightError) as ctx:
            postflight(contract_path=cpath, workspace=self.ws)
        self.assertIn("contract hash", str(ctx.exception).lower())
        # No assertions_ok / certificate should exist.
        log = EventLog.for_state_dir(run_state_dir(self.ws, "camp", "run-a"))
        types = [r.type for r in log.read_all()]
        self.assertNotIn("postflight_assertions_ok", types)
        self.assertNotIn("certificate_issued", types)

    def test_timeout_cannot_be_certified_even_with_matching_exit_code(self) -> None:
        (self.ws / "work" / "job.py").write_text(
            "import time\ntime.sleep(30)\n",
            encoding="utf-8",
        )
        doc = base_contract(
            caps={
                "wall_timeout_sec": 1,
                "stdout_max_bytes": 65536,
                "stderr_max_bytes": 65536,
            }
        )
        # SIGKILL is commonly -9; even an explicitly matching assertion must not
        # convert an orchestration timeout into a certified execution.
        doc["postflight"]["exit_code"] = -9
        doc["postflight"]["require_outputs"] = False
        doc["postflight"]["json_equals"] = []
        cpath = write_contract(self.ws, "timeout.json", doc)
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        with self.assertRaises(RunError):
            run_contract(contract_path=cpath, workspace=self.ws)
        with self.assertRaises(PostflightError) as ctx:
            postflight(contract_path=cpath, workspace=self.ws)
        self.assertIn("only completed", str(ctx.exception).lower())


class TestPredecessorCrypto(RunSpecimenTestCase):
    def _complete_run(self, run_id: str, *, post: bool = True) -> Path:
        out = f"outputs/{run_id}.json"
        doc = base_contract(run_id=run_id, outputs={"required": [out]})
        doc["postflight"]["json_equals"] = [
            {"path": out, "field": "status", "equals": "ok"}
        ]
        job = (
            "import json\nfrom pathlib import Path\n"
            f"Path({out!r}).write_text(json.dumps({{'status': 'ok'}})+'\\n')\n"
        )
        (self.ws / "work" / "job.py").write_text(job, encoding="utf-8")
        cpath = write_contract(self.ws, f"{run_id}.json", doc)
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        if post:
            postflight(contract_path=cpath, workspace=self.ws)
        return cpath

    def test_tampered_predecessor_blocks(self) -> None:
        self._complete_run("run-a", post=True)
        # Tamper live predecessor output while leaving certificate untouched.
        (self.ws / "outputs" / "run-a.json").write_text(
            json.dumps({"status": "ok", "evil": True}) + "\n", encoding="utf-8"
        )

        out_b = "outputs/run-b.json"
        (self.ws / "work" / "job.py").write_text(
            "import json\nfrom pathlib import Path\n"
            f"Path({out_b!r}).write_text(json.dumps({{'status':'ok'}})+'\\n')\n",
            encoding="utf-8",
        )
        doc = base_contract(
            run_id="run-b",
            outputs={"required": [out_b]},
            predecessor={
                "campaign_id": "camp",
                "run_id": "run-a",
                "require_postflight": True,
                "refuse_if_failed": True,
            },
        )
        doc["postflight"]["json_equals"] = [
            {"path": out_b, "field": "status", "equals": "ok"}
        ]
        cpath = write_contract(self.ws, "run-b.json", doc)
        approve(self.ws, cpath)
        with self.assertRaises(PreflightError) as ctx:
            preflight(contract_path=cpath, workspace=self.ws)
        self.assertIn("predecessor", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
