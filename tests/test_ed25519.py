"""Tests for optional Ed25519 public-key receipt signatures."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

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


@unittest.skipUnless(HAS_NACL, "PyNaCl not installed; pip install 'runspecimen[ed25519]'")
class TestEd25519Crypto(unittest.TestCase):
    def test_sign_verify_roundtrip_and_wrong_key(self) -> None:
        from runspecimen.hashutil import canonical_json_bytes, sha256_bytes
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            sign_certificate_ed25519,
            verify_certificate_ed25519,
        )

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
        cert = {"certificate_id": sha256_bytes(canonical_json_bytes(body)), **body}
        pair = Ed25519KeyPair.generate(key_id="edtest")
        signed = sign_certificate_ed25519(cert, pair)
        ok = verify_certificate_ed25519(signed, public_key=pair.public_key)
        self.assertTrue(ok.ok)

        other = Ed25519KeyPair.generate(key_id="other")
        bad = verify_certificate_ed25519(signed, public_key=other.public_key)
        self.assertFalse(bad.ok)

    def test_tamper_fails(self) -> None:
        from runspecimen.hashutil import canonical_json_bytes, sha256_bytes
        from runspecimen.pubkey import (
            Ed25519KeyPair,
            Ed25519SignedCertificate,
            sign_certificate_ed25519,
            verify_certificate_ed25519,
        )

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
        cert = {"certificate_id": sha256_bytes(canonical_json_bytes(body)), **body}
        pair = Ed25519KeyPair.generate(key_id="edtest2")
        signed = sign_certificate_ed25519(cert, pair)
        tampered_cert = dict(signed.certificate)
        tampered_cert["source_hash"] = "f" * 64
        # Keep old certificate_id so schema check fails OR signature fails
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
        save_ed25519_keypair(self.ws, pair)
        loaded = load_ed25519_keypair(self.ws, "persist1")
        self.assertEqual(loaded.public_hex(), pair.public_hex())
        self.assertIn("persist1", list_ed25519_key_ids(self.ws))
