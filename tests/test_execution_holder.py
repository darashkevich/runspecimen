"""Unprivileged execution-holder tests.

These tests run in the same user account as the holder files. They do not
prove installed protection, and they do not exercise Touch ID, Face ID, or
a paired phone.
"""

from __future__ import annotations

import hashlib
import tempfile
import time
import unittest
from pathlib import Path

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
        with self.assertRaises(PreflightError) as missing:
            run_contract(contract_path=path, workspace=self.ws)
        self.assertIn("requires the holder", str(missing.exception))
        self.assertIn("no typed-phrase fallback", str(missing.exception))
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
    device_secrets: dict[str, str],
    purpose: str,
    subject: str,
    policy: str,
    authorized: dict | None = None,
) -> dict:
    """Build a cryptographically signed local/companion/dual authorization.

    Device-HMAC is labeled not-hardware. This is not biometric execution and
    these tests do not prove installed protection.
    """
    from runspecimen.execution_holder import message_mac

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
        "domain": "holder-device-hmac-v1",
        "attestation_class": "device-hmac-not-hardware",
        "authorized": auth,
    }
    signatures = {
        device_id: message_mac(secret, challenge) for device_id, secret in device_secrets.items()
    }
    return {
        "method": policy,
        "purpose": purpose,
        "subject": subject,
        "policy": policy,
        "devices": devices,
        "expires_at": expires_at,
        "hardware": False,
        "attestation_class": "device-hmac-not-hardware",
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
        paired = self.holder.pair_device("mac-1", pair_human)
        secrets_map = {"mac-1": paired["device_secret"]}

        policy_human = _sign_human(self.holder, secrets_map, "set-policy", "local", "local")
        self.holder.set_policy(policy_human)

        script = self.ws / "job.py"
        script.write_text("print('from-snapshot')\n", encoding="utf-8")
        digest = sha256_file(script)
        launch_argv = ["python3", str(script.resolve())]
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
        # Clean the snapshot from dry-bind so consume can recreate
        import shutil
        shutil.rmtree(Path(snapshot_root), ignore_errors=True)
        authorized = {
            "payload_digest": payload_digest,
            "launch_argv": launch_argv,
            "bounds": binding["bounds"],
            "mutation_digest": mutation_digest,
            "attestation_class": "device-hmac-not-hardware",
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
            "attestation_class": "device-hmac-not-hardware",
        }
        execute_human = _sign_human(
            self.holder, secrets_map, "execute", "n-exec", "local", authorized=exec_authorized
        )
        result = self.holder.execute(token="n-exec", human=execute_human)
        self.assertEqual(result["exit_code"], 0)
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
        binding["launch_argv"] = ["python3", str(path.resolve())]
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
        self.assertTrue(result.get("attestation_class") == "device-hmac-not-hardware" or result.get("hardware") is False)

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

