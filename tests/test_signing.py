"""Tests for receipt signing functionality."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runspecimen.atomic import atomic_write_json
from runspecimen.errors import SigningError
from runspecimen.signing import (
    SignedCertificate,
    SigningKey,
    list_signing_keys,
    load_signing_key,
    save_signing_key,
    sign_certificate,
    sign_certificate_file,
    verify_signature,
    verify_signed_file,
)


class TestSigningKey(unittest.TestCase):
    """Tests for SigningKey generation and operations."""

    def test_generate_creates_valid_key(self):
        key = SigningKey.generate()
        self.assertIsNotNone(key.key_id)
        self.assertEqual(len(key.key_bytes), 32)
        self.assertEqual(key.algorithm, "hmac-sha256-v1")

    def test_generate_with_custom_id(self):
        key = SigningKey.generate(key_id="my-custom-key")
        self.assertEqual(key.key_id, "my-custom-key")

    def test_from_hex_creates_key(self):
        original = SigningKey.generate()
        hex_key = original.to_hex()
        
        restored = SigningKey.from_hex(original.key_id, hex_key)
        self.assertEqual(restored.key_id, original.key_id)
        self.assertEqual(restored.key_bytes, original.key_bytes)

    def test_from_hex_rejects_invalid_length(self):
        with self.assertRaises(SigningError):
            SigningKey.from_hex("test", "abc123")  # Too short

    def test_from_hex_rejects_invalid_hex(self):
        with self.assertRaises(SigningError):
            SigningKey.from_hex("test", "g" * 64)  # Invalid hex chars

    def test_sign_and_verify_roundtrip(self):
        key = SigningKey.generate()
        data = b"test data to sign"
        
        signature = key.sign(data)
        self.assertTrue(key.verify(data, signature))

    def test_verify_fails_for_wrong_data(self):
        key = SigningKey.generate()
        signature = key.sign(b"original data")
        
        self.assertFalse(key.verify(b"different data", signature))

    def test_verify_fails_for_wrong_key(self):
        key1 = SigningKey.generate()
        key2 = SigningKey.generate()
        
        signature = key1.sign(b"test data")
        self.assertFalse(key2.verify(b"test data", signature))

    def test_verify_fails_for_invalid_signature(self):
        key = SigningKey.generate()
        self.assertFalse(key.verify(b"test", "invalid-signature"))


class TestKeyStorage(unittest.TestCase):
    """Tests for saving and loading keys."""

    def test_save_and_load_key(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            
            key = SigningKey.generate(key_id="test-key")
            save_signing_key(workspace, key)
            
            loaded = load_signing_key(workspace, "test-key")
            self.assertEqual(loaded.key_id, key.key_id)
            self.assertEqual(loaded.key_bytes, key.key_bytes)

    def test_load_missing_key_fails(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            
            with self.assertRaises(SigningError):
                load_signing_key(workspace, "nonexistent")

    def test_list_keys(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            
            # Initially empty
            self.assertEqual(list_signing_keys(workspace), [])
            
            # Add keys
            save_signing_key(workspace, SigningKey.generate(key_id="key1"))
            save_signing_key(workspace, SigningKey.generate(key_id="key2"))
            
            keys = list_signing_keys(workspace)
            self.assertEqual(set(keys), {"key1", "key2"})


class TestCertificateSigning(unittest.TestCase):
    """Tests for signing certificates."""

    def test_sign_certificate_creates_valid_signature(self):
        key = SigningKey.generate()
        cert = {
            "certificate_id": "abc123",
            "campaign_id": "test",
            "run_id": "run-001",
        }
        
        signed = sign_certificate(cert, key)
        
        self.assertEqual(signed.certificate, cert)
        self.assertEqual(signed.key_id, key.key_id)
        self.assertEqual(signed.algorithm, key.algorithm)
        self.assertIsInstance(signed.signature, str)

    def test_verify_signature_succeeds_for_valid(self):
        key = SigningKey.generate()
        cert = {"test": "data", "nested": {"value": 123}}
        
        signed = sign_certificate(cert, key)
        ok, msg = verify_signature(signed, key)
        
        self.assertTrue(ok)
        self.assertEqual(msg, "ok")

    def test_verify_signature_fails_for_wrong_key(self):
        key1 = SigningKey.generate(key_id="key1")
        key2 = SigningKey.generate(key_id="key2")
        cert = {"test": "data"}
        
        signed = sign_certificate(cert, key1)
        ok, msg = verify_signature(signed, key2)
        
        self.assertFalse(ok)
        self.assertIn("key_id mismatch", msg)

    def test_verify_signature_fails_for_tampered_cert(self):
        key = SigningKey.generate()
        cert = {"test": "data"}
        
        signed = sign_certificate(cert, key)
        
        # Tamper with the certificate
        tampered = SignedCertificate(
            certificate={"test": "tampered"},
            signature=signed.signature,
            key_id=signed.key_id,
            algorithm=signed.algorithm,
        )
        
        ok, msg = verify_signature(tampered, key)
        self.assertFalse(ok)
        self.assertIn("verification failed", msg)


class TestSignedCertificate(unittest.TestCase):
    """Tests for SignedCertificate serialization."""

    def test_to_dict_and_from_dict_roundtrip(self):
        key = SigningKey.generate()
        cert = {"id": "test123"}
        signed = sign_certificate(cert, key)
        
        serialized = signed.to_dict()
        restored = SignedCertificate.from_dict(serialized)
        
        self.assertEqual(restored.certificate, signed.certificate)
        self.assertEqual(restored.signature, signed.signature)
        self.assertEqual(restored.key_id, signed.key_id)
        self.assertEqual(restored.algorithm, signed.algorithm)

    def test_from_dict_rejects_invalid_format(self):
        with self.assertRaises(SigningError):
            SignedCertificate.from_dict({"invalid": "data"})


class TestFileOperations(unittest.TestCase):
    """Tests for file-based signing operations."""

    def test_sign_certificate_file(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            
            # Create a certificate file
            cert = {"certificate_id": "test123", "data": "value"}
            cert_path = workspace / "certificate.json"
            atomic_write_json(cert_path, cert)
            
            # Create and save a key
            key = SigningKey.generate(key_id="file-test-key")
            save_signing_key(workspace, key)
            
            # Sign the file
            output_path = sign_certificate_file(cert_path, key)
            
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.name, "certificate.signed.json")
            
            # Verify the signed file
            ok, msg, loaded_cert = verify_signed_file(output_path, key)
            self.assertTrue(ok)
            self.assertEqual(loaded_cert, cert)

    def test_sign_certificate_file_custom_output(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            
            cert = {"id": "test"}
            cert_path = workspace / "cert.json"
            atomic_write_json(cert_path, cert)
            
            key = SigningKey.generate()
            custom_output = workspace / "custom.signed.json"
            
            output_path = sign_certificate_file(cert_path, key, custom_output)
            
            self.assertEqual(output_path, custom_output)
            self.assertTrue(output_path.exists())

    def test_verify_signed_file_detects_tampering(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            
            cert = {"id": "original"}
            cert_path = workspace / "cert.json"
            atomic_write_json(cert_path, cert)
            
            key = SigningKey.generate()
            signed_path = sign_certificate_file(cert_path, key)
            
            # Tamper with the signed file
            with signed_path.open("r") as f:
                data = json.load(f)
            data["certificate"]["id"] = "tampered"
            with signed_path.open("w") as f:
                json.dump(data, f)
            
            ok, msg, _ = verify_signed_file(signed_path, key)
            self.assertFalse(ok)
            self.assertIn("verification failed", msg)

    def test_verify_missing_file_fails(self):
        key = SigningKey.generate()
        ok, msg, cert = verify_signed_file(Path("/nonexistent/file.json"), key)
        
        self.assertFalse(ok)
        self.assertIn("not found", msg)
        self.assertIsNone(cert)


if __name__ == "__main__":
    unittest.main()
