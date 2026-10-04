"""Production control flow with an injected boundary double. Not hardware.

The confirmed pin is the Developer ID holder identity. TESTTEAMID is a fixture.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from runspecimen.execution_holder import ExecutionHolder, HolderRefusal, handle_message, seal
from runspecimen.hashutil import canonical_json_bytes, sha256_file
from runspecimen.native_bridge import (
    BOUNDARY_DOUBLE,
    PRODUCTION_BRIDGE,
    HumanNativeSigner,
    HumanOperatedNativeAdapter,
    TrustedNativeBoundary,
    VerifierPin,
    production_enrollment_refusal,
    assemble_developer_id_artifact,
    identity_matches,
    native_signers_connected,
    parse_codesign_identity,
    platform_verifier_report,
    production_verifier_pin,
    read_verifier_identity,
    refresh_verifier_provenance,
    require_verifier_identity,
    resolve_verifier,
)

TEST_TEAM = "TESTTEAMID"
TEST_REQUIREMENT = (
    'identifier "com.darashkevich.runspecimen.native-p256-verify" '
    "and certificate leaf[subject.OU] = TESTTEAMID"
)


CONFIRMED_REQUIREMENT = (
    'identifier "com.darashkevich.runspecimen.native-p256-verify" '
    "and anchor apple generic "
    "and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ "
    "and certificate leaf[field.1.2.840.113635.100.6.1.13] /* exists */ "
    "and certificate leaf[subject.OU] = UN6KF8636A"
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

    def _injected(self, root: Path) -> ExecutionHolder:
        from tests.test_native_bridge_policies import _boot

        secret = "ef" * 32
        boundary = TrustedNativeBoundary()
        holder = ExecutionHolder(
            root / "state",
            allow_test_double=False,
            installed_protection=False,
            bootstrap_secret=secret,
            snapshot_base=root / "snaps",
            verifier_pin=_pin(),
            trusted_native_boundary=boundary,
        )
        holder.enroll("app", _boot(secret, "enroll", "app", "local"))
        return holder

    def _pair(self, holder: ExecutionHolder, role: str, policy: str, *, hardware: bool = False, backend: str = BOUNDARY_DOUBLE) -> None:
        from runspecimen.holder_asymmetric import public_key_fingerprint
        from tests.test_native_bridge_policies import _boot

        public = "AQID" + role
        compared = public_key_fingerprint(public)
        boundary = holder.trusted_native_boundary
        if isinstance(boundary, TrustedNativeBoundary):
            boundary.issue(
                public_key=public,
                role=role,
                policy=policy,
                generation=holder.generation,
            )
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

    def test_confirmed_pin_is_exact_and_refuses_a_software_key(self) -> None:
        pin = production_verifier_pin()
        self.assertIsNotNone(pin)
        assert pin is not None
        self.assertEqual(pin.team_identifier, "UN6KF8636A")
        self.assertEqual(pin.designated_requirement, CONFIRMED_REQUIREMENT)
        self.assertEqual(pin.designated_requirement.count("identifier"), 1)
        self.assertNotIn('identifier "*"', pin.designated_requirement)
        self.assertNotIn("Apple Development", pin.designated_requirement)
        td = tempfile.TemporaryDirectory(prefix="rsh-bound-confirmed-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), pin=pin)
        with self.assertRaises(HolderRefusal) as ctx:
            self._pair(holder, "mac", "local")
        self.assertIn("does not authorize a software key", str(ctx.exception))

    def test_identity_mismatch_against_the_confirmed_pin(self) -> None:
        pin = production_verifier_pin()
        assert pin is not None
        display = parse_codesign_identity(
            "Authority=Developer ID Application: Not A Pin\nTeamIdentifier=not set\n",
            "designated =>\n",
        )
        self.assertFalse(identity_matches(display, pin))
        self.assertNotIn("Developer ID", display["team_identifier"])
        wrong_team = {
            "team_identifier": "WRONGTEAM",
            "designated_requirement": CONFIRMED_REQUIREMENT,
        }
        self.assertFalse(identity_matches(wrong_team, pin))
        wrong_identifier = {
            "team_identifier": "UN6KF8636A",
            "designated_requirement": CONFIRMED_REQUIREMENT.replace(
                "com.darashkevich.runspecimen.native-p256-verify",
                "com.example.other",
            ),
        }
        self.assertFalse(identity_matches(wrong_identifier, pin))
        apple_development = {
            "team_identifier": "UN6KF8636A",
            "designated_requirement": (
                'identifier "com.darashkevich.runspecimen.native-p256-verify" '
                "and anchor apple generic and certificate leaf[subject.OU] = UN6KF8636A"
            ),
        }
        self.assertNotEqual(apple_development["designated_requirement"], CONFIRMED_REQUIREMENT)
        self.assertFalse(identity_matches(apple_development, pin))
        with mock.patch(
            "runspecimen.native_bridge.read_verifier_identity",
            return_value=wrong_team,
        ), mock.patch("runspecimen.native_bridge.verifier_signature_strict", return_value=True):
            with self.assertRaises(Exception) as team:
                require_verifier_identity(pin)
        self.assertIn("team identifier does not match", str(team.exception))
        with mock.patch(
            "runspecimen.native_bridge.read_verifier_identity",
            return_value=wrong_identifier,
        ), mock.patch("runspecimen.native_bridge.verifier_signature_strict", return_value=True):
            with self.assertRaises(Exception) as requirement:
                require_verifier_identity(pin)
        self.assertIn("designated requirement does not match", str(requirement.exception))

    def test_adhoc_repository_verifier_does_not_meet_the_confirmed_pin(self) -> None:
        if sys.platform != "darwin":
            self.skipTest("codesign identity is macOS-only")
        pin = production_verifier_pin()
        assert pin is not None
        with self.assertRaises(Exception) as ctx:
            require_verifier_identity(pin)
        self.assertTrue(
            "does not match" in str(ctx.exception) or "not pinned" in str(ctx.exception)
        )

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
        with self.assertRaises(Exception) as team:
            require_verifier_identity(_pin())
        self.assertIn("team identifier does not match", str(team.exception))
        with mock.patch(
            "runspecimen.native_bridge.read_verifier_identity",
            return_value={"team_identifier": TEST_TEAM, "designated_requirement": 'identifier "other"'},
        ):
            with self.assertRaises(Exception) as req:
                require_verifier_identity(_pin())
        self.assertIn("designated requirement does not match", str(req.exception))
        self._start()
        holder = self._holder(Path(td.name), pin=_pin())
        with self.assertRaises(HolderRefusal) as software:
            self._pair(holder, "mac", "local")
        self.assertIn("does not authorize a software key", str(software.exception))

    def test_boundary_signers_connect_for_local_and_phone(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-bound-roles-")
        self.addCleanup(td.cleanup)
        holder = self._injected(Path(td.name))
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
        result = self._execute(host, binary, "local", ("mac",), injected=True)
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

    def test_installed_protection_refuses_a_software_key_when_the_pin_matches(self) -> None:
        from tests.test_native_bridge_policies import LabeledBridgePolicyTests, _signer

        binary, _public, _private = _signer(self)
        host = LabeledBridgePolicyTests(methodName="test_local_companion_and_dual_execute_and_are_not_hardware")
        self._start()
        os.environ["RS_HOLDER_TRUSTED_NATIVE_BOUNDARY"] = "1"
        self.addCleanup(lambda: os.environ.pop("RS_HOLDER_TRUSTED_NATIVE_BOUNDARY", None))
        for policy, roles in (
            ("local", ("mac",)),
            ("companion", ("phone",)),
            ("dual", ("mac", "phone")),
        ):
            with self.subTest(policy=policy):
                with self.assertRaises(HolderRefusal) as ctx:
                    self._execute(host, binary, policy, roles, injected=False)
                message = str(ctx.exception)
                self.assertIn("does not authorize a software key", message)
                self.assertIn("boundary_double", message)
                self.assertIn("installed protection is on", message)

    def test_wire_and_config_cannot_select_the_double(self) -> None:
        from runspecimen.holder_asymmetric import public_key_fingerprint
        from tests.test_native_bridge_policies import _boot

        self._start()
        td = tempfile.TemporaryDirectory(prefix="rsh-bound-wire-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        (root / "holder-config.json").write_text(
            json.dumps({"boundary_double": True, "trusted_native_boundary": True}),
            encoding="utf-8",
        )
        os.environ["RS_HOLDER_TRUSTED_NATIVE_BOUNDARY"] = "1"
        self.addCleanup(lambda: os.environ.pop("RS_HOLDER_TRUSTED_NATIVE_BOUNDARY", None))
        with self.assertRaises(TypeError):
            ExecutionHolder(root / "bad", trusted_native_boundary={"boundary_double": True})
        secret = "ef" * 32
        holder = ExecutionHolder(
            root / "state",
            allow_test_double=False,
            installed_protection=True,
            bootstrap_secret=secret,
            snapshot_base=root / "snaps",
            verifier_pin=_pin(),
        )
        with self.assertRaises(HolderRefusal) as human_step:
            holder.begin_human_secure_enclave_enrollment()
        self.assertIn("was not invoked", str(human_step.exception))
        enrolled = holder.enroll("app", _boot(secret, "enroll", "app", "local"))
        public = "AQID"
        compared = public_key_fingerprint(public)
        human = _boot(
            secret,
            "pair",
            "mac-1",
            "local",
            role="mac",
            fingerprint=compared,
            algorithm="p256",
            public_key=public,
            key_comparison=compared,
            provenance={
                "bridge": PRODUCTION_BRIDGE,
                "backend": BOUNDARY_DOUBLE,
                "boundary_double": True,
                "public_key": public,
                "role": "mac",
                "policy": "local",
                "generation": holder.generation,
            },
        )
        message = seal(
            enrolled["caller_secret"],
            caller_id="app",
            body={"op": "pair", "device_id": "mac-1", "human": human},
        )
        with self.assertRaises(HolderRefusal) as ctx:
            handle_message(holder, message, bootstrap_secret=secret)
        self.assertIn("does not authorize a software key", str(ctx.exception))
        self.assertEqual(holder._devices(), {})

    def test_injected_boundary_exercises_local_companion_and_dual(self) -> None:
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
                result = self._execute(host, binary, policy, roles, injected=True)
                self.assertEqual(result["exit_code"], 0)
                self.assertFalse(result["hardware"])
                self.assertEqual(result["attestation_class"], "device-p256-not-hardware")
                self.assertFalse(result["installed_protection"])

    def test_injected_control_flow_cancel_revoke_rotate_restart_downgrade_and_race(self) -> None:
        from runspecimen.hashutil import sha256_file
        from runspecimen.holder_asymmetric import public_key_fingerprint
        from tests.test_native_bridge_policies import LabeledBridgePolicyTests, _boot, _signer

        binary, public_b64, private_b64 = _signer(self)
        host = LabeledBridgePolicyTests(methodName="test_cancel_revoke_replay_rotation_binding_restart_and_concurrency")
        self._start()
        secret = "cd" * 32
        td = tempfile.TemporaryDirectory(prefix="rsh-bound-life-")
        self.addCleanup(td.cleanup)
        root = Path(td.name) / "state"
        snaps = Path(td.name) / "snaps"
        boundary = TrustedNativeBoundary()
        holder = ExecutionHolder(
            root,
            allow_test_double=False,
            installed_protection=False,
            bootstrap_secret=secret,
            snapshot_base=snaps,
            verifier_pin=_pin(),
            trusted_native_boundary=boundary,
        )
        holder.enroll("app", _boot(secret, "enroll", "app", "local"))
        compared = public_key_fingerprint(public_b64)
        boundary.issue(public_key=public_b64, role="mac", policy="local", generation=holder.generation)
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
                public_key=public_b64,
                key_comparison=compared,
                provenance={
                    "bridge": PRODUCTION_BRIDGE,
                    "backend": BOUNDARY_DOUBLE,
                    "boundary_double": True,
                    "public_key": public_b64,
                    "role": "mac",
                    "policy": "local",
                    "generation": holder.generation,
                },
            ),
        )
        device = {
            "public": public_b64,
            "private": private_b64,
            "fingerprint": compared,
            "generation": holder.generation,
            "role": "mac",
            "policy": "local",
        }
        host._set_policy(holder, binary, {"mac-1": device}, "local")
        ws, script, _marker = host._workspace(Path(td.name) / "ws")
        binding = host._binding(ws, script, "local")
        human = host._consume_human(holder, binary, {"mac-1": device}, "local", "once", ws, script, binding)
        holder.consume(
            nonce="once",
            policy="local",
            human=human,
            workspace=ws,
            files=[(str(script.resolve()), sha256_file(script))],
            binding=binding,
        )
        restarted = ExecutionHolder(
            root,
            allow_test_double=False,
            installed_protection=False,
            bootstrap_secret=secret,
            snapshot_base=snaps,
            verifier_pin=_pin(),
            trusted_native_boundary=boundary,
        )
        self.assertEqual(restarted.holder_id, holder.holder_id)
        cancelled = restarted.cancel_uncertain(
            "once", host._sign_human(restarted, binary, {"mac-1": device}, "cancel", "once", "local")
        )
        self.assertTrue(cancelled["cancelled"])
        self.assertFalse(cancelled.get("hardware", False))
        errors: list[BaseException] = []
        ok: list[bool] = []
        race_human = host._consume_human(restarted, binary, {"mac-1": device}, "local", "race", ws, script, binding)

        def _once() -> None:
            try:
                restarted.consume(
                    nonce="race",
                    policy="local",
                    human=race_human,
                    workspace=ws,
                    files=[(str(script.resolve()), sha256_file(script))],
                    binding=binding,
                )
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            else:
                ok.append(True)

        threads = [threading.Thread(target=_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(ok), 1)
        self.assertEqual(len(errors), 1)
        restarted.cancel_uncertain(
            "race", host._sign_human(restarted, binary, {"mac-1": device}, "cancel", "race", "local")
        )
        rotated = restarted.rotate_caller(
            host._sign_human(restarted, binary, {"mac-1": device}, "rotate", "app", "local")
        )
        self.assertEqual(rotated["key_generation"], 2)
        self.assertFalse(rotated["hardware"])
        restarted.revoke_device(
            "mac-1", host._sign_human(restarted, binary, {"mac-1": device}, "revoke", "mac-1", "local")
        )
        with self.assertRaises(HolderRefusal) as revoked:
            restarted.consume(
                nonce="after-revoke",
                policy="local",
                human=host._sign_human(restarted, binary, {"mac-1": device}, "consume", "after-revoke", "local"),
                workspace=ws,
                files=[(str(script.resolve()), sha256_file(script))],
                binding=binding,
            )
        self.assertIn("revoked", str(revoked.exception))
        covered = {"protocol": 0, "caller_id": "bootstrap", "body": {"op": "enroll"}}
        with self.assertRaises(HolderRefusal) as downgraded:
            handle_message(restarted, {**covered, "mac": "00"}, bootstrap_secret=secret)
        self.assertIn("downgrade", str(downgraded.exception))

    def test_caller_flag_without_the_injection_is_refused(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-bound-flag-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), pin=_pin(), installed=False)
        self._start()
        with self.assertRaises(HolderRefusal) as ctx:
            self._pair(holder, "mac", "local")
        self.assertIn("caller boundary flag", str(ctx.exception))

    def _execute(self, host, binary: Path, policy: str, roles: tuple[str, ...], *, injected: bool = False) -> dict:
        from runspecimen.hashutil import sha256_file
        from runspecimen.holder_asymmetric import public_key_fingerprint
        from tests.test_native_bridge_policies import _boot

        secret = "ab" * 32
        td = tempfile.TemporaryDirectory(prefix=f"rsh-bound-{policy}-")
        self.addCleanup(td.cleanup)
        boundary = TrustedNativeBoundary() if injected else None
        holder = ExecutionHolder(
            Path(td.name) / "state",
            allow_test_double=False,
            installed_protection=not injected,
            bootstrap_secret=secret,
            snapshot_base=Path(td.name) / "snaps",
            verifier_pin=_pin(),
            trusted_native_boundary=boundary,
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
            if boundary is not None:
                boundary.issue(
                    public_key=public_b64,
                    role=role,
                    policy=policy,
                    generation=generation,
                )
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

    def test_extracted_artifact_is_the_holder_verifier_without_repo_fallback(self) -> None:
        if sys.platform != "darwin":
            self.skipTest("codesign and the Darwin verifier are macOS-only")
        root = Path(__file__).resolve().parents[1]
        source = root / "src/runspecimen/platform/darwin_arm64/native_p256_verify"
        repo_provenance = source.with_name("native_p256_verify.provenance.json")
        repo_before = repo_provenance.read_text(encoding="utf-8")
        self.assertIn('"signed": "adhoc"', repo_before)
        td = tempfile.TemporaryDirectory(prefix="rsh-extract-verifier-")
        self.addCleanup(td.cleanup)
        build = Path(td.name) / "build"
        placed = assemble_developer_id_artifact(build, source)
        identity = "Developer ID Application: YAHOR DARASHKEVICH (UN6KF8636A)"
        listed = subprocess.run(
            ["/usr/bin/security", "find-identity", "-v", "-p", "codesigning"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        sign_as = identity if identity in listed.stdout else "-"
        signed = subprocess.run(
            [
                "/usr/bin/codesign",
                "--force",
                "--sign",
                sign_as,
                "--identifier",
                "com.darashkevich.runspecimen.native-p256-verify",
                "--timestamp=none",
                str(placed),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(signed.returncode, 0, signed.stderr)
        refreshed = refresh_verifier_provenance(placed)
        body = json.loads(refreshed.read_text(encoding="utf-8"))
        self.assertEqual(body["signed"], "codesign" if sign_as == identity else "adhoc")
        self.assertEqual(body["sha256"], hashlib.sha256(placed.read_bytes()).hexdigest())
        self.assertNotIn("Developer ID", json.dumps(body))
        parsed = read_verifier_identity(placed)
        confirmed = production_verifier_pin()
        assert confirmed is not None
        if sign_as == identity:
            self.assertEqual(parsed["team_identifier"], confirmed.team_identifier)
            self.assertEqual(parsed["designated_requirement"], confirmed.designated_requirement)
            require_verifier_identity(confirmed, placed)
        else:
            self.assertNotEqual(parsed.get("designated_requirement"), confirmed.designated_requirement)
            with self.assertRaises(Exception):
                require_verifier_identity(confirmed, placed)
        self.assertEqual(repo_provenance.read_text(encoding="utf-8"), repo_before)
        archive = Path(td.name) / "verifier.zip"
        with zipfile.ZipFile(archive, "w") as packed:
            for path in build.rglob("*"):
                if path.is_file():
                    packed.write(path, path.relative_to(build).as_posix())
        extracted = Path(td.name) / "extracted"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as packed:
            packed.extractall(extracted)
        self.assertIsNotNone(resolve_verifier(extracted))
        script = """
import os, sys
os.chdir("/tmp")
import runspecimen.native_bridge as nb
def boom():
    raise SystemExit("repo fallback")
nb.platform_verifier_binary = boom
from runspecimen.execution_holder import ExecutionHolder
root = sys.argv[1]
holder = ExecutionHolder(
    os.path.join(root, "state"),
    verifier_root=root,
    allow_test_double=False,
    installed_protection=True,
)
binary = holder._verifier_binary()
if binary is None or not os.path.realpath(binary).startswith(os.path.realpath(root)):
    raise SystemExit("holder did not resolve the extracted verifier")
print(os.path.realpath(binary))
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root / "src")
        launched = subprocess.run(
            [sys.executable, "-c", script, str(extracted)],
            cwd="/tmp",
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(launched.returncode, 0, launched.stderr)
        self.assertIn(str(extracted), launched.stdout)
        self.assertNotIn(str(source), launched.stdout)


class _KitSigner(HumanNativeSigner):
    """Software CryptoKit signer injected in-process. Not a Secure Enclave key."""

    def __init__(self, binary: Path, keys: dict[str, tuple[str, str]]) -> None:
        self.binary = binary
        self.keys = keys
        self.hardware = False

    def public_key(self, role: str) -> str:
        return self.keys[role][0]

    def sign(self, role: str, message: bytes) -> str:
        from tests.test_native_bridge_policies import _sign

        return _sign(self.binary, self.keys[role][1], message)


class HumanNativeSignerTests(unittest.TestCase):
    def _keys(self) -> tuple[Path, dict[str, tuple[str, str]]]:
        from tests.test_native_bridge_policies import _signer

        binary, _public, _private = _signer(self)
        keys = {}
        for role in ("mac", "phone"):
            key_out = subprocess.run(
                [str(binary), "key"], check=True, capture_output=True, text=True, timeout=10
            )
            public_b64, private_b64 = key_out.stdout.splitlines()
            keys[role] = (public_b64, private_b64)
        return binary, keys

    def _holder(self, root: Path, *, installed: bool) -> ExecutionHolder:
        from tests.test_native_bridge_policies import _boot

        secret = "ab" * 32
        holder = ExecutionHolder(
            root / "state",
            allow_test_double=False,
            installed_protection=installed,
            bootstrap_secret=secret,
            snapshot_base=root / "snaps",
            verifier_pin=production_verifier_pin(),
        )
        holder.enroll("app", _boot(secret, "enroll", "app", "local"))
        return holder

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

    def _workspace(self, ws: Path) -> tuple[Path, Path]:
        ws.mkdir()
        script = ws / "job.py"
        script.write_text(
            "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran')\n",
            encoding="utf-8",
        )
        return ws, script

    def _unseal(self, path: Path) -> None:
        if not path.exists():
            return
        for dirpath, _dirnames, filenames in os.walk(path):
            os.chmod(dirpath, 0o700)
            for name in filenames:
                os.chmod(Path(dirpath) / name, 0o600)
        shutil.rmtree(path)

    def _consume_authorization(self, holder: ExecutionHolder, nonce: str, ws: Path, script: Path, binding: dict) -> dict:
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
        return {
            "payload_digest": payload_digest,
            "launch_argv": list(envelope["launch_argv"]),
            "bounds": envelope["bounds"],
            "mutation_digest": mutation,
            "attestation_class": "device-p256-not-hardware",
        }

    def test_handler_source_does_not_call_secure_enclave(self) -> None:
        source = "\n".join(
            inspect.getsource(method)
            for method in (
                ExecutionHolder.begin_human_secure_enclave_enrollment,
                ExecutionHolder.begin_human_operated_native_adapter,
                ExecutionHolder.sign_with_human_operated_adapter,
                ExecutionHolder.enroll_user_invoked_secure_enclave,
                ExecutionHolder.sign_with_os_boundary,
                ExecutionHolder.sign_from_session,
                ExecutionHolder.accept_native_ipc,
            )
        )
        self.assertNotIn("SecureEnclave.P256.Signing.PrivateKey(", source)
        swift = (
            Path(__file__).resolve().parents[1]
            / "apps/macos/Sources/RunSpecimenCore/RSBA2Package.swift"
        ).read_text(encoding="utf-8")
        self.assertNotIn("SecureEnclave.P256.Signing.PrivateKey(", swift)
        from tests.test_native_bridge_policies import _signer

        self.assertNotIn("SecureEnclave", inspect.getsource(_signer))

    def test_unattended_call_refuses_before_a_prompt(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-human-none-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        with self.assertRaises(HolderRefusal) as missing:
            holder.begin_human_secure_enclave_enrollment()
        self.assertIn("was not invoked", str(missing.exception))

    def test_wire_env_and_config_cannot_select_the_signer(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-human-wire-")
        self.addCleanup(td.cleanup)
        secret = "ab" * 32
        holder = self._holder(Path(td.name), installed=False)
        config = Path(td.name) / "signer.json"
        config.write_text('{"hardware": true, "backend": "secure-enclave"}\n', encoding="utf-8")
        with mock.patch.dict(
            os.environ,
            {
                "RS_HOLDER_NATIVE_SIGNER": "secure-enclave",
                "RS_HOLDER_SIGNER_CONFIG": str(config),
            },
        ):
            with self.assertRaises(HolderRefusal) as unattended:
                holder.begin_human_secure_enclave_enrollment()
            self.assertIn("was not invoked", str(unattended.exception))
            with self.assertRaises(HolderRefusal) as selected:
                holder.begin_human_secure_enclave_enrollment(
                    {"hardware": True, "backend": "secure-enclave"}
                )
            self.assertIn("was not invoked", str(selected.exception))
            with self.assertRaises(TypeError) as signed:
                holder.sign_with_human_native_signer(
                    {"role": "mac"}, "set-policy", "local", "local"
                )
            self.assertIn("cannot be selected", str(signed.exception))
        message = seal(
            holder.caller_secret("app"),
            caller_id="app",
            body={"op": "begin-human", "signer": {"hardware": True, "backend": "secure-enclave"}},
        )
        with self.assertRaises(HolderRefusal) as wired:
            handle_message(holder, message, bootstrap_secret=secret)
        self.assertIn("unknown holder operation", str(wired.exception))

    def test_caller_hardware_label_is_refused(self) -> None:
        class Labeled(HumanNativeSigner):
            hardware = True

            def public_key(self, role: str) -> str:
                return "labeled"

            def sign(self, role: str, message: bytes) -> str:
                return "labeled"

        td = tempfile.TemporaryDirectory(prefix="rsh-human-label-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        with self.assertRaises(HolderRefusal) as ctx:
            holder.begin_human_secure_enclave_enrollment(Labeled(), policy="local")
        self.assertIn("caller hardware label", str(ctx.exception))

    def test_installed_protection_refuses_the_injected_signer_when_the_pin_matches(self) -> None:
        from tests.test_native_bridge_policies import _boot

        binary, keys = self._keys()
        signer = _KitSigner(binary, keys)
        td = tempfile.TemporaryDirectory(prefix="rsh-human-installed-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=True)
        self.assertEqual(holder.verifier_pin.team_identifier, production_verifier_pin().team_identifier)
        with self.assertRaises(HolderRefusal) as ctx:
            holder.begin_human_secure_enclave_enrollment(signer, policy="dual")
        self.assertIn(production_enrollment_refusal(), str(ctx.exception))
        public_b64 = keys["mac"][0]
        from runspecimen.holder_asymmetric import public_key_fingerprint

        compared = public_key_fingerprint(public_b64)
        with self.assertRaises(HolderRefusal) as doubled:
            holder.pair_device(
                "mac-1",
                _boot(
                    "ab" * 32,
                    "pair",
                    "mac-1",
                    "local",
                    role="mac",
                    fingerprint=compared,
                    algorithm="p256",
                    public_key=public_b64,
                    key_comparison=compared,
                    provenance={
                        "bridge": PRODUCTION_BRIDGE,
                        "backend": BOUNDARY_DOUBLE,
                        "boundary_double": True,
                        "public_key": public_b64,
                        "role": "mac",
                        "policy": "local",
                        "generation": holder.generation,
                    },
                ),
            )
        self.assertIn("does not authorize a software key", str(doubled.exception))

    def test_injected_signer_enrolls_pairs_and_executes(self) -> None:
        binary, keys = self._keys()
        signer = _KitSigner(binary, keys)
        for policy in ("local", "companion", "dual"):
            with self.subTest(policy=policy):
                self._execute(signer, policy)

    def test_injected_signer_cancel_revoke_rotate_restart_downgrade_and_race(self) -> None:
        binary, keys = self._keys()
        signer = _KitSigner(binary, keys)
        td = tempfile.TemporaryDirectory(prefix="rsh-human-flow-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        holder = self._holder(root, installed=False)
        enrolled = holder.begin_human_secure_enclave_enrollment(signer, policy="local")
        self.assertFalse(enrolled["hardware"])
        self.assertFalse(enrolled["biometric_invoked"])
        holder.set_policy(holder.sign_with_human_native_signer(signer, "set-policy", "local", "local"))
        ws, script = self._workspace(root / "ws")
        binding = self._binding(ws, script, "local")
        files = [(str(script.resolve()), sha256_file(script))]
        human = holder.sign_with_human_native_signer(
            signer,
            "consume",
            "once",
            "local",
            self._consume_authorization(holder, "once", ws, script, binding),
        )
        holder.consume(nonce="once", policy="local", human=human, workspace=ws, files=files, binding=binding)
        restarted = ExecutionHolder(
            root / "state",
            allow_test_double=False,
            installed_protection=False,
            bootstrap_secret="ab" * 32,
            snapshot_base=root / "snaps",
            verifier_pin=production_verifier_pin(),
        )
        self.assertEqual(restarted.holder_id, holder.holder_id)
        cancelled = restarted.cancel_uncertain(
            "once", restarted.sign_with_human_native_signer(signer, "cancel", "once", "local")
        )
        self.assertTrue(cancelled["cancelled"])
        race = restarted.sign_with_human_native_signer(
            signer,
            "consume",
            "race",
            "local",
            self._consume_authorization(restarted, "race", ws, script, binding),
        )
        errors: list[BaseException] = []
        ok: list[bool] = []

        def _once() -> None:
            try:
                restarted.consume(
                    nonce="race", policy="local", human=race, workspace=ws, files=files, binding=binding
                )
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            else:
                ok.append(True)

        threads = [threading.Thread(target=_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(ok), 1)
        self.assertEqual(len(errors), 1)
        restarted.cancel_uncertain(
            "race", restarted.sign_with_human_native_signer(signer, "cancel", "race", "local")
        )
        rotated = restarted.rotate_caller(
            restarted.sign_with_human_native_signer(signer, "rotate", "app", "local")
        )
        self.assertEqual(rotated["key_generation"], 2)
        self.assertFalse(rotated["hardware"])
        restarted.revoke_device(
            "mac-human",
            restarted.sign_with_human_native_signer(signer, "revoke", "mac-human", "local"),
        )
        with self.assertRaises(HolderRefusal) as revoked:
            restarted.consume(
                nonce="after-revoke",
                policy="local",
                human=restarted.sign_with_human_native_signer(signer, "consume", "after-revoke", "local"),
                workspace=ws,
                files=files,
                binding=binding,
            )
        self.assertIn("revoked", str(revoked.exception))
        covered = {"protocol": 0, "caller_id": "bootstrap", "body": {"op": "enroll"}}
        with self.assertRaises(HolderRefusal) as downgraded:
            handle_message(restarted, {**covered, "mac": "00"}, bootstrap_secret="ab" * 32)
        self.assertIn("downgrade", str(downgraded.exception))

    def _execute(self, signer: _KitSigner, policy: str) -> None:
        td = tempfile.TemporaryDirectory(prefix=f"rsh-human-{policy}-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        holder = self._holder(root, installed=False)
        enrolled = holder.begin_human_secure_enclave_enrollment(signer, policy=policy)
        self.assertEqual(enrolled["hardware"], False)
        self.assertEqual(enrolled["biometric_invoked"], False)
        self.assertEqual(enrolled["origin"], "injected-human-native-signer")
        for device_id in enrolled["devices"]:
            record = holder._devices()[device_id]
            self.assertFalse(record["hardware"])
            self.assertEqual(record["provenance"]["origin"], "injected-human-native-signer")
            self.assertNotIn("boundary_double", record["provenance"])
        holder.set_policy(holder.sign_with_human_native_signer(signer, "set-policy", policy, policy))
        ws, script = self._workspace(root / "ws")
        binding = self._binding(ws, script, policy)
        files = [(str(script.resolve()), sha256_file(script))]
        human = holder.sign_with_human_native_signer(
            signer,
            "consume",
            policy,
            policy,
            self._consume_authorization(holder, policy, ws, script, binding),
        )
        self.assertFalse(human["hardware"])
        holder.consume(nonce=policy, policy=policy, human=human, workspace=ws, files=files, binding=binding)
        spent = json.loads((root / "state" / "spent.json").read_text(encoding="utf-8"))["nonces"][0]
        result = holder.execute(
            token=policy,
            human=holder.sign_with_human_native_signer(
                signer,
                "execute",
                policy,
                policy,
                {
                    "payload_digest": spent["payload_digest"],
                    "launch_argv": list(binding["launch_argv"]),
                    "bounds": binding["bounds"],
                    "mutation_digest": spent["binding"]["mutation_digest"],
                    "attestation_class": "device-p256-not-hardware",
                },
            ),
        )
        self.assertEqual((ws.parent / "ran").read_text(encoding="utf-8"), "ran")
        self.assertNotEqual(result.get("hardware"), True)


class _AdapterSigner(HumanOperatedNativeAdapter):
    """Injected at the human-operated adapter. Not a software signer and not a prompt."""

    def __init__(self, binary: Path, keys: dict[str, tuple[str, str]]) -> None:
        self.binary = binary
        self.keys = keys

    def public_key(self, role: str) -> str:
        return self.keys[role][0]

    def sign(self, role: str, message: bytes) -> str:
        from tests.test_native_bridge_policies import _sign

        return _sign(self.binary, self.keys[role][1], message)


class HumanOperatedNativeAdapterTests(HumanNativeSignerTests):
    def test_software_signer_is_not_the_native_adapter(self) -> None:
        self.assertFalse(issubclass(HumanNativeSigner, HumanOperatedNativeAdapter))
        self.assertFalse(HumanNativeSigner.hardware)
        binary, keys = self._keys()
        software = _KitSigner(binary, keys)
        td = tempfile.TemporaryDirectory(prefix="rsh-adapter-software-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=True)
        self.assertEqual(holder.verifier_pin.team_identifier, production_verifier_pin().team_identifier)
        with self.assertRaises(HolderRefusal) as ctx:
            holder.begin_human_operated_native_adapter(software, policy="dual")
        self.assertIn("does not authorize a software key", str(ctx.exception))
        with self.assertRaises(HolderRefusal) as boundary:
            holder.begin_human_operated_native_adapter(TrustedNativeBoundary(), policy="local")
        self.assertIn("does not authorize a software key", str(boundary.exception))

    def test_wire_env_and_config_cannot_select_the_adapter(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-adapter-wire-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        config = Path(td.name) / "adapter.json"
        config.write_text('{"hardware": true, "origin": "human-operated-native-adapter"}\n', encoding="utf-8")
        with mock.patch.dict(
            os.environ,
            {"RS_HOLDER_NATIVE_ADAPTER": "human-operated-native-adapter", "RS_HOLDER_SIGNER_CONFIG": str(config)},
        ):
            with self.assertRaises(HolderRefusal) as missing:
                holder.begin_human_operated_native_adapter()
            self.assertIn("was not invoked", str(missing.exception))
            with self.assertRaises(HolderRefusal) as selected:
                holder.begin_human_operated_native_adapter({"hardware": True, "origin": "human-operated-native-adapter"})
            self.assertIn("was not invoked", str(selected.exception))

    def test_caller_hardware_label_cannot_select_the_adapter(self) -> None:
        class Labeled(HumanOperatedNativeAdapter):
            hardware = True

            def public_key(self, role: str) -> str:
                return "labeled"

            def sign(self, role: str, message: bytes) -> str:
                return "labeled"

        td = tempfile.TemporaryDirectory(prefix="rsh-adapter-label-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        with self.assertRaises(HolderRefusal) as ctx:
            holder.begin_human_operated_native_adapter(Labeled(), policy="local")
        self.assertIn("caller hardware label", str(ctx.exception))

    def test_installed_protection_refuses_the_adapter_origin_string(self) -> None:
        binary, keys = self._keys()
        adapter = _AdapterSigner(binary, keys)
        td = tempfile.TemporaryDirectory(prefix="rsh-adapter-installed-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=True)
        with self.assertRaises(HolderRefusal) as enrolled:
            holder.begin_human_operated_native_adapter(adapter, policy="dual")
        self.assertIn("does not authorize a software key", str(enrolled.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())

    def test_adapter_enrolls_pairs_and_executes_for_local_companion_and_dual(self) -> None:
        binary, keys = self._keys()
        adapter = _AdapterSigner(binary, keys)
        for policy in ("local", "companion", "dual"):
            with self.subTest(policy=policy):
                self._execute_adapter(adapter, policy)

    def test_adapter_cancel_revoke_rotate_restart_downgrade_and_race(self) -> None:
        binary, keys = self._keys()
        adapter = _AdapterSigner(binary, keys)
        td = tempfile.TemporaryDirectory(prefix="rsh-adapter-flow-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        holder = self._holder(root, installed=False)
        enrolled = holder.begin_human_operated_native_adapter(adapter, policy="local")
        self.assertFalse(enrolled["biometric_invoked"])
        self.assertFalse(enrolled["e2_closed"])
        self.assertEqual(enrolled["origin"], "human-operated-native-adapter")
        holder.set_policy(holder.sign_with_human_operated_adapter(adapter, "set-policy", "local", "local"))
        ws, script = self._workspace(root / "ws")
        binding = self._binding(ws, script, "local")
        files = [(str(script.resolve()), sha256_file(script))]
        human = holder.sign_with_human_operated_adapter(
            adapter,
            "consume",
            "once",
            "local",
            self._consume_authorization(holder, "once", ws, script, binding),
        )
        holder.consume(nonce="once", policy="local", human=human, workspace=ws, files=files, binding=binding)
        restarted = ExecutionHolder(
            root / "state",
            allow_test_double=False,
            installed_protection=False,
            bootstrap_secret="ab" * 32,
            snapshot_base=root / "snaps",
            verifier_pin=production_verifier_pin(),
        )
        self.assertEqual(restarted.holder_id, holder.holder_id)
        cancelled = restarted.cancel_uncertain(
            "once", restarted.sign_with_human_operated_adapter(adapter, "cancel", "once", "local")
        )
        self.assertTrue(cancelled["cancelled"])
        race = restarted.sign_with_human_operated_adapter(
            adapter,
            "consume",
            "race",
            "local",
            self._consume_authorization(restarted, "race", ws, script, binding),
        )
        errors: list[BaseException] = []
        ok: list[bool] = []

        def _once() -> None:
            try:
                restarted.consume(
                    nonce="race", policy="local", human=race, workspace=ws, files=files, binding=binding
                )
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            else:
                ok.append(True)

        threads = [threading.Thread(target=_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(ok), 1)
        self.assertEqual(len(errors), 1)
        restarted.cancel_uncertain(
            "race", restarted.sign_with_human_operated_adapter(adapter, "cancel", "race", "local")
        )
        rotated = restarted.rotate_caller(
            restarted.sign_with_human_operated_adapter(adapter, "rotate", "app", "local")
        )
        self.assertEqual(rotated["key_generation"], 2)
        restarted.revoke_device(
            "mac-human",
            restarted.sign_with_human_operated_adapter(adapter, "revoke", "mac-human", "local"),
        )
        with self.assertRaises(HolderRefusal) as revoked:
            restarted.consume(
                nonce="after-revoke",
                policy="local",
                human=restarted.sign_with_human_operated_adapter(adapter, "consume", "after-revoke", "local"),
                workspace=ws,
                files=files,
                binding=binding,
            )
        self.assertIn("revoked", str(revoked.exception))
        covered = {"protocol": 0, "caller_id": "bootstrap", "body": {"op": "enroll"}}
        with self.assertRaises(HolderRefusal) as downgraded:
            handle_message(restarted, {**covered, "mac": "00"}, bootstrap_secret="ab" * 32)
        self.assertIn("downgrade", str(downgraded.exception))

    def _execute_adapter(self, adapter: _AdapterSigner, policy: str) -> None:
        td = tempfile.TemporaryDirectory(prefix=f"rsh-adapter-{policy}-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        holder = self._holder(root, installed=False)
        enrolled = holder.begin_human_operated_native_adapter(adapter, policy=policy)
        self.assertFalse(enrolled["biometric_invoked"])
        self.assertFalse(enrolled["e2_closed"])
        self.assertEqual(enrolled["origin"], "human-operated-native-adapter")
        for device_id in enrolled["devices"]:
            record = holder._devices()[device_id]
            self.assertEqual(record["provenance"]["origin"], "human-operated-native-adapter")
            self.assertFalse(record["provenance"]["boundary_double"])
            self.assertFalse(record["provenance"]["e2_closed"])
        holder.set_policy(holder.sign_with_human_operated_adapter(adapter, "set-policy", policy, policy))
        ws, script = self._workspace(root / "ws")
        binding = self._binding(ws, script, policy)
        files = [(str(script.resolve()), sha256_file(script))]
        human = holder.sign_with_human_operated_adapter(
            adapter,
            "consume",
            policy,
            policy,
            self._consume_authorization(holder, policy, ws, script, binding),
        )
        holder.consume(nonce=policy, policy=policy, human=human, workspace=ws, files=files, binding=binding)
        spent = json.loads((root / "state" / "spent.json").read_text(encoding="utf-8"))["nonces"][0]
        holder.execute(
            token=policy,
            human=holder.sign_with_human_operated_adapter(
                adapter,
                "execute",
                policy,
                policy,
                {
                    "payload_digest": spent["payload_digest"],
                    "launch_argv": list(binding["launch_argv"]),
                    "bounds": binding["bounds"],
                    "mutation_digest": spent["binding"]["mutation_digest"],
                    "attestation_class": "device-p256-not-hardware",
                },
            ),
        )
        self.assertEqual((ws.parent / "ran").read_text(encoding="utf-8"), "ran")

    def test_persisted_origin_string_is_not_production_trust(self) -> None:
        """Source trust-boundary bug. The shipped product is not installed, and no live exploit is claimed."""

        import time

        from tests.test_native_bridge_policies import _boot

        td = tempfile.TemporaryDirectory(prefix="rsh-origin-string-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        secret = "ab" * 32
        holder = ExecutionHolder(
            root / "state",
            allow_test_double=False,
            installed_protection=True,
            bootstrap_secret=secret,
            snapshot_base=root / "snaps",
            verifier_pin=_pin(),
        )
        holder.enroll("app", _boot(secret, "enroll", "app", "local"))
        for origin in ("human-operated-native-adapter", "secure-enclave-human-prompt"):
            with self.subTest(origin=origin):
                holder._write(
                    "devices.json",
                    {
                        "mac-human": {
                            "role": "mac",
                            "revoked": False,
                            "algorithm": "p256",
                            "public_key": "AQID",
                            "generation": holder.generation,
                            "hardware": False,
                            "provenance": {
                                "origin": origin,
                                "bridge": origin,
                                "not_hardware": True,
                                "boundary_double": False,
                                "policy": "local",
                                "role": "mac",
                                "generation": holder.generation,
                                "biometric_invoked": False,
                                "os_boundary_id": "caller-supplied",
                            },
                        }
                    },
                )
                human = {
                    "method": "local",
                    "purpose": "set-policy",
                    "policy": "local",
                    "subject": "local",
                    "devices": ["mac"],
                    "expires_at": int(time.time()) + 60,
                    "hardware": False,
                    "signatures": {"mac-human": "not-a-signature"},
                }
                with (
                    mock.patch("runspecimen.native_bridge.read_verifier_identity", return_value=_parsed()),
                    mock.patch("runspecimen.native_bridge.verifier_signature_strict", return_value=True),
                ):
                    with self.assertRaises(HolderRefusal) as ctx:
                        holder.set_policy(human)
                self.assertIn("does not authorize a software key", str(ctx.exception))
                self.assertNotIn("team identifier does not match", str(ctx.exception))

    def test_unpatched_os_boundary_does_not_prompt(self) -> None:
        from runspecimen.native_bridge import (
            OsBoundaryNotInvoked,
            UserInvokedSecureEnclaveControl,
            os_secure_enclave_create_key,
        )

        td = tempfile.TemporaryDirectory(prefix="rsh-os-unpatched-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        with self.assertRaises(OsBoundaryNotInvoked):
            os_secure_enclave_create_key("mac")
        with self.assertRaises(HolderRefusal) as ctx:
            holder.enroll_user_invoked_secure_enclave(UserInvokedSecureEnclaveControl("local"))
        self.assertIn("was not invoked", str(ctx.exception))
        with self.assertRaises(HolderRefusal) as missing_peer:
            holder.enroll_user_invoked_secure_enclave(UserInvokedSecureEnclaveControl("companion"))
        self.assertIn("requires a phone peer", str(missing_peer.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())
        for supplied in (
            {"origin": "human-operated-native-adapter"},
            "human-operated-native-adapter",
            True,
            HumanNativeSigner(),
            HumanOperatedNativeAdapter(),
        ):
            with self.subTest(supplied=type(supplied).__name__):
                with self.assertRaises(HolderRefusal):
                    holder.enroll_user_invoked_secure_enclave(supplied)

    def test_user_invoked_enrollment_rechecks_generation_after_the_wait(self) -> None:
        from runspecimen.native_bridge import OsBoundaryKey, UserInvokedSecureEnclaveControl

        td = tempfile.TemporaryDirectory(prefix="rsh-os-generation-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        started = holder.generation

        def fake(_role: str) -> OsBoundaryKey:
            return OsBoundaryKey("AQID", lambda _message: "c2ln")

        def wait() -> None:
            meta = holder._read("meta.json")
            meta["generation"] = started + 1
            holder._write("meta.json", meta)

        with mock.patch("runspecimen.native_bridge.os_secure_enclave_create_key", side_effect=fake):
            with self.assertRaises(HolderRefusal) as ctx:
                holder.enroll_user_invoked_secure_enclave(
                    UserInvokedSecureEnclaveControl("local"),
                    wait=wait,
                )
        self.assertIn("generation changed during the user wait", str(ctx.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())
        self.assertNotIn("mac-human", holder._devices())

    def test_user_invoked_enrollment_rechecks_revocation_after_the_wait(self) -> None:
        from runspecimen.native_bridge import PhonePeer, UserInvokedSecureEnclaveControl

        td = tempfile.TemporaryDirectory(prefix="rsh-os-revoke-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        peer = PhonePeer("AQIDBA==", lambda _message: "c2ln")

        def wait() -> None:
            holder._write(
                "devices.json",
                {"phone-human": {"role": "phone", "revoked": True, "public_key": "revoked-during-wait"}},
            )

        with self.assertRaises(HolderRefusal) as ctx:
            holder.enroll_user_invoked_secure_enclave(
                UserInvokedSecureEnclaveControl("companion"),
                wait=wait,
                phone_peer=peer,
            )
        self.assertIn("revoked during the user wait", str(ctx.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())
        self.assertEqual(holder._devices()["phone-human"]["public_key"], "revoked-during-wait")

    def test_os_boundary_mock_enrolls_local_and_paired_phone_without_a_prompt(self) -> None:
        """The mock replaces the OS call. It does not call SecureEnclave.P256.Signing.PrivateKey."""

        from runspecimen.native_bridge import OsBoundaryKey, PhonePeer, UserInvokedSecureEnclaveControl
        from tests.test_native_bridge_policies import _boot, _sign, _signer

        if sys.platform != "darwin":
            self.skipTest("phone peer comparison uses the Darwin verifier")
        binary, mac_public, mac_private = _signer(self)
        phone_out = subprocess.run(
            [str(binary), "key"], check=True, capture_output=True, text=True, timeout=10
        )
        phone_public, phone_private = phone_out.stdout.splitlines()
        self.assertNotEqual(mac_public, phone_public)
        mac_key = OsBoundaryKey(mac_public, lambda message: _sign(binary, mac_private, message))
        phone = PhonePeer(phone_public, lambda message: _sign(binary, phone_private, message))
        seen: list[str] = []

        def fake(role: str) -> OsBoundaryKey:
            seen.append(role)
            return mac_key

        td = tempfile.TemporaryDirectory(prefix="rsh-os-mock-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        secret = "ab" * 32
        holder = ExecutionHolder(
            root / "state",
            allow_test_double=False,
            installed_protection=True,
            bootstrap_secret=secret,
            snapshot_base=root / "snaps",
            verifier_pin=_pin(),
        )
        holder.enroll("app", _boot(secret, "enroll", "app", "local"))
        with mock.patch("runspecimen.native_bridge.os_secure_enclave_create_key", side_effect=fake):
            with (
                mock.patch("runspecimen.native_bridge.read_verifier_identity", return_value=_parsed()),
                mock.patch("runspecimen.native_bridge.verifier_signature_strict", return_value=True),
            ):
                with self.assertRaises(HolderRefusal) as refused:
                    holder.enroll_user_invoked_secure_enclave(
                        UserInvokedSecureEnclaveControl("dual"),
                        phone_peer=phone,
                    )
        self.assertEqual(seen, ["mac"])
        self.assertIn("does not authorize a software key", str(refused.exception))
        self.assertNotIn("team identifier does not match", str(refused.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())

    def _local_session(self, root: Path):
        from runspecimen.native_bridge import (
            OsBoundaryKey,
            UserInvokedSecureEnclaveControl,
            UserSessionKeyCustody,
        )
        from tests.test_native_bridge_policies import _sign, _signer

        binary, public, private = _signer(self)
        key = OsBoundaryKey(public, lambda message: _sign(binary, private, message))
        holder = self._holder(root, installed=False)
        custody = UserSessionKeyCustody()
        seen: list[str] = []

        def fake(role: str) -> OsBoundaryKey:
            seen.append(role)
            if role != "mac":
                raise AssertionError(role)
            return key

        with mock.patch("runspecimen.native_bridge.os_secure_enclave_create_key", side_effect=fake):
            enrolled = holder.enroll_user_invoked_secure_enclave(
                UserInvokedSecureEnclaveControl("local"),
                custody=custody,
            )
        return holder, custody, key, seen, enrolled, binary, private

    def test_ipc_binding_refuses_a_foreign_peer_and_an_origin_string(self) -> None:
        from runspecimen.execution_holder import dispatch
        from runspecimen.native_bridge import OsBoundaryKey, UserSessionKeyCustody

        td = tempfile.TemporaryDirectory(prefix="rsh-ipc-bind-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        custody = UserSessionKeyCustody()
        custody.keep("mac", OsBoundaryKey("AQID", lambda _message: "c2ln"))
        started = holder.generation
        foreign = {
            "op": "native-enroll",
            "policy": "local",
            "peer_binding": 0,
            "claimed_uid": 0,
            "generation": started,
            "public_keys": {"mac": "AQID"},
            "origin": "human-operated-native-adapter",
        }
        with self.assertRaises(HolderRefusal) as origin:
            holder.accept_native_ipc(foreign, peer_uid=os.getuid(), custody=custody, started=started)
        self.assertIn("does not authorize a software key", str(origin.exception))
        mismatched = {key: value for key, value in foreign.items() if key != "origin"}
        with self.assertRaises(HolderRefusal) as peer:
            holder.accept_native_ipc(mismatched, peer_uid=os.getuid(), custody=custody, started=started)
        self.assertIn("ipc binding does not match the socket peer", str(peer.exception))
        claimed = dict(mismatched)
        claimed["peer_binding"] = os.getuid()
        with self.assertRaises(HolderRefusal) as claimed_uid:
            holder.accept_native_ipc(claimed, peer_uid=os.getuid(), custody=custody, started=started)
        self.assertIn("ipc binding does not match the socket peer", str(claimed_uid.exception))
        configured = dict(claimed)
        configured.pop("claimed_uid")
        configured["config"] = {"signer": "software"}
        with self.assertRaises(HolderRefusal) as config:
            holder.accept_native_ipc(configured, peer_uid=os.getuid(), custody=custody, started=started)
        self.assertIn("does not authorize a software key", str(config.exception))
        with self.assertRaises(HolderRefusal) as wire:
            dispatch(holder, {"op": "native-enroll", "origin": "software"}, caller_id="app")
        self.assertIn("cannot be selected from wire input", str(wire.exception))
        with mock.patch.dict(os.environ, {"RS_NATIVE_SIGNER": "software"}):
            from runspecimen.native_bridge import UserInvokedSecureEnclaveControl

            with self.assertRaises(HolderRefusal) as env:
                holder.enroll_user_invoked_secure_enclave(UserInvokedSecureEnclaveControl("local"))
        self.assertIn("does not authorize a software key", str(env.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())

    def test_companion_requires_a_phone_peer_not_a_local_key(self) -> None:
        from runspecimen.native_bridge import (
            OsBoundaryKey,
            PhonePeer,
            UserInvokedSecureEnclaveControl,
        )

        td = tempfile.TemporaryDirectory(prefix="rsh-phone-peer-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        seen: list[str] = []

        def fake(role: str) -> OsBoundaryKey:
            seen.append(role)
            return OsBoundaryKey("LOCALKEY", lambda _message: "c2ln")

        with mock.patch("runspecimen.native_bridge.os_secure_enclave_create_key", side_effect=fake):
            holder.enroll_user_invoked_secure_enclave(UserInvokedSecureEnclaveControl("local"))
            with self.assertRaises(HolderRefusal) as same:
                holder.enroll_user_invoked_secure_enclave(
                    UserInvokedSecureEnclaveControl("companion"),
                    phone_peer=PhonePeer("LOCALKEY", lambda _message: "c2ln"),
                )
            with self.assertRaises(HolderRefusal) as dual:
                holder.enroll_user_invoked_secure_enclave(
                    UserInvokedSecureEnclaveControl("dual"),
                    phone_peer=PhonePeer("LOCALKEY", lambda _message: "c2ln"),
                )
        self.assertEqual(seen, ["mac", "mac"])
        self.assertIn("a local key is not a phone peer", str(same.exception))
        self.assertIn("a local key is not a phone peer", str(dual.exception))
        self.assertNotIn("phone-human", holder._devices())

    def test_stale_phone_challenge_is_refused(self) -> None:
        from runspecimen.native_bridge import PhonePeer, UserInvokedSecureEnclaveControl

        td = tempfile.TemporaryDirectory(prefix="rsh-stale-challenge-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        peer = PhonePeer("PHONEKEY", lambda _message: "c2ln")

        def wait() -> None:
            holder._phone_challenge["id"] = "stale"

        with self.assertRaises(HolderRefusal) as ctx:
            holder.enroll_user_invoked_secure_enclave(
                UserInvokedSecureEnclaveControl("companion"),
                wait=wait,
                phone_peer=peer,
            )
        self.assertIn("stale phone challenge", str(ctx.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())
        self.assertNotIn("phone-human", holder._devices())

    def test_session_custody_signs_after_holder_reload(self) -> None:
        holder, custody, _key, seen, enrolled, _binary, _private = self._local_session(Path(tempfile.mkdtemp(prefix="rsh-reload-")))
        self.addCleanup(shutil.rmtree, holder.root.parent, True)
        self.assertEqual(seen, ["mac"])
        self.assertTrue(enrolled["paired"])
        self.assertFalse(enrolled["e2_closed"])
        self.assertEqual(enrolled["access_policy"], "biometry-current-set-on-each-signature")
        proof = (holder.root / "os-boundary.json").read_text(encoding="utf-8")
        self.assertNotIn("c2ln", proof)
        self.assertNotIn(_private, proof)
        holder.set_policy(holder.sign_from_session(custody, "set-policy", "local", "local"))
        reloaded = ExecutionHolder(
            holder.root,
            allow_test_double=False,
            installed_protection=False,
            bootstrap_secret="ab" * 32,
            snapshot_base=holder.root.parent / "snaps",
            verifier_pin=production_verifier_pin(),
        )
        reloaded.attach_session(custody)
        again = reloaded.sign_from_session(custody, "set-policy", "local", "local")
        self.assertIn("mac-human", again["signatures"])
        with self.assertRaises(TypeError):
            reloaded.sign_from_session("AQID", "set-policy", "local", "local")

    def test_user_invoked_enrollment_cancel_rotation_and_revocation(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-custody-life-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        holder, custody, _key, _seen, _enrolled, _binary, _private = self._local_session(root / "holder")
        holder.set_policy(holder.sign_from_session(custody, "set-policy", "local", "local"))
        ws, script = self._workspace(root / "ws")
        binding = self._binding(ws, script, "local")
        files = [(str(script.resolve()), sha256_file(script))]
        human = holder.sign_from_session(
            custody,
            "consume",
            "life",
            "local",
            self._consume_authorization(holder, "life", ws, script, binding),
        )
        holder.consume(nonce="life", policy="local", human=human, workspace=ws, files=files, binding=binding)
        spent = json.loads((holder.root / "spent.json").read_text(encoding="utf-8"))["nonces"][0]
        holder.execute(
            token="life",
            human=holder.sign_from_session(
                custody,
                "execute",
                "life",
                "local",
                {
                    "payload_digest": spent["payload_digest"],
                    "launch_argv": list(binding["launch_argv"]),
                    "bounds": binding["bounds"],
                    "mutation_digest": spent["binding"]["mutation_digest"],
                    "attestation_class": "device-p256-not-hardware",
                },
            ),
        )
        self.assertEqual((ws.parent / "ran").read_text(encoding="utf-8"), "ran")
        holder.consume(
            nonce="cancel-me",
            policy="local",
            human=holder.sign_from_session(
                custody,
                "consume",
                "cancel-me",
                "local",
                self._consume_authorization(holder, "cancel-me", ws, script, binding),
            ),
            workspace=ws,
            files=files,
            binding=binding,
        )
        holder.cancel_uncertain("cancel-me", holder.sign_from_session(custody, "cancel", "cancel-me", "local"))
        rotated = holder.rotate_caller(holder.sign_from_session(custody, "rotate", "app", "local"))
        self.assertEqual(rotated["key_generation"], 2)
        after = holder.sign_from_session(custody, "consume", "after-revoke", "local")
        holder.revoke_device(
            "mac-human",
            holder.sign_from_session(custody, "revoke", "mac-human", "local"),
        )
        with self.assertRaises(HolderRefusal) as revoked:
            holder.consume(
                nonce="after-revoke",
                policy="local",
                human=after,
                workspace=ws,
                files=files,
                binding=binding,
            )
        self.assertIn("revoked", str(revoked.exception))

    def test_concurrent_consume_of_a_custody_signature(self) -> None:
        td = tempfile.TemporaryDirectory(prefix="rsh-custody-race-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        holder, custody, _key, _seen, _enrolled, _binary, _private = self._local_session(root / "holder")
        holder.set_policy(holder.sign_from_session(custody, "set-policy", "local", "local"))
        ws, script = self._workspace(root / "ws")
        binding = self._binding(ws, script, "local")
        files = [(str(script.resolve()), sha256_file(script))]
        race = holder.sign_from_session(
            custody,
            "consume",
            "race",
            "local",
            self._consume_authorization(holder, "race", ws, script, binding),
        )
        errors: list[BaseException] = []
        ok: list[bool] = []

        def _once() -> None:
            try:
                holder.consume(
                    nonce="race", policy="local", human=race, workspace=ws, files=files, binding=binding
                )
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            else:
                ok.append(True)

        threads = [threading.Thread(target=_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(ok), 1)
        self.assertEqual(len(errors), 1)

    def test_phone_peer_comparison_enrolls_companion(self) -> None:
        from runspecimen.native_bridge import PhonePeer, UserInvokedSecureEnclaveControl
        from tests.test_native_bridge_policies import _sign, _signer

        if sys.platform != "darwin":
            self.skipTest("phone peer comparison uses the Darwin verifier")
        binary, public, private = _signer(self)
        bad = PhonePeer(public, lambda _message: _sign(binary, private, b"not-the-challenge"))
        good = PhonePeer(public, lambda message: _sign(binary, private, message))
        td = tempfile.TemporaryDirectory(prefix="rsh-phone-compare-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        with self.assertRaises(HolderRefusal) as stale_sig:
            holder.enroll_user_invoked_secure_enclave(
                UserInvokedSecureEnclaveControl("companion"),
                phone_peer=bad,
            )
        self.assertIn("phone peer comparison failed", str(stale_sig.exception))
        enrolled = holder.enroll_user_invoked_secure_enclave(
            UserInvokedSecureEnclaveControl("companion"),
            phone_peer=good,
        )
        self.assertEqual(enrolled["devices"], ["phone-human"])
        self.assertTrue(enrolled["paired"])
        self.assertTrue(holder._devices()["phone-human"]["provenance"]["not_hardware"])
        self.assertFalse((holder.root / "os-boundary.json").read_text(encoding="utf-8").find(private) >= 0)

    def _observe_transport(self):
        import threading

        from tests.helpers import base_contract, write_contract
        from runspecimen.companion import ObservePhoneTransport, generate_pairing_token, start_companion

        td = tempfile.TemporaryDirectory(prefix="rsh-observe-")
        self.addCleanup(td.cleanup)
        workspace = Path(td.name)
        contract = write_contract(workspace, "contract.json", base_contract())
        token = generate_pairing_token()
        server, url, _meta = start_companion(
            workspace=workspace,
            contract_path=contract,
            pairing_token=token,
            host="127.0.0.1",
            port=0,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        return ObservePhoneTransport(url, token), server, token

    def test_observe_transport_challenge_bytes_match(self) -> None:
        import base64

        from runspecimen.native_bridge import UserInvokedSecureEnclaveControl
        from tests.test_native_bridge_policies import _sign, _signer

        if sys.platform != "darwin":
            self.skipTest("phone peer comparison uses the Darwin verifier")
        binary, public, private = _signer(self)
        transport, _server, _token = self._observe_transport()
        seen: dict[str, bytes] = {}

        def wait() -> None:
            fetched = transport.fetch_challenge()
            raw = base64.b64decode(fetched["challenge"])
            seen["bytes"] = raw
            seen["id"] = fetched["challenge_id"]
            transport.submit_signature(
                challenge_id=fetched["challenge_id"],
                challenge=raw,
                public_key=public,
                signature=_sign(binary, private, raw),
            )

        td = tempfile.TemporaryDirectory(prefix="rsh-observe-enroll-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        enrolled = holder.enroll_user_invoked_secure_enclave(
            UserInvokedSecureEnclaveControl("companion"),
            phone_transport=transport,
            wait=wait,
        )
        self.assertEqual(len(seen["bytes"]), 32)
        self.assertEqual(enrolled["devices"], ["phone-human"])
        self.assertEqual(holder._devices()["phone-human"]["public_key"], public)
        self.assertTrue(holder._devices()["phone-human"]["provenance"]["not_hardware"])
        self.assertNotIn("mac-human", holder._devices())

    def test_observe_transport_stale_challenge_is_refused(self) -> None:
        import base64

        from runspecimen.companion import ObserveTransportError
        from runspecimen.native_bridge import UserInvokedSecureEnclaveControl

        transport, _server, _token = self._observe_transport()

        def wait() -> None:
            fetched = transport.fetch_challenge()
            raw = base64.b64decode(fetched["challenge"])
            with self.assertRaises(ObserveTransportError) as stale:
                transport.submit_signature(
                    challenge_id="stale-id",
                    challenge=raw,
                    public_key="PHONE",
                    signature="c2ln",
                )
            self.assertIn("stale phone challenge", str(stale.exception))

        td = tempfile.TemporaryDirectory(prefix="rsh-observe-stale-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        with self.assertRaises(HolderRefusal) as ctx:
            holder.enroll_user_invoked_secure_enclave(
                UserInvokedSecureEnclaveControl("companion"),
                phone_transport=transport,
                wait=wait,
            )
        self.assertIn("stale phone challenge", str(ctx.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())

    def test_observe_transport_wrong_key_is_refused(self) -> None:
        import base64

        from runspecimen.native_bridge import UserInvokedSecureEnclaveControl
        from tests.test_native_bridge_policies import _sign, _signer

        if sys.platform != "darwin":
            self.skipTest("phone peer comparison uses the Darwin verifier")
        binary, public, private = _signer(self)
        other = subprocess.run([str(binary), "key"], check=True, capture_output=True, text=True, timeout=10)
        other_public = other.stdout.splitlines()[0]
        self.assertNotEqual(public, other_public)
        transport, _server, _token = self._observe_transport()

        def wait() -> None:
            fetched = transport.fetch_challenge()
            raw = base64.b64decode(fetched["challenge"])
            transport.submit_signature(
                challenge_id=fetched["challenge_id"],
                challenge=raw,
                public_key=other_public,
                signature=_sign(binary, private, raw),
            )

        td = tempfile.TemporaryDirectory(prefix="rsh-observe-wrong-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        with self.assertRaises(HolderRefusal) as ctx:
            holder.enroll_user_invoked_secure_enclave(
                UserInvokedSecureEnclaveControl("companion"),
                phone_transport=transport,
                wait=wait,
            )
        self.assertIn("phone peer comparison failed", str(ctx.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())

    def test_observe_reload_rejects_the_old_challenge(self) -> None:
        import base64

        from runspecimen.companion import ObserveTransportError
        from runspecimen.native_bridge import UserInvokedSecureEnclaveControl

        transport, server, token = self._observe_transport()
        first = {"id": "", "raw": b""}

        def capture() -> None:
            fetched = transport.fetch_challenge()
            first["id"] = fetched["challenge_id"]
            first["raw"] = base64.b64decode(fetched["challenge"])

        td = tempfile.TemporaryDirectory(prefix="rsh-observe-reload-")
        self.addCleanup(td.cleanup)
        holder = self._holder(Path(td.name), installed=False)
        with self.assertRaises(HolderRefusal):
            holder.enroll_user_invoked_secure_enclave(
                UserInvokedSecureEnclaveControl("companion"),
                phone_transport=transport,
                wait=capture,
            )
        self.assertTrue(first["raw"])
        transport.publish_challenge(
            challenge_id="reloaded",
            generation=holder.generation,
            challenge=b"reloaded-challenge-bytes-32b!!",
            holder_id=holder.holder_id,
        )
        with self.assertRaises(ObserveTransportError) as stale:
            transport.submit_signature(
                challenge_id=first["id"],
                challenge=first["raw"],
                public_key="PHONE",
                signature="c2ln",
            )
        self.assertIn("stale phone challenge", str(stale.exception))
        server.shutdown()
        server.server_close()
        restarted, _token = self._observe_transport()[0], None
        with self.assertRaises(ObserveTransportError) as restarted_error:
            restarted.submit_signature(
                challenge_id=first["id"],
                challenge=first["raw"],
                public_key="PHONE",
                signature="c2ln",
            )
        self.assertIn("stale phone challenge", str(restarted_error.exception))

    def test_observe_transport_software_double_is_refused_when_the_pin_matches(self) -> None:
        import base64

        from runspecimen.execution_holder import ExecutionHolder
        from runspecimen.native_bridge import UserInvokedSecureEnclaveControl
        from tests.test_native_bridge_policies import _boot, _sign, _signer

        if sys.platform != "darwin":
            self.skipTest("phone peer comparison uses the Darwin verifier")
        binary, public, private = _signer(self)
        transport, _server, _token = self._observe_transport()

        def wait() -> None:
            fetched = transport.fetch_challenge()
            raw = base64.b64decode(fetched["challenge"])
            transport.submit_signature(
                challenge_id=fetched["challenge_id"],
                challenge=raw,
                public_key=public,
                signature=_sign(binary, private, raw),
            )

        td = tempfile.TemporaryDirectory(prefix="rsh-observe-installed-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        secret = "ab" * 32
        holder = ExecutionHolder(
            root / "state",
            allow_test_double=False,
            installed_protection=True,
            bootstrap_secret=secret,
            snapshot_base=root / "snaps",
            verifier_pin=_pin(),
        )
        holder.enroll("app", _boot(secret, "enroll", "app", "local"))
        with (
            mock.patch("runspecimen.native_bridge.read_verifier_identity", return_value=_parsed()),
            mock.patch("runspecimen.native_bridge.verifier_signature_strict", return_value=True),
        ):
            with self.assertRaises(HolderRefusal) as refused:
                holder.enroll_user_invoked_secure_enclave(
                    UserInvokedSecureEnclaveControl("companion"),
                    phone_transport=transport,
                    wait=wait,
                )
        self.assertIn("does not authorize a software key", str(refused.exception))
        self.assertNotIn("team identifier does not match", str(refused.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())

    def _ipc_client(self, root: Path):
        from runspecimen.holder_adapter import AdapterServer, HolderClient
        from tests.test_execution_holder import _human

        secret = "ab" * 32
        server = AdapterServer(root, bootstrap_secret=secret)
        server.start()
        self.addCleanup(server.stop)

        def human_for(purpose: str, subject: str) -> dict:
            policy = subject if purpose == "set-policy" else "local"
            return _human(purpose, subject, policy=policy)

        boot = HolderClient(server.socket_path, "bootstrap", secret, human_for)
        enrolled = boot.call({"op": "enroll", "new_caller_id": "app", "human": human_for("enroll", "app")})
        client = HolderClient(server.socket_path, "app", enrolled["caller_secret"], human_for)
        return server, client

    def test_unpatched_os_call_is_not_the_ipc_enrollment_path(self) -> None:
        from runspecimen.native_bridge import UserSessionKeyCustody, enroll_over_authenticated_ipc

        td = tempfile.TemporaryDirectory(prefix="rsh-ipc-unpatched-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        _server, client = self._ipc_client(root)
        with self.assertRaises(Exception) as ctx:
            enroll_over_authenticated_ipc(
                client,
                role="mac",
                custody=UserSessionKeyCustody(),
                store=root / "handles",
            )
        self.assertIn("was not invoked", str(ctx.exception))
        with self.assertRaises(HolderRefusal) as wire:
            client.call({"op": "native-enroll", "policy": "local"})
        self.assertIn("cannot be selected from wire input", str(wire.exception))
        source = Path("apps/holder/Sources/RunSpecimenHolderApp/main.swift").read_text(encoding="utf-8")
        client_source = Path("apps/holder/Sources/HolderSocket/HolderSocketClient.swift").read_text(encoding="utf-8")
        self.assertNotIn('return "enrolled mac-human"', source)
        self.assertIn("issue-device-challenge", client_source)
        self.assertIn("AF_UNIX", client_source)
        self.assertIn("caller_id", client_source)
        session = Path(
            "apps/ios/Sources/RunSpecimenObserve/Services/CompanionSession.swift"
        ).read_text(encoding="utf-8")
        self.assertIn("fetchPhonePeerChallenge()", session)
        self.assertIn("submitPhonePeerSignature(", session)
        view = Path("apps/ios/Sources/RunSpecimenObserve/Views/StatusObserveView.swift").read_text(encoding="utf-8")
        self.assertIn("Sign phone peer challenge", view)
        self.assertIn("signPhonePeerChallenge()", view)

    def test_local_ipc_enrollment_reloads_and_runs(self) -> None:
        import base64

        from runspecimen.native_bridge import (
            OsBoundaryKey,
            UserSessionKeyCustody,
            enroll_over_authenticated_ipc,
            reload_session_key,
        )
        from tests.test_native_bridge_policies import _sign, _signer

        if sys.platform != "darwin":
            self.skipTest("P-256 verification uses the Darwin verifier")
        binary, public, private = _signer(self)
        created: dict[str, OsBoundaryKey] = {}

        def create(role: str) -> OsBoundaryKey:
            key = OsBoundaryKey(public, lambda message: _sign(binary, private, message))
            created[role] = key
            return key

        def reload(role: str, handle: str, public_key: str) -> OsBoundaryKey:
            self.assertTrue(handle)
            self.assertEqual(public_key, public)
            return created[role]

        td = tempfile.TemporaryDirectory(prefix="rsh-ipc-local-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        server, client = self._ipc_client(root)
        store = root / "handles"
        with (
            mock.patch("runspecimen.native_bridge.os_secure_enclave_create_key", side_effect=create),
            mock.patch("runspecimen.native_bridge.os_secure_enclave_reload_key", side_effect=reload),
        ):
            enrolled = enroll_over_authenticated_ipc(
                client,
                role="mac",
                custody=UserSessionKeyCustody(),
                store=store,
            )
            self.assertTrue(enrolled["verified"])
            self.assertTrue(enrolled["consumed"])
            self.assertFalse(enrolled["hardware"])
            self.assertTrue(enrolled["not_hardware"])
            restarted = UserSessionKeyCustody()
            reload_session_key(store, "mac", restarted)
            signed = server.holder.sign_from_session(restarted, "set-policy", "local", "local")
        self.assertIn("mac-human", signed["signatures"])
        spent_nonce = json.loads((server.holder.root / "device-nonces.json").read_text(encoding="utf-8"))["nonces"][0]
        with self.assertRaises(HolderRefusal) as replay:
            client.call(
                {
                    "op": "submit-device-signature",
                    "role": "mac",
                    "public_key": public,
                    "signature": "AAAA",
                    "holder_id": "x",
                    "generation": 1,
                    "expiry": 1,
                    "nonce": spent_nonce,
                    "challenge": base64.b64encode(b"replay").decode("ascii"),
                }
            )
        self.assertIn("replayed device challenge", str(replay.exception))
        ws, script = self._workspace(root / "ws")
        binding = self._binding(ws, script, "local")
        files = [(str(script.resolve()), sha256_file(script))]
        server.holder.set_policy(signed)
        human = server.holder.sign_from_session(
            restarted,
            "consume",
            "ipc-run",
            "local",
            self._consume_authorization(server.holder, "ipc-run", ws, script, binding),
        )
        server.holder.consume(
            nonce="ipc-run",
            policy="local",
            human=human,
            workspace=ws,
            files=files,
            binding=binding,
        )
        spent = json.loads((server.holder.root / "spent.json").read_text(encoding="utf-8"))["nonces"][0]
        server.holder.execute(
            token="ipc-run",
            human=server.holder.sign_from_session(
                restarted,
                "execute",
                "ipc-run",
                "local",
                {
                    "payload_digest": spent["payload_digest"],
                    "launch_argv": list(binding["launch_argv"]),
                    "bounds": binding["bounds"],
                    "mutation_digest": spent["binding"]["mutation_digest"],
                    "attestation_class": "device-p256-not-hardware",
                },
            ),
        )
        self.assertEqual((ws.parent / "ran").read_text(encoding="utf-8"), "ran")

    def test_device_challenge_rejects_garbage_tamper_cancel_and_restart(self) -> None:
        import base64

        from runspecimen.holder_adapter import AdapterServer, HolderClient

        td = tempfile.TemporaryDirectory(prefix="rsh-ipc-refuse-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        server, client = self._ipc_client(root)
        issued = client.call({"op": "issue-device-challenge", "role": "phone"})
        self.assertFalse(issued["enrolled"])
        self.assertFalse(issued["verified"])
        garbage = {
            "op": "submit-device-signature",
            "role": "phone",
            "public_key": "AAAA",
            "signature": "BBBB",
            "holder_id": issued["holder_id"],
            "generation": issued["generation"],
            "expiry": issued["expiry"],
            "nonce": issued["nonce"],
            "challenge": issued["challenge"],
        }
        with self.assertRaises(HolderRefusal) as bad:
            client.call(garbage)
        self.assertIn("device signature verification failed", str(bad.exception))
        tampered = dict(garbage)
        tampered["challenge"] = base64.b64encode(b"tampered-challenge-bytes-32b!!!!").decode("ascii")
        with self.assertRaises(HolderRefusal) as changed:
            client.call(tampered)
        self.assertIn("device challenge bytes do not match", str(changed.exception))
        client.call({"op": "cancel-device-challenge", "role": "phone"})
        with self.assertRaises(HolderRefusal) as cancelled:
            client.call(garbage)
        self.assertIn("stale device challenge", str(cancelled.exception))
        fresh = client.call({"op": "issue-device-challenge", "role": "phone"})
        secret = client.caller_secret
        human_for = client.human_for
        server.stop()
        restarted = AdapterServer(root, bootstrap_secret="ab" * 32)
        restarted.start()
        self.addCleanup(restarted.stop)
        again = HolderClient(restarted.socket_path, "app", secret, human_for)
        stale = {
            "op": "submit-device-signature",
            "role": "phone",
            "public_key": "AAAA",
            "signature": "BBBB",
            "holder_id": fresh["holder_id"],
            "generation": fresh["generation"],
            "expiry": fresh["expiry"],
            "nonce": fresh["nonce"],
            "challenge": fresh["challenge"],
        }
        with self.assertRaises(HolderRefusal) as after_restart:
            again.call(stale)
        self.assertIn("stale device challenge", str(after_restart.exception))

    def test_phone_ipc_rejects_wrong_key_and_installed_software_double(self) -> None:
        import base64

        from tests.test_native_bridge_policies import _boot, _sign, _signer

        if sys.platform != "darwin":
            self.skipTest("P-256 verification uses the Darwin verifier")
        binary, public, private = _signer(self)
        other = subprocess.run([str(binary), "key"], check=True, capture_output=True, text=True, timeout=10)
        other_public = other.stdout.splitlines()[0]
        td = tempfile.TemporaryDirectory(prefix="rsh-ipc-phone-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        _server, client = self._ipc_client(root)
        issued = client.call({"op": "issue-device-challenge", "role": "phone"})
        signature = _sign(binary, private, base64.b64decode(issued["bound"]))
        with self.assertRaises(HolderRefusal) as mismatch:
            client.call(
                {
                    "op": "submit-device-signature",
                    "role": "phone",
                    "public_key": other_public,
                    "signature": signature,
                    "holder_id": issued["holder_id"],
                    "generation": issued["generation"],
                    "expiry": issued["expiry"],
                    "nonce": issued["nonce"],
                    "challenge": issued["challenge"],
                }
            )
        self.assertIn("device signature verification failed", str(mismatch.exception))
        holder = ExecutionHolder(
            root / "installed",
            allow_test_double=False,
            installed_protection=True,
            bootstrap_secret="cd" * 32,
            snapshot_base=root / "installed-snaps",
            verifier_pin=_pin(),
        )
        holder.enroll("app", _boot("cd" * 32, "enroll", "app", "local"))
        issued_direct = holder.issue_device_challenge("phone", peer_uid=os.getuid())
        good = _sign(binary, private, base64.b64decode(issued_direct["bound"]))
        body = {
            "role": "phone",
            "public_key": public,
            "signature": good,
            "holder_id": issued_direct["holder_id"],
            "generation": issued_direct["generation"],
            "expiry": issued_direct["expiry"],
            "nonce": issued_direct["nonce"],
            "challenge": issued_direct["challenge"],
        }
        with (
            mock.patch("runspecimen.native_bridge.read_verifier_identity", return_value=_parsed()),
            mock.patch("runspecimen.native_bridge.verifier_signature_strict", return_value=True),
        ):
            with self.assertRaises(HolderRefusal) as refused:
                holder.submit_device_signature(body, peer_uid=os.getuid())
        self.assertIn("does not authorize a software key", str(refused.exception))
        self.assertFalse((holder.root / "os-boundary.json").exists())
        self.assertNotIn("phone-human", holder._devices())

    def test_published_mailbox_signature_is_verified_and_consumed(self) -> None:
        import base64

        from runspecimen.companion import ObservePhoneTransport
        from tests.test_native_bridge_policies import _sign, _signer

        if sys.platform != "darwin":
            self.skipTest("P-256 verification uses the Darwin verifier")
        binary, public, private = _signer(self)
        td = tempfile.TemporaryDirectory(prefix="rsh-ipc-mail-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        _server, client = self._ipc_client(root)
        transport, _companion, _token = self._observe_transport()
        issued = client.call({"op": "issue-device-challenge", "role": "phone"})
        transport.publish_challenge(
            challenge_id=issued["nonce"],
            generation=issued["generation"],
            challenge=base64.b64decode(issued["challenge"]),
            holder_id=issued["holder_id"],
            expiry=issued["expiry"],
        )
        fetched = transport.fetch_challenge()
        self.assertEqual(base64.b64decode(fetched["challenge"]), base64.b64decode(issued["challenge"]))
        self.assertEqual(fetched["expiry"], issued["expiry"])
        signature = _sign(binary, private, base64.b64decode(issued["bound"]))
        transport.submit_signature(
            challenge_id=issued["nonce"],
            challenge=base64.b64decode(issued["challenge"]),
            public_key=public,
            signature=signature,
        )
        collected = transport.collect_signature()
        self.assertEqual(collected["challenge_bytes"], base64.b64decode(issued["challenge"]))
        self.assertFalse(collected["verified"])
        enrolled = client.call(
            {
                "op": "submit-device-signature",
                "role": "phone",
                "public_key": collected["public_key"],
                "signature": collected["signature"],
                "holder_id": issued["holder_id"],
                "generation": issued["generation"],
                "expiry": issued["expiry"],
                "nonce": issued["nonce"],
                "challenge": issued["challenge"],
            }
        )
        self.assertTrue(enrolled["verified"])
        self.assertTrue(enrolled["consumed"])
        self.assertFalse(enrolled["hardware"])
        with self.assertRaises(HolderRefusal) as replay:
            client.call(
                {
                    "op": "submit-device-signature",
                    "role": "phone",
                    "public_key": public,
                    "signature": signature,
                    "holder_id": issued["holder_id"],
                    "generation": issued["generation"],
                    "expiry": issued["expiry"],
                    "nonce": issued["nonce"],
                    "challenge": issued["challenge"],
                }
            )
        self.assertIn("replayed device challenge", str(replay.exception))

    def test_exact_run_signature_authorizes_one_nonce_and_refuses_software(self) -> None:
        import base64

        from runspecimen.execution_holder import HolderRefusal
        from runspecimen.native_bridge import (
            OsBoundaryKey,
            UserSessionKeyCustody,
            enroll_over_authenticated_ipc,
            reload_session_key,
        )
        from tests.test_native_bridge_policies import _sign, _signer

        if sys.platform != "darwin":
            self.skipTest("P-256 verification uses the Darwin verifier")
        binary, public, private = _signer(self)

        def create(role: str) -> OsBoundaryKey:
            return OsBoundaryKey(public, lambda message: _sign(binary, private, message))

        td = tempfile.TemporaryDirectory(prefix="rsh-exact-run-")
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        server, client = self._ipc_client(root)
        with mock.patch("runspecimen.native_bridge.os_secure_enclave_create_key", side_effect=create):
            enrolled = enroll_over_authenticated_ipc(
                client,
                role="mac",
                custody=UserSessionKeyCustody(),
                store=root / "handles",
            )
        self.assertTrue(enrolled["verified"])
        self.assertFalse(enrolled["hardware"])
        payload = "ab" * 32
        launch = ["/usr/bin/true"]
        issued = client.call(
            {
                "op": "issue-exact-run",
                "payload_digest": payload,
                "launch_argv": launch,
                "request_id": "req-exact-1",
            }
        )
        self.assertEqual(issued["request_id"], "req-exact-1")
        self.assertFalse(issued["authorized"])
        signature = _sign(binary, private, base64.b64decode(issued["bound"]))
        with self.assertRaises(HolderRefusal) as labeled:
            client.call(
                {
                    "op": "authorize-exact-run",
                    "payload_digest": payload,
                    "launch_argv": launch,
                    "nonce": issued["nonce"],
                    "public_key": public,
                    "signature": signature,
                    "hardware": True,
                    "origin": "os-secure-enclave-boundary",
                }
            )
        self.assertIn("caller authority labels", str(labeled.exception))
        authorized = client.call(
            {
                "op": "authorize-exact-run",
                "payload_digest": payload,
                "launch_argv": launch,
                "nonce": issued["nonce"],
                "public_key": public,
                "signature": signature,
            }
        )
        self.assertTrue(authorized["authorized"])
        self.assertTrue(authorized["consumed"])
        self.assertFalse(authorized["hardware"])
        self.assertTrue(authorized["not_hardware"])
        self.assertFalse(authorized["e2_closed"])
        ws, script = self._workspace(root / "ws")
        binding = self._binding(ws, script, "local")
        custody = UserSessionKeyCustody()
        with mock.patch(
            "runspecimen.native_bridge.os_secure_enclave_reload_key",
            return_value=OsBoundaryKey(public, lambda message: _sign(binary, private, message)),
        ):
            reload_session_key(root / "handles", "mac", custody)
        server.holder.set_policy(server.holder.sign_from_session(custody, "set-policy", "local", "local"))
        with self.assertRaises(HolderRefusal) as second:
            server.holder.consume(
                nonce=issued["nonce"],
                policy="local",
                human={"method": "not-a-signature"},
                workspace=ws,
                files=[(str(script.resolve()), "00")],
                binding=binding,
            )
        self.assertIn("nonce was already consumed", str(second.exception))
        installed_root = root / "installed-state"
        for dirpath, _dirnames, filenames in os.walk(server.holder.root):
            os.chmod(dirpath, 0o700)
            for name in filenames:
                os.chmod(Path(dirpath) / name, 0o600)
        shutil.copytree(server.holder.root, installed_root)
        meta_path = installed_root / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["installed_protection"] = True
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        from runspecimen.execution_holder import ExecutionHolder

        installed = ExecutionHolder(
            installed_root,
            allow_test_double=False,
            installed_protection=True,
            bootstrap_secret="ab" * 32,
            snapshot_base=root / "installed-snaps",
            verifier_pin=_pin(),
        )
        again = installed.issue_exact_run(
            {"payload_digest": payload, "launch_argv": launch},
            peer_uid=os.getuid(),
        )
        again_signature = _sign(binary, private, base64.b64decode(again["bound"]))
        with (
            mock.patch("runspecimen.native_bridge.read_verifier_identity", return_value=_parsed()),
            mock.patch("runspecimen.native_bridge.verifier_signature_strict", return_value=True),
        ):
            with self.assertRaises(HolderRefusal) as software:
                installed.authorize_exact_run(
                    {
                        "payload_digest": payload,
                        "launch_argv": launch,
                        "nonce": again["nonce"],
                        "public_key": public,
                        "signature": again_signature,
                    },
                    peer_uid=os.getuid(),
                )
        self.assertIn("does not authorize a software key", str(software.exception))
        self.assertNotIn("team identifier does not match", str(software.exception))
