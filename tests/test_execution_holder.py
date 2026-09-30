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
    }
    doc.update(extra)
    return doc


def _binding(workspace: Path, path: Path, digest: str, policy: str = "local") -> dict:
    return {
        "contract_hash": "c" * 64,
        "workspace": str(workspace.resolve()),
        "argv": [str(path), "payload.txt"],
        "executable": str(path.resolve()),
        "policy": policy,
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
        with self.assertRaises(HolderRefusal):
            self.holder.set_policy(_human("set-policy", "local", method="local"))
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
        self.holder.note_child_absent("n1", _human("note-absent", "n1"))
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
        # Mutating the live script after consume must not affect a spent nonce.
        (self.ws / "work" / "job.py").write_text("raise SystemExit('live tree')\n", encoding="utf-8")
        server.stop()
        restarted = AdapterServer(Path(td.name), bootstrap_secret="ef" * 32)
        restarted.start()
        self.addCleanup(restarted.stop)
        again = HolderClient(restarted.socket_path, "app", enrolled["caller_secret"], _human)
        with self.assertRaises(HolderRefusal):
            again.call(
                {
                    "op": "consume",
                    "nonce": "different-after-restart",
                    "policy": "local",
                    "human": _human("consume", "different-after-restart"),
                    "workspace": str(self.ws),
                    "files": [[str((self.ws / "work" / "job.py").resolve()), sha256_file(self.ws / "work" / "job.py")]],
                    "binding": {
                        "contract_hash": "d" * 64,
                        "workspace": str(self.ws.resolve()),
                        "argv": ["job.py"],
                        "executable": str((self.ws / "work" / "job.py").resolve()),
                        "policy": "local",
                        "bounds": {"wall_timeout_sec": 1, "stdout_max_bytes": 1, "stderr_max_bytes": 1},
                        "key_generation": 1,
                    },
                }
            )



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
