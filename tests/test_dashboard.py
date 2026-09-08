"""Tests for the loopback-only, read-only dashboard."""

from __future__ import annotations

import html
import http.client
import json
import shlex
import sys
import threading
import unittest
from unittest.mock import patch

from tests.helpers import SRC, RunSpecimenTestCase, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.dashboard import (
    _lifecycle_states,
    _presentation,
    dashboard_document,
    make_handler,
    start_dashboard,
)
from runspecimen.contract import load_contract


class TestDashboard(RunSpecimenTestCase):
    def test_dashboard_is_loopback_read_only_and_scoped_to_contract(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        handler = make_handler(workspace=self.ws, contract_path=contract_path)
        self.assertTrue(issubclass(handler, object))
        page = dashboard_document(
            workspace=self.ws.resolve(),
            contract_path=contract_path.resolve(),
            status={"phase": "none"},
        )
        self.assertIn("Safety boundary", page)
        self.assertIn("Approve in a terminal", page)
        self.assertIn("Command and limits", page)
        self.assertIn("Guided lifecycle", page)
        self.assertIn("About RunSpecimen", page)
        self.assertIn('id="about"', page)
        self.assertIn("Exactly one human-approved, bounded local run", page)
        self.assertIn("evidence controls", page)
        self.assertIn("https://github.com/darashkevich/runspecimen/blob/main/docs/ABOUT.md", page)
        self.assertIn("https://github.com/darashkevich/runspecimen/blob/main/docs/USER_GUIDE.md", page)
        self.assertIn("https://github.com/darashkevich/runspecimen/blob/main/docs/FAQ.md", page)
        self.assertIn("Raw evidence", page)
        self.assertIn('class="status-grid"', page)
        self.assertIn('class="copy-button"', page)
        self.assertIn("Auto-refresh every 5s", page)
        self.assertNotIn("/api/run", page)

    def test_dashboard_lifecycle_states_follow_evidence(self) -> None:
        self.assertEqual(
            _lifecycle_states({"phase": "none"}),
            ["current", "upcoming", "upcoming", "upcoming", "upcoming", "upcoming"],
        )
        self.assertEqual(
            _lifecycle_states({"phase": "postflighted", "certificate": {"certificate_id": "a"}}),
            ["recorded"] * 5 + ["not-checked"],
        )
        self.assertEqual(
            _lifecycle_states({"phase": "failed", "state": {"postflight_ok": False}})[4],
            "failed",
        )

    def test_dashboard_binds_loopback_only(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        with patch("runspecimen.dashboard.ThreadingHTTPServer") as server_cls:
            server = server_cls.return_value
            server.server_address = ("127.0.0.1", 43210)
            _server, url = start_dashboard(
                workspace=self.ws, contract_path=contract_path, port=0
            )
        self.assertEqual(server_cls.call_args.args[0], ("127.0.0.1", 0))
        self.assertEqual(url, "http://127.0.0.1:43210/")

    def test_dashboard_shell_quotes_copyable_paths(self) -> None:
        spaced = self.ws / "workspace with spaces"
        spaced.mkdir()
        (spaced / "work").mkdir()
        (spaced / "work" / "script.py").write_text("print('ok')\n", encoding="utf-8")
        contract_path = write_contract(spaced, "contract with spaces.json", base_contract())
        page = dashboard_document(
            workspace=spaced.resolve(),
            contract_path=contract_path.resolve(),
            status={"phase": "none"},
        )
        rendered = html.unescape(page)
        self.assertIn(shlex.quote(str(spaced.resolve())), rendered)
        self.assertIn(shlex.quote(str(contract_path.resolve())), rendered)


class TestDashboardPresentation(RunSpecimenTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.contract_path = write_contract(self.ws, "contract.json", base_contract())
        self.contract = load_contract(self.contract_path)

    def recorded_approval(self, **overrides: object) -> dict:
        """Synthetic display fixture; never passed to the approval API or saved."""
        return {
            "campaign_id": self.contract.campaign_id,
            "run_id": self.contract.run_id,
            "contract_hash": self.contract.contract_hash,
            "expires_at_unix": 2000,
            **overrides,
        }

    def test_expired_approval_requires_attention_before_launch(self) -> None:
        for phase in ("approved", "preflighted"):
            with self.subTest(phase=phase), patch("runspecimen.dashboard.time.time", return_value=3000):
                view = _presentation({
                    "phase": phase,
                    "approval": self.recorded_approval(),
                }, self.contract)
                self.assertEqual(view["cards"]["approval"][0], "Expired")
                self.assertEqual(view["cards"]["approval"][2], "bad")
                self.assertEqual(view["phase_tone"], "danger")
                self.assertTrue(any("approve again" in item for item in view["warnings"]))

    def test_approval_expiry_does_not_retroactively_fail_completed_run(self) -> None:
        with patch("runspecimen.dashboard.time.time", return_value=3000):
            view = _presentation({
                "phase": "postflighted",
                "approval": self.recorded_approval(),
                "certificate": {"certificate_id": "a" * 64},
            }, self.contract)
        self.assertEqual(view["cards"]["approval"][0], "Expired")
        self.assertIn("Historical", view["cards"]["approval"][1])
        self.assertNotEqual(view["cards"]["approval"][2], "bad")
        self.assertEqual(view["warnings"], [])
        self.assertNotEqual(view["phase_tone"], "danger")

    def test_mismatched_approval_is_never_presented_as_current(self) -> None:
        for edits in (
            {"campaign_id": "another-campaign"},
            {"run_id": "another-run"},
            {"contract_hash": "not-the-current-contract"},
        ):
            with self.subTest(edits=edits), patch("runspecimen.dashboard.time.time", return_value=1000):
                view = _presentation({
                    "phase": "approved",
                    "approval": self.recorded_approval(**edits),
                }, self.contract)
                self.assertEqual(view["cards"]["approval"][0], "Contract mismatch")
                self.assertEqual(view["cards"]["approval"][2], "bad")
                self.assertEqual(view["phase_label"], "Attention required")
                self.assertTrue(view["warnings"])

    def test_postflight_and_certificate_do_not_imply_live_verification(self) -> None:
        view = _presentation({
            "phase": "postflighted",
            "certificate": {"certificate_id": "a" * 64},
            "event_count": 7,
            "event_chain_ok": True,
        }, self.contract)
        self.assertEqual(view["phase_label"], "Postflight recorded")
        self.assertEqual(view["steps"], ["recorded"] * 5 + ["not-checked"])
        self.assertEqual(view["cards"]["certificate"][0], "Recorded")
        self.assertIn("Live verification required", view["cards"]["certificate"][1])
        self.assertNotEqual(view["cards"]["certificate"][2], "good")
        self.assertIn("has not performed", view["next_action"])

    def test_empty_history_is_neutral_and_invalid_history_demands_attention(self) -> None:
        empty = _presentation({
            "phase": "none", "event_count": 0, "event_chain_ok": True,
        }, self.contract)
        self.assertEqual(empty["cards"]["chain"][0], "No events")
        self.assertEqual(empty["cards"]["chain"][2], "")

        invalid = _presentation({
            "phase": "postflighted", "event_count": 7,
            "certificate": {"certificate_id": "a" * 64},
            "event_chain_ok": False, "event_chain_msg": "event_hash mismatch at seq 3",
        }, self.contract)
        self.assertEqual(invalid["cards"]["chain"][0], "Invalid")
        self.assertEqual(invalid["cards"]["chain"][2], "bad")
        self.assertEqual(invalid["phase_tone"], "danger")
        self.assertIn("event_hash mismatch at seq 3", " ".join(invalid["warnings"]))

    def test_postflight_failures_are_visible_and_identify_failed_step(self) -> None:
        failures = ["exit_code: expected 0, got 2", "required output missing: outputs/out.json"]
        view = _presentation({
            "phase": "failed",
            "state": {"postflight_ok": False, "postflight_failures": failures, "exit_code": 2},
        }, self.contract)
        self.assertEqual(view["steps"][4], "failed")
        self.assertEqual(view["phase_tone"], "danger")
        for failure in failures:
            self.assertIn(failure, view["warnings"])
        self.assertIn("do not reuse this run ID", view["next_action"])

    def test_argv_outputs_and_evidence_are_escaped_as_text(self) -> None:
        argument = '</code><img src=x onerror="alert(1)">'
        output = 'outputs/<svg onload="alert(2)">.json'
        failure = '</li><script>alert("evidence")</script>'
        contract_doc = base_contract()
        contract_doc["argv"].append(argument)
        contract_doc["outputs"]["required"].append(output)
        path = write_contract(self.ws, "display.json", contract_doc)
        page = dashboard_document(
            workspace=self.ws, contract_path=path,
            status={"phase": "failed", "state": {
                "postflight_ok": False, "postflight_failures": [failure],
            }},
        )
        for value in (argument, output, failure):
            with self.subTest(value=value):
                self.assertNotIn(value, page)
                self.assertIn(html.escape(value, quote=True), page)
        self.assertNotIn("<img", page)
        self.assertNotIn("<svg", page)
        self.assertEqual(page.count("<script>"), 1)


class TestDashboardHTTP(RunSpecimenTestCase):
    """Exercise the actual HTTP boundary without approving or running a payload."""

    def setUp(self) -> None:
        super().setUp()
        self.contract_path = write_contract(self.ws, "contract.json", base_contract())
        self.server, self.url = start_dashboard(
            workspace=self.ws, contract_path=self.contract_path, port=0
        )
        self.port = self.server.server_address[1]
        self.authority = f"127.0.0.1:{self.port}"
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        super().tearDown()

    def request(
        self,
        path: str = "/api/status",
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        hosts: list[str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.putrequest(method, path, skip_host=True)
            for host in [self.authority] if hosts is None else hosts:
                connection.putheader("Host", host)
            for name, value in (headers or {}).items():
                connection.putheader(name, value)
            connection.endheaders()
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def assert_json_error(self, response: tuple[int, dict[str, str], bytes], code: int) -> dict:
        status, headers, body = response
        self.assertEqual(status, code)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual(headers.get("Cache-Control"), "no-store")
        self.assertEqual(int(headers["Content-Length"]), len(body))
        result = json.loads(body)
        self.assertIn("error", result)
        self.assertNotIn("Traceback", body.decode())
        return result

    def test_status_and_document_are_available_for_exact_loopback_host(self) -> None:
        code, headers, body = self.request()
        self.assertEqual(code, 200)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        status = json.loads(body)
        self.assertEqual(status["campaign_id"], "camp")
        self.assertEqual(status["run_id"], "run-a")
        self.assertEqual(status["phase"], "none")
        self.assertIsNone(status["approval"])
        self.assertIsNone(status["certificate"])
        self.assertEqual(status["contract"]["argv"], base_contract()["argv"])

        code, headers, body = self.request("/")
        self.assertEqual(code, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertIn(b"RunSpecimen", body)
        self.assertIn(b"About RunSpecimen", body)
        self.assertIn(b'id="about"', body)
        self.assertIn(b"USER_GUIDE.md", body)
        self.assertIn(b"FAQ.md", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(int(headers["Content-Length"]), len(body))

    def test_foreign_missing_duplicate_and_ambiguous_host_are_rejected(self) -> None:
        cases = [
            [],
            ["attacker.example"],
            [f"attacker.example:{self.port}"],
            [f"localhost:{self.port}"],
            ["127.0.0.1"],
            [f"127.0.0.1:{self.port + 1}"],
            [f"127.0.0.1.attacker.example:{self.port}"],
            [f"attacker.example@127.0.0.1:{self.port}"],
            [self.authority, self.authority],
            [self.authority, "attacker.example"],
        ]
        for hosts in cases:
            with self.subTest(hosts=hosts):
                self.assert_json_error(self.request(hosts=hosts), 403)

    def test_cross_origin_and_cross_site_requests_are_rejected(self) -> None:
        cases = [
            {"Origin": "https://attacker.example"},
            {"Origin": "null"},
            {"Origin": f"http://127.0.0.1:{self.port + 1}"},
            {"Origin": f"https://{self.authority}"},
            {"Sec-Fetch-Site": "cross-site"},
            {"Origin": f"http://{self.authority}", "Sec-Fetch-Site": "cross-site"},
        ]
        for headers in cases:
            with self.subTest(headers=headers):
                self.assert_json_error(self.request(headers=headers), 403)

        code, _, _ = self.request(headers={
            "Origin": f"http://{self.authority}", "Sec-Fetch-Site": "same-origin"
        })
        self.assertEqual(code, 200)

    def test_write_methods_are_rejected_without_creating_run_evidence(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            for path in ("/", "/api/status", "/api/run", "/api/approve"):
                with self.subTest(method=method, path=path):
                    self.assert_json_error(self.request(path, method=method), 405)
        self.assertFalse((self.ws / ".runspecimen" / "runs").exists())
        self.assertFalse((self.ws / "outputs" / "out.json").exists())

    def test_unknown_routes_do_not_expose_workspace_files(self) -> None:
        for path in (
            "/contract.json", "/work/job.py", "/api/run", "/api/approve",
            "/../contract.json", "/%2e%2e/contract.json",
        ):
            with self.subTest(path=path):
                self.assert_json_error(self.request(path), 404)

    def test_corrupt_evidence_returns_controlled_unavailable_response(self) -> None:
        state_dir = self.ws / ".runspecimen" / "runs" / "camp" / "run-a"
        state_dir.mkdir(parents=True)
        for filename in ("state.json", "approval.json", "certificate.json", "events.jsonl"):
            path = state_dir / filename
            with self.subTest(filename=filename):
                path.write_text("{broken evidence", encoding="utf-8")
                try:
                    self.assert_json_error(self.request(), 503)
                finally:
                    path.unlink()
                self.assertEqual(self.request()[0], 200)

    def test_edited_contract_hash_cannot_be_mixed_with_bound_run_evidence(self) -> None:
        self.assertEqual(self.request()[0], 200)
        edited = base_contract()
        edited["caps"]["wall_timeout_sec"] = 11
        write_contract(self.ws, "contract.json", edited)
        for path in ("/", "/api/status"):
            with self.subTest(path=path):
                self.assert_json_error(self.request(path), 409)

    def test_edited_contract_identity_cannot_switch_dashboard_run(self) -> None:
        for edits in ({"run_id": "different-run"}, {"campaign_id": "different-campaign"}):
            write_contract(self.ws, "contract.json", base_contract(**edits))
            for path in ("/", "/api/status"):
                with self.subTest(edits=edits, path=path):
                    self.assert_json_error(self.request(path), 409)


if __name__ == "__main__":
    unittest.main()
