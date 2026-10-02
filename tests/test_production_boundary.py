"""Production control flow with an injected boundary double. Not hardware.

The shipped pin stays unset. TESTTEAMID is a fixture, not an authorized identity.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runspecimen.execution_holder import ExecutionHolder, HolderRefusal
from runspecimen.native_bridge import (
    BOUNDARY_DOUBLE,
    PRODUCTION_BRIDGE,
    VerifierPin,
    assemble_developer_id_artifact,
    identity_matches,
    native_signers_connected,
    parse_codesign_identity,
    platform_verifier_report,
    production_verifier_pin,
    resolve_verifier,
)

TEST_TEAM = "TESTTEAMID"
TEST_REQUIREMENT = (
    'identifier "com.darashkevich.runspecimen.native-p256-verify" '
    "and certificate leaf[subject.OU] = TESTTEAMID"
)


def _pin() -> VerifierPin:
    return VerifierPin(TEST_TEAM, TEST_REQUIREMENT)


def _parsed() -> dict[str, str]:
    return {"team_identifier": TEST_TEAM, "designated_requirement": TEST_REQUIREMENT}


class ProductionBoundaryTests(unittest.TestCase):
    def _patches(self, parsed: dict[str, str] | None = None):
        body = parsed if parsed is not None else _parsed()
        items = [mock.patch("runspecimen.native_bridge.read_verifier_identity", return_value=body)]
        if sys.platform != "darwin":
            items.append(
                mock.patch("runspecimen.native_bridge.verifier_signature_strict", return_value=True)
            )
        return items

    def _start(self, parsed: dict[str, str] | None = None):
        items = self._patches(parsed)
        for item in items:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in items])

    def _holder(self, root: Path, *, pin: VerifierPin | None, installed: bool = True, artifact: Path | None = None) -> ExecutionHolder:
        from tests.test_native_bridge_policies import _boot

        secret = "ef" * 32
        holder = ExecutionHolder(
            root / "state",
            allow_test_double=False,
            installed_protection=installed,
            bootstrap_secret=secret,
            snapshot_base=root / "snaps",
            verifier_pin=pin,
            verifier_root=artifact,
        )
        holder.enroll("app", _boot(secret, "enroll", "app", "local"))
        return holder

    def _pair(self, holder: ExecutionHolder, role: str, policy: str, *, hardware: bool = False, backend: str = BOUNDARY_DOUBLE) -> None:
        from runspecimen.holder_asymmetric import public_key_fingerprint
        from tests.test_native_bridge_policies import _boot

        public = "AQID" + role
        compared = public_key_fingerprint(public)
        human = _boot(
            holder.bootstrap_secret,
            "pair",
            f"{role}-1",
            policy,
            role=role,
            fingerprint=compared,
            algorithm="p256",
            public_key=public,
            key_comparison=compared,
            hardware=hardware,
            provenance={
                "bridge": PRODUCTION_BRIDGE,
                "backend": backend,
                "boundary_double": True,
                "public_key": public,
                "role": role,
                "policy": policy,
                "generation": holder.generation,
            },
        )
        holder.pair_device(f"{role}-1", human)

    def test_shipped_pin_is_unset_and_refuses_the_boundary(self) -> None:
        self.assertIsNone(production_verifier_pin())
        td = tempfile.TemporaryDirectory(prefix="rsh-bound-unset-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), pin=None)
        with self.assertRaises(HolderRefusal) as ctx:
            self._pair(holder, "mac", "local")
        self.assertIn("not pinned", str(ctx.exception))

    def test_hardware_claim_is_refused(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-bound-hw-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), pin=_pin())
        with self.assertRaises(HolderRefusal) as ctx:
            self._pair(holder, "mac", "local", hardware=True)
        self.assertIn("not hardware", str(ctx.exception))

    def test_display_text_wrong_team_and_wrong_requirement_are_refused(self) -> None:
        details = "Authority=Developer ID Application: Not A Pin\nTeamIdentifier=WRONGTEAM\n"
        requirement = '# designated => identifier "other"\n'
        parsed = parse_codesign_identity(details, requirement)
        self.assertFalse(identity_matches(parsed, _pin()))
        self.assertNotIn("Developer ID", parsed["team_identifier"])
        td = tempfile.TemporaryDirectory(prefix="rsh-bound-id-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), pin=_pin())
        self._start({"team_identifier": "WRONGTEAM", "designated_requirement": TEST_REQUIREMENT})
        with self.assertRaises(HolderRefusal) as team:
            self._pair(holder, "mac", "local")
        self.assertIn("team identifier does not match", str(team.exception))
        holder = self._holder(Path(td.name) / "other", pin=_pin())
        with mock.patch(
            "runspecimen.native_bridge.read_verifier_identity",
            return_value={"team_identifier": TEST_TEAM, "designated_requirement": 'identifier "other"'},
        ):
            with self.assertRaises(HolderRefusal) as req:
                self._pair(holder, "mac", "local")
        self.assertIn("designated requirement does not match", str(req.exception))

    def test_boundary_signers_connect_for_local_and_phone(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-bound-roles-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), pin=_pin())
        self._start()
        self._pair(holder, "mac", "local")
        self.assertEqual(native_signers_connected(holder._devices()), {"local": True, "companion": False})
        self.assertFalse(holder._devices()["mac-1"]["hardware"])
        self._pair(holder, "phone", "local")
        self.assertEqual(native_signers_connected(holder._devices()), {"local": True, "companion": True})

    def test_replay_stays_refused_on_the_boundary_path(self) -> None:
        from tests.test_native_bridge_policies import LabeledBridgePolicyTests, _signer

        binary, _public, _private = _signer(self)
        host = LabeledBridgePolicyTests(methodName="test_local_companion_and_dual_execute_and_are_not_hardware")
        self._start()
        result = self._execute(host, binary, "local", ("mac",))
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["hardware"])
        with self.assertRaises(HolderRefusal) as replay:
            self._holder_for_replay.consume(
                nonce="local",
                policy="local",
                human=self._replay_human,
                workspace=self._replay_ws,
                files=self._replay_files,
                binding=self._replay_binding,
            )
        self.assertIn("already consumed", str(replay.exception))

    def test_local_companion_and_dual_boundary_execute(self) -> None:
        from tests.test_native_bridge_policies import LabeledBridgePolicyTests, _signer

        binary, _public, _private = _signer(self)
        host = LabeledBridgePolicyTests(methodName="test_local_companion_and_dual_execute_and_are_not_hardware")
        self._start()
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
        from runspecimen.hashutil import sha256_file
        from runspecimen.holder_asymmetric import public_key_fingerprint
        from tests.test_native_bridge_policies import _boot

        secret = "ab" * 32
        td = tempfile.TemporaryDirectory(prefix=f"rsh-bound-{policy}-")
        self.addCleanup(td.cleanup)
        holder = ExecutionHolder(
            Path(td.name) / "state",
            allow_test_double=False,
            installed_protection=True,
            bootstrap_secret=secret,
            snapshot_base=Path(td.name) / "snaps",
            verifier_pin=_pin(),
        )
        holder.enroll("app", _boot(secret, "enroll", "app", policy))
        devices = {}
        for role in roles:
            key_out = subprocess.run(
                [str(binary), "key"], check=True, capture_output=True, text=True, timeout=10
            )
            public_b64, private_b64 = key_out.stdout.splitlines()
            device_id = f"{role}-1"
            generation = holder.generation
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
                        "bridge": PRODUCTION_BRIDGE,
                        "backend": BOUNDARY_DOUBLE,
                        "boundary_double": True,
                        "public_key": public_b64,
                        "role": role,
                        "policy": policy,
                        "generation": generation,
                    },
                ),
            )
            devices[device_id] = {
                "public": public_b64,
                "private": private_b64,
                "fingerprint": compared,
                "generation": generation,
                "role": role,
                "policy": policy,
            }
            self.assertFalse(holder._devices()[device_id].get("hardware", True))
        host._set_policy(holder, binary, devices, policy)
        ws, script, marker = host._workspace(Path(td.name) / "ws")
        binding = host._binding(ws, script, policy)
        human = host._consume_human(holder, binary, devices, policy, policy, ws, script, binding)
        files = [(str(script.resolve()), sha256_file(script))]
        holder.consume(
            nonce=policy,
            policy=policy,
            human=human,
            workspace=ws,
            files=files,
            binding=binding,
        )
        if policy == "local":
            self._holder_for_replay = holder
            self._replay_human = human
            self._replay_ws = ws
            self._replay_files = files
            self._replay_binding = binding
        result = holder.execute(
            token=policy,
            human=host._sign_human(holder, binary, devices, "execute", policy, policy, {
                "payload_digest": __import__("json").loads((Path(td.name) / "state" / "spent.json").read_text())["nonces"][0]["payload_digest"],
                "launch_argv": list(binding["launch_argv"]),
                "bounds": binding["bounds"],
                "mutation_digest": __import__("json").loads((Path(td.name) / "state" / "spent.json").read_text())["nonces"][0]["binding"]["mutation_digest"],
                "attestation_class": "device-p256-not-hardware",
            }),
        )
        self.assertEqual(marker.read_text(encoding="utf-8"), "ran")
        return result


class CleanPackageTests(unittest.TestCase):
    def test_pure_package_omits_verifier_and_artifact_resolves_it(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn('"native_p256_verify"', text)
        spec = importlib.util.spec_from_file_location("rs_release_check", root / "scripts/release_check.py")
        self.assertIsNotNone(spec and spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(
            module._is_platform_verifier_member(
                "runspecimen-0.2.0rc15/src/runspecimen/platform/darwin_arm64/native_p256_verify"
            )
        )
        self.assertFalse(module._is_platform_verifier_member("runspecimen/native_p256_verify.swift"))
        td = tempfile.TemporaryDirectory(prefix="rsh-clean-pkg-")
        self.addCleanup(td.cleanup)
        empty = Path(td.name) / "pure"
        empty.mkdir()
        report = platform_verifier_report(empty)
        self.assertFalse(report["present"])
        self.assertFalse(report["pure_wheel_includes_verifier"])
        self.assertEqual(report["enrollment"], "fail-closed")
        self.assertIn("do not enroll", report["cli_when_absent"])
        self.assertIn("does not pass a holder", report["plugin_when_absent"])
        self.assertIsNone(resolve_verifier(empty))
        artifact = Path(td.name) / "developer-id"
        placed = assemble_developer_id_artifact(artifact)
        self.assertEqual(resolve_verifier(artifact), placed)
        self.assertTrue(placed.is_file())
        self.assertTrue(platform_verifier_report(artifact)["present"])
