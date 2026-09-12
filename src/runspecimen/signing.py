"""Receipt signing and verification with local keys.

This module provides signing capabilities for RunSpecimen certificates.
The MVP implementation uses HMAC-SHA256 with a local secret key, providing
integrity verification when the key is shared out-of-band.

For production use with true asymmetric cryptography (where verifiers don't
need the signing key), upgrade to Ed25519 or RSA via an optional dependency.
The interface here is designed to support that transition.

Key storage:
- Keys are stored as hex-encoded files in the workspace's .runspecimen/keys/ dir
- Key files are chmod 0600 to limit access
- Production deployments should use hardware-backed keys or a key management service
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.errors import SigningError
from runspecimen.hashutil import canonical_json_bytes, sha256_bytes
from runspecimen.paths import ensure_dir

# Key configuration
KEY_LENGTH_BYTES = 32  # 256-bit key for HMAC-SHA256
SIGNATURE_ALGORITHM = "hmac-sha256-v1"


@dataclass(frozen=True)
class SigningKey:
    """A local signing key (secret)."""
    key_id: str
    key_bytes: bytes
    algorithm: str = SIGNATURE_ALGORITHM
    
    @classmethod
    def generate(cls, key_id: str | None = None) -> "SigningKey":
        """Generate a new random signing key."""
        key_bytes = secrets.token_bytes(KEY_LENGTH_BYTES)
        if key_id is None:
            key_id = sha256_bytes(key_bytes)[:16]  # Short ID from key hash
        return cls(key_id=key_id, key_bytes=key_bytes)
    
    @classmethod
    def from_hex(cls, key_id: str, hex_key: str) -> "SigningKey":
        """Load a signing key from hex-encoded bytes."""
        try:
            key_bytes = bytes.fromhex(hex_key)
        except ValueError as e:
            raise SigningError(f"invalid hex key: {e}") from e
        if len(key_bytes) != KEY_LENGTH_BYTES:
            raise SigningError(f"key must be {KEY_LENGTH_BYTES} bytes, got {len(key_bytes)}")
        return cls(key_id=key_id, key_bytes=key_bytes)
    
    def to_hex(self) -> str:
        """Export key as hex-encoded string."""
        return self.key_bytes.hex()
    
    def sign(self, data: bytes) -> str:
        """Sign data and return hex-encoded signature."""
        sig = hmac.new(self.key_bytes, data, hashlib.sha256).digest()
        return sig.hex()
    
    def verify(self, data: bytes, signature: str) -> bool:
        """Verify a signature against data."""
        try:
            sig_bytes = bytes.fromhex(signature)
        except ValueError:
            return False
        expected = hmac.new(self.key_bytes, data, hashlib.sha256).digest()
        return hmac.compare_digest(sig_bytes, expected)


@dataclass(frozen=True)
class SignedCertificate:
    """A certificate with its signature."""
    certificate: dict[str, Any]
    signature: str
    key_id: str
    algorithm: str
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "certificate": self.certificate,
            "signature": {
                "value": self.signature,
                "key_id": self.key_id,
                "algorithm": self.algorithm,
            },
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignedCertificate":
        if "certificate" not in data or "signature" not in data:
            raise SigningError("invalid signed certificate format")
        sig = data["signature"]
        if not isinstance(sig, dict) or "value" not in sig:
            raise SigningError("invalid signature format")
        return cls(
            certificate=data["certificate"],
            signature=sig["value"],
            key_id=sig.get("key_id", "unknown"),
            algorithm=sig.get("algorithm", "unknown"),
        )


def keys_dir(workspace: Path) -> Path:
    """Return the keys directory for a workspace."""
    return workspace / ".runspecimen" / "keys"


def save_signing_key(workspace: Path, key: SigningKey) -> Path:
    """Save a signing key to the workspace keys directory.
    
    The key file is chmod 0600 to limit read access.
    """
    workspace = workspace.resolve()
    kdir = keys_dir(workspace)
    ensure_dir(kdir)
    
    key_path = kdir / f"{key.key_id}.key"
    key_data = {
        "key_id": key.key_id,
        "algorithm": key.algorithm,
        "key_hex": key.to_hex(),
    }
    
    atomic_write_json(key_path, key_data)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass  # Best effort on platforms that don't support chmod
    
    return key_path


def load_signing_key(workspace: Path, key_id: str) -> SigningKey:
    """Load a signing key from the workspace keys directory."""
    workspace = workspace.resolve()
    key_path = keys_dir(workspace) / f"{key_id}.key"
    
    if not key_path.exists():
        raise SigningError(f"signing key not found: {key_id}")
    
    try:
        data = read_json(key_path)
    except Exception as e:
        raise SigningError(f"failed to read key file: {e}") from e
    
    if data.get("key_id") != key_id:
        raise SigningError("key file key_id mismatch")
    
    return SigningKey.from_hex(key_id, data["key_hex"])


def list_signing_keys(workspace: Path) -> list[str]:
    """List available signing key IDs in the workspace."""
    workspace = workspace.resolve()
    kdir = keys_dir(workspace)
    
    if not kdir.exists():
        return []
    
    return [
        p.stem for p in kdir.iterdir()
        if p.suffix == ".key" and p.is_file()
    ]


def sign_certificate(
    certificate: dict[str, Any],
    key: SigningKey,
) -> SignedCertificate:
    """Sign a certificate with the given key."""
    # Canonicalize the certificate for signing
    cert_bytes = canonical_json_bytes(certificate)
    signature = key.sign(cert_bytes)
    
    return SignedCertificate(
        certificate=certificate,
        signature=signature,
        key_id=key.key_id,
        algorithm=key.algorithm,
    )


def verify_signature(
    signed_cert: SignedCertificate,
    key: SigningKey,
) -> tuple[bool, str]:
    """Verify a signed certificate against a key.
    
    Returns (ok, message).
    """
    if signed_cert.key_id != key.key_id:
        return False, f"key_id mismatch: expected {key.key_id}, got {signed_cert.key_id}"
    
    if signed_cert.algorithm != key.algorithm:
        return False, f"algorithm mismatch: expected {key.algorithm}, got {signed_cert.algorithm}"
    
    cert_bytes = canonical_json_bytes(signed_cert.certificate)
    if not key.verify(cert_bytes, signed_cert.signature):
        return False, "signature verification failed"
    
    return True, "ok"


def sign_certificate_file(
    cert_path: Path,
    key: SigningKey,
    output_path: Path | None = None,
) -> Path:
    """Sign a certificate file and write the signed version.
    
    If output_path is None, writes to {cert_path.stem}.signed.json
    """
    cert_path = cert_path.resolve()
    if not cert_path.exists():
        raise SigningError(f"certificate file not found: {cert_path}")
    
    try:
        cert = read_json(cert_path)
    except Exception as e:
        raise SigningError(f"failed to read certificate: {e}") from e
    
    signed = sign_certificate(cert, key)
    
    if output_path is None:
        output_path = cert_path.parent / f"{cert_path.stem}.signed.json"
    output_path = output_path.resolve()
    
    atomic_write_json(output_path, signed.to_dict())
    return output_path


def verify_signed_file(
    signed_path: Path,
    key: SigningKey,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Verify a signed certificate file.
    
    Returns (ok, message, certificate or None).
    """
    signed_path = signed_path.resolve()
    if not signed_path.exists():
        return False, f"signed file not found: {signed_path}", None
    
    try:
        data = read_json(signed_path)
    except Exception as e:
        return False, f"failed to read signed file: {e}", None
    
    try:
        signed_cert = SignedCertificate.from_dict(data)
    except SigningError as e:
        return False, str(e), None
    
    ok, msg = verify_signature(signed_cert, key)
    return ok, msg, signed_cert.certificate if ok else None
