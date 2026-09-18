"""Tests for the opt-in, fail-closed iOS companion observation endpoint."""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import patch

from tests.helpers import SRC, RunSpecimenTestCase, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.companion import (
    CAPABILITIES,
    assert_bind_allowed,
    generate_pairing_token,
    make_handler,
    path_is_forbidden,
    start_companion,
)
from runspecimen.errors import RunSpecimenError


class TestCompanion(RunSpecimenTestCase):
    def test_capabilities_refuse_approval_and_execution(self) -> None:
        self.assertFalse(CAPABILITIES["can_approve"])
        self.assertFalse(CAPABILITIES["can_execute"])
        self.assertFalse(CAPABILITIES["can_mutate_lifecycle"])
        self.assertFalse(CAPABILITIES["can_remote_confirm"])
        self.assertIn("TTY", CAPABILITIES["boundary"])

    def test_forbidden_paths_include_lifecycle_verbs(self) -> None:
        for path in (
            "/v1/approve",
            "/api/run",
            "/v1/preflight",
            "/postflight",
            "/execute",
            "/pty/inject",
        ):
            self.assertTrue(path_is_forbidden(path), path)
        self.assertFalse(path_is_forbidden("/v1/status"))
        self.assertFalse(path_is_forbidden("/v1/attention"))
        self.assertFalse(path_is_forbidden("/v1/remote-confirm"))

    def test_bind_policy_fail_closed(self) -> None:
        assert_bind_allowed("127.0.0.1", allow_lan=False)
        assert_bind_allowed("localhost", allow_lan=False)
        with self.assertRaises(RunSpecimenError):
            assert_bind_allowed("192.168.1.10", allow_lan=False)
        assert_bind_allowed("192.168.1.10", allow_lan=True)
        assert_bind_allowed("100.64.1.2", allow_lan=True)
        with self.assertRaises(RunSpecimenError):
            assert_bind_allowed("0.0.0.0", allow_lan=True)
        with self.assertRaises(RunSpecimenError):
            assert_bind_allowed("8.8.8.8", allow_lan=True)

    def test_companion_serves_status_and_rejects_approve(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        token = generate_pairing_token()
        attention_events: list[dict] = []
        server, url, meta = start_companion(
            workspace=self.ws,
            contract_path=contract_path,
            pairing_token=token,
            host="127.0.0.1",
            port=0,
            allow_lan=False,
            on_attention=attention_events.append,
        )
        self.assertFalse(meta["can_approve"])
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            conn = HTTPConnection(host, port, timeout=5)

            conn.request("GET", "/v1/health")
            health = json.loads(conn.getresponse().read().decode("utf-8"))
            self.assertTrue(health["ok"])
            self.assertFalse(health["can_approve"])

            conn.request("GET", "/v1/status")
            unauthorized = conn.getresponse()
            self.assertEqual(unauthorized.status, 401)

            headers = {"Authorization": f"Bearer {token}"}
            conn.request("GET", "/v1/capabilities", headers=headers)
            caps = json.loads(conn.getresponse().read().decode("utf-8"))
            self.assertFalse(caps["can_approve"])
            self.assertFalse(caps["can_execute"])
            # Without a Mac-armed pending, remote confirm stays unavailable.
            self.assertFalse(caps.get("can_remote_confirm", False))

            conn.request("GET", "/v1/status", headers=headers)
            status_resp = conn.getresponse()
            self.assertEqual(status_resp.status, 200)
            status_doc = json.loads(status_resp.read().decode("utf-8"))
            self.assertIn("phase", status_doc)
            self.assertFalse(status_doc["companion"]["can_approve"])
            self.assertFalse(status_doc["companion"].get("can_remote_confirm", False))

            conn.request(
                "POST",
                "/v1/attention",
                body=json.dumps({"message": "please look"}),
                headers={**headers, "Content-Type": "application/json"},
            )
            attention = conn.getresponse()
            self.assertEqual(attention.status, 202)
            body = json.loads(attention.read().decode("utf-8"))
            self.assertFalse(body["mutates_lifecycle"])
            self.assertEqual(len(attention_events), 1)

            conn.request("POST", "/v1/approve", body=b"{}", headers=headers)
            forbidden = conn.getresponse()
            self.assertEqual(forbidden.status, 403)

            conn.request("POST", "/v1/run", body=b"{}", headers=headers)
            self.assertEqual(conn.getresponse().status, 403)

            conn.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_start_companion_requires_token_strength(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        with self.assertRaises(RunSpecimenError):
            start_companion(
                workspace=self.ws,
                contract_path=contract_path,
                pairing_token="short",
            )

    def test_make_handler_exists(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        handler = make_handler(
            workspace=self.ws,
            contract_path=contract_path,
            pairing_token=generate_pairing_token(),
        )
        self.assertTrue(issubclass(handler, object))

    def test_lan_bind_refuses_without_flag(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        with patch("runspecimen.companion.ThreadingHTTPServer") as server_cls:
            with self.assertRaises(RunSpecimenError):
                start_companion(
                    workspace=self.ws,
                    contract_path=contract_path,
                    pairing_token=generate_pairing_token(),
                    host="192.168.0.5",
                    allow_lan=False,
                )
            server_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
