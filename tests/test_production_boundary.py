"""Production control flow with an injected boundary double. Not hardware.

The shipped pin stays unset. TESTTEAMID is a fixture, not an authorized identity.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from runspecimen.execution_holder import ExecutionHolder, HolderRefusal, handle_message, seal
from runspecimen.native_bridge import (
    BOUNDARY_DOUBLE,
    PRODUCTION_BRIDGE,
    TrustedNativeBoundary,
    VerifierPin,
    assemble_developer_id_artifact,
    identity_matches,
    native_signers_connected,
    parse_codesign_identity,
    platform_verifier_report,
    production_verifier_pin,
    refresh_verifier_provenance,
    require_verifier_identity,
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
        signed = subprocess.run(
            [
                "/usr/bin/codesign",
                "--force",
                "--sign",
                "Developer ID Application: YAHOR DARASHKEVICH (UN6KF8636A)",
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
        self.assertEqual(body["signed"], "codesign")
        self.assertEqual(body["sha256"], hashlib.sha256(placed.read_bytes()).hexdigest())
        self.assertNotIn("Developer ID", json.dumps(body))
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
