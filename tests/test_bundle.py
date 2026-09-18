"""Incident bundle export (Community; not a Veto vault)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tests.helpers import SRC, NullWriter, PhraseReader, RunSpecimenTestCase, approve, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.bundle import write_incident_bundle
from runspecimen.certificate import verify_run_receipt
from runspecimen.cli import main
from runspecimen.contract import load_contract
from runspecimen.paths import run_state_dir
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.remote_confirm import (
    arm_remote_confirm,
    read_local_challenge_for_display,
    refuse_remote_confirm,
)
from runspecimen.run import run_contract


class TestIncidentBundle(RunSpecimenTestCase):
    def _complete(self, *, run_id: str = "run-a", predecessor: dict | None = None) -> Path:
        out = f"outputs/{run_id}.json"
        doc = base_contract(run_id=run_id, outputs={"required": [out]}, predecessor=predecessor)
        doc["postflight"]["json_equals"] = [{"path": out, "field": "status", "equals": "ok"}]
        (self.ws / "work" / "job.py").write_text(
            "import json\nfrom pathlib import Path\n"
            f"Path({out!r}).write_text(json.dumps({{'status': 'ok'}})+'\\n')\n",
            encoding="utf-8",
        )
        cpath = write_contract(self.ws, f"{run_id}.json", doc)
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        postflight(contract_path=cpath, workspace=self.ws)
        return cpath

    def test_bundle_omits_challenge_secret_and_surfaces_confirm_channel(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        state_dir = run_state_dir(self.ws, "camp", "run-a")
        secret = state_dir / "remote_confirm_challenge.local"
        secret.write_text("SHOULD-NOT-COPY\n", encoding="utf-8")
        dest = self.ws / "pack"
        manifest = write_incident_bundle(
            workspace=self.ws,
            campaign_id="camp",
            run_id="run-a",
            out_dir=dest,
            contract_path=cpath,
        )
        self.assertEqual(manifest["kind"], "incident_bundle")
        self.assertEqual(manifest["confirm_channel"], "local_tty_approve")
        self.assertTrue(manifest["not_a_compliance_product"])
        self.assertFalse((dest / "remote_confirm_challenge.local").exists())
        blob = (dest / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn("SHOULD-NOT-COPY", blob)
        self.assertTrue((dest / "approval.json").is_file())
        self.assertTrue((dest / "state.json").is_file())
        self.assertFalse((dest / "refusals.json").exists())

    def test_bundle_includes_refusals_after_remote_confirm_refuse(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        arm_remote_confirm(
            contract_path=cpath,
            workspace=self.ws,
            stdin=PhraseReader(""),
            stdout=NullWriter(),
            skip_tty_check=True,
        )
        challenge = read_local_challenge_for_display(run_state_dir(self.ws, "camp", "run-a"))
        refuse_remote_confirm(
            contract_path=cpath,
            workspace=self.ws,
            challenge=challenge or "",
            reason="scope too wide",
        )
        dest = self.ws / "refused-pack"
        write_incident_bundle(
            workspace=self.ws,
            campaign_id="camp",
            run_id="run-a",
            out_dir=dest,
        )
        refusals = json.loads((dest / "refusals.json").read_text(encoding="utf-8"))
        self.assertEqual(refusals[0]["type"], "remote_confirm_refused")
        self.assertEqual(refusals[0]["body"]["reason"], "scope too wide")
        self.assertFalse((dest / "approval.json").exists())

    def test_postflight_bundle_verify_json_and_chain(self) -> None:
        first = self._complete(run_id="run-a")
        second = self._complete(
            run_id="run-b",
            predecessor={
                "campaign_id": "camp",
                "run_id": "run-a",
                "require_postflight": True,
                "refuse_if_failed": True,
            },
        )
        dest = self.ws / "chain-pack"
        manifest = write_incident_bundle(
            workspace=self.ws,
            campaign_id="camp",
            run_id="run-b",
            out_dir=dest,
            contract_path=second,
            include_chain=True,
        )
        self.assertIn("verify.json", manifest["files"])
        verify_doc = json.loads((dest / "verify.json").read_text(encoding="utf-8"))
        self.assertTrue(verify_doc["ok"])
        self.assertEqual(verify_doc["confirm_channel"], "local_tty_approve")
        self.assertTrue((dest / "predecessors" / "camp" / "run-a" / "manifest.json").is_file())
        live = verify_run_receipt(
            workspace=self.ws,
            campaign_id="camp",
            run_id="run-b",
            contract=load_contract(second),
            require_live_provenance=True,
        )
        self.assertEqual(live["confirm_channel"], "local_tty_approve")
        self.assertIsNone(live["confirm_channel_note"])
        self.assertTrue(first.is_file())

    def test_cli_bundle_writes_manifest(self) -> None:
        import contextlib
        import io

        self._complete()
        dest = self.ws / "cli-pack"
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink):
            code = main(
                [
                    "bundle",
                    "--workspace",
                    str(self.ws),
                    "--campaign-id",
                    "camp",
                    "--run-id",
                    "run-a",
                    "--out",
                    str(dest),
                ]
            )
        self.assertEqual(code, 0)
        self.assertTrue((dest / "manifest.json").is_file())
        self.assertTrue((dest / "certificate.json").is_file())
        self.assertIn("incident_bundle", sink.getvalue())
