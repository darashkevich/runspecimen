"""Isolated native enrollment. Not hardware and not a production identity.

The test pin is a fixture. ``production_verifier_pin`` stays unset.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runspecimen.execution_holder import ExecutionHolder, HolderRefusal
from runspecimen.native_bridge import (
    ISOLATED_DOUBLE,
    VerifierPin,
    identity_matches,
    native_signers_connected,
    packaged_verifier_publisher,
    parse_codesign_identity,
    production_verifier_pin,
)

TEST_TEAM = "TESTTEAMID"
TEST_REQUIREMENT = (
    'identifier "com.darashkevich.runspecimen.native-p256-verify" '
    "and certificate leaf[subject.OU] = TESTTEAMID"
)


def _pin() -> VerifierPin:
    return VerifierPin(TEST_TEAM, TEST_REQUIREMENT)


class VerifierIdentityTests(unittest.TestCase):
    def test_developer_id_display_text_is_not_sufficient(self) -> None:
        details = (
            "Authority=Developer ID Application: Not A Pin\n"
            "TeamIdentifier=WRONGTEAM\n"
        )
        requirement = '# designated => identifier "other"\n'
        parsed = parse_codesign_identity(details, requirement)
        self.assertEqual(parsed["team_identifier"], "WRONGTEAM")
        self.assertNotIn("Developer ID", parsed["team_identifier"])
        self.assertFalse(identity_matches(parsed, _pin()))
        fake = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr=details,
        )
        requirement_result = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=requirement,
            stderr="",
        )
        with mock.patch(
            "runspecimen.native_bridge.subprocess.run",
            side_effect=[fake, requirement_result, fake],
        ):
            with mock.patch(
                "runspecimen.native_bridge.platform_verifier_binary",
                return_value=Path("/tmp/not-a-production-verifier"),
            ):
                with mock.patch("runspecimen.native_bridge.sys.platform", "darwin"):
                    publisher = packaged_verifier_publisher()
        self.assertFalse(publisher["publisher_trusted"])
        self.assertNotEqual(publisher["signed"], "developer-id")

    def test_wrong_team_is_refused(self) -> None:
        parsed = {"team_identifier": "OTHERRTEAM", "designated_requirement": TEST_REQUIREMENT}
        self.assertFalse(identity_matches(parsed, _pin()))

    def test_wrong_designated_requirement_is_refused(self) -> None:
        parsed = {
            "team_identifier": TEST_TEAM,
            "designated_requirement": 'identifier "other"',
        }
        self.assertFalse(identity_matches(parsed, _pin()))

    def test_production_pin_is_unset(self) -> None:
        self.assertIsNone(production_verifier_pin())
        self.assertFalse(
            identity_matches(
                {"team_identifier": TEST_TEAM, "designated_requirement": TEST_REQUIREMENT},
                None,
            )
        )

    def test_pure_wheel_package_data_omits_the_mach_o(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn('"native_p256_verify"', text)
        self.assertIn("native_p256_verify.swift", text)
        binary = root / "src/runspecimen/platform/darwin_arm64/native_p256_verify"
        self.assertTrue(binary.is_file())


class IsolatedEnrollmentTests(unittest.TestCase):
    def _holder(self, root: Path, *, installed: bool = False) -> ExecutionHolder:
        from tests.test_native_bridge_policies import _boot

        secret = "ef" * 32
        holder = ExecutionHolder(
            root / "state",
            allow_test_double=False,
            installed_protection=installed,
            bootstrap_secret=secret,
            snapshot_base=root / "snaps",
            verifier_pin=_pin() if not installed else None,
        )
        holder.enroll("app", _boot(secret, "enroll", "app", "local"))
        return holder

    def _matching(self):
        parsed = {
            "team_identifier": TEST_TEAM,
            "designated_requirement": TEST_REQUIREMENT,
        }
        patches = [
            mock.patch("runspecimen.native_bridge.read_verifier_identity", return_value=parsed)
        ]
        if sys.platform != "darwin":
            patches.append(
                mock.patch("runspecimen.native_bridge.verifier_signature_strict", return_value=True)
            )
        return patches

    def _pair(self, holder: ExecutionHolder, role: str, policy: str) -> None:
        from tests.test_native_bridge_policies import _boot

        public = "AQID" + role
        from runspecimen.holder_asymmetric import public_key_fingerprint

        compared = public_key_fingerprint(public)
        holder.pair_device(
            f"{role}-1",
            _boot(
                holder.bootstrap_secret,
                "pair",
                f"{role}-1",
                policy,
                role=role,
                fingerprint=compared,
                algorithm="p256",
                public_key=public,
                key_comparison=compared,
                provenance={
                    "bridge": ISOLATED_DOUBLE,
                    "public_key": public,
                    "role": role,
                    "policy": policy,
                    "generation": holder.generation,
                },
            ),
        )

    def test_signers_connected_follow_paired_roles(self) -> None:
        self.assertEqual(native_signers_connected(None), {"local": False, "companion": False})
        td = tempfile.TemporaryDirectory(prefix="rsh-iso-connect-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name))
        patches = self._matching()
        for item in patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in patches])
        self._pair(holder, "mac", "local")
        self.assertEqual(
            native_signers_connected(holder._devices()),
            {"local": True, "companion": False},
        )
        self._pair(holder, "phone", "local")
        self.assertEqual(
            native_signers_connected(holder._devices()),
            {"local": True, "companion": True},
        )

    def test_installed_protection_refuses_the_isolated_double(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-iso-protect-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=True)
        with self.assertRaises(HolderRefusal) as ctx:
            self._pair(holder, "mac", "local")
        message = str(ctx.exception)
        self.assertIn("installed protection is on", message)
        self.assertIn(ISOLATED_DOUBLE, message)
        self.assertIn("not a Secure Enclave", message)
        self.assertEqual(native_signers_connected(holder._devices()), {"local": False, "companion": False})

    def test_wrong_team_refuses_pairing(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-iso-team-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name))
        parsed = {
            "team_identifier": "OTHERRTEAM",
            "designated_requirement": TEST_REQUIREMENT,
        }
        with mock.patch("runspecimen.native_bridge.read_verifier_identity", return_value=parsed):
            with self.assertRaises(HolderRefusal) as ctx:
                self._pair(holder, "mac", "local")
        self.assertIn("team identifier does not match", str(ctx.exception))

    def test_wrong_designated_requirement_refuses_pairing(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-iso-dr-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name))
        parsed = {
            "team_identifier": TEST_TEAM,
            "designated_requirement": 'identifier "other"',
        }
        with mock.patch("runspecimen.native_bridge.read_verifier_identity", return_value=parsed):
            with self.assertRaises(HolderRefusal) as ctx:
                self._pair(holder, "mac", "local")
        self.assertIn("designated requirement does not match", str(ctx.exception))

    def test_local_companion_and_dual_isolated_execute(self) -> None:
        from tests.test_native_bridge_policies import LabeledBridgePolicyTests, _signer

        binary, _public, _private = _signer(self)
        host = LabeledBridgePolicyTests(methodName="test_local_companion_and_dual_execute_and_are_not_hardware")
        host.setUp()
        self.addCleanup(host.doCleanups)
        parsed = {
            "team_identifier": TEST_TEAM,
            "designated_requirement": TEST_REQUIREMENT,
        }
        patches = [mock.patch("runspecimen.native_bridge.read_verifier_identity", return_value=parsed)]
        if sys.platform != "darwin":
            patches.append(
                mock.patch("runspecimen.native_bridge.verifier_signature_strict", return_value=True)
            )
        for item in patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in patches])
        for policy, roles in (
            ("local", ("mac",)),
            ("companion", ("phone",)),
            ("dual", ("mac", "phone")),
        ):
            with self.subTest(policy=policy):
                result = self._execute(host, binary, policy, roles)
                self.assertEqual(result["exit_code"], 0)
                self.assertFalse(result["hardware"])
                self.assertEqual(result["attestation_class"], "device-p256-not-hardware")

    def _execute(self, host, binary: Path, policy: str, roles: tuple[str, ...]) -> dict:
        secret = "ab" * 32
        td = tempfile.TemporaryDirectory(prefix=f"rsh-iso-{policy}-")
        self.addCleanup(td.cleanup)
        holder = ExecutionHolder(
            Path(td.name) / "state",
            allow_test_double=False,
            bootstrap_secret=secret,
            snapshot_base=Path(td.name) / "snaps",
            verifier_pin=_pin(),
        )
        from tests.test_native_bridge_policies import _boot

        holder.enroll("app", _boot(secret, "enroll", "app", policy))
        devices = {}
        for role in roles:
            key_out = subprocess.run(
                [str(binary), "key"], check=True, capture_output=True, text=True, timeout=10
            )
            public_b64, private_b64 = key_out.stdout.splitlines()
            device_id = f"{role}-1"
            compared_generation = holder.generation
            from runspecimen.holder_asymmetric import public_key_fingerprint

            compared = public_key_fingerprint(public_b64)
            holder.pair_device(
                device_id,
                _boot(
                    secret,
                    "pair",
                    device_id,
                    policy,
                    role=role,
                    fingerprint=compared,
                    algorithm="p256",
                    public_key=public_b64,
                    key_comparison=compared,
                    provenance={
                        "bridge": ISOLATED_DOUBLE,
                        "public_key": public_b64,
                        "role": role,
                        "policy": policy,
                        "generation": compared_generation,
                    },
                ),
            )
            devices[device_id] = {
                "public": public_b64,
                "private": private_b64,
                "fingerprint": compared,
                "generation": compared_generation,
                "role": role,
                "policy": policy,
            }
        host._set_policy(holder, binary, devices, policy)
        ws, script, marker = host._workspace(Path(td.name) / "ws")
        binding = host._binding(ws, script, policy)
        human = host._consume_human(holder, binary, devices, policy, policy, ws, script, binding)
        holder.consume(
            nonce=policy,
            policy=policy,
            human=human,
            workspace=ws,
            files=[(str(script.resolve()), __import__("runspecimen.hashutil", fromlist=["sha256_file"]).sha256_file(script))],
            binding=binding,
        )
        connected = native_signers_connected(holder._devices())
        if policy == "local":
            self.assertTrue(connected["local"])
            self.assertFalse(connected["companion"])
        elif policy == "companion":
            self.assertFalse(connected["local"])
            self.assertTrue(connected["companion"])
        else:
            self.assertTrue(connected["local"])
            self.assertTrue(connected["companion"])
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
            human=host._sign_human(holder, binary, devices, "execute", policy, policy, authorized),
        )
        self.assertEqual(marker.read_text(encoding="utf-8"), "ran")
        return result
