"""Tests for CLI sign and verify-signature commands."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from runspecimen.approve import approve_contract
from runspecimen.atomic import atomic_write_json
from runspecimen.certificate import load_certificate
from runspecimen.hashutil import canonical_json_bytes, sha256_bytes
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.run import run_contract
from runspecimen.signing import SigningKey, save_signing_key


def _run_cli(*args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run the CLI and return (exit_code, stdout, stderr)."""
    import os
    env = os.environ.copy()
    # Add src directory to PYTHONPATH so runspecimen can be found
    src_dir = Path(__file__).parent.parent / "src"
    env["PYTHONPATH"] = str(src_dir) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "runspecimen.cli", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def _create_valid_run(workspace: Path) -> tuple[Path, str, str]:
    """Create a valid postflighted run and return (contract_path, campaign_id, run_id)."""
    from tests.helpers import base_contract, write_contract, PhraseReader, NullWriter

    (workspace / "work").mkdir(exist_ok=True)
    (workspace / "outputs").mkdir(exist_ok=True)

    # Create a job script that produces the expected output
    job = workspace / "work" / "job.py"
    job.write_text('''
import json
with open("outputs/out.json", "w") as f:
    json.dump({"status": "ok"}, f)
''', encoding="utf-8")

    doc = base_contract()
    doc["argv"] = [sys.executable, "work/job.py"]
    doc["run_id"] = "cli-test-run"
    contract_path = write_contract(workspace, "contract.json", doc)

    # Full lifecycle
    approve_contract(
        contract_path=contract_path,
        workspace=workspace,
        skip_tty_check=True,
        stdin=PhraseReader("APPROVE\n"),
        stdout=NullWriter(),
    )
    preflight(contract_path=contract_path, workspace=workspace)
    run_contract(contract_path=contract_path, workspace=workspace)
    postflight(contract_path=contract_path, workspace=workspace)

    return contract_path, doc["campaign_id"], doc["run_id"]


class TestSignCommand(unittest.TestCase):
    """Tests for the sign CLI command."""

    def test_sign_command_does_not_crash_on_import(self):
        """sign command should not crash with ImportError."""
        rc, stdout, stderr = _run_cli("sign", "--help")
        self.assertEqual(rc, 0, f"sign --help failed: {stderr}")
        self.assertIn("sign", stdout.lower())

    def test_sign_valid_canonical_receipt(self):
        """sign should succeed for a valid canonical receipt."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            contract_path, campaign_id, run_id = _create_valid_run(workspace)

            # Create a signing key
            key = SigningKey.generate(key_id="test-key")
            save_signing_key(workspace, key)

            # Get the canonical certificate path
            state_dir = workspace / ".runspecimen" / "runs" / campaign_id / run_id
            cert_path = state_dir / "certificate.json"

            self.assertTrue(cert_path.exists(), "certificate.json should exist after postflight")

            # Sign the canonical certificate
            rc, stdout, stderr = _run_cli(
                "sign",
                "--workspace", str(workspace),
                "--key-id", "test-key",
                "--certificate", str(cert_path),
                "--contract", str(contract_path),
            )

            self.assertEqual(rc, 0, f"sign failed: {stderr}")
            result = json.loads(stdout)
            self.assertTrue(result["ok"])
            self.assertTrue(result["receipt_verified"])

    def test_sign_rejects_fabricated_certificate(self):
        """sign should reject a fabricated certificate with modified source_hash."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            contract_path, campaign_id, run_id = _create_valid_run(workspace)

            # Create a signing key
            key = SigningKey.generate(key_id="test-key")
            save_signing_key(workspace, key)

            # Load the canonical certificate
            state_dir = workspace / ".runspecimen" / "runs" / campaign_id / run_id
            cert = load_certificate(state_dir)

            # Fabricate a certificate with modified source_hash
            fabricated = dict(cert)
            fabricated["source_hash"] = "f" * 64

            # Recompute certificate_id to make it self-consistent
            material = {
                "approval_expires_at_unix": fabricated.get("approval_expires_at_unix"),
                "campaign_id": fabricated["campaign_id"],
                "contract_hash": fabricated["contract_hash"],
                "event_head": fabricated["event_head"],
                "exit_code": fabricated.get("exit_code"),
                "issued_at": fabricated["issued_at"],
                "output_digests": fabricated["output_digests"],
                "run_id": fabricated["run_id"],
                "run_result": fabricated.get("run_result"),
                "source_hash": fabricated["source_hash"],
                "runtime": fabricated["runtime"],
            }
            fabricated["certificate_id"] = sha256_bytes(canonical_json_bytes(material))

            # Save the fabricated certificate
            fabricated_path = workspace / "fabricated.json"
            atomic_write_json(fabricated_path, fabricated)

            # Attempt to sign the fabricated certificate
            rc, stdout, stderr = _run_cli(
                "sign",
                "--workspace", str(workspace),
                "--key-id", "test-key",
                "--certificate", str(fabricated_path),
                "--contract", str(contract_path),
            )

            self.assertNotEqual(rc, 0, "sign should reject fabricated certificate")
            self.assertIn("does not match", stderr.lower())

    def test_sign_missing_key_error(self):
        """sign should report clear error for missing key without traceback."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            contract_path, campaign_id, run_id = _create_valid_run(workspace)

            state_dir = workspace / ".runspecimen" / "runs" / campaign_id / run_id
            cert_path = state_dir / "certificate.json"

            rc, stdout, stderr = _run_cli(
                "sign",
                "--workspace", str(workspace),
                "--key-id", "nonexistent-key",
                "--certificate", str(cert_path),
                "--contract", str(contract_path),
            )

            self.assertNotEqual(rc, 0)
            self.assertIn("error", stderr.lower())
            self.assertNotIn("Traceback", stderr)


class TestVerifySignatureCommand(unittest.TestCase):
    """Tests for the verify-signature CLI command."""

    def test_verify_signature_command_does_not_crash_on_import(self):
        """verify-signature command should not crash with ImportError."""
        rc, stdout, stderr = _run_cli("verify-signature", "--help")
        self.assertEqual(rc, 0, f"verify-signature --help failed: {stderr}")
        self.assertIn("verify", stdout.lower())

    def test_verify_signature_valid_signed_receipt(self):
        """verify-signature should succeed for a properly signed canonical receipt."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            contract_path, campaign_id, run_id = _create_valid_run(workspace)

            # Create and save a signing key
            key = SigningKey.generate(key_id="test-key")
            save_signing_key(workspace, key)

            # Get the canonical certificate
            state_dir = workspace / ".runspecimen" / "runs" / campaign_id / run_id
            cert_path = state_dir / "certificate.json"

            # Sign the certificate
            rc, stdout, stderr = _run_cli(
                "sign",
                "--workspace", str(workspace),
                "--key-id", "test-key",
                "--certificate", str(cert_path),
                "--contract", str(contract_path),
            )
            self.assertEqual(rc, 0, f"sign failed: {stderr}")
            sign_result = json.loads(stdout)
            signed_path = sign_result["signed_output"]

            # Verify the signed certificate
            rc, stdout, stderr = _run_cli(
                "verify-signature",
                "--workspace", str(workspace),
                "--key-id", "test-key",
                "--signed", signed_path,
                "--contract", str(contract_path),
            )

            self.assertEqual(rc, 0, f"verify-signature failed: {stderr}")
            result = json.loads(stdout)
            self.assertTrue(result["ok"])
            self.assertTrue(result["mac_valid"])
            self.assertTrue(result["receipt_valid"])
            self.assertTrue(result["canonical_match"])

    def test_verify_signature_rejects_signed_fabricated_receipt(self):
        """verify-signature should reject a signed fabricated certificate."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            contract_path, campaign_id, run_id = _create_valid_run(workspace)

            # Create and save a signing key
            key = SigningKey.generate(key_id="test-key")
            save_signing_key(workspace, key)

            # Get the canonical certificate and sign it
            state_dir = workspace / ".runspecimen" / "runs" / campaign_id / run_id
            cert_path = state_dir / "certificate.json"

            rc, stdout, stderr = _run_cli(
                "sign",
                "--workspace", str(workspace),
                "--key-id", "test-key",
                "--certificate", str(cert_path),
                "--contract", str(contract_path),
            )
            self.assertEqual(rc, 0, f"sign failed: {stderr}")
            sign_result = json.loads(stdout)
            signed_path = Path(sign_result["signed_output"])

            # Tamper with the signed file to create a fabricated signed receipt
            # (This simulates having a signed fabricated receipt from an attacker)
            signed_data = json.loads(signed_path.read_text())
            signed_data["certificate"]["source_hash"] = "f" * 64
            # Note: MAC will fail because we tampered with the content
            atomic_write_json(signed_path, signed_data)

            # Verify should fail
            rc, stdout, stderr = _run_cli(
                "verify-signature",
                "--workspace", str(workspace),
                "--key-id", "test-key",
                "--signed", str(signed_path),
                "--contract", str(contract_path),
            )

            self.assertNotEqual(rc, 0, "verify-signature should reject tampered certificate")

    def test_verify_signature_missing_file_error(self):
        """verify-signature should report clear error for missing file."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / ".runspecimen").mkdir()

            key = SigningKey.generate(key_id="test-key")
            save_signing_key(workspace, key)

            # Create a minimal contract for the --contract arg
            contract_path = workspace / "contract.json"
            atomic_write_json(contract_path, {
                "schema": 1,
                "campaign_id": "test",
                "run_id": "test",
                "argv": ["/bin/true"],
                "cwd": ".",
            })

            rc, stdout, stderr = _run_cli(
                "verify-signature",
                "--workspace", str(workspace),
                "--key-id", "test-key",
                "--signed", str(workspace / "nonexistent.signed.json"),
                "--contract", str(contract_path),
            )

            self.assertNotEqual(rc, 0)
            self.assertNotIn("Traceback", stderr)


class TestListKeysSymlinkSecurity(unittest.TestCase):
    """Tests for list-keys symlink security."""

    def test_list_keys_rejects_symlinked_keys_dir_outside(self):
        """list-keys should reject symlinked keys directory pointing outside."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            outside = Path(tempfile.mkdtemp())

            try:
                (workspace / ".runspecimen").mkdir()
                keys_link = workspace / ".runspecimen" / "keys"
                keys_link.symlink_to(outside)

                # Create a key in the outside directory
                key_file = outside / "leaked.key"
                key_file.write_text('{"key_id": "leaked", "algorithm": "hmac-sha256", "key_hex": "00" * 32}')

                rc, stdout, stderr = _run_cli(
                    "list-keys",
                    "--workspace", str(workspace),
                )

                self.assertNotEqual(rc, 0)
                self.assertIn("symlink", stderr.lower())
            finally:
                import shutil
                shutil.rmtree(outside)

    def test_list_keys_rejects_symlinked_keys_dir_inside(self):
        """list-keys should reject symlinked keys directory pointing inside workspace."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            # Create a real directory inside workspace
            real_keys = workspace / "real_keys"
            real_keys.mkdir()

            (workspace / ".runspecimen").mkdir()
            keys_link = workspace / ".runspecimen" / "keys"
            keys_link.symlink_to(real_keys)

            rc, stdout, stderr = _run_cli(
                "list-keys",
                "--workspace", str(workspace),
            )

            self.assertNotEqual(rc, 0)
            self.assertIn("symlink", stderr.lower())

    def test_list_keys_api_rejects_symlinked_keys_dir(self):
        """list_signing_keys() API should reject symlinked keys directory."""
        from runspecimen.signing import list_signing_keys
        from runspecimen.errors import SigningError

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            outside = Path(tempfile.mkdtemp())

            try:
                (workspace / ".runspecimen").mkdir()
                keys_link = workspace / ".runspecimen" / "keys"
                keys_link.symlink_to(outside)

                with self.assertRaises(SigningError) as ctx:
                    list_signing_keys(workspace)
                self.assertIn("symlink", str(ctx.exception).lower())
            finally:
                import shutil
                shutil.rmtree(outside)


if __name__ == "__main__":
    unittest.main()
