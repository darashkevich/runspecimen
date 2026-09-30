"""Isolate installed-holder discovery from the live /Library socket.

Unit tests must point RS_HOLDER_SOCKET at a temp path or AdapterServer.
These tests do not prove installed protection and do not exercise Touch ID,
Face ID, or a paired phone.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.helpers import (
    NullWriter,
    PhraseReader,
    RunSpecimenTestCase,
    base_contract,
    write_contract,
)

from runspecimen.approve import approve_contract
from runspecimen.errors import ApprovalError, PreflightError
from runspecimen.holder_adapter import (
    INSTALLED_SUPPORT_DIR,
    AdapterServer,
    HolderClient,
    discover_installed_holder_client,
    installed_socket_path,
)
from runspecimen.run import run_contract


def _human(purpose: str, subject: str, policy: str = "local") -> dict:
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


class _EnvIsolation:
    """Restore RS_HOLDER_* keys after a test mutates them."""

    _KEYS = ("RS_HOLDER_SOCKET", "RS_HOLDER_CALLER_ID", "RS_HOLDER_CALLER_SECRET")

    def __init__(self, test: unittest.TestCase) -> None:
        self._previous = {key: os.environ.get(key) for key in self._KEYS}
        test.addCleanup(self.restore)

    def restore(self) -> None:
        for key, value in self._previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def clear_caller(self) -> None:
        os.environ.pop("RS_HOLDER_CALLER_ID", None)
        os.environ.pop("RS_HOLDER_CALLER_SECRET", None)

    def point_socket(self, path: Path) -> None:
        os.environ["RS_HOLDER_SOCKET"] = str(path)

    def set_caller(self, caller_id: str, caller_secret: str) -> None:
        os.environ["RS_HOLDER_CALLER_ID"] = caller_id
        os.environ["RS_HOLDER_CALLER_SECRET"] = caller_secret


class InstalledSocketPathTests(unittest.TestCase):
    def test_default_live_path_when_unset(self) -> None:
        env = _EnvIsolation(self)
        os.environ.pop("RS_HOLDER_SOCKET", None)
        self.assertEqual(
            installed_socket_path(),
            INSTALLED_SUPPORT_DIR / "holder.sock",
        )
        env.restore()

    def test_override_path_when_set(self) -> None:
        env = _EnvIsolation(self)
        override = Path("/tmp/runspecimen-test-holder.sock")
        env.point_socket(override)
        self.assertEqual(installed_socket_path(), override)
        client = discover_installed_holder_client("app", "ab" * 32, _human)
        self.assertIsNone(client)


class HolderSocketIsolationTests(RunSpecimenTestCase):
    """Fail-closed discovery via RS_HOLDER_SOCKET. Not installed protection."""

    def test_missing_socket_fails_closed_without_spawn_or_phrase(self) -> None:
        env = _EnvIsolation(self)
        missing = Path(self.ws) / "missing-holder.sock"
        env.point_socket(missing)
        env.clear_caller()
        path = write_contract(self.ws, "c.json", base_contract(execution_approval="local"))
        reader = PhraseReader("APPROVE\n")
        with self.assertRaises(ApprovalError) as approve_ctx:
            approve_contract(
                contract_path=path,
                workspace=self.ws,
                skip_tty_check=True,
                stdin=reader,
                stdout=NullWriter(),
            )
        self.assertIn("no typed-phrase fallback", str(approve_ctx.exception))
        self.assertEqual(reader._pos, 0)
        with self.assertRaises(PreflightError) as run_ctx:
            run_contract(contract_path=path, workspace=self.ws)
        message = str(run_ctx.exception)
        self.assertIn("requires the holder", message)
        self.assertIn("no typed-phrase fallback", message)
        self.assertFalse((self.ws / "outputs" / "out.json").exists())

    def test_socket_present_without_caller_env_fails_closed(self) -> None:
        env = _EnvIsolation(self)
        td = tempfile.TemporaryDirectory(prefix="rsh-sock-present-", dir="/tmp")
        self.addCleanup(td.cleanup)
        server = AdapterServer(Path(td.name), bootstrap_secret="ab" * 32)
        server.start()
        self.addCleanup(server.stop)
        env.point_socket(server.socket_path)
        env.clear_caller()
        path = write_contract(self.ws, "c.json", base_contract(execution_approval="local"))
        with self.assertRaises(PreflightError) as ctx:
            run_contract(contract_path=path, workspace=self.ws)
        message = str(ctx.exception)
        self.assertIn("RS_HOLDER_CALLER_ID/RS_HOLDER_CALLER_SECRET are unset", message)
        self.assertIn("no typed-phrase fallback", message)
        self.assertFalse((self.ws / "outputs" / "out.json").exists())

    def test_unenrolled_caller_fails_closed_on_adapter_socket(self) -> None:
        env = _EnvIsolation(self)
        td = tempfile.TemporaryDirectory(prefix="rsh-unenrolled-", dir="/tmp")
        self.addCleanup(td.cleanup)
        server = AdapterServer(Path(td.name), bootstrap_secret="cd" * 32)
        server.start()
        self.addCleanup(server.stop)
        env.point_socket(server.socket_path)
        env.set_caller("app", "ef" * 32)
        path = write_contract(self.ws, "c.json", base_contract(execution_approval="local"))
        with self.assertRaises(PreflightError) as ctx:
            run_contract(contract_path=path, workspace=self.ws)
        message = str(ctx.exception)
        self.assertTrue(
            "not enrolled" in message or "authentication failed" in message or "requires the holder" in message,
            msg=message,
        )
        self.assertFalse((self.ws / "outputs" / "out.json").exists())

    def test_named_policy_hardware_true_fails_closed(self) -> None:
        """CLI helper claims hardware:True; HMAC is not biometric."""
        for policy in ("local", "companion", "dual"):
            with self.subTest(policy=policy):
                env = _EnvIsolation(self)
                td = tempfile.TemporaryDirectory(prefix=f"rsh-hw-{policy}-", dir="/tmp")
                self.addCleanup(td.cleanup)
                secret = "11" * 32
                server = AdapterServer(Path(td.name), bootstrap_secret=secret)
                server.start()
                self.addCleanup(server.stop)
                boot = HolderClient(server.socket_path, "bootstrap", secret, _human)
                enrolled = boot.call(
                    {
                        "op": "enroll",
                        "new_caller_id": "app",
                        "human": _human("enroll", "app", policy=policy),
                    }
                )
                client = HolderClient(
                    server.socket_path,
                    "app",
                    enrolled["caller_secret"],
                    _human,
                )
                client.call(
                    {
                        "op": "set-policy",
                        "human": _human("set-policy", policy, policy=policy),
                    }
                )
                env.point_socket(server.socket_path)
                env.set_caller("app", enrolled["caller_secret"])
                # Fresh workspace per policy so prior outputs cannot confuse asserts.
                ws_td = tempfile.TemporaryDirectory(prefix=f"rsh-ws-{policy}-")
                self.addCleanup(ws_td.cleanup)
                ws = Path(ws_td.name)
                (ws / "work").mkdir()
                (ws / "outputs").mkdir()
                (ws / "work" / "job.py").write_text(
                    "import json\nfrom pathlib import Path\n"
                    "Path('outputs/out.json').write_text(json.dumps({'status': 'ok'}) + '\\n')\n",
                    encoding="utf-8",
                )
                path = write_contract(ws, "c.json", base_contract(execution_approval=policy))
                with self.assertRaises(PreflightError) as ctx:
                    run_contract(contract_path=path, workspace=ws)
                message = str(ctx.exception)
                # Fail closed: missing device signatures, or explicit HMAC≠hardware.
                # Fail closed before spawn: unpaired devices, missing HMAC
                # signatures, or an explicit hardware claim refusal.
                self.assertTrue(
                    "required approval devices" in message
                    or "signatures are missing" in message
                    or "not hardware" in message
                    or "requires the holder" in message
                    or "installed holder did not claim" in message,
                    msg=message,
                )
                self.assertFalse((ws / "outputs" / "out.json").exists())

    def test_signed_hmac_with_hardware_true_is_refused(self) -> None:
        """Device HMAC must stay labeled not-hardware; it is not biometric."""
        from runspecimen.execution_holder import ExecutionHolder, HolderRefusal, message_mac
        import time

        td = tempfile.TemporaryDirectory(prefix="rsh-hmac-hw-", dir="/tmp")
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "state"
        holder = ExecutionHolder(root, allow_test_double=True, bootstrap_secret="22" * 32)
        holder.enroll("app", _human("enroll", "app"))
        paired = holder.pair_device(
            "mac-1",
            {
                **_human("pair", "mac-1"),
                "role": "mac",
                "fingerprint": "fp-mac",
            },
        )
        secrets = {"mac-1": paired["device_secret"]}
        holder.set_policy(_human("set-policy", "local"))
        expires_at = int(time.time()) + 3600
        challenge = {
            "purpose": "set-policy",
            "subject": "local",
            "policy": "local",
            "devices": ["mac"],
            "expires_at": expires_at,
            "holder_id": holder.holder_id,
            "generation": holder.generation,
            "domain": "holder-device-hmac-v1",
            "attestation_class": "device-hmac-not-hardware",
            "authorized": {},
        }
        human = {
            "method": "local",
            "purpose": "set-policy",
            "subject": "local",
            "policy": "local",
            "devices": ["mac"],
            "expires_at": expires_at,
            "hardware": True,
            "attestation_class": "device-hmac-not-hardware",
            "signatures": {"mac-1": message_mac(secrets["mac-1"], challenge)},
        }
        with self.assertRaises(HolderRefusal) as ctx:
            holder.set_policy(human)
        self.assertIn("not hardware", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
