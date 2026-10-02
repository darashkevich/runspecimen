"""Labeled native-bridge doubles for local, companion, and dual.

These runs use a software P-256 key and the packaged CryptoKit verifier.
They are not Secure Enclave, Touch ID, Face ID, or a paired phone.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from runspecimen.execution_holder import ExecutionHolder, HolderRefusal, handle_message, message_mac
from runspecimen.hashutil import canonical_json_bytes, sha256_file
from runspecimen.holder_asymmetric import digest_challenge, public_key_fingerprint


def _signer(test: unittest.TestCase) -> tuple[Path, str, str]:
    if not os.path.isfile("/usr/bin/swiftc"):
        test.skipTest("CryptoKit signer compiler is absent")
    source_text = r'''
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
    td = tempfile.TemporaryDirectory(prefix="rsh-bridge-sign-")
    test.addCleanup(td.cleanup)
    source = Path(td.name) / "sign.swift"
    binary = Path(td.name) / "sign"
    source.write_text(source_text, encoding="utf-8")
    built = subprocess.run(
        ["/usr/bin/swiftc", "-O", "-o", str(binary), str(source)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if built.returncode != 0:
        test.skipTest(built.stderr)
    key_out = subprocess.run([str(binary), "key"], check=True, capture_output=True, text=True, timeout=10)
    public_b64, private_b64 = key_out.stdout.splitlines()
    return binary, public_b64, private_b64


def _sign(binary: Path, private_b64: str, message: bytes) -> str:
    with tempfile.NamedTemporaryFile(prefix="rs-bridge-msg-") as handle:
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


def _boot(secret: str, purpose: str, subject: str, policy: str, **extra: object) -> dict:
    devices = {"local": ["mac"], "companion": ["phone"], "dual": ["mac", "phone"]}[policy]
    expires = int(time.time()) + 60
    fields = {
        "purpose": purpose,
        "subject": subject,
        "policy": policy,
        "devices": devices,
        "expires_at": expires,
        "domain": "holder-bootstrap-v1",
    }
    body = {
        "method": "bootstrap",
        "purpose": purpose,
        "policy": policy,
        "subject": subject,
        "devices": devices,
        "expires_at": expires,
        "hardware": False,
        "bootstrap_mac": message_mac(secret, fields),
    }
    body.update(extra)
    return body


class LabeledBridgePolicyTests(unittest.TestCase):
    def test_production_bridge_rejects_adhoc_verifier_and_the_labeled_double(self) -> None:
        secret = "99" * 32
        td = tempfile.TemporaryDirectory(prefix="rsh-prod-bridge-")
        self.addCleanup(td.cleanup)
        holder = ExecutionHolder(
            Path(td.name) / "state",
            allow_test_double=False,
            installed_protection=True,
            bootstrap_secret=secret,
            snapshot_base=Path(td.name) / "snaps",
        )
        holder.enroll("app", _boot(secret, "enroll", "app", "local"))
        compared = public_key_fingerprint("AQID")
        with self.assertRaises(HolderRefusal) as ctx:
            holder.pair_device(
                "mac-1",
                _boot(
                    secret,
                    "pair",
                    "mac-1",
                    "local",
                    role="mac",
                    fingerprint=compared,
                    algorithm="p256",
                    public_key="AQID",
                    key_comparison=compared,
                    provenance={
                        "bridge": "labeled-native-bridge-double-not-hardware",
                        "public_key": "AQID",
                        "role": "mac",
                        "policy": "local",
                        "generation": holder.generation,
                    },
                ),
            )
        message = str(ctx.exception)
        self.assertIn("Developer ID", message)
        self.assertIn("labeled-native-bridge-double-not-hardware", message)
        self.assertIn("not a Secure Enclave", message)
        self.assertIn("not pinned", message)
        self.assertIn("installed protection is on", message)

    def test_local_companion_and_dual_execute_and_are_not_hardware(self) -> None:
        binary, _public, _private = _signer(self)
        for policy, roles in (
            ("local", ("mac",)),
            ("companion", ("phone",)),
            ("dual", ("mac", "phone")),
        ):
            with self.subTest(policy=policy):
                result = self._execute(binary, policy, roles)
                self.assertEqual(result["exit_code"], 0)
                self.assertFalse(result["hardware"])
                self.assertEqual(result["attestation_class"], "device-p256-not-hardware")

    def test_cancel_revoke_replay_rotation_binding_restart_and_concurrency(self) -> None:
        binary, public_b64, private_b64 = _signer(self)
        secret = "cd" * 32
        td = tempfile.TemporaryDirectory(prefix="rsh-bridge-life-")
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "state"
        snaps = Path(td.name) / "run-snapshots"
        holder = self._holder(root, snaps, secret, "local")
        device = self._pair(holder, binary, public_b64, private_b64, "mac-1", "mac", "local")
        self._set_policy(holder, binary, {"mac-1": device}, "local")
        ws, script, marker = self._workspace(Path(td.name) / "ws")
        binding = self._binding(ws, script, "local")
        human = self._consume_human(holder, binary, {"mac-1": device}, "local", "once", ws, script, binding)
        holder.consume(
            nonce="once",
            policy="local",
            human=human,
            workspace=ws,
            files=[(str(script.resolve()), sha256_file(script))],
            binding=binding,
        )
        reloaded = ExecutionHolder(root, allow_test_double=False, bootstrap_secret=secret, snapshot_base=snaps)
        cancelled = reloaded.cancel_uncertain("once", self._sign_human(reloaded, binary, {"mac-1": device}, "cancel", "once", "local"))
        self.assertTrue(cancelled["cancelled"])
        self.assertFalse(cancelled.get("hardware", False))
        with self.assertRaises(HolderRefusal):
            reloaded.execute(token="once", human=self._sign_human(reloaded, binary, {"mac-1": device}, "execute", "once", "local"))
        with self.assertRaises(HolderRefusal) as replay:
            reloaded.consume(
                nonce="once",
                policy="local",
                human=human,
                workspace=ws,
                files=[(str(script.resolve()), sha256_file(script))],
                binding=binding,
            )
        self.assertIn("already consumed", str(replay.exception))
        bound_human = self._consume_human(reloaded, binary, {"mac-1": device}, "local", "bound", ws, script, binding)
        reloaded.consume(
            nonce="bound",
            policy="local",
            human=bound_human,
            workspace=ws,
            files=[(str(script.resolve()), sha256_file(script))],
            binding=binding,
        )
        sealed = snaps / "bound" / "authorized_launch.json"
        sealed.chmod(0o600)
        sealed.write_text('{"launch_argv":["/not/the/bound/argv"]}\n', encoding="utf-8")
        spent = __import__("json").loads((root / "spent.json").read_text(encoding="utf-8"))
        record = next(item for item in spent["nonces"] if item["nonce"] == "bound")
        execute_human = self._sign_human(
            reloaded,
            binary,
            {"mac-1": device},
            "execute",
            "bound",
            "local",
            {
                "payload_digest": record["payload_digest"],
                "launch_argv": list(record["binding"]["launch_argv"]),
                "bounds": record["binding"]["bounds"],
                "mutation_digest": record["binding"]["mutation_digest"],
                "attestation_class": "device-p256-not-hardware",
            },
        )
        with self.assertRaises(HolderRefusal) as mutated:
            reloaded.execute(token="bound", human=execute_human)
        self.assertIn("mutated", str(mutated.exception))
        reloaded.cancel_uncertain("bound", self._sign_human(reloaded, binary, {"mac-1": device}, "cancel", "bound", "local"))

        rotated = reloaded.rotate_caller(self._sign_human(reloaded, binary, {"mac-1": device}, "rotate", "app", "local"))
        self.assertEqual(rotated["key_generation"], 2)
        self.assertFalse(rotated["hardware"])
        stale = dict(binding)
        stale["key_generation"] = 1
        with self.assertRaises(HolderRefusal) as generation:
            reloaded.consume(
                nonce="stale-gen",
                policy="local",
                human=self._sign_human(reloaded, binary, {"mac-1": device}, "consume", "stale-gen", "local"),
                workspace=ws,
                files=[(str(script.resolve()), sha256_file(script))],
                binding=stale,
            )
        self.assertIn("key generation", str(generation.exception))

        reloaded.revoke_device("mac-1", self._sign_human(reloaded, binary, {"mac-1": device}, "revoke", "mac-1", "local"))
        fresh = dict(binding)
        fresh["key_generation"] = 2
        with self.assertRaises(HolderRefusal) as revoked:
            reloaded.consume(
                nonce="after-revoke",
                policy="local",
                human=self._sign_human(reloaded, binary, {"mac-1": device}, "consume", "after-revoke", "local"),
                workspace=ws,
                files=[(str(script.resolve()), sha256_file(script))],
                binding=fresh,
            )
        self.assertIn("revoked", str(revoked.exception))

        covered = {"protocol": 0, "caller_id": "bootstrap", "body": {"op": "enroll"}}
        with self.assertRaises(HolderRefusal) as downgraded:
            handle_message(
                reloaded,
                {**covered, "mac": message_mac(secret, covered)},
                bootstrap_secret=secret,
            )
        self.assertIn("downgrade", str(downgraded.exception))
        self.assertFalse(marker.exists())

    def test_concurrent_consume_of_one_nonce_fails_closed(self) -> None:
        binary, public_b64, private_b64 = _signer(self)
        secret = "ef" * 32
        td = tempfile.TemporaryDirectory(prefix="rsh-bridge-race-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name) / "state", Path(td.name) / "snaps", secret, "local")
        device = self._pair(holder, binary, public_b64, private_b64, "mac-1", "mac", "local")
        self._set_policy(holder, binary, {"mac-1": device}, "local")
        ws, script, _marker = self._workspace(Path(td.name) / "ws")
        binding = self._binding(ws, script, "local")
        errors: list[BaseException] = []
        ok = []
        human = self._consume_human(holder, binary, {"mac-1": device}, "local", "race", ws, script, binding)

        def _once() -> None:
            try:
                holder.consume(
                    nonce="race",
                    policy="local",
                    human=human,
                    workspace=ws,
                    files=[(str(script.resolve()), sha256_file(script))],
                    binding=binding,
                )
            except BaseException as exc:  # noqa: BLE001 - the loser must fail closed
                errors.append(exc)
            else:
                ok.append(True)

        threads = [threading.Thread(target=_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(len(ok), 1, ok)
        self.assertTrue(any(isinstance(item, HolderRefusal) for item in errors), errors)

    def test_snapshot_mkdir_collision_is_a_refusal(self) -> None:
        secret = "aa" * 32
        td = tempfile.TemporaryDirectory(prefix="rsh-snap-race-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name) / "state", Path(td.name) / "snaps", secret, "local")

        def _collide(self_path: Path, *args, **kwargs) -> None:
            raise FileExistsError(17, "File exists")

        with mock.patch.object(Path, "mkdir", _collide):
            with self.assertRaises(HolderRefusal) as ctx:
                holder._prepare_payload_snapshot("race-token")
        self.assertIn("already exists", str(ctx.exception))

    def _execute(self, binary: Path, policy: str, roles: tuple[str, ...]) -> dict:
        secret = "ab" * 32
        td = tempfile.TemporaryDirectory(prefix=f"rsh-bridge-{policy}-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name) / "state", Path(td.name) / "snaps", secret, policy)
        devices = {}
        for role in roles:
            key_out = subprocess.run([str(binary), "key"], check=True, capture_output=True, text=True, timeout=10)
            public_b64, private_b64 = key_out.stdout.splitlines()
            device_id = f"{role}-1"
            devices[device_id] = self._pair(holder, binary, public_b64, private_b64, device_id, role, policy)
        self._set_policy(holder, binary, devices, policy)
        ws, script, marker = self._workspace(Path(td.name) / "ws")
        binding = self._binding(ws, script, policy)
        human = self._consume_human(holder, binary, devices, policy, policy, ws, script, binding)
        holder.consume(
            nonce=policy,
            policy=policy,
            human=human,
            workspace=ws,
            files=[(str(script.resolve()), sha256_file(script))],
            binding=binding,
        )
        spent = __import__("json").loads((Path(td.name) / "state" / "spent.json").read_text(encoding="utf-8"))
        record = next(item for item in spent["nonces"] if item["nonce"] == policy)
        authorized = {
            "payload_digest": record["payload_digest"],
            "launch_argv": list(record["binding"]["launch_argv"]),
            "bounds": record["binding"]["bounds"],
            "mutation_digest": record["binding"]["mutation_digest"],
            "attestation_class": "device-p256-not-hardware",
        }
        result = holder.execute(
            token=policy,
            human=self._sign_human(holder, binary, devices, "execute", policy, policy, authorized),
        )
        self.assertEqual(marker.read_text(encoding="utf-8"), "ran")
        sealed = Path(td.name) / "snaps" / policy / "authorized_launch.json"
        sealed.chmod(0o600)
        sealed.write_text('{"launch_argv":["/not/the/bound/argv"]}\n', encoding="utf-8")
        return result

    def _holder(self, root: Path, snaps: Path, secret: str, policy: str) -> ExecutionHolder:
        holder = ExecutionHolder(root, allow_test_double=False, bootstrap_secret=secret, snapshot_base=snaps)
        holder.enroll("app", _boot(secret, "enroll", "app", policy))
        return holder

    def _pair(self, holder, binary, public_b64, private_b64, device_id, role, policy) -> dict:
        compared = public_key_fingerprint(public_b64)
        generation = holder.generation
        holder.pair_device(
            device_id,
            _boot(
                holder.bootstrap_secret,
                "pair",
                device_id,
                policy,
                role=role,
                fingerprint=compared,
                algorithm="p256",
                public_key=public_b64,
                key_comparison=compared,
                provenance={
                    "bridge": "labeled-native-bridge-double-not-hardware",
                    "public_key": public_b64,
                    "role": role,
                    "policy": policy,
                    "generation": generation,
                },
            ),
        )
        return {
            "public": public_b64,
            "private": private_b64,
            "binary": binary,
            "fingerprint": compared,
            "generation": generation,
            "role": role,
            "policy": policy,
        }

    def _set_policy(self, holder, binary, devices: dict, policy: str) -> None:
        holder.set_policy(self._sign_human(holder, binary, devices, "set-policy", policy, policy))

    def _sign_human(self, holder, binary, devices: dict, purpose: str, subject: str, policy: str, authorized: dict | None = None) -> dict:
        names = {"local": ["mac"], "companion": ["phone"], "dual": ["mac", "phone"]}[policy]
        challenge = {
            "purpose": purpose,
            "subject": subject,
            "policy": policy,
            "devices": names,
            "expires_at": int(time.time()) + 60,
            "holder_id": holder.holder_id,
            "generation": holder.generation,
            "domain": "holder-device-p256-v1",
            "attestation_class": "device-p256-not-hardware",
            "authorized": authorized or {},
            "paired": [
                {
                    "device_id": device_id,
                    "fingerprint": item["fingerprint"],
                    "generation": item["generation"],
                    "policy": item["policy"],
                    "role": item["role"],
                }
                for device_id, item in sorted(devices.items())
            ],
        }
        # devices list in the canonical challenge is sorted by the holder for
        # local/companion/dual. Match that order.
        challenge["devices"] = sorted(names)
        return {
            "method": policy,
            "purpose": purpose,
            "policy": policy,
            "subject": subject,
            "devices": sorted(names),
            "expires_at": challenge["expires_at"],
            "hardware": False,
            "attestation_class": "device-p256-not-hardware",
            "signatures": {
                device_id: _sign(binary, item["private"], digest_challenge(challenge))
                for device_id, item in devices.items()
            },
        }

    def _consume_human(self, holder, binary, devices, policy, nonce, ws, script, binding) -> dict:
        from runspecimen.execution_holder import ExecutionHolder as _Holder

        del _Holder
        envelope = holder._binding_envelope(binding)
        mutation = hashlib.sha256(
            canonical_json_bytes(
                {"files": [[str(script.resolve()), sha256_file(script)]], "binding": envelope}
            )
        ).hexdigest()
        _path_map, payload_digest, snapshot_root = holder._bind(
            nonce,
            ws,
            [(str(script.resolve()), sha256_file(script))],
            executable=str(script.resolve()),
            argv=[str(script.resolve())],
        )
        self._unseal(Path(snapshot_root))
        authorized = {
            "payload_digest": payload_digest,
            "launch_argv": list(envelope["launch_argv"]),
            "bounds": envelope["bounds"],
            "mutation_digest": mutation,
            "attestation_class": "device-p256-not-hardware",
        }
        return self._sign_human(holder, binary, devices, "consume", nonce, policy, authorized)

    def _workspace(self, ws: Path) -> tuple[Path, Path, Path]:
        ws.mkdir()
        marker = ws.parent / "ran"
        script = ws / "job.py"
        script.write_text(
            "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran')\n",
            encoding="utf-8",
        )
        return ws, script, marker

    def _binding(self, ws: Path, script: Path, policy: str) -> dict:
        launch = [sys.executable, str(script.resolve()), str(ws.parent / "ran")]
        return {
            "contract_hash": "c" * 64,
            "workspace": str(ws.resolve()),
            "argv": [str(script.resolve()), str(ws.parent / "ran")],
            "executable": str(script.resolve()),
            "policy": policy,
            "cwd": str(ws.resolve()),
            "launch_argv": launch,
            "bounds": {"wall_timeout_sec": 10, "stdout_max_bytes": 65536, "stderr_max_bytes": 65536},
            "key_generation": 1,
        }

    def _unseal(self, path: Path) -> None:
        import shutil

        if not path.exists():
            return
        for dirpath, _dirnames, filenames in os.walk(path):
            os.chmod(dirpath, 0o700)
            for name in filenames:
                os.chmod(Path(dirpath) / name, 0o600)
        shutil.rmtree(path)


if __name__ == "__main__":
    unittest.main()
