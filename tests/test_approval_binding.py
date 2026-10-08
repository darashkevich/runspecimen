"""BH-01/BH-02 approval.json is not a bearer token; BH-03..06 regressions."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from tests.helpers import (
    SRC,
    RunSpecimenTestCase,
    approve,
    base_contract,
    write_contract,
)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.approve import (
    ALLOWED_CONFIRM_CHANNELS,
    APPROVAL_EVENT_MISMATCH,
    PLANTED_OR_EDITED_APPROVAL,
    TTL_REFRESH_REQUIRES_TTY,
    UNKNOWN_CONFIRM_CHANNEL,
    approval_document_hash,
    approval_path,
    complete_approval_document,
    latest_approval_event,
    load_approval,
)
from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.certificate import MISSING_BOUND_APPROVAL, verify_run_receipt
from runspecimen.cli import main
from runspecimen.contract import load_contract
from runspecimen.errors import ApprovalError, CertificateError, PreflightError
from runspecimen.events import EventLog, GENESIS_HASH, _line_hash
from runspecimen.paths import run_state_dir
from runspecimen.preflight import preflight
from runspecimen.postflight import postflight
from runspecimen.present import format_pretty
from runspecimen.remote_confirm import settle_remote_confirm
from runspecimen.run import run_contract
from runspecimen.schema import CURRENT_RECEIPT_SCHEMA_VERSION, certificate_id_material
from runspecimen.state import load_state


def _rewrite_events(state_dir: Path, records: list) -> None:
    lines = []
    prev = GENESIS_HASH
    for seq, rec in enumerate(records, start=1):
        body = dict(rec.body)
        event_hash = _line_hash(prev, seq, rec.ts, rec.type, body)
        lines.append(
            json.dumps(
                {
                    "seq": seq,
                    "prev_hash": prev,
                    "event_hash": event_hash,
                    "ts": rec.ts,
                    "type": rec.type,
                    "body": body,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        prev = event_hash
    (state_dir / "events.jsonl").write_text("".join(lines), encoding="utf-8")


class TestApprovalBinding(RunSpecimenTestCase):
    def _state_dir(self) -> Path:
        return run_state_dir(self.ws, "camp", "run-a")

    def _plant_valid_looking_approval(self, cpath: Path) -> dict:
        approve(self.ws, cpath, now=1_000.0)
        approval = load_approval(self._state_dir())
        assert approval is not None
        events = self._state_dir() / "events.jsonl"
        if events.exists():
            events.unlink()
        return approval

    def _refuse_preflight_and_run(self, cpath: Path, now: float | None = None) -> str:
        with self.assertRaises(PreflightError) as pre:
            preflight(contract_path=cpath, workspace=self.ws, now=now)
        with self.assertRaises(PreflightError) as run_ctx:
            run_contract(contract_path=cpath, workspace=self.ws, now=now)
        self.assertEqual(str(pre.exception), str(run_ctx.exception))
        return str(pre.exception)

    def _drop_approval_events_keep_cert_issuance(self) -> None:
        from runspecimen.certificate import _recompute_certificate_id
        from runspecimen.state import save_state

        state_dir = self._state_dir()
        kept = [
            rec
            for rec in EventLog.for_state_dir(state_dir).read_all()
            if rec.type != "approval"
        ]
        _rewrite_events(state_dir, kept)
        rebuilt = EventLog.for_state_dir(state_dir).read_all()
        assertions = next(rec for rec in rebuilt if rec.type == "postflight_assertions_ok")
        cert_path = state_dir / "certificate.json"
        cert = read_json(cert_path)
        cert["event_head"] = assertions.event_hash
        cert["certificate_id"] = _recompute_certificate_id(cert)
        atomic_write_json(cert_path, cert)
        rebound = []
        for rec in rebuilt:
            if rec.type == "certificate_issued":
                body = dict(rec.body)
                body["certificate_id"] = cert["certificate_id"]
                body["event_head"] = cert["event_head"]
                rec = rec.__class__(
                    seq=rec.seq,
                    prev_hash=rec.prev_hash,
                    event_hash=rec.event_hash,
                    ts=rec.ts,
                    type=rec.type,
                    body=body,
                )
            rebound.append(rec)
        _rewrite_events(state_dir, rebound)
        state = load_state(state_dir)
        state["certificate_id"] = cert["certificate_id"]
        save_state(state_dir, state)

    def _complete(self, cpath: Path | None = None) -> Path:
        cpath = cpath or write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        run_contract(contract_path=cpath, workspace=self.ws)
        postflight(contract_path=cpath, workspace=self.ws)
        return cpath

    def test_plant_with_no_event_refused_at_preflight_run_and_verify(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        self._plant_valid_looking_approval(cpath)
        msg = self._refuse_preflight_and_run(cpath, now=1_100.0)
        self.assertEqual(msg, PLANTED_OR_EDITED_APPROVAL)
        self._complete(cpath)
        self._drop_approval_events_keep_cert_issuance()
        with self.assertRaises(CertificateError) as ctx:
            verify_run_receipt(
                workspace=self.ws,
                campaign_id="camp",
                run_id="run-a",
                contract=load_contract(cpath),
            )
        self.assertEqual(str(ctx.exception), MISSING_BOUND_APPROVAL)

    def test_plant_with_matching_looking_confirm_channel_refused(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        planted = self._plant_valid_looking_approval(cpath)
        self.assertEqual(planted["confirm_channel"], "local_tty_approve")
        self.assertIn(planted["confirm_channel"], ALLOWED_CONFIRM_CHANNELS)
        msg = self._refuse_preflight_and_run(cpath, now=1_100.0)
        self.assertEqual(msg, PLANTED_OR_EDITED_APPROVAL)

    def test_ttl_extension_after_expiry_refused(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath, now=1_000.0)
        path = approval_path(self._state_dir())
        doc = read_json(path)
        doc["expires_at_unix"] = 99_999.0
        atomic_write_json(path, doc)
        msg = self._refuse_preflight_and_run(cpath, now=5_000.0)
        self.assertEqual(msg, APPROVAL_EVENT_MISMATCH)

    def test_approval_json_edited_after_approve_refused(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath, now=1_000.0)
        path = approval_path(self._state_dir())
        doc = read_json(path)
        doc["ttl_sec"] = int(doc["ttl_sec"]) + 1
        atomic_write_json(path, doc)
        msg = self._refuse_preflight_and_run(cpath, now=1_100.0)
        self.assertEqual(msg, APPROVAL_EVENT_MISMATCH)

    def test_event_present_but_file_swapped_refused(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        first = approve(self.ws, cpath, now=1_000.0)
        first_copy = json.loads(json.dumps(first))
        approve(self.ws, cpath, now=1_200.0)
        atomic_write_json(approval_path(self._state_dir()), first_copy)
        msg = self._refuse_preflight_and_run(cpath, now=1_300.0)
        self.assertEqual(msg, APPROVAL_EVENT_MISMATCH)
        rec = latest_approval_event(self._state_dir())
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertNotEqual(rec.body.get("approval_document_hash"), approval_document_hash(first_copy))

    def test_unknown_confirm_channel_refused(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath, now=1_000.0)
        path = approval_path(self._state_dir())
        doc = read_json(path)
        doc["confirm_channel"] = "agent_forged_channel"
        atomic_write_json(path, doc)
        msg = self._refuse_preflight_and_run(cpath, now=1_100.0)
        self.assertEqual(msg, UNKNOWN_CONFIRM_CHANNEL)

    def test_old_receipt_without_bound_approval_never_verifies(self) -> None:
        from runspecimen.certificate import _recompute_certificate_id
        from runspecimen.state import save_state

        cpath = self._complete()
        state_dir = self._state_dir()
        records = []
        for rec in EventLog.for_state_dir(state_dir).read_all():
            if rec.type == "approval":
                body = dict(rec.body)
                body.pop("approval_document_hash", None)
                rec = rec.__class__(
                    seq=rec.seq,
                    prev_hash=rec.prev_hash,
                    event_hash=rec.event_hash,
                    ts=rec.ts,
                    type=rec.type,
                    body=body,
                )
            records.append(rec)
        _rewrite_events(state_dir, records)
        rebuilt = EventLog.for_state_dir(state_dir).read_all()
        assertions = next(rec for rec in rebuilt if rec.type == "postflight_assertions_ok")
        cert_path = state_dir / "certificate.json"
        cert = read_json(cert_path)
        cert["event_head"] = assertions.event_hash
        cert["certificate_id"] = _recompute_certificate_id(cert)
        atomic_write_json(cert_path, cert)
        rebound = []
        for rec in rebuilt:
            if rec.type == "certificate_issued":
                body = dict(rec.body)
                body["certificate_id"] = cert["certificate_id"]
                body["event_head"] = cert["event_head"]
                rec = rec.__class__(
                    seq=rec.seq,
                    prev_hash=rec.prev_hash,
                    event_hash=rec.event_hash,
                    ts=rec.ts,
                    type=rec.type,
                    body=body,
                )
            rebound.append(rec)
        _rewrite_events(state_dir, rebound)
        state = load_state(state_dir)
        state["certificate_id"] = cert["certificate_id"]
        save_state(state_dir, state)
        ok, _ = EventLog.for_state_dir(state_dir).verify_chain()
        self.assertTrue(ok)
        with self.assertRaises(CertificateError) as ctx:
            verify_run_receipt(
                workspace=self.ws,
                campaign_id="camp",
                run_id="run-a",
                contract=load_contract(cpath),
            )
        self.assertIn("Planted or edited", str(ctx.exception))

    def test_honest_approve_still_launches_and_verifies(self) -> None:
        cpath = self._complete()
        result = verify_run_receipt(
            workspace=self.ws,
            campaign_id="camp",
            run_id="run-a",
            contract=load_contract(cpath),
            require_live_provenance=True,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["confirm_channel"], "local_tty_approve")
        cert = read_json(self._state_dir() / "certificate.json")
        self.assertEqual(cert["schema_version"], CURRENT_RECEIPT_SCHEMA_VERSION)
        self.assertEqual(cert["confirm_channel"], "local_tty_approve")
        self.assertIn("confirm_channel", certificate_id_material(cert))

    def test_tty_reapproval_while_approved_appends_and_latest_governs(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        first = approve(self.ws, cpath, now=1_000.0)
        self.assertEqual(load_state(self._state_dir())["phase"], "approved")
        second = approve(self.ws, cpath, now=1_500.0)
        self.assertGreater(second["expires_at_unix"], first["expires_at_unix"])
        types = [rec.type for rec in EventLog.for_state_dir(self._state_dir()).read_all()]
        self.assertEqual(types.count("approval"), 2)
        latest = latest_approval_event(self._state_dir())
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.body["approval_document_hash"], approval_document_hash(second))
        self.assertEqual(latest.body["expires_at_unix"], second["expires_at_unix"])
        preflight(contract_path=cpath, workspace=self.ws, now=1_600.0)
        run_contract(contract_path=cpath, workspace=self.ws, now=1_700.0)

    def test_remote_confirm_cannot_refresh_existing_approval(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath, now=1_000.0)
        contract = load_contract(cpath)
        with self.assertRaises(ApprovalError) as ctx:
            complete_approval_document(
                contract=contract,
                workspace=self.ws,
                now=1_500.0,
                confirm_channel="remote_human_confirm",
                confirm_evidence={"kind": "test"},
                allow_ttl_refresh=False,
            )
        self.assertEqual(str(ctx.exception), TTL_REFRESH_REQUIRES_TTY)
        with self.assertRaises(ApprovalError):
            settle_remote_confirm(
                contract_path=cpath,
                workspace=self.ws,
                challenge="DEADBEEF",
                phrase="APPROVE",
                now=1_500.0,
            )

    def test_pretty_run_nonzero_exit_is_neutral(self) -> None:
        (self.ws / "work" / "job.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
        cpath = write_contract(self.ws, "fail.json", base_contract())
        approve(self.ws, cpath)
        result = run_contract(contract_path=cpath, workspace=self.ws)
        self.assertEqual(result["exit_code"], 3)
        self.assertEqual(result["run_result"], "completed")
        pretty = format_pretty(result, kind="run", color_mode="never")
        self.assertIn("Process finished with exit code 3", pretty)
        self.assertNotIn("Run completed", pretty)
        self.assertNotIn("OK", pretty)
        colored = format_pretty(result, kind="run", color_mode="always")
        self.assertNotIn("\033[32mOK", colored)
        self.assertIn("Process finished with exit code 3", colored)

        import contextlib
        import io

        cpath2 = write_contract(self.ws, "fail2.json", base_contract(run_id="run-b"))
        approve(self.ws, cpath2)
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(
                ["run", "--workspace", str(self.ws), "--contract", str(cpath2)]
            )
        self.assertEqual(code, 0)
        doc = json.loads(out.getvalue())
        self.assertEqual(doc["exit_code"], 3)
        self.assertEqual(doc["run_result"], "completed")

        out = io.StringIO()
        err = io.StringIO()
        cpath3 = write_contract(self.ws, "fail3.json", base_contract(run_id="run-c"))
        approve(self.ws, cpath3)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(
                [
                    "--pretty",
                    "--color",
                    "never",
                    "run",
                    "--workspace",
                    str(self.ws),
                    "--contract",
                    str(cpath3),
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("Process finished with exit code 3", out.getvalue())
        self.assertNotIn("Run completed", out.getvalue())
        self.assertNotIn("OK  ", out.getvalue())

    def test_certificate_unknown_field_fails_verify(self) -> None:
        cpath = self._complete()
        path = self._state_dir() / "certificate.json"
        cert = read_json(path)
        cert["watcher"] = {"enabled": True}
        atomic_write_json(path, cert)
        with self.assertRaises(CertificateError) as ctx:
            verify_run_receipt(
                workspace=self.ws,
                campaign_id="camp",
                run_id="run-a",
                contract=load_contract(cpath),
            )
        self.assertIn("unknown field", str(ctx.exception).lower())
        self.assertIn("watcher", str(ctx.exception))


class TestShowcaseHonesty(unittest.TestCase):
    def test_readme_showcase_leads_with_refresh_script(self) -> None:
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        showcase = readme.split("### Showcase receipt", 1)[1]
        verify_idx = showcase.find("runspecimen verify --workspace examples/showcase")
        refresh_idx = showcase.find("scripts/refresh_showcase.py")
        self.assertGreaterEqual(refresh_idx, 0)
        self.assertTrue(
            refresh_idx < verify_idx or verify_idx < 0,
            "README showcase must lead with scripts/refresh_showcase.py",
        )

    def test_user_guide_showcase_leads_with_refresh_script(self) -> None:
        guide = (
            Path(__file__).resolve().parents[1] / "docs" / "USER_GUIDE.md"
        ).read_text(encoding="utf-8")
        showcase = guide.split("## Showcase refresh (host-bound)", 1)[1]
        verify_idx = showcase.find("runspecimen verify --workspace examples/showcase")
        refresh_idx = showcase.find("scripts/refresh_showcase.py")
        self.assertGreaterEqual(refresh_idx, 0)
        self.assertTrue(
            refresh_idx < verify_idx or verify_idx < 0,
            "USER_GUIDE showcase must lead with scripts/refresh_showcase.py",
        )


if __name__ == "__main__":
    unittest.main()
