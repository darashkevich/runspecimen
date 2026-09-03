"""Predecessor gating and postflight assertion tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from tests.helpers import SRC, RunSpecimenTestCase, approve, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.errors import PostflightError, PreflightError
from runspecimen.hashutil import sha256_file
from runspecimen.paths import run_state_dir
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.run import run_contract
from runspecimen.state import update_state


class TestPredecessor(RunSpecimenTestCase):
    def _complete_run(self, run_id: str, *, post: bool = True) -> Path:
        doc = base_contract(run_id=run_id)
        # Unique output per run to avoid output-exists collision across runs.
        out = f"outputs/{run_id}.json"
        doc["outputs"] = {"required": [out]}
        doc["postflight"]["json_equals"] = [
            {"path": out, "field": "status", "equals": "ok"}
        ]
        job = (
            "import json, sys\n"
            "from pathlib import Path\n"
            f"p = Path({out!r})\n"
            "p.parent.mkdir(parents=True, exist_ok=True)\n"
            "p.write_text(json.dumps({'status': 'ok'}) + '\\n')\n"
        )
        (self.ws / "work" / "job.py").write_text(job, encoding="utf-8")
        cpath = write_contract(self.ws, f"{run_id}.json", doc)
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        if post:
            postflight(contract_path=cpath, workspace=self.ws)
        return cpath

    def test_predecessor_unpostflighted_blocks(self) -> None:
        self._complete_run("run-a", post=False)
        # Restore job to write run-b output; source change requires fresh approval anyway.
        out_b = "outputs/run-b.json"
        job = (
            "import json\n"
            "from pathlib import Path\n"
            f"p = Path({out_b!r})\n"
            "p.parent.mkdir(parents=True, exist_ok=True)\n"
            "p.write_text(json.dumps({'status': 'ok'}) + '\\n')\n"
        )
        (self.ws / "work" / "job.py").write_text(job, encoding="utf-8")
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
        self.assertIn("postflight", str(ctx.exception).lower())

    def test_predecessor_failed_blocks(self) -> None:
        self._complete_run("run-a", post=True)
        # Mark predecessor as failed after the fact to simulate failed gate.
        pred_dir = run_state_dir(self.ws, "camp", "run-a")
        update_state(pred_dir, phase="failed", run_result="failed")

        out_b = "outputs/run-b.json"
        (self.ws / "work" / "job.py").write_text(
            "from pathlib import Path\n"
            f"Path({out_b!r}).write_text('{{\"status\":\"ok\"}}\\n')\n",
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
        self.assertIn("fail", str(ctx.exception).lower())

    def test_predecessor_postflighted_allows(self) -> None:
        self._complete_run("run-a", post=True)
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
        result = preflight(contract_path=cpath, workspace=self.ws)
        self.assertTrue(result["ok"])


class TestPostflight(RunSpecimenTestCase):
    def test_json_equals_and_sha(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        out = self.ws / "outputs" / "out.json"
        digest = sha256_file(out)

        # Rewrite contract with expected sha (changes contract hash → need new approve).
        # Instead, mutate postflight via a second contract file after run, OR
        # assert using current postflight then fail sha with crafted state.
        # Here: run postflight successfully first without sha constraint.
        cert = postflight(contract_path=cpath, workspace=self.ws)
        self.assertIn("certificate_id", cert)

        # Fresh workspace-relative assertion: wrong expected sha fails.
        # Build a completed twin run with forced sha mismatch.
        td_state = run_state_dir(self.ws, "camp", "run-sha")
        # Simpler: create new run with baked expected wrong sha before run completes.
        doc = base_contract(run_id="run-sha")
        out2 = "outputs/sha.json"
        doc["outputs"] = {"required": [out2]}
        wrong = "ab" * 32
        doc["postflight"] = {
            "exit_code": 0,
            "require_outputs": True,
            "output_sha256": {out2: wrong},
            "json_equals": [{"path": out2, "field": "status", "equals": "ok"}],
            "source_unchanged": True,
        }
        (self.ws / "work" / "job.py").write_text(
            "import json\nfrom pathlib import Path\n"
            f"Path({out2!r}).write_text(json.dumps({{'status':'ok'}})+'\\n')\n",
            encoding="utf-8",
        )
        c2 = write_contract(self.ws, "sha.json", doc)
        approve(self.ws, c2)
        preflight(contract_path=c2, workspace=self.ws)
        run_contract(contract_path=c2, workspace=self.ws)
        with self.assertRaises(PostflightError) as ctx:
            postflight(contract_path=c2, workspace=self.ws)
        self.assertIn("sha256", str(ctx.exception).lower())
        self.assertNotEqual(wrong, digest)

    def test_source_unchanged_assertion(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        (self.ws / "work" / "job.py").write_text(
            (self.ws / "work" / "job.py").read_text(encoding="utf-8") + "# drift\n",
            encoding="utf-8",
        )
        with self.assertRaises(PostflightError) as ctx:
            postflight(contract_path=cpath, workspace=self.ws)
        self.assertIn("source", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
