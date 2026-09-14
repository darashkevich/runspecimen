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
    validate_key_id,
    verify_signature,
    verify_signed_file,
)
from tests.helpers import assert_paths_same


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


def _make_valid_certificate() -> dict:
    """Create a valid RunSpecimen certificate for testing."""
    from runspecimen.hashutil import canonical_json_bytes, sha256_bytes

    body = {
        "approval_expires_at_unix": 1234567890,
        "campaign_id": "test-campaign",
        "contract_hash": "a" * 64,
        "event_head": "b" * 64,
        "exit_code": 0,
        "issued_at": "2024-01-01T00:00:00Z",
        "output_digests": {"output.json": "c" * 64},
        "run_id": "run-001",
        "run_result": "completed",
        "source_hash": "d" * 64,
        "runtime": {"runtime_id": "e" * 64, "argv0": "python", "resolved_executable": "/usr/bin/python"},
    }
    cert_id = sha256_bytes(canonical_json_bytes(body))
    return {"certificate_id": cert_id, **body}


class TestCertificateSigning(unittest.TestCase):
    """Tests for signing certificates."""

    def test_sign_certificate_creates_valid_signature(self):
        key = SigningKey.generate()
        cert = _make_valid_certificate()

        signed = sign_certificate(cert, key)

        self.assertEqual(signed.certificate, cert)
        self.assertEqual(signed.key_id, key.key_id)
        self.assertEqual(signed.algorithm, key.algorithm)
        self.assertIsInstance(signed.signature, str)

    def test_sign_certificate_always_rejects_arbitrary_json(self):
        """sign_certificate ALWAYS rejects arbitrary JSON - no bypass."""
        key = SigningKey.generate()
        cert = {"test": "data"}  # Not a valid RunSpecimen certificate

        # Must reject - no validate=False bypass allowed
        with self.assertRaises(SigningError) as ctx:
            sign_certificate(cert, key)
        self.assertIn("missing required fields", str(ctx.exception))

    def test_sign_certificate_rejects_invalid_schema(self):
        """Signing rejects invalid certificates (missing required fields)."""
        key = SigningKey.generate()
        cert = {"test": "data"}  # Missing required fields

        with self.assertRaises(SigningError) as ctx:
            sign_certificate(cert, key)
        self.assertIn("missing required fields", str(ctx.exception))

    def test_sign_certificate_rejects_tampered_id(self):
        """Signing rejects certificate with tampered certificate_id."""
        key = SigningKey.generate()
        cert = _make_valid_certificate()
        cert["certificate_id"] = "tampered" + cert["certificate_id"][8:]

        with self.assertRaises(SigningError) as ctx:
            sign_certificate(cert, key)
        self.assertIn("mismatch", str(ctx.exception).lower())

    def test_verify_signature_succeeds_for_valid(self):
        key = SigningKey.generate()
        cert = _make_valid_certificate()

        signed = sign_certificate(cert, key)
        result = verify_signature(signed, key)

        self.assertTrue(result.ok)
        self.assertTrue(result.mac_valid)
        self.assertTrue(result.schema_valid)
        self.assertTrue(result.certificate_id_valid)

    def test_verify_signature_fails_for_wrong_key(self):
        key1 = SigningKey.generate(key_id="key1")
        key2 = SigningKey.generate(key_id="key2")
        cert = _make_valid_certificate()

        signed = sign_certificate(cert, key1)
        result = verify_signature(signed, key2)

        self.assertFalse(result.ok)
        self.assertFalse(result.mac_valid)
        self.assertIn("key_id mismatch", result.message)

    def test_verify_signature_fails_for_tampered_cert(self):
        key = SigningKey.generate()
        cert = _make_valid_certificate()

        signed = sign_certificate(cert, key)

        # Tamper with the certificate
        tampered_cert = dict(signed.certificate)
        tampered_cert["run_id"] = "tampered"
        tampered = SignedCertificate(
            certificate=tampered_cert,
            signature=signed.signature,
            key_id=signed.key_id,
            algorithm=signed.algorithm,
        )

        result = verify_signature(tampered, key)
        self.assertFalse(result.ok)
        self.assertFalse(result.mac_valid)
        self.assertIn("MAC verification failed", result.message)

    def test_verify_signature_always_validates_schema(self):
        """verify_signature ALWAYS validates schema - no bypass."""
        key = SigningKey.generate()
        cert = _make_valid_certificate()

        signed = sign_certificate(cert, key)

        # Tamper with the signed certificate's content directly
        # This simulates receiving a signed blob with invalid schema
        tampered = SignedCertificate(
            certificate={"not": "a real certificate"},
            signature=signed.signature,  # Original signature won't match anyway
            key_id=key.key_id,
            algorithm=key.algorithm,
        )

        result = verify_signature(tampered, key)
        self.assertFalse(result.ok)
        # MAC fails because content changed
        self.assertFalse(result.mac_valid)


class TestSignedCertificate(unittest.TestCase):
    """Tests for SignedCertificate serialization."""

    def test_to_dict_and_from_dict_roundtrip(self):
        key = SigningKey.generate()
        cert = _make_valid_certificate()  # Use valid certificate
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

            # Create a valid certificate file
            cert = _make_valid_certificate()
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

    def test_sign_certificate_file_rejects_invalid(self):
        """sign_certificate_file ALWAYS rejects invalid certificates."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            # Create an invalid certificate file
            cert = {"not": "a valid certificate"}
            cert_path = workspace / "cert.json"
            atomic_write_json(cert_path, cert)

            key = SigningKey.generate()

            with self.assertRaises(SigningError) as ctx:
                sign_certificate_file(cert_path, key)
            self.assertIn("missing required fields", str(ctx.exception))

    def test_sign_certificate_file_custom_output(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            cert = _make_valid_certificate()
            cert_path = workspace / "cert.json"
            atomic_write_json(cert_path, cert)

            key = SigningKey.generate()
            custom_output = workspace / "custom.signed.json"

            output_path = sign_certificate_file(cert_path, key, custom_output)

            # Use portable path assertion for macOS /var vs /private/var
            assert_paths_same(self, output_path, custom_output)
            self.assertTrue(output_path.exists())

    def test_verify_signed_file_detects_tampering(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            cert = _make_valid_certificate()
            cert_path = workspace / "cert.json"
            atomic_write_json(cert_path, cert)

            key = SigningKey.generate()
            signed_path = sign_certificate_file(cert_path, key)

            # Tamper with the signed file
            with signed_path.open("r") as f:
                data = json.load(f)
            data["certificate"]["campaign_id"] = "tampered"
            with signed_path.open("w") as f:
                json.dump(data, f)

            # MAC check should fail due to tampering
            ok, msg, _ = verify_signed_file(signed_path, key)
            self.assertFalse(ok)
            self.assertIn("MAC verification failed", msg)

    def test_verify_missing_file_fails(self):
        key = SigningKey.generate()
        ok, msg, cert = verify_signed_file(Path("/nonexistent/file.json"), key)

        self.assertFalse(ok)
        self.assertIn("not found", msg)
        self.assertIsNone(cert)


class TestKeyIdValidation(unittest.TestCase):
    """Tests for key ID validation and safe-ID grammar."""

    def test_valid_key_ids(self):
        """Valid key IDs should pass validation."""
        valid_ids = [
            "a",
            "ab",
            "key1",
            "my-key",
            "my_key",
            "MyKey123",
            "a" * 64,  # Max length
            "key-with-hyphens",
            "key_with_underscores",
        ]
        for key_id in valid_ids:
            try:
                validate_key_id(key_id)
            except SigningError:
                self.fail(f"Valid key_id {key_id!r} was rejected")

    def test_empty_key_id_rejected(self):
        """Empty key ID should be rejected."""
        with self.assertRaises(SigningError) as ctx:
            validate_key_id("")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_too_long_key_id_rejected(self):
        """Key ID longer than 64 chars should be rejected."""
        with self.assertRaises(SigningError) as ctx:
            validate_key_id("a" * 65)
        self.assertIn("too long", str(ctx.exception).lower())

    def test_path_separator_rejected(self):
        """Path separators in key ID should be rejected."""
        with self.assertRaises(SigningError) as ctx:
            validate_key_id("../escape")
        self.assertIn("separator", str(ctx.exception).lower())

        with self.assertRaises(SigningError) as ctx:
            validate_key_id("path/to/key")
        self.assertIn("separator", str(ctx.exception).lower())

        with self.assertRaises(SigningError) as ctx:
            validate_key_id("path\\to\\key")
        self.assertIn("separator", str(ctx.exception).lower())

    def test_leading_dot_rejected(self):
        """Leading dot in key ID should be rejected."""
        with self.assertRaises(SigningError) as ctx:
            validate_key_id(".hidden")
        self.assertIn("dot", str(ctx.exception).lower())

    def test_dot_traversal_rejected(self):
        """Dot traversal in key ID should be rejected."""
        with self.assertRaises(SigningError) as ctx:
            validate_key_id("key..name")
        self.assertIn("traversal", str(ctx.exception).lower())

    def test_special_chars_rejected(self):
        """Special characters should be rejected."""
        invalid_ids = [
            "key@name",
            "key#name",
            "key$name",
            "key%name",
            "key name",  # space
            "key\tname",  # tab
            "key\nname",  # newline
        ]
        for key_id in invalid_ids:
            with self.assertRaises(SigningError):
                validate_key_id(key_id)

    def test_generate_rejects_invalid_custom_id(self):
        """SigningKey.generate should reject invalid custom key IDs."""
        with self.assertRaises(SigningError):
            SigningKey.generate(key_id="../escape")


class TestKeyStorageHardening(unittest.TestCase):
    """Tests for key storage path traversal and overwrite protection."""

    def test_path_traversal_attack_blocked_on_save(self):
        """Saving a key with path traversal in ID should be blocked."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            # This would escape the keys directory
            with self.assertRaises(SigningError) as ctx:
                key = SigningKey(key_id="../escape", key_bytes=b"0" * 32)
                save_signing_key(workspace, key)
            self.assertIn("separator", str(ctx.exception).lower())

    def test_path_traversal_attack_blocked_on_load(self):
        """Loading a key with path traversal in ID should be blocked."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            with self.assertRaises(SigningError) as ctx:
                load_signing_key(workspace, "../escape")
            self.assertIn("separator", str(ctx.exception).lower())

    def test_overwrite_protection(self):
        """Saving a key with an existing ID should fail without explicit flag."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            key = SigningKey.generate(key_id="test-key")
            save_signing_key(workspace, key)

            # Attempt to overwrite should fail
            key2 = SigningKey.generate(key_id="test-key")
            with self.assertRaises(SigningError) as ctx:
                save_signing_key(workspace, key2)
            self.assertIn("already exists", str(ctx.exception).lower())

    def test_symlink_keys_dir_escape_blocked(self):
        """A symlinked keys directory pointing outside workspace must be rejected."""
        import os

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            outside = Path(tempfile.mkdtemp())

            try:
                # Create .runspecimen dir
                (workspace / ".runspecimen").mkdir()

                # Create keys as a symlink pointing outside
                keys_link = workspace / ".runspecimen" / "keys"
                keys_link.symlink_to(outside)

                # Attempt to save should fail
                key = SigningKey.generate(key_id="test-key")
                with self.assertRaises(SigningError) as ctx:
                    save_signing_key(workspace, key)
                self.assertIn("symlink", str(ctx.exception).lower())
            finally:
                import shutil
                shutil.rmtree(outside)

    def test_symlink_keys_dir_inside_workspace_blocked(self):
        """A symlinked keys directory pointing INSIDE workspace must also be rejected."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            # Create a real directory inside workspace
            real_keys = workspace / "real_keys_dir"
            real_keys.mkdir()

            # Create .runspecimen dir
            (workspace / ".runspecimen").mkdir()

            # Create keys as a symlink pointing inside workspace
            keys_link = workspace / ".runspecimen" / "keys"
            keys_link.symlink_to(real_keys)

            # Attempt to save should fail - ALL symlinks rejected
            key = SigningKey.generate(key_id="test-key")
            with self.assertRaises(SigningError) as ctx:
                save_signing_key(workspace, key)
            self.assertIn("symlink", str(ctx.exception).lower())

    def test_symlink_control_plane_inside_workspace_blocked(self):
        """A symlinked .runspecimen pointing INSIDE workspace must also be rejected."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            # Create a real directory inside workspace
            real_control = workspace / "real_runspecimen"
            real_control.mkdir()

            # Create .runspecimen as a symlink pointing inside workspace
            control_link = workspace / ".runspecimen"
            control_link.symlink_to(real_control)

            # Attempt to save should fail - ALL symlinks rejected
            key = SigningKey.generate(key_id="test-key")
            with self.assertRaises(SigningError) as ctx:
                save_signing_key(workspace, key)
            self.assertIn("symlink", str(ctx.exception).lower())

    def test_symlink_control_plane_escape_blocked(self):
        """A symlinked .runspecimen pointing outside workspace must be rejected."""
        import os

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            outside = Path(tempfile.mkdtemp())

            try:
                # Create .runspecimen as a symlink pointing outside
                control_link = workspace / ".runspecimen"
                control_link.symlink_to(outside)

                # Attempt to save should fail
                key = SigningKey.generate(key_id="test-key")
                with self.assertRaises(SigningError) as ctx:
                    save_signing_key(workspace, key)
                self.assertIn("symlink", str(ctx.exception).lower())
            finally:
                import shutil
                shutil.rmtree(outside)

    def test_concurrent_key_creation_race_safe(self):
        """Concurrent key creation with same ID should not corrupt or overwrite."""
        import threading
        import time

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            results = {"success": 0, "exists": 0, "errors": []}
            lock = threading.Lock()

            def try_create():
                try:
                    key = SigningKey.generate(key_id="race-key")
                    save_signing_key(workspace, key)
                    with lock:
                        results["success"] += 1
                except SigningError as e:
                    with lock:
                        if "already exists" in str(e).lower():
                            results["exists"] += 1
                        else:
                            results["errors"].append(str(e))

            # Run multiple threads trying to create the same key
            threads = [threading.Thread(target=try_create) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Exactly one should succeed, others should get "already exists"
            self.assertEqual(results["success"], 1)
            self.assertEqual(results["exists"], 9)
            self.assertEqual(results["errors"], [])

    def test_list_keys_filters_invalid_ids(self):
        """list_signing_keys should only return valid key IDs."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            kdir = workspace / ".runspecimen" / "keys"
            kdir.mkdir(parents=True)

            # Create a valid key
            key = SigningKey.generate(key_id="valid-key")
            save_signing_key(workspace, key)

            # Manually create an invalid key file
            invalid_path = kdir / ".hidden.key"
            invalid_path.write_text('{"key_id": ".hidden"}')

            # List should only return valid keys
            keys = list_signing_keys(workspace)
            self.assertEqual(keys, ["valid-key"])


if __name__ == "__main__":
    unittest.main()
