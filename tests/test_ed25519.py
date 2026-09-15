"""Tests for optional Ed25519 public-key receipt signatures."""

from __future__ import annotations

import json
import os
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
            "Version: 0.2.0rc9\n"
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

        real_open = open

        def guarded_open(path, *args, **kwargs):  # type: ignore[no-untyped-def]
            resolved = Path(path).resolve()
            if resolved == priv.resolve():
                raise AssertionError("export must not open the private key file")
            return real_open(path, *args, **kwargs)

        with mock.patch("builtins.open", guarded_open):
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

    def test_refuse_overwrite_without_flag(self) -> None:
        from runspecimen.pubkey import Ed25519KeyPair, save_ed25519_keypair

        pair = Ed25519KeyPair.generate(key_id="once")
        save_ed25519_keypair(self.ws, pair)
        other = Ed25519KeyPair.generate(key_id="once")
        with self.assertRaises(SigningError):
            save_ed25519_keypair(self.ws, other)


if __name__ == "__main__":
    unittest.main()
