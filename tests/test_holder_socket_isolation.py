"""Installed-holder discovery stays off the live /Library socket in unit tests.

Production ``installed_socket_path`` ignores ``RS_HOLDER_SOCKET``. These tests
inject a temp path by patching that function. They do not prove installed
protection and they do not exercise Touch ID, Face ID, or a paired phone.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import RunSpecimenTestCase, base_contract, write_contract

from runspecimen.errors import PreflightError
from runspecimen.holder_adapter import (
    INSTALLED_SUPPORT_DIR,
    AdapterServer,
    HolderClient,
    installed_socket_path,
)
from runspecimen.run import run_contract


_CALLER_KEYS = ("RS_HOLDER_CALLER_ID", "RS_HOLDER_CALLER_SECRET")
_LIVE = INSTALLED_SUPPORT_DIR / "holder.sock"


def _software_human(purpose: str, subject: str, policy: str = "local") -> dict:
    import time

    devices = {"local": ["mac"], "companion": ["phone"], "dual": ["mac", "phone"]}[policy]
    return {
        "method": "software-test-double",
        "purpose": purpose,
        "policy": policy,
        "subject": subject,
        "expires_at": int(time.time()) + 3600,
        "hardware": False,
        "devices": devices,
        "attestation_class": "software-test-double-not-hardware",
    }


class _CallerEnv:
    def __init__(self, test: unittest.TestCase) -> None:
        self._previous = {key: os.environ.get(key) for key in _CALLER_KEYS}
        test.addCleanup(self.restore)

    def restore(self) -> None:
        for key, value in self._previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def clear(self) -> None:
        for key in _CALLER_KEYS:
            os.environ.pop(key, None)

    def set(self, caller_id: str, caller_secret: str) -> None:
        os.environ["RS_HOLDER_CALLER_ID"] = caller_id
        os.environ["RS_HOLDER_CALLER_SECRET"] = caller_secret


def _seed_job(ws: Path) -> None:
    (ws / "work").mkdir(parents=True, exist_ok=True)
    (ws / "outputs").mkdir(parents=True, exist_ok=True)
    (ws / "work" / "job.py").write_text(
        "import json\nfrom pathlib import Path\n"
        "Path('outputs/out.json').write_text(json.dumps({'status': 'ok'}) + '\\n')\n",
        encoding="utf-8",
    )


class HolderSocketIsolationTests(RunSpecimenTestCase):
    def test_production_path_stays_live_while_tests_inject_a_temp_socket(self) -> None:
        previous = os.environ.get("RS_HOLDER_SOCKET")
        os.environ["RS_HOLDER_SOCKET"] = "/tmp/not-the-live-holder.sock"
        self.addCleanup(self._restore_socket_env, previous)
        self.assertEqual(installed_socket_path(), _LIVE)

    def _restore_socket_env(self, previous: str | None) -> None:
        if previous is None:
            os.environ.pop("RS_HOLDER_SOCKET", None)
        else:
            os.environ["RS_HOLDER_SOCKET"] = previous

    def test_missing_socket_fails_closed_without_the_live_path(self) -> None:
        env = _CallerEnv(self)
        env.clear()
        missing = Path(self.ws) / "missing-holder.sock"
        path = write_contract(self.ws, "c.json", base_contract(execution_approval="local"))
        with mock.patch(
            "runspecimen.holder_adapter.installed_socket_path",
            return_value=missing,
        ) as patched:
            with self.assertRaises(PreflightError) as ctx:
                run_contract(contract_path=path, workspace=self.ws)
        self.assertIn("socket is missing", str(ctx.exception))
        self.assertIn("no typed-phrase fallback", str(ctx.exception))
        self.assertTrue(patched.called)
        self.assertNotEqual(patched.return_value, _LIVE)
        self.assertFalse((self.ws / "outputs" / "out.json").exists())

    def test_socket_present_without_caller_env_fails_closed(self) -> None:
        env = _CallerEnv(self)
        env.clear()
        present = Path(self.ws) / "present-holder.sock"
        present.write_bytes(b"")
        path = write_contract(self.ws, "c.json", base_contract(execution_approval="local"))
        with mock.patch(
            "runspecimen.holder_adapter.installed_socket_path",
            return_value=present,
        ):
            with self.assertRaises(PreflightError) as ctx:
                run_contract(contract_path=path, workspace=self.ws)
        message = str(ctx.exception)
        self.assertIn("RS_HOLDER_CALLER_ID/RS_HOLDER_CALLER_SECRET are unset", message)
        self.assertIn("no typed-phrase fallback", message)
        self.assertFalse((self.ws / "outputs" / "out.json").exists())

    def test_unenrolled_caller_fails_closed_on_a_temp_adapter(self) -> None:
        env = _CallerEnv(self)
        td = tempfile.TemporaryDirectory(prefix="rsh-unenrolled-", dir="/tmp")
        self.addCleanup(td.cleanup)
        server = AdapterServer(Path(td.name), bootstrap_secret="cd" * 32)
        server.start()
        self.addCleanup(server.stop)
        env.set("app", "ef" * 32)
        path = write_contract(self.ws, "c.json", base_contract(execution_approval="local"))
        with mock.patch(
            "runspecimen.holder_adapter.installed_socket_path",
            return_value=server.socket_path,
        ):
            with self.assertRaises(PreflightError) as ctx:
                run_contract(contract_path=path, workspace=self.ws)
        message = str(ctx.exception)
        self.assertIn("will not claim a hardware human", message)
        self.assertIn("device signature", message)
        self.assertNotEqual(server.socket_path, _LIVE)
        self.assertFalse((self.ws / "outputs" / "out.json").exists())

    def test_named_policy_hardware_true_fails_closed(self) -> None:
        """CLI refuses before it claims hardware or opens the holder."""
        for policy in ("local", "companion", "dual"):
            with self.subTest(policy=policy):
                self._named_policy_refuses_hardware_claim(policy)

    def _named_policy_refuses_hardware_claim(self, policy: str) -> None:
        env = _CallerEnv(self)
        td = tempfile.TemporaryDirectory(prefix=f"rsh-hw-{policy}-", dir="/tmp")
        self.addCleanup(td.cleanup)
        secret = "11" * 32
        server = AdapterServer(Path(td.name), bootstrap_secret=secret)
        server.start()
        self.addCleanup(server.stop)
        boot = HolderClient(server.socket_path, "bootstrap", secret, _software_human)
        enrolled = boot.call(
            {
                "op": "enroll",
                "new_caller_id": "app",
                "human": _software_human("enroll", "app", policy=policy),
            }
        )
        client = HolderClient(
            server.socket_path,
            "app",
            enrolled["caller_secret"],
            _software_human,
        )
        client.call({"op": "set-policy", "human": _software_human("set-policy", policy, policy=policy)})
        env.set("app", enrolled["caller_secret"])
        ws_td = tempfile.TemporaryDirectory(prefix=f"rsh-ws-{policy}-", dir="/tmp")
        self.addCleanup(ws_td.cleanup)
        ws = Path(ws_td.name)
        _seed_job(ws)
        path = write_contract(ws, "c.json", base_contract(execution_approval=policy))
        with mock.patch(
            "runspecimen.holder_adapter.installed_socket_path",
            return_value=server.socket_path,
        ):
            with self.assertRaises(PreflightError) as ctx:
                run_contract(contract_path=path, workspace=ws)
        message = str(ctx.exception)
        self.assertIn("will not claim a hardware human", message)
        self.assertIn("device signature", message)
        self.assertNotIn("hardware\": true", message.lower())
        self.assertFalse((ws / "outputs" / "out.json").exists())

    def test_socket_peer_ignores_a_claimed_foreign_uid(self) -> None:
        import socket

        from runspecimen.holder_daemon import authenticated_peer

        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        claimed = os.getuid() + 1
        uid, _gid = authenticated_peer(right, claimed_uid=claimed)
        self.assertEqual(uid, os.getuid())
        self.assertNotEqual(uid, claimed)
        self.assertNotEqual(authenticated_peer(left, claimed_uid=0)[0], claimed)


if __name__ == "__main__":
    unittest.main()
