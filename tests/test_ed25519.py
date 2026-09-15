"""Tests for optional Ed25519 public-key receipt signatures."""

from __future__ import annotations

import json
import os
import signal
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import SRC, RunSpecimenTestCase, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.errors import SigningError
from runspecimen.pubkey import require_ed25519

try:
    require_ed25519()
    HAS_NACL = True
except SigningError:
    HAS_NACL = False


def _sample_cert() -> dict:
    from runspecimen.hashutil import canonical_json_bytes, sha256_bytes

    body = {
        "approval_expires_at_unix": 1,
        "campaign_id": "c",
        "contract_hash": "a" * 64,
        "event_head": "b" * 64,
        "exit_code": 0,
        "issued_at": "2026-01-01T00:00:00Z",
        "output_digests": {},
        "run_id": "r",
        "run_result": "completed",
        "runtime": {"runtime_id": "c" * 64},
        "schema_version": 1,
        "source_hash": "d" * 64,
    }
    return {"certificate_id": sha256_bytes(canonical_json_bytes(body)), **body}


class TestEd25519OptionalDependency(unittest.TestCase):
    def test_extra_install_hint_is_documented(self) -> None:
        src = (Path(__file__).resolve().parents[1] / "src/runspecimen/pubkey.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("runspecimen[ed25519]", src)
        if not HAS_NACL:
            with self.assertRaises(SigningError) as ctx:
                require_ed25519()
            self.assertIn("runspecimen[ed25519]", str(ctx.exception))


class TestPackagingOptionalExtras(unittest.TestCase):
    """Release metadata must stay dependency-free except vetted optional extras."""

    def test_pyproject_declares_only_vetted_optional_extras(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('ed25519 = ["pynacl>=1.5.0"]', text)
        self.assertIn('signing = ["pynacl>=1.5.0"]', text)
        self.assertIn("dependencies = []", text)

    def test_release_check_allows_vetted_optional_requires_dist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "scripts"))
        import release_check

        good = (
            "Metadata-Version: 2.1\n"
            "Name: runspecimen\n"
            "Version: 0.2.0rc10\n"
            'Requires-Dist: pynacl>=1.5.0; extra == "ed25519"\n'
            'Requires-Dist: pynacl>=1.5.0; extra == "signing"\n'
            "Provides-Extra: ed25519\n"
            "Provides-Extra: signing\n"
        )
        release_check.validate_requires_dist_metadata(good)

    def test_release_check_rejects_hard_dependency(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "scripts"))
        import release_check

        with self.assertRaises(SystemExit) as ctx:
            release_check.validate_requires_dist_metadata(
                "Name: runspecimen\nRequires-Dist: requests>=2.0\n"
            )
        self.assertIn("hard dependency", str(ctx.exception))

    def test_release_check_rejects_unvetted_extra(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "scripts"))
        import release_check

        with self.assertRaises(SystemExit) as ctx:
            release_check.validate_requires_dist_metadata(
                'Requires-Dist: cryptography>=42; extra == "crypto"\n'
            )
        self.assertIn("unvetted", str(ctx.exception).lower())


@unittest.skipUnless(HAS_NACL, "PyNaCl not installed; pip install 'runspecimen[ed25519]'")
class TestEd25519Crypto(unittest.TestCase):
    def test_sign_verify_roundtrip_and_wrong_key(self) -> None:
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            sign_certificate_ed25519,
            verify_certificate_ed25519,
        )

        cert = _sample_cert()
        pair = Ed25519KeyPair.generate(key_id="edtest")
        signed = sign_certificate_ed25519(cert, pair)
        ok = verify_certificate_ed25519(signed, public_key=pair.public_key)
        self.assertTrue(ok.ok)
        self.assertTrue(ok.trusted)
        self.assertTrue(ok.signature_consistent)

        other = Ed25519KeyPair.generate(key_id="other")
        bad = verify_certificate_ed25519(signed, public_key=other.public_key)
        self.assertFalse(bad.ok)
        self.assertFalse(bad.trusted)

    def test_embedded_key_only_is_consistency_not_trusted(self) -> None:
        """Forged receipt: attacker embeds their own key — must not be ok/trusted."""
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            sign_certificate_ed25519,
            verify_certificate_ed25519,
        )

        attacker = Ed25519KeyPair.generate(key_id="attacker")
        signed = sign_certificate_ed25519(_sample_cert(), attacker)
        result = verify_certificate_ed25519(signed, public_key=None)
        self.assertTrue(result.signature_consistent)
        self.assertFalse(result.trusted)
        self.assertFalse(result.ok)
        self.assertIn("not trusted", result.message.lower())

    def test_forged_receipt_fails_against_victim_trust_anchor(self) -> None:
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            sign_certificate_ed25519,
            verify_certificate_ed25519,
        )

        victim = Ed25519KeyPair.generate(key_id="victim")
        attacker = Ed25519KeyPair.generate(key_id="attacker")
        forged = sign_certificate_ed25519(_sample_cert(), attacker)
        result = verify_certificate_ed25519(forged, public_key=victim.public_key)
        self.assertFalse(result.ok)
        self.assertFalse(result.trusted)
        self.assertFalse(result.public_key_match)

    def test_tamper_fails(self) -> None:
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            Ed25519SignedCertificate,
            sign_certificate_ed25519,
            verify_certificate_ed25519,
        )

        pair = Ed25519KeyPair.generate(key_id="edtest2")
        signed = sign_certificate_ed25519(_sample_cert(), pair)
        tampered_cert = dict(signed.certificate)
        tampered_cert["source_hash"] = "f" * 64
        tampered = Ed25519SignedCertificate(
            certificate=tampered_cert,
            signature=signed.signature,
            key_id=signed.key_id,
            algorithm=signed.algorithm,
            public_key=signed.public_key,
        )
        result = verify_certificate_ed25519(tampered, public_key=pair.public_key)
        self.assertFalse(result.ok)

    def test_hmac_blob_rejected_by_ed25519_path(self) -> None:
        from runspecimen.pubkey import verify_rejects_hmac_blob

        with self.assertRaises(SigningError) as ctx:
            verify_rejects_hmac_blob({"algorithm": "hmac-sha256-v1", "signature": "00"})
        self.assertIn("HMAC", str(ctx.exception))


@unittest.skipUnless(HAS_NACL, "PyNaCl not installed")
class TestEd25519Persistence(RunSpecimenTestCase):
    def test_save_load_and_list(self) -> None:
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            list_ed25519_key_ids,
            load_ed25519_keypair,
            save_ed25519_keypair,
        )

        pair = Ed25519KeyPair.generate(key_id="persist1")
        priv, pub = save_ed25519_keypair(self.ws, pair)
        self.assertEqual(stat.S_IMODE(priv.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(pub.stat().st_mode), 0o644)
        loaded = load_ed25519_keypair(self.ws, "persist1")
        self.assertEqual(loaded.public_hex(), pair.public_hex())
        self.assertIn("persist1", list_ed25519_key_ids(self.ws))

    def test_private_key_created_with_0600_not_chmod_after(self) -> None:
        from runspecimen.pubkey import Ed25519KeyPair, save_ed25519_keypair

        pair = Ed25519KeyPair.generate(key_id="mode0600")
        modes: list[int] = []

        real_open = os.open

        def tracking_open(path, flags, mode=0o777, *args, **kwargs):  # type: ignore[no-untyped-def]
            # Ignore the keys.op.lock / journal opens used by the lock helper.
            if str(path).endswith("keys.op.lock") or ".ed25519.rotate.journal" in str(path):
                return real_open(path, flags, mode, *args, **kwargs)
            modes.append(mode)
            return real_open(path, flags, mode, *args, **kwargs)

        with mock.patch("os.open", tracking_open):
            priv, _pub = save_ed25519_keypair(self.ws, pair)
        self.assertTrue(any(m == 0o600 for m in modes), f"expected 0600 create, got {modes}")
        self.assertEqual(stat.S_IMODE(priv.stat().st_mode), 0o600)

    def test_export_public_key_does_not_read_private_seed(self) -> None:
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            export_ed25519_public_key,
            private_key_path,
            save_ed25519_keypair,
        )

        pair = Ed25519KeyPair.generate(key_id="export1")
        save_ed25519_keypair(self.ws, pair)
        priv = private_key_path(self.ws, "export1")
        out = self.ws / "exported.pub"
        priv_resolved = str(priv.resolve())

        real_open = os.open

        def guarded_open(path, flags, *args, **kwargs):  # type: ignore[no-untyped-def]
            resolved = str(Path(path).resolve())
            if resolved.endswith("keys.op.lock") or ".ed25519.rotate.journal" in resolved:
                return real_open(path, flags, *args, **kwargs)
            if resolved == priv_resolved:
                raise AssertionError("export must not open the private key file")
            return real_open(path, flags, *args, **kwargs)

        with mock.patch("os.open", guarded_open):
            export_ed25519_public_key(self.ws, "export1", out)
        self.assertEqual(out.read_text(encoding="utf-8").strip(), pair.public_hex())

    def test_refuse_symlink_private_key_path_on_save(self) -> None:
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            private_key_path,
            save_ed25519_keypair,
        )

        pair = Ed25519KeyPair.generate(key_id="symattack")
        keys = self.ws / ".runspecimen" / "keys"
        keys.mkdir(parents=True)
        target = self.ws / "escape.secret"
        target.write_text("victim\n", encoding="utf-8")
        priv = private_key_path(self.ws, "symattack")
        priv.symlink_to(target)
        with self.assertRaises(SigningError) as ctx:
            save_ed25519_keypair(self.ws, pair)
        self.assertIn("symlink", str(ctx.exception).lower())
        self.assertEqual(target.read_text(encoding="utf-8"), "victim\n")

    def test_refuse_symlink_private_key_on_load(self) -> None:
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            load_ed25519_keypair,
            private_key_path,
            public_key_path,
            save_ed25519_keypair,
        )

        pair = Ed25519KeyPair.generate(key_id="symload")
        save_ed25519_keypair(self.ws, pair)
        priv = private_key_path(self.ws, "symload")
        pub = public_key_path(self.ws, "symload")
        seed = priv.read_text(encoding="utf-8")
        priv.unlink()
        outside = self.ws / "outside.seed"
        outside.write_text(seed, encoding="utf-8")
        priv.symlink_to(outside)
        self.assertTrue(pub.is_file())
        with self.assertRaises(SigningError) as ctx:
            load_ed25519_keypair(self.ws, "symload")
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_refuse_symlink_public_key_on_load(self) -> None:
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            load_ed25519_keypair,
            load_ed25519_public_key_bytes,
            private_key_path,
            public_key_path,
            save_ed25519_keypair,
        )

        pair = Ed25519KeyPair.generate(key_id="sympub")
        save_ed25519_keypair(self.ws, pair)
        pub = public_key_path(self.ws, "sympub")
        hex_pub = pub.read_text(encoding="utf-8")
        pub.unlink()
        outside = self.ws / "outside.pub"
        outside.write_text(hex_pub, encoding="utf-8")
        pub.symlink_to(outside)
        self.assertTrue(private_key_path(self.ws, "sympub").is_file())
        with self.assertRaises(SigningError) as ctx:
            load_ed25519_keypair(self.ws, "sympub")
        self.assertIn("symlink", str(ctx.exception).lower())
        with self.assertRaises(SigningError) as ctx2:
            load_ed25519_public_key_bytes(self.ws, "sympub")
        self.assertIn("symlink", str(ctx2.exception).lower())

    def test_refuse_overwrite_without_flag(self) -> None:
        from runspecimen.pubkey import Ed25519KeyPair, save_ed25519_keypair

        pair = Ed25519KeyPair.generate(key_id="once")
        save_ed25519_keypair(self.ws, pair)
        other = Ed25519KeyPair.generate(key_id="once")
        with self.assertRaises(SigningError):
            save_ed25519_keypair(self.ws, other)

    def test_rotate_overwrite_replaces_pair(self) -> None:
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            load_ed25519_keypair,
            save_ed25519_keypair,
        )

        first = Ed25519KeyPair.generate(key_id="rotate1")
        save_ed25519_keypair(self.ws, first)
        second = Ed25519KeyPair.generate(key_id="rotate1")
        save_ed25519_keypair(self.ws, second, overwrite=True)
        loaded = load_ed25519_keypair(self.ws, "rotate1")
        self.assertEqual(loaded.public_hex(), second.public_hex())
        self.assertNotEqual(loaded.public_hex(), first.public_hex())

    def test_failed_rotation_keeps_old_keypair(self) -> None:
        """If public staging fails, the previous private+public pair must still load."""
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            load_ed25519_keypair,
            save_ed25519_keypair,
        )

        first = Ed25519KeyPair.generate(key_id="rotfail")
        save_ed25519_keypair(self.ws, first)
        second = Ed25519KeyPair.generate(key_id="rotfail")

        real_write = None
        import runspecimen.pubkey as pubkey_mod

        real_write = pubkey_mod._write_exclusive_bytes
        calls = {"n": 0}

        def flaky_write(path, data, *, mode):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            # First call stages the new private temp; fail on public temp.
            if calls["n"] >= 2:
                raise OSError("simulated public key write failure")
            return real_write(path, data, mode=mode)

        with mock.patch.object(pubkey_mod, "_write_exclusive_bytes", flaky_write):
            with self.assertRaises(OSError):
                save_ed25519_keypair(self.ws, second, overwrite=True)

        loaded = load_ed25519_keypair(self.ws, "rotfail")
        self.assertEqual(loaded.private_hex(), first.private_hex())
        self.assertEqual(loaded.public_hex(), first.public_hex())

    def test_failed_public_install_during_rotation_keeps_old_keypair(self) -> None:
        """Private must not be removed if installing the new public path fails."""
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            _ROTATE_TMP_MARK,
            load_ed25519_keypair,
            save_ed25519_keypair,
        )
        import runspecimen.pubkey as pubkey_mod

        first = Ed25519KeyPair.generate(key_id="rotpubfail")
        save_ed25519_keypair(self.ws, first)
        second = Ed25519KeyPair.generate(key_id="rotpubfail")
        pub_final = pubkey_mod.public_key_path(self.ws.resolve(), "rotpubfail")

        real_rename = pubkey_mod._rename_nofollow

        def rename_fail_pub_install(src, dst):  # type: ignore[no-untyped-def]
            # After staging, install attempt is new pub_tmp → pub.
            if Path(dst).resolve() == pub_final.resolve() and _ROTATE_TMP_MARK in Path(src).name:
                raise SigningError("simulated public install failure")
            return real_rename(src, dst)

        with mock.patch.object(pubkey_mod, "_rename_nofollow", rename_fail_pub_install):
            with self.assertRaises(SigningError):
                save_ed25519_keypair(self.ws, second, overwrite=True)

        loaded = load_ed25519_keypair(self.ws, "rotpubfail")
        self.assertEqual(loaded.public_hex(), first.public_hex())
        self.assertEqual(loaded.private_hex(), first.private_hex())

    def test_interrupted_private_install_rolls_back_to_old_keypair(self) -> None:
        """If new private install fails after new public is in place, restore old pair."""
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            load_ed25519_keypair,
            save_ed25519_keypair,
        )
        import runspecimen.pubkey as pubkey_mod

        first = Ed25519KeyPair.generate(key_id="rotprivfail")
        save_ed25519_keypair(self.ws, first)
        second = Ed25519KeyPair.generate(key_id="rotprivfail")
        priv_final = pubkey_mod.private_key_path(self.ws.resolve(), "rotprivfail")

        real_rename = pubkey_mod._rename_nofollow

        def rename_fail_priv_install(src, dst):  # type: ignore[no-untyped-def]
            if (
                Path(dst).resolve() == priv_final.resolve()
                and pubkey_mod._ROTATE_TMP_MARK in Path(src).name
            ):
                raise SigningError("simulated private install failure")
            return real_rename(src, dst)

        with mock.patch.object(pubkey_mod, "_rename_nofollow", rename_fail_priv_install):
            with self.assertRaises(SigningError):
                save_ed25519_keypair(self.ws, second, overwrite=True)

        loaded = load_ed25519_keypair(self.ws, "rotprivfail")
        self.assertEqual(loaded.public_hex(), first.public_hex())
        self.assertEqual(loaded.private_hex(), first.private_hex())

    def test_symlink_swap_during_private_read_is_rejected(self) -> None:
        """TOCTOU: path must be opened O_NOFOLLOW; fd fstat must reject link swaps."""
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            load_ed25519_keypair,
            private_key_path,
            save_ed25519_keypair,
        )
        import runspecimen.pubkey as pubkey_mod

        pair = Ed25519KeyPair.generate(key_id="toctou")
        save_ed25519_keypair(self.ws, pair)
        priv = private_key_path(self.ws, "toctou")
        outside = self.ws / "swapped.seed"
        outside.write_text(pair.private_hex() + "\n", encoding="utf-8")

        real_open = os.open
        opened: list[int] = []

        def open_then_swap(path, flags, *args, **kwargs):  # type: ignore[no-untyped-def]
            if "keys.op.lock" in str(path) or ".ed25519.rotate.journal" in str(path):
                return real_open(path, flags, *args, **kwargs)
            fd = real_open(path, flags, *args, **kwargs)
            if Path(path).resolve() == priv.resolve():
                opened.append(flags)
                # After open of the real file, replace path with a symlink.
                # Subsequent path-based reads would follow it; fd-based must not.
                priv.unlink()
                priv.symlink_to(outside)
            return fd

        with mock.patch.object(pubkey_mod.os, "open", open_then_swap):
            # Load should still succeed via the already-opened fd (same inode),
            # proving we do not re-resolve the path after open.
            loaded = load_ed25519_keypair(self.ws, "toctou")
        self.assertEqual(loaded.public_hex(), pair.public_hex())
        self.assertTrue(opened)
        self.assertTrue(all(f & os.O_NOFOLLOW for f in opened))

        # Direct load when the private path is already a symlink must fail.
        with self.assertRaises(SigningError) as ctx:
            load_ed25519_keypair(self.ws, "toctou")
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_public_key_file_load_refuses_symlink(self) -> None:
        from runspecimen.pubkey import Ed25519KeyPair, load_ed25519_public_key_file

        pair = Ed25519KeyPair.generate(key_id="filepub")
        target = self.ws / "real.pub"
        target.write_text(pair.public_hex() + "\n", encoding="utf-8")
        link = self.ws / "link.pub"
        link.symlink_to(target)
        with self.assertRaises(SigningError) as ctx:
            load_ed25519_public_key_file(link)
        self.assertIn("symlink", str(ctx.exception).lower())


@unittest.skipUnless(HAS_NACL, "PyNaCl not installed")
class TestEd25519CrashSafeRotation(RunSpecimenTestCase):
    """SIGKILL / durable-journal recovery at each rotation transition."""

    CRASH_PHASES = (
        "intent",
        "staged",
        "pub_backed",
        "pub_installed",
        "priv_backed",
        "priv_installed",
    )

    _CHILD_SCRIPT = r"""
import os
import signal
import sys
from pathlib import Path

from nacl.signing import SigningKey

sys.path.insert(0, sys.argv[1])
from runspecimen.pubkey import Ed25519KeyPair, save_ed25519_keypair
import runspecimen.pubkey as pubkey_mod

workspace = Path(sys.argv[2])
phase = sys.argv[3]
seed = bytes.fromhex(sys.argv[4])


def crash(hit: str) -> None:
    if hit == phase:
        os.kill(os.getpid(), signal.SIGKILL)


pubkey_mod._CRASH_AFTER_PHASE = crash
sk = SigningKey(seed)
pair = Ed25519KeyPair(
    key_id="crashrot",
    private_seed=seed,
    public_key=bytes(sk.verify_key),
)
save_ed25519_keypair(workspace, pair, overwrite=True)
"""

    def _child_rotate_and_crash(self, workspace: Path, phase: str, second_seed_hex: str) -> int:
        import subprocess

        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                self._CHILD_SCRIPT,
                str(SRC),
                str(workspace),
                phase,
                second_seed_hex,
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        return proc.returncode

    def test_sigkill_at_each_rotation_phase_recovers_working_pair(self) -> None:
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            load_ed25519_keypair,
            save_ed25519_keypair,
        )

        first = Ed25519KeyPair.generate(key_id="crashrot")
        save_ed25519_keypair(self.ws, first)
        second = Ed25519KeyPair.generate(key_id="crashrot")

        for phase in self.CRASH_PHASES:
            with self.subTest(phase=phase):
                # Reset to first key before each kill scenario.
                save_ed25519_keypair(self.ws, first, overwrite=True)
                rc = self._child_rotate_and_crash(self.ws, phase, second.private_hex())
                # SIGKILL typically yields returncode -9 / 128+9 depending on platform.
                self.assertNotEqual(rc, 0, f"child should not exit cleanly after crash at {phase}")
                self.assertIn(
                    rc,
                    {-signal.SIGKILL, -9, 128 + signal.SIGKILL, 137},
                    f"expected SIGKILL status for {phase}, got rc={rc}",
                )

                loaded = load_ed25519_keypair(self.ws, "crashrot")
                if phase == "priv_installed":
                    # New pair fully installed; recovery only cleans sidecars.
                    self.assertEqual(loaded.public_hex(), second.public_hex())
                    self.assertEqual(loaded.private_hex(), second.private_hex())
                else:
                    # Prior phases must restore the previous working pair.
                    self.assertEqual(loaded.public_hex(), first.public_hex())
                    self.assertEqual(loaded.private_hex(), first.private_hex())

    def test_sigkill_during_fresh_create_does_not_leave_half_pair(self) -> None:
        import subprocess

        from runspecimen.pubkey import (
            list_ed25519_key_ids,
            load_ed25519_keypair,
            private_key_path,
            public_key_path,
        )

        script = r"""
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from runspecimen.pubkey import Ed25519KeyPair, save_ed25519_keypair
import runspecimen.pubkey as pubkey_mod


def crash(hit: str) -> None:
    if hit == "fresh_priv_installed":
        os.kill(os.getpid(), signal.SIGKILL)


pubkey_mod._CRASH_AFTER_PHASE = crash
pair = Ed25519KeyPair.generate(key_id="freshkill")
save_ed25519_keypair(Path(sys.argv[2]), pair)
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c", script, str(SRC), str(self.ws)],
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertIn(proc.returncode, {-signal.SIGKILL, -9, 128 + signal.SIGKILL, 137})
        self.assertNotIn("freshkill", list_ed25519_key_ids(self.ws))
        self.assertFalse(private_key_path(self.ws, "freshkill").exists())
        self.assertFalse(public_key_path(self.ws, "freshkill").exists())
        with self.assertRaises(SigningError):
            load_ed25519_keypair(self.ws, "freshkill")


@unittest.skipUnless(HAS_NACL, "PyNaCl not installed")
class TestEd25519KeyDirConcurrency(RunSpecimenTestCase):
    def test_cross_process_rotation_and_load_stay_consistent(self) -> None:
        import subprocess
        import time

        from runspecimen.pubkey import Ed25519KeyPair, load_ed25519_keypair, save_ed25519_keypair

        first = Ed25519KeyPair.generate(key_id="race1")
        save_ed25519_keypair(self.ws, first)

        rotator = r"""
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from runspecimen.pubkey import Ed25519KeyPair, save_ed25519_keypair
ws = Path(sys.argv[2])
for _ in range(12):
    save_ed25519_keypair(ws, Ed25519KeyPair.generate(key_id="race1"), overwrite=True)
    time.sleep(0.002)
"""
        loader = r"""
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from runspecimen.pubkey import load_ed25519_keypair
ws = Path(sys.argv[2])
for _ in range(40):
    load_ed25519_keypair(ws, "race1")
    time.sleep(0.001)
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", rotator, str(SRC), str(self.ws)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ),
            subprocess.Popen(
                [sys.executable, "-c", loader, str(SRC), str(self.ws)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ),
        ]
        codes = []
        errs = []
        for proc in procs:
            try:
                _out, err = proc.communicate(timeout=60)
                codes.append(proc.returncode)
                errs.append(err)
            except subprocess.TimeoutExpired:
                proc.kill()
                _out, err = proc.communicate()
                codes.append(99)
                errs.append(err)
        self.assertEqual(codes, [0, 0], f"rotator/loader failed: {errs}")
        final = load_ed25519_keypair(self.ws, "race1")
        self.assertEqual(len(final.public_hex()), 64)

    def test_nonblocking_lock_rejects_second_process(self) -> None:
        import subprocess
        import time

        holder = r"""
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from runspecimen.pubkey import hold_keys_dir_lock
with hold_keys_dir_lock(Path(sys.argv[2]), blocking=True):
    time.sleep(2.0)
"""
        challenger = r"""
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from runspecimen.errors import SigningError
from runspecimen.pubkey import hold_keys_dir_lock
try:
    with hold_keys_dir_lock(Path(sys.argv[2]), blocking=False):
        raise SystemExit("lock should have been busy")
except SigningError as exc:
    if "busy" in str(exc).lower():
        raise SystemExit(0)
    raise
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        hold_proc = subprocess.Popen(
            [sys.executable, "-c", holder, str(SRC), str(self.ws)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            time.sleep(0.3)
            chal = subprocess.run(
                [sys.executable, "-c", challenger, str(SRC), str(self.ws)],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(chal.returncode, 0, chal.stdout + chal.stderr)
        finally:
            try:
                hold_proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                hold_proc.kill()
                hold_proc.communicate()


if __name__ == "__main__":
    unittest.main()
