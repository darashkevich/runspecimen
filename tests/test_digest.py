"""Receipt digest and diff. Neither path is live verification."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest

from tests.helpers import SRC, RunSpecimenTestCase, approve, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.cli import main
from runspecimen.digest import diff_summaries, summarize_receipt
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.run import run_contract


class DigestTests(RunSpecimenTestCase):
    def _finish(self, run_id: str) -> Path:
        out = f"outputs/{run_id}.json"
        doc = base_contract(run_id=run_id, outputs={"required": [out]})
        doc["postflight"]["json_equals"] = [{"path": out, "field": "status", "equals": "ok"}]
        (self.ws / "work" / "job.py").write_text(
            "import json\nfrom pathlib import Path\n"
            f"Path({out!r}).write_text(json.dumps({{'status': 'ok'}})+'\\n')\n",
            encoding="utf-8",
        )
        path = write_contract(self.ws, f"{run_id}.json", doc)
        approve(self.ws, path)
        preflight(contract_path=path, workspace=self.ws)
        run_contract(contract_path=path, workspace=self.ws)
        postflight(contract_path=path, workspace=self.ws)
        return path

    def test_digest_is_not_verify_and_live_sees_a_changed_file(self) -> None:
        self._finish("run-a")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(
                ["digest", "--workspace", str(self.ws), "--campaign-id", "camp", "--run-id", "run-a"]
            )
        self.assertEqual(code, 0)
        recorded = json.loads(buf.getvalue())
        self.assertFalse(recorded["live_verification"])
        self.assertNotIn("live_outputs", recorded)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(
                [
                    "digest",
                    "--workspace",
                    str(self.ws),
                    "--campaign-id",
                    "camp",
                    "--run-id",
                    "run-a",
                    "--live",
                ]
            )
        self.assertEqual(code, 0)
        doc = json.loads(buf.getvalue())
        self.assertFalse(doc["live_verification"])
        self.assertIn("not runspecimen verify", doc["note"])
        self.assertEqual(doc["isolation"]["backend"], "none")
        self.assertEqual(doc["live_outputs"][0]["status"], "match")
        target = self.ws / "outputs" / "run-a.json"
        target.write_text('{"status":"tampered"}\n', encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(
                [
                    "digest",
                    "--workspace",
                    str(self.ws),
                    "--campaign-id",
                    "camp",
                    "--run-id",
                    "run-a",
                    "--live",
                ]
            )
        self.assertEqual(code, 0)
        drifted = json.loads(buf.getvalue())
        self.assertEqual(drifted["live_outputs"][0]["status"], "differs")

    def test_diff_reports_two_receipts_without_failing(self) -> None:
        self._finish("run-a")
        self._finish("run-b")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(
                [
                    "diff",
                    "--workspace",
                    str(self.ws),
                    "--campaign-id",
                    "camp",
                    "--run-id",
                    "run-a",
                    "--against-campaign-id",
                    "camp",
                    "--against-run-id",
                    "run-b",
                ]
            )
        self.assertEqual(code, 0)
        doc = json.loads(buf.getvalue())
        self.assertFalse(doc["identical"])
        self.assertFalse(doc["live_verification"])
        fields = {item["field"] for item in doc["changed"]}
        self.assertIn("run_id", fields)
        self.assertIn("certificate_id", fields)

    def test_missing_certificate_is_an_error(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(
                ["digest", "--workspace", str(self.ws), "--campaign-id", "camp", "--run-id", "missing"]
            )
        self.assertEqual(code, 1)
        self.assertIn("certificate not found", err.getvalue())

    def test_summary_diff_ignores_the_note(self) -> None:
        left = summarize_receipt(
            {
                "campaign_id": "camp",
                "run_id": "run-a",
                "certificate_id": "aa",
                "contract_hash": "bb",
                "source_hash": "cc",
                "event_head": "dd",
                "exit_code": 0,
                "issued_at": "t",
                "output_digests": {},
                "run_result": "ok",
                "runtime": {"runtime_id": "rt"},
                "schema_version": 1,
            }
        )
        right = dict(left)
        right["note"] = "different wording"
        report = diff_summaries(left, right)
        self.assertTrue(report["identical"])
        right["exit_code"] = 1
        report = diff_summaries(left, right)
        self.assertEqual(report["changed"][0]["field"], "exit_code")


if __name__ == "__main__":
    unittest.main()
