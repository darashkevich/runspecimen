"""Unprivileged execution-holder tests.

These tests run in the same user account as the holder files. They do not
prove installed protection, and they do not exercise Touch ID, Face ID, or
a paired phone.
"""

from __future__ import annotations

import ctypes
import gc
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path
from unittest import mock

from tests.helpers import (
    NullWriter,
    PhraseReader,
    RunSpecimenTestCase,
    approve,
    base_contract,
    write_contract,
)

from runspecimen.approve import approve_contract
from runspecimen.errors import ApprovalError, PreflightError
from runspecimen.execution_holder import (
    PROTOCOL,
    ExecutionHolder,
    HolderRefusal,
    handle_message,
    message_mac,
    unlink_replay_history,
)
from runspecimen.holder_adapter import AdapterServer, HolderClient
from runspecimen.hashutil import sha256_file
from runspecimen.run import run_contract
from runspecimen.state import load_state
from runspecimen.paths import run_state_dir


def _human(purpose: str, subject: str, policy: str = "local", method: str = "software-test-double", **extra: object) -> dict:
    devices = {"local": ["mac"], "companion": ["phone"], "dual": ["mac", "phone"]}[policy]
    doc = {
        "method": method,
        "purpose": purpose,
        "policy": policy,
        "subject": subject,
        "expires_at": int(time.time()) + 3600,
        "hardware": False,
        "devices": devices,
        "attestation_class": "software-test-double-not-hardware",
    }
    doc.update(extra)
    return doc


def _binding(workspace: Path, path: Path, digest: str, policy: str = "local") -> dict:
    exe = str(path.resolve())
    return {
        "contract_hash": "c" * 64,
        "workspace": str(workspace.resolve()),
        "argv": [str(path), "payload.txt"],
        "executable": exe,
        "policy": policy,
        "cwd": str(workspace.resolve()),
        "launch_argv": [exe, "payload.txt"],
        "bounds": {"wall_timeout_sec": 10, "stdout_max_bytes": 65536, "stderr_max_bytes": 65536},
        "key_generation": 1,
    }


def _remove_sealed_tree(path: Path) -> None:
    """Remove a holder snapshot. Owner-only modes are restored first."""
    import shutil

    if not path.exists():
        return
    for dirpath, _dirnames, filenames in os.walk(path):
        os.chmod(dirpath, 0o700)
        for name in filenames:
            os.chmod(Path(dirpath) / name, 0o600)
    shutil.rmtree(path)
    if path.exists():
        raise AssertionError(f"snapshot cleanup left {path}")


def _snapshot_execute_roundtrip(test: unittest.TestCase) -> None:
    """Positive snapshot execute without PyNaCl. Not a hardware approval."""
    td = tempfile.TemporaryDirectory(prefix="rsh-snap-exec-")
    test.addCleanup(td.cleanup)
    root = Path(td.name) / "state"
    ws = Path(td.name) / "ws"
    ws.mkdir()
    holder = ExecutionHolder(
        root,
        allow_test_double=True,
        snapshot_base=Path(td.name) / "run-snapshots",
    )
    holder.enroll("app", _human("enroll", "app"))
    holder.set_policy(_human("set-policy", "local"))
    script = ws / "job.py"
    script.write_text("print('from-snapshot')\n", encoding="utf-8")
    digest = sha256_file(script)
    binding = _binding(ws, script, digest)
    launch = [sys.executable, str(script.resolve())]
    binding["launch_argv"] = launch
    binding["argv"] = [str(script.resolve())]
    consumed = holder.consume(
        nonce="n-exec",
        policy="local",
        human=_human("consume", "n-exec"),
        workspace=ws,
        files=[(str(script.resolve()), digest)],
        binding=binding,
    )
    test.assertIn("snapshot_root", consumed)
    result = holder.execute(token="n-exec", human=_human("execute", "n-exec"))
    test.assertEqual(result["exit_code"], 0)
    test.assertIn(b"from-snapshot", __import__("base64").b64decode(result["stdout_b64"]))
    test.assertFalse(result["hardware"])
    test.assertNotEqual(result["attestation_class"], "secure-enclave")


def _payload(directory: Path, text: str = "alpha\n") -> tuple[Path, str]:
    path = directory / "payload.txt"
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return path, digest


class HolderCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="rsh-")
        self.root = Path(self._td.name) / "state"
        self.ws = Path(self._td.name) / "ws"
        self.ws.mkdir()
        self.holder = ExecutionHolder(self.root, allow_test_double=True)
        self.holder.enroll("app", _human("enroll", "app"))
        self.holder.set_policy(_human("set-policy", "local"))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_phrase_expiry_and_unconnected_verifier_fail_closed(self) -> None:
        phrase = _human("set-policy", "local")
        phrase["method"] = "APPROVE"
        with self.assertRaises(HolderRefusal):
            self.holder.set_policy(phrase)
        expired = _human("set-policy", "local")
        expired["expires_at"] = int(time.time()) - 1
        with self.assertRaises(HolderRefusal) as expired_ctx:
            self.holder.set_policy(expired)
        self.assertIn("expired", str(expired_ctx.exception))
        with self.assertRaises(HolderRefusal) as local_ctx:
            self.holder.set_policy(_human("set-policy", "local", method="local"))
        self.assertIn("signature", str(local_ctx.exception).lower())
        closed = ExecutionHolder(Path(self._td.name) / "closed", allow_test_double=False)
        with self.assertRaises(HolderRefusal):
            closed.enroll("app", _human("enroll", "app"))

    def test_replay_rollback_downgrade_and_state_loss(self) -> None:
        path, digest = _payload(self.ws)
        first = self.holder.consume(
            nonce="n1",
            policy="local",
            human=_human("consume", "n1"),
            workspace=self.ws,
            files=[("payload.txt", digest)],
            binding=_binding(self.ws, path, digest),
        )
        self.assertNotEqual(first["holder_id"], first["payload_digest"])
        self.assertFalse(first["installed_protection"])
        self.assertIn(str(path.resolve()), first["path_map"])
        with self.assertRaises(HolderRefusal):
            self.holder.consume(
                nonce="n1",
                policy="local",
                human=_human("consume", "n1"),
                workspace=self.ws,
                files=[("payload.txt", digest)],
                binding=_binding(self.ws, path, digest),
            )
        self.holder.cancel_uncertain("n1", _human("cancel", "n1"))
        with self.assertRaises(HolderRefusal) as replay:
            self.holder.consume(
                nonce="n1",
                policy="local",
                human=_human("consume", "n1"),
                workspace=self.ws,
                files=[("payload.txt", digest)],
                binding=_binding(self.ws, path, digest),
            )
        self.assertIn("already consumed", str(replay.exception))

        previous = (self.root / "policy.json").read_text(encoding="utf-8")
        self.holder.set_policy(_human("set-policy", "companion", policy="local"))
        (self.root / "policy.json").write_text(previous, encoding="utf-8")
        with self.assertRaises(HolderRefusal) as rolled:
            ExecutionHolder(self.root, allow_test_double=True)
        self.assertIn("generation", str(rolled.exception))

        fresh = Path(self._td.name) / "down"
        holder = ExecutionHolder(fresh, allow_test_double=True)
        meta = (fresh / "meta.json").read_text(encoding="utf-8").replace(
            f'"protocol": {PROTOCOL}', '"protocol": 0', 1
        )
        (fresh / "meta.json").write_text(meta, encoding="utf-8")
        with self.assertRaises(HolderRefusal) as down:
            ExecutionHolder(fresh, allow_test_double=True)
        self.assertIn("downgraded", str(down.exception))
        self.assertIsNotNone(holder.holder_id)

        enrolled = Path(self._td.name) / "lost"
        lost = ExecutionHolder(enrolled, allow_test_double=True)
        lost.enroll("app", _human("enroll", "app"))
        unlink_replay_history(enrolled)
        with self.assertRaises(HolderRefusal) as missing:
            ExecutionHolder(enrolled, allow_test_double=True)
        self.assertIn("replay history is missing", str(missing.exception))

    def test_input_mutation_does_not_spend_or_match_holder_identity(self) -> None:
        path, _digest = _payload(self.ws, "alpha\n")
        stale = hashlib.sha256(b"other\n").hexdigest()
        with self.assertRaises(HolderRefusal):
            self.holder.consume(
                nonce="mutated",
                policy="local",
                human=_human("consume", "mutated"),
                workspace=self.ws,
                files=[("payload.txt", stale)],
                binding=_binding(self.ws, path, stale),
            )
        spent = (self.root / "spent.json").read_text(encoding="utf-8")
        self.assertNotIn("mutated", spent)

    def test_uncertain_child_blocks_and_cancel_clears(self) -> None:
        path, digest = _payload(self.ws)
        self.holder.consume(
            nonce="child",
            policy="local",
            human=_human("consume", "child"),
            workspace=self.ws,
            files=[("payload.txt", digest)],
            binding=_binding(self.ws, path, digest),
        )
        with self.assertRaises(HolderRefusal) as held:
            self.holder.consume(
                nonce="next",
                policy="local",
                human=_human("consume", "next"),
                workspace=self.ws,
                files=[("payload.txt", digest)],
                binding=_binding(self.ws, path, digest),
            )
        self.assertIn("lease", str(held.exception))
        self.holder.cancel_uncertain("child", _human("cancel", "child"))
        again = self.holder.consume(
            nonce="next",
            policy="local",
            human=_human("consume", "next"),
            workspace=self.ws,
            files=[("payload.txt", digest)],
            binding=_binding(self.ws, path, digest),
        )
        self.assertTrue(again["ok"])

    def test_pair_rotate_revoke_and_imported_label(self) -> None:
        paired = self.holder.pair_device(
            "mac-1",
            _human("pair", "mac-1", role="mac", fingerprint="aa" * 16),
        )
        self.assertEqual(paired["attestation"], "software-test-double")
        with self.assertRaises(HolderRefusal):
            self.holder.pair_device(
                "mac-2",
                _human(
                    "pair",
                    "mac-2",
                    role="mac",
                    fingerprint="bb" * 16,
                    attestation="secure-enclave",
                ),
            )
        rotated = self.holder.rotate_caller(_human("rotate", "app"))
        self.assertEqual(rotated["key_generation"], 2)
        self.holder.revoke_device("mac-1", _human("revoke", "mac-1"))
        path, digest = _payload(self.ws)
        binding = _binding(self.ws, path, digest)
        binding["key_generation"] = 2
        with self.assertRaises(HolderRefusal) as revoked:
            self.holder.consume(
                nonce="after-revoke",
                policy="local",
                human=_human("consume", "after-revoke", device_ids=["mac-1"]),
                workspace=self.ws,
                files=[("payload.txt", digest)],
                binding=binding,
            )
        self.assertIn("revoked", str(revoked.exception))


class HolderIpcTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="rsh-", dir="/tmp")
        self.secret = "ab" * 32
        self.server = AdapterServer(Path(self._td.name), bootstrap_secret=self.secret)
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()
        self._td.cleanup()

    def _human_for(self, purpose: str, subject: str) -> dict:
        policy = "local"
        if purpose == "set-policy":
            policy = subject
        return _human(purpose, subject, policy=policy)

    def _enrolled(self) -> HolderClient:
        boot = HolderClient(self.server.socket_path, "bootstrap", self.secret, self._human_for)
        enrolled = boot.call(
            {"op": "enroll", "new_caller_id": "app", "human": self._human_for("enroll", "app")}
        )
        client = HolderClient(
            self.server.socket_path,
            "app",
            enrolled["caller_secret"],
            self._human_for,
        )
        client.call({"op": "set-policy", "human": self._human_for("set-policy", "local")})
        return client

    def test_caller_impersonation_fails(self) -> None:
        client = self._enrolled()
        covered = {
            "protocol": PROTOCOL,
            "caller_id": client.caller_id,
            "body": {"op": "set-policy", "human": self._human_for("set-policy", "local")},
        }
        forged = {**covered, "mac": message_mac("cd" * 32, covered)}
        with self.assertRaises(HolderRefusal) as ctx:
            handle_message(
                self.server.holder,
                forged,
                bootstrap_secret=self.secret,
            )
        self.assertIn("authentication failed", str(ctx.exception))

    def test_protocol_downgrade_is_refused(self) -> None:
        covered = {"protocol": 0, "caller_id": "bootstrap", "body": {"op": "enroll"}}
        message = {**covered, "mac": message_mac(self.secret, covered)}
        with self.assertRaises(HolderRefusal) as ctx:
            handle_message(self.server.holder, message, bootstrap_secret=self.secret)
        self.assertIn("downgrade", str(ctx.exception))


class HeldRunTests(RunSpecimenTestCase):
    def test_policy_without_holder_does_not_spawn_or_accept_a_phrase(self) -> None:
        doc = base_contract(execution_approval="local")
        path = write_contract(self.ws, "c.json", doc)
        reader = PhraseReader("APPROVE\n")
        with self.assertRaises(ApprovalError) as ctx:
            approve_contract(
                contract_path=path,
                workspace=self.ws,
                skip_tty_check=True,
                stdin=reader,
                stdout=NullWriter(),
            )
        self.assertIn("no typed-phrase fallback", str(ctx.exception))
        self.assertEqual(reader._pos, 0)
        missing_sock = Path(self.ws) / "absent-holder.sock"
        with mock.patch(
            "runspecimen.holder_adapter.installed_socket_path",
            return_value=missing_sock,
        ):
            with self.assertRaises(PreflightError) as missing:
                run_contract(contract_path=path, workspace=self.ws)
        message = str(missing.exception)
        self.assertIn("requires the holder", message)
        self.assertIn("socket is missing", message)
        self.assertIn("no typed-phrase fallback", message)
        self.assertFalse((self.ws / "outputs" / "out.json").exists())

    def test_adapter_consume_runs_from_snapshots_once(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-", dir="/tmp")
        self.addCleanup(td.cleanup)
        server = AdapterServer(Path(td.name), bootstrap_secret="ef" * 32)
        server.start()
        self.addCleanup(server.stop)
        boot = HolderClient(server.socket_path, "bootstrap", "ef" * 32, _human)
        enrolled = boot.call({"op": "enroll", "new_caller_id": "app", "human": _human("enroll", "app")})
        client = HolderClient(server.socket_path, "app", enrolled["caller_secret"], _human)
        client.call({"op": "set-policy", "human": _human("set-policy", "local")})
        path = write_contract(self.ws, "c.json", base_contract(execution_approval="local"))
        result = run_contract(contract_path=path, workspace=self.ws, holder=client)
        self.assertEqual(result["exit_code"], 0, result)
        self.assertTrue((self.ws / "outputs" / "out.json").exists())
        state = load_state(run_state_dir(self.ws, "camp", "run-a"))
        self.assertFalse(state["execution_holder"]["installed_protection"])
        self.assertNotEqual(
            state["execution_holder"]["holder_id"],
            state["execution_holder"]["payload_digest"],
        )
        self.assertTrue(state["execution_holder"]["snapshot_root"])
        # Mutating the live script after a completed held run must not revive a spent nonce.
        (self.ws / "work" / "job.py").write_text("raise SystemExit('live tree')\n", encoding="utf-8")
        server.stop()
        restarted = AdapterServer(Path(td.name), bootstrap_secret="ef" * 32)
        restarted.start()
        self.addCleanup(restarted.stop)
        again = HolderClient(restarted.socket_path, "app", enrolled["caller_secret"], _human)
        with self.assertRaises(HolderRefusal) as spent:
            again.call(
                {
                    "op": "consume",
                    "nonce": state["contract_hash"],
                    "policy": "local",
                    "human": _human("consume", state["contract_hash"]),
                    "workspace": str(self.ws),
                    "files": [[str((self.ws / "work" / "job.py").resolve()), sha256_file(self.ws / "work" / "job.py")]],
                    "binding": {
                        "contract_hash": state["contract_hash"],
                        "workspace": str(self.ws.resolve()),
                        "argv": ["job.py"],
                        "executable": str((self.ws / "work" / "job.py").resolve()),
                        "policy": "local",
                        "cwd": str(self.ws.resolve()),
                        "bounds": {"wall_timeout_sec": 1, "stdout_max_bytes": 1, "stderr_max_bytes": 1},
                        "key_generation": 1,
                    },
                }
            )
        self.assertIn("already consumed", str(spent.exception))
        # Unprivileged adapter tests do not prove installed protection.
        self.assertFalse(state["execution_holder"]["installed_protection"])



class HolderFailClosedRegressionTests(unittest.TestCase):
    """These tests do not prove installed protection."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="rsh-")
        self.root = Path(self._td.name) / "state"
        self.ws = Path(self._td.name) / "ws"
        self.ws.mkdir()
        self.holder = ExecutionHolder(self.root, allow_test_double=True)
        self.holder.enroll("app", _human("enroll", "app", policy="dual"))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_local_only_authorization_cannot_downgrade_dual(self) -> None:
        before = self.holder.set_policy(_human("set-policy", "dual", policy="dual"))
        self.assertEqual(before["policy"], "dual")
        generation = before["generation"]
        with self.assertRaises(HolderRefusal) as ctx:
            self.holder.set_policy(_human("set-policy", "local", policy="local"))
        self.assertIn("authorization", str(ctx.exception).lower())
        policy = (self.root / "policy.json").read_text(encoding="utf-8")
        self.assertIn('"name": "dual"', policy)
        self.assertIn(f'"generation": {generation}', policy)
        restarted = ExecutionHolder(self.root, allow_test_double=True)
        self.assertEqual(restarted.generation, generation)

    def test_caller_clock_cannot_bypass_expiry(self) -> None:
        self.holder.set_policy(_human("set-policy", "local", policy="local"))
        expired = _human("set-policy", "companion", policy="local")
        expired["expires_at"] = int(time.time()) - 30
        with self.assertRaises(HolderRefusal) as ctx:
            self.holder.set_policy(expired, now=float(expired["expires_at"] - 100))
        self.assertIn("expired", str(ctx.exception))
        # A still-valid expiry keeps working against the holder clock.
        self.holder.set_policy(_human("set-policy", "companion", policy="local"))

    def test_malformed_lease_fails_closed(self) -> None:
        self.holder.set_policy(_human("set-policy", "local", policy="local"))
        path, digest = _payload(self.ws)
        first = self.holder.consume(
            nonce="lease-n1",
            policy="local",
            human=_human("consume", "lease-n1"),
            workspace=self.ws,
            files=[("payload.txt", digest)],
            binding=_binding(self.ws, path, digest),
        )
        self.assertTrue(first["ok"])
        spent_before = (self.root / "spent.json").read_text(encoding="utf-8")
        for bad in ('{}', '{"held": "yes"}', 'not-json'):
            (self.root / "lease.json").write_text(bad, encoding="utf-8")
            with self.assertRaises(HolderRefusal) as ctx:
                self.holder.consume(
                    nonce=f"after-{bad[:3]}",
                    policy="local",
                    human=_human("consume", f"after-{bad[:3]}"),
                    workspace=self.ws,
                    files=[("payload.txt", digest)],
                    binding=_binding(self.ws, path, digest),
                )
            self.assertIn("lease", str(ctx.exception).lower())
            spent_after = (self.root / "spent.json").read_text(encoding="utf-8")
            self.assertEqual(spent_before, spent_after)
            self.assertNotIn(f"after-{bad[:3]}", spent_after)
        # Well-formed held lease still blocks the next nonce.
        (self.root / "lease.json").write_text(
            '{"held": true, "token": "lease-n1", "child": "uncertain"}\n',
            encoding="utf-8",
        )
        with self.assertRaises(HolderRefusal) as held:
            self.holder.consume(
                nonce="still-blocked",
                policy="local",
                human=_human("consume", "still-blocked"),
                workspace=self.ws,
                files=[("payload.txt", digest)],
                binding=_binding(self.ws, path, digest),
            )
        self.assertIn("lease", str(held.exception).lower())


class PhrasePathUnchangedTests(RunSpecimenTestCase):
    def test_ordinary_contract_still_uses_the_typed_phrase(self) -> None:
        path = write_contract(self.ws, "c.json", base_contract())
        approve(self.ws, path)
        self.assertTrue((run_state_dir(self.ws, "camp", "run-a") / "approval.json").exists())


if __name__ == "__main__":
    unittest.main()


def _sign_human(
    holder: ExecutionHolder,
    device_private_keys: dict[str, str],
    purpose: str,
    subject: str,
    policy: str,
    authorized: dict | None = None,
) -> dict:
    """Build an Ed25519-signed local/companion/dual authorization.

    Labeled not-hardware. This is not biometric execution and these tests do
    not prove installed protection.
    """
    from runspecimen.holder_asymmetric import digest_challenge, sign_device_challenge

    devices = {"local": ["mac"], "companion": ["phone"], "dual": ["mac", "phone"]}[policy]
    expires_at = int(time.time()) + 3600
    auth = authorized or {}
    challenge = {
        "purpose": purpose,
        "subject": subject,
        "policy": policy,
        "devices": sorted(devices),
        "expires_at": expires_at,
        "holder_id": holder.holder_id,
        "generation": holder.generation,
        "domain": "holder-device-ed25519-v1",
        "attestation_class": "device-ed25519-not-hardware",
        "authorized": auth,
    }
    message = digest_challenge(challenge)
    signatures = {
        device_id: sign_device_challenge(priv, message)
        for device_id, priv in device_private_keys.items()
    }
    return {
        "method": policy,
        "purpose": purpose,
        "subject": subject,
        "policy": policy,
        "devices": devices,
        "expires_at": expires_at,
        "hardware": False,
        "attestation_class": "device-ed25519-not-hardware",
        "signatures": signatures,
    }


class HolderSocketAdmissionTests(unittest.TestCase):
    """Unprivileged harness only. These tests do not prove installed protection."""

    def test_stalled_client_and_oversize_frame_are_refused(self) -> None:
        import socket
        import threading

        from runspecimen.holder_io import MAX_FRAME_BYTES

        td = tempfile.TemporaryDirectory(prefix="rsh-sock-", dir="/tmp")
        self.addCleanup(td.cleanup)
        server = AdapterServer(
            Path(td.name),
            bootstrap_secret="ab" * 32,
            read_timeout_sec=0.2,
            max_frame_bytes=4096,
            max_in_flight=1,
        )
        server.start()
        self.addCleanup(server.stop)

        def stall() -> None:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(str(server.socket_path))
            try:
                sock.sendall(b"x" * 16)  # no newline
                time.sleep(0.6)
            finally:
                sock.close()

        t = threading.Thread(target=stall)
        t.start()
        time.sleep(0.05)
        # While stalled connection holds admission, second client is refused.
        sock2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock2.connect(str(server.socket_path))
        sock2.sendall(b'{"ok":false}\n')
        raw = sock2.recv(4096).decode("utf-8")
        sock2.close()
        t.join(timeout=2)
        self.assertIn("admission limit reached", raw)

        # Oversize frame
        sock3 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock3.connect(str(server.socket_path))
        sock3.sendall(b"y" * 5000 + b"\n")
        raw3 = sock3.recv(4096).decode("utf-8")
        sock3.close()
        self.assertIn("frame limit", raw3)
        self.assertLess(4096, MAX_FRAME_BYTES)


class HolderCryptoAndExecuteTests(unittest.TestCase):
    """Unprivileged core. These tests do not prove installed protection."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="rsh-crypto-")
        self.root = Path(self._td.name) / "state"
        self.ws = Path(self._td.name) / "ws"
        self.ws.mkdir()
        self.bootstrap = "cd" * 32
        self.holder = ExecutionHolder(
            self.root,
            allow_test_double=False,
            bootstrap_secret=self.bootstrap,
        )

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_bootstrap_and_signed_local_execute_from_snapshots(self) -> None:
        from runspecimen.execution_holder import message_mac

        enroll_human = {
            "method": "bootstrap",
            "purpose": "enroll",
            "subject": "app",
            "policy": "local",
            "devices": ["mac"],
            "expires_at": int(time.time()) + 60,
            "hardware": False,
            "bootstrap_mac": message_mac(
                self.bootstrap,
                {
                    "purpose": "enroll",
                    "subject": "app",
                    "policy": "local",
                    "devices": ["mac"],
                    "expires_at": int(time.time()) + 60,
                },
            ),
        }
        # expires_at must match exactly in MAC — rebuild carefully
        expires_at = int(time.time()) + 60
        enroll_human["expires_at"] = expires_at
        enroll_human["bootstrap_mac"] = message_mac(
            self.bootstrap,
            {
                "purpose": "enroll",
                "subject": "app",
                "policy": "local",
                "devices": ["mac"],
                "expires_at": expires_at,
                "domain": "holder-bootstrap-v1",
            },
        )
        enrolled = self.holder.enroll("app", enroll_human)
        self.assertFalse(enrolled["hardware"])

        pair_expires = int(time.time()) + 60
        pair_human = {
            "method": "bootstrap",
            "purpose": "pair",
            "subject": "mac-1",
            "policy": "local",
            "role": "mac",
            "fingerprint": "fp-mac",
            "devices": ["mac"],
            "expires_at": pair_expires,
            "hardware": False,
            "bootstrap_mac": message_mac(
                self.bootstrap,
                {
                    "purpose": "pair",
                    "subject": "mac-1",
                    "policy": "local",
                    "devices": ["mac"],
                    "expires_at": pair_expires,
                    "domain": "holder-bootstrap-v1",
                },
            ),
        }
        from runspecimen.holder_asymmetric import vetted_verifier_available

        if not vetted_verifier_available():
            with self.assertRaises(HolderRefusal) as closed:
                self.holder.pair_device("mac-1", pair_human)
            self.assertIn("vetted device verifier is not connected", str(closed.exception))
            # The signed branch needs PyNaCl. Snapshot execute still runs.
            _snapshot_execute_roundtrip(self)
            return
        paired = self.holder.pair_device("mac-1", pair_human)
        secrets_map = {"mac-1": paired["private_key"]}

        policy_human = _sign_human(self.holder, secrets_map, "set-policy", "local", "local")
        self.holder.set_policy(policy_human)

        script = self.ws / "job.py"
        script.write_text("print('from-snapshot')\n", encoding="utf-8")
        digest = sha256_file(script)
        launch_argv = [sys.executable, str(script.resolve())]
        binding = {
            "contract_hash": "e" * 64,
            "workspace": str(self.ws.resolve()),
            "argv": [str(script.resolve())],
            "executable": str(script.resolve()),
            "policy": "local",
            "cwd": str(self.ws.resolve()),
            "launch_argv": launch_argv,
            "bounds": {"wall_timeout_sec": 5, "stdout_max_bytes": 4096, "stderr_max_bytes": 4096},
            "key_generation": 1,
            "reads": [str(script.resolve())],
        }
        # First consume attempt signs provisional mutation; holder re-checks with payload digest.
        import hashlib
        from runspecimen.hashutil import canonical_json_bytes
        from runspecimen.execution_holder import message_mac
        provisional = {
            "contract_hash": binding["contract_hash"],
            "workspace": binding["workspace"],
            "argv": binding["argv"],
            "executable": binding["executable"],
            "policy": binding["policy"],
            "bounds": binding["bounds"],
            "key_generation": 1,
            "launch_argv": launch_argv,
            "cwd": binding["cwd"],
            "reads": binding["reads"],
            "mutation_digest": None,
        }
        mutation_digest = hashlib.sha256(
            canonical_json_bytes({"files": [[str(script.resolve()), digest]], "binding": {**provisional, "mutation_digest": None}})
        ).hexdigest()
        # Holder computes mutation_digest internally; sign with that exact algorithm by dry-running envelope fields
        envelope_for_mac = {
            "contract_hash": binding["contract_hash"],
            "workspace": binding["workspace"],
            "argv": list(binding["argv"]),
            "executable": binding["executable"],
            "policy": binding["policy"],
            "bounds": binding["bounds"],
            "key_generation": 1,
            "launch_argv": launch_argv,
            "cwd": binding["cwd"],
            "reads": binding["reads"],
            "mutation_digest": None,
        }
        mutation_digest = hashlib.sha256(
            canonical_json_bytes({"files": [[str(script.resolve()), digest]], "binding": envelope_for_mac})
        ).hexdigest()
        # Bind to get payload digest via a software-double holder clone? Simpler path: use test double for pairing already done —
        # For device-HMAC consume we need payload_digest before signing. Temporarily bind using allow_test_double helper.
        # Compute by calling consume with software path is wrong. Instead: use holder._bind under the hood after set_policy.
        path_map, payload_digest, snapshot_root = self.holder._bind(
            "n-exec",
            self.ws,
            [(str(script.resolve()), digest)],
            executable=str(script.resolve()),
            argv=[str(script.resolve())],
        )
        # 0500 directories make rmtree(ignore_errors=True) leave the tree in place.
        _remove_sealed_tree(Path(snapshot_root))
        authorized = {
            "payload_digest": payload_digest,
            "launch_argv": launch_argv,
            "bounds": binding["bounds"],
            "mutation_digest": mutation_digest,
            "attestation_class": "device-ed25519-not-hardware",
        }
        consume_human = _sign_human(
            self.holder, secrets_map, "consume", "n-exec", "local", authorized=authorized
        )
        consumed = self.holder.consume(
            nonce="n-exec",
            policy="local",
            human=consume_human,
            workspace=self.ws,
            files=[(str(script.resolve()), digest)],
            binding=binding,
        )
        self.assertIn(str(script.resolve()), consumed["path_map"])
        script.write_text("raise SystemExit('live-tree')\n", encoding="utf-8")
        exec_authorized = {
            "payload_digest": consumed["payload_digest"],
            "launch_argv": launch_argv,
            "bounds": binding["bounds"],
            "mutation_digest": consumed["binding"]["mutation_digest"],
            "attestation_class": "device-ed25519-not-hardware",
        }
        execute_human = _sign_human(
            self.holder, secrets_map, "execute", "n-exec", "local", authorized=exec_authorized
        )
        result = self.holder.execute(token="n-exec", human=execute_human)
        stderr = __import__("base64").b64decode(result["stderr_b64"])
        self.assertEqual(result["exit_code"], 0, stderr)
        self.assertIn(b"from-snapshot", __import__("base64").b64decode(result["stdout_b64"]))
        self.assertFalse(result["installed_protection"])
        # Client note-absent cannot release; lease already cleared by verified exit.
        with self.assertRaises(HolderRefusal):
            self.holder.note_child_absent(
                "n-exec", _sign_human(self.holder, secrets_map, "note-absent", "n-exec", "local")
            )


class HolderSchemaRegressionTests(unittest.TestCase):
    """These tests do not prove installed protection."""

    def test_unknown_lease_field_fails_closed(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-schema-")
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "state"
        holder = ExecutionHolder(root, allow_test_double=True)
        holder.enroll("app", _human("enroll", "app"))
        (root / "lease.json").write_text(
            '{"held": false, "token": "t", "child": "exited", "surprise": true}\n',
            encoding="utf-8",
        )
        with self.assertRaises(HolderRefusal) as ctx:
            holder._read("lease.json")
        self.assertIn("unknown fields", str(ctx.exception))


class HolderQA69RegressionTests(unittest.TestCase):
    """Regressions for QA-2026-09-30-69ab2b9. Do not prove installed protection."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="rsh-qa69-")
        self.root = Path(self._td.name) / "state"
        self.ws = Path(self._td.name) / "ws"
        self.ws.mkdir()
        self.holder = ExecutionHolder(self.root, allow_test_double=True)
        self.holder.enroll("app", _human("enroll", "app"))
        self.holder.set_policy(_human("set-policy", "local"))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_execute_refuses_caller_interpreter_override(self) -> None:
        from runspecimen.execution_holder import handle_message, seal

        path, digest = _payload(self.ws, "print(1)\n")
        binding = _binding(self.ws, path, digest)
        binding["launch_argv"] = ["python3", str(path.resolve())]
        self.holder.consume(
            nonce="ov",
            policy="local",
            human=_human("consume", "ov"),
            workspace=self.ws,
            files=[(str(path.resolve()), digest)],
            binding=binding,
        )
        secret = self.holder.caller_secret("app")
        message = seal(
            secret,
            caller_id="app",
            body={
                "op": "execute",
                "token": "ov",
                "human": _human("execute", "ov"),
                "interpreter": "/tmp/evil-python",
            },
        )
        with self.assertRaises(HolderRefusal) as ctx:
            handle_message(self.holder, message, bootstrap_secret="zz" * 32)
        self.assertIn("interpreter", str(ctx.exception))

    def test_bootstrap_cannot_authorize_consume(self) -> None:
        from runspecimen.execution_holder import message_mac

        closed = ExecutionHolder(
            Path(self._td.name) / "boot",
            allow_test_double=False,
            bootstrap_secret="ee" * 32,
        )
        expires = int(time.time()) + 60
        enroll = {
            "method": "bootstrap",
            "purpose": "enroll",
            "subject": "app",
            "policy": "local",
            "devices": ["mac"],
            "expires_at": expires,
            "hardware": False,
            "bootstrap_mac": message_mac(
                "ee" * 32,
                {
                    "purpose": "enroll",
                    "subject": "app",
                    "policy": "local",
                    "devices": ["mac"],
                    "expires_at": expires,
                    "domain": "holder-bootstrap-v1",
                },
            ),
        }
        closed.enroll("app", enroll)
        path, digest = _payload(self.ws)
        binding = _binding(self.ws, path, digest)
        boot_consume = {
            "method": "bootstrap",
            "purpose": "consume",
            "subject": "n1",
            "policy": "local",
            "devices": ["mac"],
            "expires_at": int(time.time()) + 60,
            "hardware": False,
            "bootstrap_mac": "00" * 32,
        }
        with self.assertRaises(HolderRefusal) as ctx:
            closed.consume(
                nonce="n1",
                policy="local",
                human=boot_consume,
                workspace=self.ws,
                files=[("payload.txt", digest)],
                binding=binding,
            )
        self.assertIn("enroll and pair", str(ctx.exception))

    def test_non_root_execute_records_least_privilege_identity(self) -> None:
        import os

        path = self.ws / "job.py"
        path.write_text("print('uid-ok')\n", encoding="utf-8")
        digest = sha256_file(path)
        binding = _binding(self.ws, path, digest)
        binding["launch_argv"] = [sys.executable, str(path.resolve())]
        binding["argv"] = [str(path.resolve())]
        self.holder.consume(
            nonce="uid",
            policy="local",
            human=_human("consume", "uid"),
            workspace=self.ws,
            files=[(str(path.resolve()), digest)],
            binding=binding,
        )
        result = self.holder.execute(token="uid", human=_human("execute", "uid"))
        self.assertEqual(result["run_uid"], os.getuid())
        self.assertEqual(result["run_gid"], os.getgid())
        self.assertTrue(result.get("attestation_class") == "device-ed25519-not-hardware" or result.get("hardware") is False)

    def test_mutate_launch_argv_after_consume_fails(self) -> None:
        path = self.ws / "job.py"
        path.write_text("print(1)\n", encoding="utf-8")
        digest = sha256_file(path)
        binding = _binding(self.ws, path, digest)
        binding["launch_argv"] = ["python3", str(path.resolve())]
        binding["argv"] = [str(path.resolve())]
        self.holder.consume(
            nonce="mut",
            policy="local",
            human=_human("consume", "mut"),
            workspace=self.ws,
            files=[(str(path.resolve()), digest)],
            binding=binding,
        )
        # Tamper spent binding launch_argv after consume.
        spent_path = self.root / "spent.json"
        import json
        spent = json.loads(spent_path.read_text())
        for item in spent["nonces"]:
            if item["nonce"] == "mut":
                item["binding"]["launch_argv"] = ["/tmp/evil", str(path.resolve())]
        spent_path.write_text(json.dumps(spent))
        # Also tamper lease path map executable rewrite surface via launch in spent only.
        with self.assertRaises(HolderRefusal):
            self.holder.execute(token="mut", human=_human("execute", "mut"))


class HolderRuntimeTrustTests(unittest.TestCase):
    """Protected runtime source checks. Do not prove installed protection."""

    def test_refuses_pythonpath_and_homebrew(self) -> None:
        from runspecimen.holder_runtime import (
            RuntimeTrustError,
            choose_protected_interpreter,
            refuse_user_python_injection,
        )

        with self.assertRaises(RuntimeTrustError):
            refuse_user_python_injection({"PYTHONPATH": "/tmp/evil"})
        with self.assertRaises(RuntimeTrustError):
            refuse_user_python_injection({"RS_HOLDER_PYTHON": "/tmp/evil-python"})
        with self.assertRaises(RuntimeTrustError):
            choose_protected_interpreter(
                embedded=None,
                system_candidates=[Path("/opt/homebrew/bin/python3.12")],
                require_root_owned=False,
            )


class HolderAbsoluteDeadlineTests(unittest.TestCase):
    """Framing absolute deadlines. Do not prove installed protection."""

    def test_slow_drip_exceeds_absolute_deadline(self) -> None:
        import socket
        import threading

        from runspecimen.holder_io import FrameError, read_frame

        server, client = socket.socketpair()
        errors: list[BaseException] = []

        def reader() -> None:
            try:
                read_frame(server, deadline_sec=0.15, max_bytes=1024)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        t = threading.Thread(target=reader)
        t.start()
        time.sleep(0.05)
        client.sendall(b"abc")
        time.sleep(0.2)
        try:
            client.sendall(b"def\n")
        except OSError:
            pass
        t.join(timeout=2)
        client.close()
        server.close()
        self.assertTrue(errors)
        self.assertIsInstance(errors[0], FrameError)
        self.assertIn("deadline", str(errors[0]))



class HolderQA5dd1EntrypointTests(unittest.TestCase):
    """Isolated entrypoint. These tests do not prove installed protection."""

    def test_holder_entry_bootstraps_without_rs_holder_module_root(self) -> None:
        import subprocess
        import sys

        src_root = Path(__file__).resolve().parents[1] / "src"
        entry = src_root / "runspecimen" / "holder_entry.py"
        # Fresh interpreter, no PYTHONPATH, no RS_HOLDER_MODULE_ROOT: entry must
        # still locate the package by inserting its module root before import.
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": self._td_home if hasattr(self, "_td_home") else "/tmp",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        # Build a clean module tree copy without relying on site-packages.
        td = tempfile.TemporaryDirectory(prefix="rsh-entry-")
        self.addCleanup(td.cleanup)
        module_root = Path(td.name) / "Python"
        import shutil

        src_pkg = src_root / "runspecimen"
        shutil.copytree(
            src_pkg,
            module_root / "runspecimen",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        clean_entry = module_root / "runspecimen" / "holder_entry.py"
        # Probe: import path only — invoke entry with --help equivalent by asking daemon parser.
        # Missing bootstrap secret should exit 2 after successful import bootstrap.
        proc = subprocess.run(
            [sys.executable, "-I", str(clean_entry), "--support-dir", td.name],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(proc.returncode, 0)
        # Must not be ModuleNotFoundError for runspecimen.
        self.assertNotIn("ModuleNotFoundError", proc.stderr + proc.stdout)
        self.assertIn("RS_HOLDER_BOOTSTRAP_SECRET", proc.stderr + proc.stdout)

    def test_entrypoint_refuses_pythonpath(self) -> None:
        import subprocess
        import sys

        src_root = Path(__file__).resolve().parents[1] / "src"
        entry = src_root / "runspecimen" / "holder_entry.py"
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": "/tmp",
            "PYTHONPATH": "/tmp/evil",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        proc = subprocess.run(
            [sys.executable, "-I", str(entry), "--support-dir", "/tmp"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("PYTHONPATH", proc.stderr + proc.stdout)


class HolderQA5dd1PrivilegeAndSnapshotTests(unittest.TestCase):
    """Privilege drop and readable snapshots. Do not prove installed protection."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="rsh-5dd1-")
        self.root = Path(self._td.name) / "state"
        self.snaps = Path(self._td.name) / "run-snapshots"
        self.ws = Path(self._td.name) / "ws"
        self.ws.mkdir()
        self.holder = ExecutionHolder(
            self.root,
            allow_test_double=True,
            snapshot_base=self.snaps,
        )
        self.holder.enroll("app", _human("enroll", "app"))
        self.holder.set_policy(_human("set-policy", "local"))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_payload_identity_refuses_uid_zero(self) -> None:
        with self.assertRaises(HolderRefusal):
            self.holder._payload_identity(peer_uid=0, peer_gid=0)

    def test_env_uid_is_not_authenticated_peer_mapping(self) -> None:
        import os as _os

        _os.environ["RS_HOLDER_RUN_AS_UID"] = "0"
        _os.environ["RS_HOLDER_RUN_AS_GID"] = "0"
        try:
            # Non-root harness uses getuid; env must not force uid 0.
            if _os.geteuid() != 0:
                uid, gid = self.holder._payload_identity()
                self.assertNotEqual(uid, 0)
            else:  # pragma: no cover
                with self.assertRaises(HolderRefusal):
                    self.holder._payload_identity()
        finally:
            _os.environ.pop("RS_HOLDER_RUN_AS_UID", None)
            _os.environ.pop("RS_HOLDER_RUN_AS_GID", None)

    def test_snapshots_live_outside_state_and_are_payload_readable(self) -> None:
        path = self.ws / "job.py"
        path.write_text("print('snap')\n", encoding="utf-8")
        digest = sha256_file(path)
        binding = _binding(self.ws, path, digest)
        binding["launch_argv"] = ["python3", str(path.resolve())]
        binding["argv"] = [str(path.resolve())]
        consumed = self.holder.consume(
            nonce="snap1",
            policy="local",
            human=_human("consume", "snap1"),
            workspace=self.ws,
            files=[(str(path.resolve()), digest)],
            binding=binding,
        )
        snap = Path(consumed["snapshot_root"])
        self.assertTrue(str(snap).startswith(str(self.snaps)))
        self.assertFalse(str(snap).startswith(str(self.root)))
        # State stays private; snapshot root is traversable.
        self.assertTrue(os.access(snap, os.R_OK | os.X_OK))
        self.assertTrue(snap.is_dir())

    def test_setsid_descendant_keeps_lease_until_tree_gone(self) -> None:
        # Spawn a short-lived payloads that setsid a child; holder must track the tree.
        path = self.ws / "setsid_job.py"
        path.write_text(
            "import os, time, sys\n"
            "if os.fork() == 0:\n"
            "    os.setsid()\n"
            "    time.sleep(0.05)\n"
            "    os._exit(0)\n"
            "time.sleep(0.1)\n",
            encoding="utf-8",
        )
        digest = sha256_file(path)
        binding = _binding(self.ws, path, digest)
        binding["launch_argv"] = [sys.executable, str(path.resolve())]
        binding["argv"] = [str(path.resolve())]
        binding["bounds"] = {
            "wall_timeout_sec": 5,
            "stdout_max_bytes": 1024,
            "stderr_max_bytes": 1024,
            "cpu_time_sec": None,
            "memory_bytes": None,
            "fsize_bytes": None,
            "open_files": None,
            "processes": None,
        }
        self.holder.consume(
            nonce="sid1",
            policy="local",
            human=_human("consume", "sid1"),
            workspace=self.ws,
            files=[(str(path.resolve()), digest)],
            binding=binding,
        )
        with self.assertRaises(HolderRefusal) as ctx:
            self.holder.execute(token="sid1", human=_human("execute", "sid1"))
        self.assertIn("lease", str(ctx.exception))
        self.assertTrue(self.holder._lease_held())


class HolderQA5dd1AsymmetricTests(unittest.TestCase):
    """Ed25519 pairing. Do not prove installed protection. Not biometric execution."""

    def test_hmac_is_rejected_for_local_policy(self) -> None:
        from runspecimen.execution_holder import message_mac

        td = tempfile.TemporaryDirectory(prefix="rsh-asym-")
        self.addCleanup(td.cleanup)
        holder = ExecutionHolder(
            Path(td.name) / "state",
            allow_test_double=False,
            bootstrap_secret="aa" * 32,
            snapshot_base=Path(td.name) / "run-snapshots",
        )
        # enroll+pair via bootstrap
        expires = int(time.time()) + 60
        enroll = {
            "method": "bootstrap",
            "purpose": "enroll",
            "subject": "app",
            "policy": "local",
            "devices": ["mac"],
            "expires_at": expires,
            "hardware": False,
            "bootstrap_mac": message_mac(
                "aa" * 32,
                {
                    "purpose": "enroll",
                    "subject": "app",
                    "policy": "local",
                    "devices": ["mac"],
                    "expires_at": expires,
                    "domain": "holder-bootstrap-v1",
                },
            ),
        }
        holder.enroll("app", enroll)
        pair_exp = int(time.time()) + 60
        pair = {
            "method": "bootstrap",
            "purpose": "pair",
            "subject": "mac-1",
            "policy": "local",
            "role": "mac",
            "fingerprint": "fp",
            "devices": ["mac"],
            "expires_at": pair_exp,
            "hardware": False,
            "bootstrap_mac": message_mac(
                "aa" * 32,
                {
                    "purpose": "pair",
                    "subject": "mac-1",
                    "policy": "local",
                    "devices": ["mac"],
                    "expires_at": pair_exp,
                    "domain": "holder-bootstrap-v1",
                },
            ),
        }
        from runspecimen.holder_asymmetric import verify_device_signature, vetted_verifier_available

        if not vetted_verifier_available():
            with self.assertRaises(HolderRefusal) as closed:
                holder.pair_device("mac-1", pair)
            self.assertIn("vetted device verifier is not connected", str(closed.exception))
        else:
            paired = holder.pair_device("mac-1", pair)
            self.assertIn("private_key", paired)
            self.assertEqual(paired["attestation"], "device-ed25519-not-hardware")
            self.assertFalse(paired["hardware"])
            bad = {
                "method": "local",
                "purpose": "set-policy",
                "subject": "local",
                "policy": "local",
                "devices": ["mac"],
                "expires_at": int(time.time()) + 60,
                "hardware": False,
                "attestation_class": "device-ed25519-not-hardware",
                "signatures": {"mac-1": message_mac(paired["private_key"], {"x": 1})},
            }
            with self.assertRaises(HolderRefusal):
                holder.set_policy(bad)
        # Identity-point forge that the removed handwritten verifier accepted.
        self.assertFalse(
            verify_device_signature("01" + "00" * 31, "01" + "00" * 63, b"unapproved message")
        )
        self.assertFalse(verify_device_signature("zz", "00" * 64, b"invalid-key"))
        self.assertFalse(verify_device_signature("ab" * 32, "cd" * 64, b"invalid-signature"))


class HolderForgedSignatureAndSupervisionTests(unittest.TestCase):
    """Codex recheck of b945220. These tests do not prove installed protection.

    They do not run Touch ID, Face ID, or a paired phone. A software signature
    is not a Secure Enclave.
    """

    def test_identity_point_forge_is_rejected_without_handwritten_verifier(self) -> None:
        from runspecimen.holder_asymmetric import verify_device_signature

        self.assertFalse(
            verify_device_signature(
                "01" + "00" * 31,
                "01" + "00" * 63,
                b"unapproved message",
            )
        )
        self.assertFalse(verify_device_signature("not-hex", "00" * 64, b"x"))
        self.assertFalse(verify_device_signature("aa" * 16, "bb" * 32, b"short"))

    def test_production_socket_path_ignores_env_override(self) -> None:
        from runspecimen.holder_adapter import INSTALLED_SUPPORT_DIR, installed_socket_path

        previous = os.environ.get("RS_HOLDER_SOCKET")
        os.environ["RS_HOLDER_SOCKET"] = "/tmp/not-the-live-holder.sock"
        try:
            path = installed_socket_path()
        finally:
            if previous is None:
                os.environ.pop("RS_HOLDER_SOCKET", None)
            else:
                os.environ["RS_HOLDER_SOCKET"] = previous
        self.assertEqual(path, INSTALLED_SUPPORT_DIR / "holder.sock")
        self.assertFalse(str(path).startswith("/tmp"))

    def test_snapshot_is_not_world_readable_and_omits_protected_state(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-snap-")
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "state"
        snaps = Path(td.name) / "run-snapshots"
        ws = Path(td.name) / "ws"
        ws.mkdir()
        holder = ExecutionHolder(root, allow_test_double=True, snapshot_base=snaps)
        holder.enroll("app", _human("enroll", "app"))
        holder.set_policy(_human("set-policy", "local"))
        path = ws / "job.py"
        path.write_text("print(1)\n", encoding="utf-8")
        digest = sha256_file(path)
        binding = _binding(ws, path, digest)
        binding["launch_argv"] = ["python3", str(path.resolve())]
        binding["argv"] = [str(path.resolve())]
        consumed = holder.consume(
            nonce="priv",
            policy="local",
            human=_human("consume", "priv"),
            workspace=ws,
            files=[(str(path.resolve()), digest)],
            binding=binding,
        )
        snap = Path(consumed["snapshot_root"])
        self.assertTrue(str(snap).startswith(str(snaps)))
        self.assertFalse((snap / "enrollment.json").exists())
        self.assertFalse((snap / "spent.json").exists())
        self.assertFalse((snap / "lease.json").exists())
        mode = os.stat(snap).st_mode
        self.assertEqual(mode & 0o077, 0)
        for dirpath, _dirs, files in os.walk(snap):
            self.assertEqual(os.stat(dirpath).st_mode & 0o077, 0)
            for name in files:
                self.assertEqual(os.stat(Path(dirpath) / name).st_mode & 0o077, 0)

    def test_inspection_failure_retains_the_lease(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-sup-")
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "state"
        ws = Path(td.name) / "ws"
        ws.mkdir()
        holder = ExecutionHolder(
            root,
            allow_test_double=True,
            snapshot_base=Path(td.name) / "run-snapshots",
        )
        holder.enroll("app", _human("enroll", "app"))
        holder.set_policy(_human("set-policy", "local"))
        path = ws / "job.py"
        path.write_text("print('ok')\n", encoding="utf-8")
        digest = sha256_file(path)
        binding = _binding(ws, path, digest)
        binding["launch_argv"] = [sys.executable, str(path.resolve())]
        binding["argv"] = [str(path.resolve())]
        holder.consume(
            nonce="unc",
            policy="local",
            human=_human("consume", "unc"),
            workspace=ws,
            files=[(str(path.resolve()), digest)],
            binding=binding,
        )
        holder._process_table = lambda: None  # type: ignore[method-assign]
        with self.assertRaises(HolderRefusal) as ctx:
            holder.execute(token="unc", human=_human("execute", "unc"))
        self.assertIn("lease", str(ctx.exception))
        self.assertTrue(holder._lease_held())
        restarted = ExecutionHolder(
            root,
            allow_test_double=True,
            snapshot_base=Path(td.name) / "run-snapshots",
        )
        with self.assertRaises(HolderRefusal):
            restarted.consume(
                nonce="after-crash",
                policy="local",
                human=_human("consume", "after-crash"),
                workspace=ws,
                files=[(str(path.resolve()), digest)],
                binding=binding,
            )

    def test_reparented_pid_is_outside_the_post_wait_tree(self) -> None:
        """setsid children reparent to init and disappear from the parent tree."""
        import subprocess
        import sys

        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])

        def _stop() -> None:
            sleeper.kill()
            sleeper.wait(timeout=2)

        self.addCleanup(_stop)
        td = tempfile.TemporaryDirectory(prefix="rsh-tree-")
        self.addCleanup(td.cleanup)
        holder = ExecutionHolder(
            Path(td.name) / "state",
            allow_test_double=True,
            snapshot_base=Path(td.name) / "snaps",
        )
        dead_parent = 2**30
        table = {sleeper.pid: 1, 1: 0}
        descendants = holder._descendants_of(dead_parent, table)
        self.assertNotIn(sleeper.pid, descendants)
        self.assertFalse(holder._pid_absent(sleeper.pid))

    def test_double_fork_setsid_retains_the_lease(self) -> None:
        """A real fast setsid grandchild must not clear the lease."""
        td = tempfile.TemporaryDirectory(prefix="rsh-fork-")
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "state"
        ws = Path(td.name) / "ws"
        ws.mkdir()
        marker = Path(td.name) / "grandchild"
        holder = ExecutionHolder(
            root,
            allow_test_double=True,
            snapshot_base=Path(td.name) / "run-snapshots",
        )
        holder.enroll("app", _human("enroll", "app"))
        holder.set_policy(_human("set-policy", "local"))
        script = ws / "job.py"
        script.write_text(
            "import os, sys, time\n"
            "marker = sys.argv[1]\n"
            "if os.fork() == 0:\n"
            "    os.setsid()\n"
            "    if os.fork() == 0:\n"
            "        open(marker, 'w').write(str(os.getpid()))\n"
            "        time.sleep(30)\n"
            "        os._exit(0)\n"
            "    os._exit(0)\n"
            "os._exit(0)\n",
            encoding="utf-8",
        )
        digest = sha256_file(script)
        binding = _binding(ws, script, digest)
        launch = [sys.executable, str(script.resolve()), str(marker)]
        binding["launch_argv"] = launch
        binding["argv"] = [str(script.resolve()), str(marker)]
        holder.consume(
            nonce="fork",
            policy="local",
            human=_human("consume", "fork"),
            workspace=ws,
            files=[(str(script.resolve()), digest)],
            binding=binding,
        )

        def _stop_grandchild() -> None:
            if not marker.is_file():
                return
            try:
                pid = int(marker.read_text(encoding="utf-8").strip())
            except ValueError:
                return
            command = ""
            try:
                command = subprocess.check_output(
                    ["ps", "-p", str(pid), "-o", "command="],
                    text=True,
                    stderr=subprocess.DEVNULL,
                )
            except (OSError, subprocess.CalledProcessError):
                return
            if "time.sleep" not in command and str(marker) not in command:
                return
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass

        self.addCleanup(_stop_grandchild)
        with self.assertRaises(HolderRefusal) as ctx:
            holder.execute(token="fork", human=_human("execute", "fork"))
        self.assertIn("lease", str(ctx.exception))
        lease = json.loads((root / "lease.json").read_text(encoding="utf-8"))
        self.assertTrue(lease["held"])
        self.assertIs(lease["descendants_absent"], False)
        self.assertTrue(marker.is_file())
        restarted = ExecutionHolder(
            root,
            allow_test_double=True,
            snapshot_base=Path(td.name) / "run-snapshots",
        )
        with self.assertRaises(HolderRefusal):
            restarted.consume(
                nonce="after-fork",
                policy="local",
                human=_human("consume", "after-fork"),
                workspace=ws,
                files=[(str(script.resolve()), digest)],
                binding=binding,
            )

    def test_owner_chmod_mutates_and_root_seal_does_not_chown_payload(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-own-")
        self.addCleanup(td.cleanup)
        snap = Path(td.name) / "snap"
        snap.mkdir()
        approved = snap / "payload.txt"
        approved.write_text("approved\n", encoding="utf-8")
        os.chmod(approved, 0o400)
        os.chmod(approved, 0o600)
        approved.write_text("mutated\n", encoding="utf-8")
        self.assertEqual(approved.read_text(encoding="utf-8"), "mutated\n")
        holder = ExecutionHolder(
            Path(td.name) / "state",
            allow_test_double=True,
            snapshot_base=Path(td.name) / "snaps",
        )
        chowns: list[int] = []
        real_chown = os.chown
        real_euid = os.geteuid

        def _record_chown(path: object, uid: int, gid: int) -> None:
            del path, gid
            chowns.append(int(uid))

        os.chown = _record_chown  # type: ignore[assignment]
        os.geteuid = lambda: 0  # type: ignore[assignment]
        refused = ""
        try:
            try:
                holder._seal_payload_snapshot(snap, uid=424242, gid=424242)
            except HolderRefusal as exc:
                refused = str(exc)
        finally:
            os.chown = real_chown  # type: ignore[assignment]
            os.geteuid = real_euid  # type: ignore[assignment]
        self.assertNotIn(424242, chowns)
        self.assertNotIn("chown", refused.lower())
        self.assertEqual(os.stat(approved).st_uid, os.getuid())
        self.assertEqual(os.stat(snap).st_mode & 0o077, 0)

    def test_linux_subreaper_is_cleared_after_the_payload_exits(self) -> None:
        """PR_SET_CHILD_SUBREAPER must not stay on after the payload parent exits.

        Leaving it set made later waitpid checks reap a foreign orphan
        ('waited') instead of reporting ECHILD.
        """
        calls: list[tuple[int, ...]] = []

        class _Prctl:
            argtypes = None
            restype = None

            def __call__(self, op: int, enable: int, a: int, b: int, c: int) -> int:
                calls.append((int(op), int(enable), int(a), int(b), int(c)))
                return 0

        class _Libc:
            def __init__(self) -> None:
                self.prctl = _Prctl()

        td = tempfile.TemporaryDirectory(prefix="rsh-subreaper-")
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "state"
        ws = Path(td.name) / "ws"
        ws.mkdir()
        holder = ExecutionHolder(
            root,
            allow_test_double=True,
            snapshot_base=Path(td.name) / "run-snapshots",
        )
        holder.enroll("app", _human("enroll", "app"))
        holder.set_policy(_human("set-policy", "local"))
        script = ws / "job.py"
        script.write_text("print('subreaper-off')\n", encoding="utf-8")
        digest = sha256_file(script)
        binding = _binding(ws, script, digest)
        launch = [sys.executable, str(script.resolve())]
        binding["launch_argv"] = launch
        binding["argv"] = [str(script.resolve())]
        holder.consume(
            nonce="sub",
            policy="local",
            human=_human("consume", "sub"),
            workspace=ws,
            files=[(str(script.resolve()), digest)],
            binding=binding,
        )
        with mock.patch.object(sys, "platform", "linux"), mock.patch.object(
            ctypes, "CDLL", lambda *_args, **_kwargs: _Libc()
        ):
            result = holder.execute(token="sub", human=_human("execute", "sub"))
        self.assertEqual(result["exit_code"], 0)
        self.assertIn((36, 1, 0, 0, 0), calls)
        self.assertEqual(calls[-1], (36, 0, 0, 0, 0))

    def test_closed_gate_wrong_byte_and_read_error_do_not_exec(self) -> None:
        """EOF, a wrong byte, and a read error are not permission to run."""
        from runspecimen.holder_supervise_exec import GO_BYTE, main

        supervise = Path(__file__).resolve().parents[1] / "src" / "runspecimen" / "holder_supervise_exec.py"
        td = tempfile.TemporaryDirectory(prefix="rsh-gate-")
        self.addCleanup(td.cleanup)
        marker = Path(td.name) / "ran"
        script = Path(td.name) / "job.py"
        script.write_text(
            "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran')\n",
            encoding="utf-8",
        )
        payload = [sys.executable, str(script), str(marker)]

        def _spawn(prelude: bytes | None) -> subprocess.CompletedProcess[bytes]:
            read_fd, write_fd = os.pipe()
            try:
                if prelude is not None:
                    os.write(write_fd, prelude)
                os.close(write_fd)
                write_fd = -1
                return subprocess.run(
                    [sys.executable, "-I", str(supervise), str(read_fd), "--", *payload],
                    check=False,
                    capture_output=True,
                    timeout=5,
                    pass_fds=(read_fd,),
                )
            finally:
                if write_fd >= 0:
                    os.close(write_fd)
                os.close(read_fd)

        closed = _spawn(None)
        self.assertNotEqual(closed.returncode, 0, closed.stderr)
        self.assertFalse(marker.exists())
        wrong = _spawn(b"\x01")
        self.assertNotEqual(wrong.returncode, 0, wrong.stderr)
        self.assertFalse(marker.exists())
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        os.close(write_fd)
        self.assertEqual(main([str(read_fd), "--", *payload]), 2)
        self.assertFalse(marker.exists())
        allowed = _spawn(GO_BYTE)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertTrue(marker.is_file())

    def test_relative_interpreter_is_refused_before_spawn(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-rel-")
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "state"
        ws = Path(td.name) / "ws"
        ws.mkdir()
        marker = Path(td.name) / "ran"
        holder = ExecutionHolder(
            root,
            allow_test_double=True,
            snapshot_base=Path(td.name) / "run-snapshots",
        )
        holder.enroll("app", _human("enroll", "app"))
        holder.set_policy(_human("set-policy", "local"))
        script = ws / "job.py"
        script.write_text(
            "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran')\n",
            encoding="utf-8",
        )
        digest = sha256_file(script)
        binding = _binding(ws, script, digest)
        binding["launch_argv"] = ["python3", str(script.resolve()), str(marker)]
        binding["argv"] = [str(script.resolve()), str(marker)]
        holder.consume(
            nonce="rel",
            policy="local",
            human=_human("consume", "rel"),
            workspace=ws,
            files=[(str(script.resolve()), digest)],
            binding=binding,
        )
        with self.assertRaises(HolderRefusal) as ctx:
            holder.execute(token="rel", human=_human("execute", "rel"))
        self.assertIn("absolute", str(ctx.exception))
        self.assertFalse(marker.exists())
        self.assertTrue(holder._lease_held())

    def test_unarmed_spawn_reaps_without_running_and_keeps_a_living_child(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-arm-")
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "state"
        ws = Path(td.name) / "ws"
        ws.mkdir()
        marker = Path(td.name) / "ran"
        holder = ExecutionHolder(
            root,
            allow_test_double=True,
            snapshot_base=Path(td.name) / "run-snapshots",
        )
        holder.enroll("app", _human("enroll", "app"))
        holder.set_policy(_human("set-policy", "local"))
        script = ws / "job.py"
        script.write_text(
            "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran')\n",
            encoding="utf-8",
        )
        digest = sha256_file(script)
        binding = _binding(ws, script, digest)
        launch = [sys.executable, str(script.resolve()), str(marker)]
        binding["launch_argv"] = launch
        binding["argv"] = [str(script.resolve()), str(marker)]
        holder.consume(
            nonce="arm",
            policy="local",
            human=_human("consume", "arm"),
            workspace=ws,
            files=[(str(script.resolve()), digest)],
            binding=binding,
        )

        def _unarmed(pid: int) -> dict:
            return {
                "armed": False,
                "fork_seen": False,
                "kq": None,
                "started": None,
                "baseline": set(),
                "payload_pid": pid,
                "identities": [],
            }

        holder._arm_payload_watch = _unarmed  # type: ignore[method-assign]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            with self.assertRaises(HolderRefusal) as ctx:
                holder.execute(token="arm", human=_human("execute", "arm"))
            gc.collect()
        leaked = [str(item.message) for item in caught if issubclass(item.category, ResourceWarning)]
        self.assertFalse(leaked, leaked)
        self.assertIn("armed", str(ctx.exception))
        self.assertFalse(marker.exists())
        lease = json.loads((root / "lease.json").read_text(encoding="utf-8"))
        self.assertFalse(lease["held"])
        self.assertEqual(lease["child"], "spawn-failed")

        holder.consume(
            nonce="arm2",
            policy="local",
            human=_human("consume", "arm2"),
            workspace=ws,
            files=[(str(script.resolve()), digest)],
            binding=binding,
        )

        def _timeout(self: subprocess.Popen, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired(self.args, timeout or 0)

        def _no_kill(pid: int, sig: int) -> None:
            raise PermissionError("not this child")

        with warnings.catch_warnings(record=True) as retained_warnings:
            warnings.simplefilter("always", ResourceWarning)
            with mock.patch.object(subprocess.Popen, "wait", _timeout), mock.patch("os.killpg", _no_kill):
                with self.assertRaises(HolderRefusal) as stuck:
                    holder.execute(token="arm2", human=_human("execute", "arm2"))
            self.assertIn("lease retained", str(stuck.exception))
            self.assertFalse(marker.exists())
            retained = json.loads((root / "lease.json").read_text(encoding="utf-8"))
            self.assertTrue(retained["held"])
            self.assertIs(retained["descendants_absent"], False)
            del stuck
            gc.collect()
        unclosed = [
            str(item.message)
            for item in retained_warnings
            if issubclass(item.category, ResourceWarning) and "unclosed file" in str(item.message)
        ]
        self.assertFalse(unclosed, unclosed)

        def _drain() -> None:
            while True:
                try:
                    pid, _status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    return
                if pid == 0:
                    return

        _drain()

    def test_cryptokit_p256_authorizes_a_bounded_run_and_is_not_hardware(self) -> None:
        """CryptoKit can verify a signature. That signature is not a Secure Enclave."""
        if not os.path.isfile("/usr/bin/swiftc"):
            self.skipTest("CryptoKit verifier compiler is absent")
        from runspecimen.execution_holder import message_mac
        from runspecimen.holder_asymmetric import digest_challenge

        signer_src = r'''
import CryptoKit
import Foundation
let args = CommandLine.arguments
guard args.count >= 2 else { exit(2) }
if args[1] == "key" {
    let key = P256.Signing.PrivateKey()
    print(key.publicKey.x963Representation.base64EncodedString())
    print(key.rawRepresentation.base64EncodedString())
    exit(0)
}
guard args.count == 4, args[1] == "sign",
      let raw = Data(base64Encoded: args[2]) else { exit(2) }
let key = try! P256.Signing.PrivateKey(rawRepresentation: raw)
let message = try! Data(contentsOf: URL(fileURLWithPath: args[3]))
print(try! key.signature(for: message).rawRepresentation.base64EncodedString())
'''
        tool_dir = tempfile.TemporaryDirectory(prefix="rsh-p256-")
        self.addCleanup(tool_dir.cleanup)
        source = Path(tool_dir.name) / "sign.swift"
        binary = Path(tool_dir.name) / "sign"
        source.write_text(signer_src, encoding="utf-8")
        built = subprocess.run(
            ["/usr/bin/swiftc", "-O", "-o", str(binary), str(source)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(built.returncode, 0, built.stderr)
        key_out = subprocess.run([str(binary), "key"], check=True, capture_output=True, text=True, timeout=10)
        public_b64, private_b64 = key_out.stdout.splitlines()

        def _sign(message: bytes) -> str:
            with tempfile.NamedTemporaryFile(prefix="rs-msg-") as handle:
                handle.write(message)
                handle.flush()
                signed = subprocess.run(
                    [str(binary), "sign", private_b64, handle.name],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            return signed.stdout.strip()

        td = tempfile.TemporaryDirectory(prefix="rsh-p256-run-")
        self.addCleanup(td.cleanup)
        secret = "ab" * 32
        holder = ExecutionHolder(
            Path(td.name) / "state",
            allow_test_double=False,
            bootstrap_secret=secret,
            snapshot_base=Path(td.name) / "run-snapshots",
        )
        expires = int(time.time()) + 60

        def _boot(purpose: str, subject: str, **extra: object) -> dict:
            fields = {
                "purpose": purpose,
                "subject": subject,
                "policy": "local",
                "devices": ["mac"],
                "expires_at": expires,
                "domain": "holder-bootstrap-v1",
            }
            body = {
                "method": "bootstrap",
                "purpose": purpose,
                "subject": subject,
                "policy": "local",
                "devices": ["mac"],
                "expires_at": expires,
                "hardware": False,
                "bootstrap_mac": message_mac(secret, fields),
            }
            body.update(extra)
            return body

        holder.enroll("app", _boot("enroll", "app"))
        holder.pair_device(
            "mac-1",
            _boot("pair", "mac-1", role="mac", fingerprint="fp-p256", algorithm="p256", public_key=public_b64),
        )

        def _authorize(purpose: str, subject: str, authorized: dict | None = None) -> dict:
            challenge = {
                "purpose": purpose,
                "subject": subject,
                "policy": "local",
                "devices": ["mac"],
                "expires_at": expires,
                "holder_id": holder.holder_id,
                "generation": holder.generation,
                "domain": "holder-device-p256-v1",
                "attestation_class": "device-p256-not-hardware",
                "authorized": authorized or {},
            }
            return {
                "method": "local",
                "purpose": purpose,
                "policy": "local",
                "subject": subject,
                "devices": ["mac"],
                "expires_at": expires,
                "hardware": False,
                "attestation_class": "device-p256-not-hardware",
                "signatures": {"mac-1": _sign(digest_challenge(challenge))},
            }

        holder.set_policy(_authorize("set-policy", "local"))
        ws = Path(td.name) / "ws"
        ws.mkdir()
        marker = Path(td.name) / "ran"
        script = ws / "job.py"
        script.write_text(
            "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran')\n",
            encoding="utf-8",
        )
        digest = sha256_file(script)
        binding = _binding(ws, script, digest)
        launch = [sys.executable, str(script.resolve()), str(marker)]
        binding["launch_argv"] = launch
        binding["argv"] = [str(script.resolve()), str(marker)]
        from runspecimen.hashutil import canonical_json_bytes

        envelope = holder._binding_envelope(binding)
        mutation = hashlib.sha256(
            canonical_json_bytes({"files": [[str(script.resolve()), digest]], "binding": envelope})
        ).hexdigest()
        _path_map, payload_digest, snapshot_root = holder._bind(
            "p256",
            ws,
            [(str(script.resolve()), digest)],
            executable=str(script.resolve()),
            argv=[str(script.resolve()), str(marker)],
        )
        _remove_sealed_tree(Path(snapshot_root))
        authorized = {
            "payload_digest": payload_digest,
            "launch_argv": launch,
            "bounds": binding["bounds"],
            "mutation_digest": mutation,
            "attestation_class": "device-ed25519-not-hardware",
        }
        holder.consume(
            nonce="p256",
            policy="local",
            human=_authorize("consume", "p256", authorized),
            workspace=ws,
            files=[(str(script.resolve()), digest)],
            binding=binding,
        )
        spent = json.loads((Path(td.name) / "state" / "spent.json").read_text(encoding="utf-8"))
        record = next(item for item in spent["nonces"] if item["nonce"] == "p256")
        exec_authorized = {
            "payload_digest": record["payload_digest"],
            "launch_argv": list(record["binding"]["launch_argv"]),
            "bounds": record["binding"]["bounds"],
            "mutation_digest": record["binding"]["mutation_digest"],
            "attestation_class": "device-ed25519-not-hardware",
        }
        result = holder.execute(token="p256", human=_authorize("execute", "p256", exec_authorized))
        stderr = __import__("base64").b64decode(result["stderr_b64"])
        self.assertEqual(result["exit_code"], 0, stderr)
        self.assertTrue(marker.is_file())
        self.assertFalse(result["hardware"])
        self.assertNotEqual(result["attestation_class"], "secure-enclave")
        protected = ExecutionHolder(
            Path(td.name) / "protected",
            allow_test_double=False,
            installed_protection=True,
            bootstrap_secret=secret,
            snapshot_base=Path(td.name) / "protected-snaps",
        )
        protected.enroll("app", _boot("enroll", "app"))
        with self.assertRaises(HolderRefusal) as refused:
            protected.pair_device(
                "mac-1",
                _boot(
                    "pair",
                    "mac-1",
                    role="mac",
                    fingerprint="fp-p256",
                    algorithm="p256",
                    public_key=public_b64,
                ),
            )
        self.assertIn("not a Secure Enclave", str(refused.exception))

    def test_vetted_ed25519_is_not_secure_enclave_approval(self) -> None:
        from runspecimen.holder_asymmetric import (
            AsymmetricError,
            constant_time_label_ok,
            verify_device_signature,
        )

        self.assertFalse(
            verify_device_signature("01" + "00" * 31, "01" + "00" * 63, b"unapproved message")
        )
        with self.assertRaises(AsymmetricError):
            constant_time_label_ok("secure-enclave", hardware=True)
        with self.assertRaises(AsymmetricError):
            constant_time_label_ok("device-ed25519-not-hardware", hardware=True)

    def test_production_rejects_software_test_double(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-prod-")
        self.addCleanup(td.cleanup)
        holder = ExecutionHolder(
            Path(td.name) / "state",
            allow_test_double=False,
            installed_protection=True,
            snapshot_base=Path(td.name) / "snaps",
        )
        with self.assertRaises(HolderRefusal) as ctx:
            holder.enroll("app", _human("enroll", "app"))
        self.assertIn("software test double", str(ctx.exception))
