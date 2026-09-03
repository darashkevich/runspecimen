"""Event-log tamper detection and certificate verify tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from tests.helpers import SRC, RunSpecimenTestCase, approve, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.atomic import read_json
from runspecimen.certificate import load_certificate, verify_run_receipt
from runspecimen.contract import load_contract
from runspecimen.errors import CertificateError
from runspecimen.events import EventLog
from runspecimen.paths import run_state_dir
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.run import run_contract


class TestTamper(RunSpecimenTestCase):
    def _happy_path(self) -> Path:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        postflight(contract_path=cpath, workspace=self.ws)
        return cpath

    def test_event_log_tamper_detected(self) -> None:
        self._happy_path()
        state_dir = run_state_dir(self.ws, "camp", "run-a")
        log = EventLog.for_state_dir(state_dir)
        ok, _ = log.verify_chain()
        self.assertTrue(ok)

        text = log.path.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        self.assertGreaterEqual(len(lines), 2)
        obj = json.loads(lines[1])
        obj["body"] = {**obj["body"], "tampered": True}
        lines[1] = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        ok, msg = log.verify_chain()
        self.assertFalse(ok)
        self.assertIn("mismatch", msg.lower())

        with self.assertRaises(CertificateError):
            verify_run_receipt(workspace=self.ws, campaign_id="camp", run_id="run-a")

    def test_certificate_body_tamper_detected(self) -> None:
        self._happy_path()
        state_dir = run_state_dir(self.ws, "camp", "run-a")
        cert_path = state_dir / "certificate.json"
        cert = read_json(cert_path)
        cert["source_hash"] = "0" * 64
        cert_path.write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8")
        with self.assertRaises(CertificateError) as ctx:
            verify_run_receipt(workspace=self.ws, campaign_id="camp", run_id="run-a")
        self.assertIn("certificate_id", str(ctx.exception).lower())

    def test_verify_ok_after_clean_run(self) -> None:
        cpath = self._happy_path()
        contract = load_contract(cpath)
        result = verify_run_receipt(
            workspace=self.ws,
            campaign_id="camp",
            run_id="run-a",
            contract=contract,
            require_live_provenance=True,
        )
        self.assertTrue(result["ok"])
        cert = load_certificate(run_state_dir(self.ws, "camp", "run-a"))
        assert cert is not None
        self.assertEqual(result["certificate_id"], cert["certificate_id"])

        # Issuance ordering present in log.
        log = EventLog.for_state_dir(run_state_dir(self.ws, "camp", "run-a"))
        types = [r.type for r in log.read_all()]
        self.assertIn("postflight_assertions_ok", types)
        self.assertIn("certificate_issued", types)
        self.assertEqual(types[-1], "certificate_issued")


if __name__ == "__main__":
    unittest.main()
