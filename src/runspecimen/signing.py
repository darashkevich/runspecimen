"""Shared-secret authentication for RunSpecimen certificates (HMAC-SHA256).

IMPORTANT SECURITY LIMITATIONS:

This module uses HMAC-SHA256 for certificate authentication. HMAC is a
shared-secret Message Authentication Code (MAC), which means:

1. NOT A SIGNATURE: Anyone who can verify a certificate can also forge one.
   The same secret key is used for both authentication and verification.

2. NO NON-REPUDIATION: You cannot prove to a third party that a specific
   entity created a certificate. Both you and the verifier share the key.

3. NO INDEPENDENT VERIFICATION: A skeptical third party cannot verify a
   certificate without receiving the shared secret, which would then allow
   them to forge certificates.

WHAT THIS PROVIDES:

- Tamper detection: If you share the key only with trusted parties, you can
  detect unauthorized modifications to certificates.
- Origin authentication: If you and one other party share a key, and you
  receive a valid MAC, it came from either you or them.

For true digital signatures with non-repudiation and independent third-party
verification, upgrade to asymmetric cryptography (Ed25519/RSA) when available.

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

import re

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.errors import SigningError
from runspecimen.hashutil import canonical_json_bytes, sha256_bytes
from runspecimen.paths import ensure_dir

# Key configuration
KEY_LENGTH_BYTES = 32  # 256-bit key for HMAC-SHA256
SIGNATURE_ALGORITHM = "hmac-sha256-v1"

# Safe key ID pattern: alphanumeric, hyphens, underscores only
# No path separators, no dots, no leading/trailing special chars
# Length 1-64 characters
_SAFE_KEY_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}[a-zA-Z0-9]?$")


def validate_key_id(key_id: str) -> None:
    """Validate a key ID against the safe-ID grammar.
    
    Rejects:
    - Empty strings
    - Path separators (/, \\)
    - Dot traversal (.., .)
    - Leading dots
    - Non-alphanumeric characters except hyphen and underscore
    - Key IDs longer than 64 characters
    """
    if not key_id:
        raise SigningError("key_id cannot be empty")
    
    if len(key_id) > 64:
        raise SigningError(f"key_id too long (max 64 chars): {len(key_id)}")
    
    # Check for path traversal attacks
    if "/" in key_id or "\\" in key_id:
        raise SigningError("key_id cannot contain path separators")
    
    if key_id.startswith("."):
        raise SigningError("key_id cannot start with a dot")
    
    if ".." in key_id:
        raise SigningError("key_id cannot contain dot traversal")
    
    # Validate against safe pattern
    if not _SAFE_KEY_ID_PATTERN.match(key_id):
        raise SigningError(
            f"invalid key_id: must be 1-64 alphanumeric chars with optional "
            f"hyphens/underscores (not at start), got {key_id!r}"
        )


@dataclass(frozen=True)
class SigningKey:
    """A local signing key (secret)."""
    key_id: str
    key_bytes: bytes
    algorithm: str = SIGNATURE_ALGORITHM
    
    @classmethod
    def generate(cls, key_id: str | None = None) -> "SigningKey":
        """Generate a new random signing key.
        
        Args:
            key_id: Optional key ID. If None, generates one from key hash.
                   Must match safe-ID grammar if provided.
        
        Raises:
            SigningError: If provided key_id is invalid.
        """
        key_bytes = secrets.token_bytes(KEY_LENGTH_BYTES)
        if key_id is None:
            key_id = sha256_bytes(key_bytes)[:16]  # Short ID from key hash
        else:
            validate_key_id(key_id)
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


def _safe_key_path(workspace: Path, key_id: str) -> Path:
    """Compute and validate the key file path, ensuring it stays inside keys_dir.
    
    Raises SigningError if key_id is invalid or would escape the keys directory.
    """
    validate_key_id(key_id)
    
    workspace = workspace.resolve()
    kdir = keys_dir(workspace).resolve()
    key_path = (kdir / f"{key_id}.key").resolve()
    
    # Ensure the resolved path is inside the keys directory
    try:
        key_path.relative_to(kdir)
    except ValueError:
        raise SigningError(f"key path escapes keys directory: {key_id}")
    
    return key_path


def save_signing_key(
    workspace: Path,
    key: SigningKey,
    *,
    allow_overwrite: bool = False,
) -> Path:
    """Save a signing key to the workspace keys directory.
    
    The key file is chmod 0600 to limit read access.
    
    Args:
        workspace: Workspace root path
        key: The signing key to save
        allow_overwrite: If False (default), refuse to overwrite existing keys.
                        Key rotation should use an explicit workflow.
    
    Raises:
        SigningError: If key_id is invalid, path escapes, or key exists
    """
    workspace = workspace.resolve()
    kdir = keys_dir(workspace)
    ensure_dir(kdir)
    
    key_path = _safe_key_path(workspace, key.key_id)
    
    # Refuse to overwrite unless explicitly allowed
    if key_path.exists() and not allow_overwrite:
        raise SigningError(
            f"key {key.key_id!r} already exists; use explicit key rotation "
            f"workflow to replace keys"
        )
    
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
    """Load a signing key from the workspace keys directory.
    
    Raises:
        SigningError: If key_id is invalid, path escapes, or key not found
    """
    key_path = _safe_key_path(workspace, key_id)
    
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
    """List available signing key IDs in the workspace.
    
    Only returns key IDs that match the safe-ID grammar.
    """
    workspace = workspace.resolve()
    kdir = keys_dir(workspace)
    
    if not kdir.exists():
        return []
    
    key_ids = []
    for p in kdir.iterdir():
        if p.suffix == ".key" and p.is_file():
            key_id = p.stem
            # Only include keys with valid IDs
            try:
                validate_key_id(key_id)
                key_ids.append(key_id)
            except SigningError:
                pass  # Skip invalid key IDs
    return sorted(key_ids)


# Required fields for a valid RunSpecimen certificate
_REQUIRED_CERT_FIELDS = frozenset({
    "certificate_id",
    "campaign_id",
    "run_id",
    "contract_hash",
    "source_hash",
    "event_head",
    "output_digests",
    "issued_at",
    "runtime",
})


def _recompute_certificate_id(cert: dict[str, Any]) -> str:
    """Recompute the certificate_id from the certificate body."""
    material = {
        "approval_expires_at_unix": cert.get("approval_expires_at_unix"),
        "campaign_id": cert["campaign_id"],
        "contract_hash": cert["contract_hash"],
        "event_head": cert["event_head"],
        "exit_code": cert.get("exit_code"),
        "issued_at": cert["issued_at"],
        "output_digests": cert["output_digests"],
        "run_id": cert["run_id"],
        "run_result": cert.get("run_result"),
        "source_hash": cert["source_hash"],
        "runtime": cert["runtime"],
    }
    return sha256_bytes(canonical_json_bytes(material))


def validate_certificate_schema(cert: dict[str, Any]) -> tuple[bool, str]:
    """Validate that a certificate has the required schema.
    
    Checks:
    - All required fields are present
    - certificate_id matches recomputed value
    
    Returns (ok, message).
    """
    if not isinstance(cert, dict):
        return False, "certificate must be a JSON object"
    
    missing = _REQUIRED_CERT_FIELDS - set(cert.keys())
    if missing:
        return False, f"certificate missing required fields: {sorted(missing)}"
    
    # Validate types for critical fields
    if not isinstance(cert.get("certificate_id"), str):
        return False, "certificate_id must be a string"
    if not isinstance(cert.get("output_digests"), dict):
        return False, "output_digests must be a dict"
    if not isinstance(cert.get("runtime"), dict):
        return False, "runtime must be a dict"
    
    # Recompute and verify certificate_id
    try:
        recomputed = _recompute_certificate_id(cert)
    except (KeyError, TypeError) as e:
        return False, f"cannot recompute certificate_id: {e}"
    
    if recomputed != cert["certificate_id"]:
        return False, (
            f"certificate_id mismatch (tampering detected): "
            f"expected {recomputed}, got {cert['certificate_id']}"
        )
    
    return True, "ok"


def sign_certificate(
    certificate: dict[str, Any],
    key: SigningKey,
    *,
    validate: bool = True,
) -> SignedCertificate:
    """Sign a RunSpecimen certificate with the given key.
    
    Args:
        certificate: The certificate to sign
        key: The signing key
        validate: If True (default), validate the certificate schema and
                 recompute certificate_id before signing. Set to False only
                 for testing or when signing non-RunSpecimen data.
    
    Raises:
        SigningError: If validation fails
    
    Note: This provides shared-secret authentication only. Anyone with the
    key can both sign and verify. For independent third-party verification,
    use asymmetric cryptography.
    """
    if validate:
        ok, msg = validate_certificate_schema(certificate)
        if not ok:
            raise SigningError(f"certificate validation failed: {msg}")
    
    # Canonicalize the certificate for signing
    cert_bytes = canonical_json_bytes(certificate)
    signature = key.sign(cert_bytes)
    
    return SignedCertificate(
        certificate=certificate,
        signature=signature,
        key_id=key.key_id,
        algorithm=key.algorithm,
    )


@dataclass
class SignatureVerificationResult:
    """Result of signature verification with clear status levels."""
    mac_valid: bool  # Is the MAC (signature) cryptographically valid?
    schema_valid: bool | None  # Does the certificate match RunSpecimen schema? None if not checked.
    certificate_id_valid: bool | None  # Does certificate_id match recomputed value? None if not checked.
    message: str
    
    @property
    def ok(self) -> bool:
        """Verification passed based on what was checked.
        
        If schema validation was skipped (schema_valid=None), only MAC validity matters.
        If schema validation was performed, all three checks must pass.
        """
        if not self.mac_valid:
            return False
        # If schema wasn't checked, MAC validity is sufficient
        if self.schema_valid is None:
            return True
        # If schema was checked, it must be valid along with certificate_id
        return self.schema_valid and (self.certificate_id_valid is True)


def verify_signature(
    signed_cert: SignedCertificate,
    key: SigningKey,
    *,
    validate_schema: bool = True,
) -> SignatureVerificationResult:
    """Verify a signed certificate against a key.
    
    This verifies:
    1. MAC validity: The signature matches the certificate content
    2. Schema validity: The certificate has required RunSpecimen fields
    3. Certificate ID validity: The certificate_id matches recomputed value
    
    Args:
        signed_cert: The signed certificate to verify
        key: The key to verify against
        validate_schema: If True (default), also validate the certificate schema
    
    Returns:
        SignatureVerificationResult with detailed status
    
    Note: This uses shared-secret HMAC - anyone with the key can forge signatures.
    MAC validity does NOT prove the certificate came from a trusted source unless
    the key was securely shared out-of-band.
    """
    # Check key_id match
    if signed_cert.key_id != key.key_id:
        return SignatureVerificationResult(
            mac_valid=False,
            schema_valid=False,
            certificate_id_valid=False,
            message=f"key_id mismatch: expected {key.key_id}, got {signed_cert.key_id}",
        )
    
    # Check algorithm match
    if signed_cert.algorithm != key.algorithm:
        return SignatureVerificationResult(
            mac_valid=False,
            schema_valid=False,
            certificate_id_valid=False,
            message=f"algorithm mismatch: expected {key.algorithm}, got {signed_cert.algorithm}",
        )
    
    # Verify MAC
    cert_bytes = canonical_json_bytes(signed_cert.certificate)
    mac_valid = key.verify(cert_bytes, signed_cert.signature)
    
    if not mac_valid:
        return SignatureVerificationResult(
            mac_valid=False,
            schema_valid=False,
            certificate_id_valid=False,
            message="MAC verification failed (signature invalid or content tampered)",
        )
    
    # MAC is valid - now check schema if requested
    if not validate_schema:
        return SignatureVerificationResult(
            mac_valid=True,
            schema_valid=None,  # Not checked
            certificate_id_valid=None,  # Not checked
            message="MAC valid (schema not validated)",
        )
    
    schema_ok, schema_msg = validate_certificate_schema(signed_cert.certificate)
    if not schema_ok:
        return SignatureVerificationResult(
            mac_valid=True,
            schema_valid=False,
            certificate_id_valid=False,
            message=f"MAC valid but certificate schema invalid: {schema_msg}",
        )
    
    return SignatureVerificationResult(
        mac_valid=True,
        schema_valid=True,
        certificate_id_valid=True,
        message="MAC valid, certificate schema valid, certificate_id verified",
    )


def sign_certificate_file(
    cert_path: Path,
    key: SigningKey,
    output_path: Path | None = None,
    *,
    validate: bool = True,
) -> Path:
    """Sign a certificate file and write the signed version.
    
    Args:
        cert_path: Path to the certificate file
        key: The signing key
        output_path: Output path (default: {cert_path.stem}.signed.json)
        validate: If True (default), validate the certificate schema.
                 Set to False only for testing or non-RunSpecimen data.
    
    Returns:
        Path to the signed certificate file
    """
    cert_path = cert_path.resolve()
    if not cert_path.exists():
        raise SigningError(f"certificate file not found: {cert_path}")
    
    try:
        cert = read_json(cert_path)
    except Exception as e:
        raise SigningError(f"failed to read certificate: {e}") from e
    
    signed = sign_certificate(cert, key, validate=validate)
    
    if output_path is None:
        output_path = cert_path.parent / f"{cert_path.stem}.signed.json"
    output_path = output_path.resolve()
    
    atomic_write_json(output_path, signed.to_dict())
    return output_path


def verify_signed_file(
    signed_path: Path,
    key: SigningKey,
    *,
    validate_schema: bool = True,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Verify a signed certificate file.
    
    Args:
        signed_path: Path to the signed certificate file
        key: The key to verify against
        validate_schema: If True (default), also validate the certificate schema
    
    Returns:
        (ok, message, certificate or None)
        
        ok is True only if MAC is valid AND (when validate_schema=True) the
        certificate has a valid RunSpecimen schema with matching certificate_id.
    
    Note: MAC validity alone does NOT prove the certificate is a legitimate
    RunSpecimen receipt. It only proves the content wasn't modified after signing
    by someone with the same shared secret.
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
    
    result = verify_signature(signed_cert, key, validate_schema=validate_schema)
    return result.ok, result.message, signed_cert.certificate if result.ok else None
