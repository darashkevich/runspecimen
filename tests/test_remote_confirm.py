"""Tests for Mac-armed remote human confirm (ADR-004)."""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from io import StringIO

from tests.helpers import SRC, NullWriter, PhraseReader, RunSpecimenTestCase, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.approve import load_approval
from runspecimen.companion import CAPABILITIES, generate_pairing_token, path_is_forbidden, start_companion
from runspecimen.errors import ApprovalError
from runspecimen.paths import run_state_dir
from runspecimen.remote_confirm import (
    arm_remote_confirm,
    load_pending,
    read_local_challenge_for_display,
    settle_remote_confirm,
)
from runspecimen.state import load_state


class TestRemoteConfirm(RunSpecimenTestCase):
    def test_capabilities_keep_can_approve_false(self) -> None:
        self.assertFalse(CAPABILITIES["can_approve"])
        self.assertFalse(CAPABILITIES["can_execute"])
        self.assertFalse(CAPABILITIES["can_mutate_lifecycle"])
        self.assertFalse(CAPABILITIES["can_remote_confirm"])
        self.assertIn("not TTY-equivalent", CAPABILITIES["boundary"])

    def test_remote_confirm_path_allowed_approve_path_forbidden(self) -> None:
        self.assertFalse(path_is_forbidden("/v1/remote-confirm"))
        self.assertTrue(path_is_forbidden("/v1/approve"))
        self.assertTrue(path_is_forbidden("/v1/run"))

    def test_arm_and_settle_happy_path(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        out = StringIO()
        # PhraseReader isatty True; StringIO isatty is False — use NullWriter for stdout tty.
        class TtyOut(NullWriter):
            def __init__(self) -> None:
                self.buf = StringIO()

            def write(self, s: str) -> int:
                return self.buf.write(s)

            def flush(self) -> None:
                self.buf.flush()

            def getvalue(self) -> str:
                return self.buf.getvalue()

        stdout = TtyOut()
        meta = arm_remote_confirm(
            contract_path=contract_path,
            workspace=self.ws,
            stdin=PhraseReader(""),
            stdout=stdout,
            skip_tty_check=True,
            ttl_sec=120,
        )
        self.assertTrue(meta["armed"])
        self.assertNotIn("challenge", meta)  # secret not in JSON return
        state_dir = run_state_dir(self.ws, "camp", "run-a")
        challenge = read_local_challenge_for_display(state_dir)
        self.assertIsNotNone(challenge)
        self.assertIn(challenge, stdout.getvalue())

        doc = settle_remote_confirm(
            contract_path=contract_path,
            workspace=self.ws,
            challenge=challenge or "",
            phrase="APPROVE",
        )
        self.assertEqual(doc["confirm_channel"], "remote_human_confirm")
        self.assertEqual(doc["confirm_evidence"]["not_equivalent_to"], "local_tty_approve")
        state = load_state(state_dir)
        self.assertEqual(state.get("phase"), "approved")
        self.assertIsNone(load_pending(state_dir))

    def test_wrong_challenge_refuses(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        arm_remote_confirm(
            contract_path=contract_path,
            workspace=self.ws,
            stdin=PhraseReader(""),
            stdout=NullWriter(),
            skip_tty_check=True,
        )
        with self.assertRaises(ApprovalError):
            settle_remote_confirm(
                contract_path=contract_path,
                workspace=self.ws,
                challenge="DEADBEEF",
                phrase="APPROVE",
            )
        pending = load_pending(run_state_dir(self.ws, "camp", "run-a"))
        self.assertIsNotNone(pending)
        self.assertEqual(pending.get("failed_attempts"), 1)

    def test_reuse_refuses(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        arm_remote_confirm(
            contract_path=contract_path,
            workspace=self.ws,
            stdin=PhraseReader(""),
            stdout=NullWriter(),
            skip_tty_check=True,
        )
        challenge = read_local_challenge_for_display(run_state_dir(self.ws, "camp", "run-a"))
        settle_remote_confirm(
            contract_path=contract_path,
            workspace=self.ws,
            challenge=challenge or "",
            phrase="APPROVE",
        )
        with self.assertRaises(ApprovalError):
            settle_remote_confirm(
                contract_path=contract_path,
                workspace=self.ws,
                challenge=challenge or "",
                phrase="APPROVE",
            )

    def test_companion_http_happy_and_fail_closed(self) -> None:
        contract_path = write_contract(self.ws, "contract.json", base_contract())
        arm_remote_confirm(
            contract_path=contract_path,
            workspace=self.ws,
            stdin=PhraseReader(""),
            stdout=NullWriter(),
            skip_tty_check=True,
        )
        challenge = read_local_challenge_for_display(run_state_dir(self.ws, "camp", "run-a"))
        token = generate_pairing_token()
        server, _url, meta = start_companion(
            workspace=self.ws,
            contract_path=contract_path,
            pairing_token=token,
            host="127.0.0.1",
            port=0,
        )
        self.assertFalse(meta["can_approve"])
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            conn = HTTPConnection(host, port, timeout=5)

            # Unauthenticated remote-confirm refused
            conn.request(
                "POST",
                "/v1/remote-confirm",
                body=json.dumps({"challenge": challenge, "phrase": "APPROVE"}),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(conn.getresponse().status, 401)

            # Plugin-style /v1/approve still forbidden even with pairing
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            conn.request("POST", "/v1/approve", body=b"{}", headers=headers)
            self.assertEqual(conn.getresponse().status, 403)

            # Capabilities: can_approve false; can_remote_confirm true while pending
            conn.request("GET", "/v1/capabilities", headers=headers)
            caps = json.loads(conn.getresponse().read().decode("utf-8"))
            self.assertFalse(caps["can_approve"])
            self.assertTrue(caps["can_remote_confirm"])
            self.assertTrue(caps["remote_confirm"]["pending"])

            # Status must not leak challenge secret
            conn.request("GET", "/v1/status", headers=headers)
            status_doc = json.loads(conn.getresponse().read().decode("utf-8"))
            blob = json.dumps(status_doc)
            self.assertNotIn(challenge, blob)
            self.assertTrue(status_doc["companion"]["can_remote_confirm"])
            self.assertFalse(status_doc["companion"]["can_approve"])

            # Wrong challenge refuses
            conn.request(
                "POST",
                "/v1/remote-confirm",
                body=json.dumps({"challenge": "00000000", "phrase": "APPROVE"}),
                headers=headers,
            )
            self.assertEqual(conn.getresponse().status, 403)

            # Happy path with pairing
            conn.request(
                "POST",
                "/v1/remote-confirm",
                body=json.dumps({"challenge": challenge, "phrase": "APPROVE"}),
                headers=headers,
            )
            ok = conn.getresponse()
            self.assertEqual(ok.status, 200)
            body = json.loads(ok.read().decode("utf-8"))
            self.assertTrue(body["settled"])
            self.assertEqual(body["confirm_channel"], "remote_human_confirm")
            self.assertFalse(body["can_approve"])

            approval = load_approval(run_state_dir(self.ws, "camp", "run-a"))
            self.assertIsNotNone(approval)
            self.assertEqual(approval["confirm_channel"], "remote_human_confirm")

            # Reuse refuses
            conn.request(
                "POST",
                "/v1/remote-confirm",
                body=json.dumps({"challenge": challenge, "phrase": "APPROVE"}),
                headers=headers,
            )
            self.assertEqual(conn.getresponse().status, 403)

            # After settle, can_remote_confirm false again
            conn.request("GET", "/v1/capabilities", headers=headers)
            caps2 = json.loads(conn.getresponse().read().decode("utf-8"))
            self.assertFalse(caps2["can_approve"])
            self.assertFalse(caps2["can_remote_confirm"])

            conn.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
