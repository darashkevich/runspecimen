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


def _validate_keys_dir_security(workspace: Path) -> Path:
    """Validate the keys directory is secure (not symlinked).

    SECURITY: Symlinked control-plane directories are ALWAYS rejected,
    even when the target is inside the workspace. Symlinks create unexpected
    aliasing and TOCTOU hazards in security-critical paths.

    Returns the resolved keys directory path.
    Raises SigningError if security checks fail.
    """
    workspace = workspace.resolve()
    control_plane = workspace / ".runspecimen"
    kdir = control_plane / "keys"

    # SECURITY: Reject ANY symlinked .runspecimen directory
    if control_plane.exists() and control_plane.is_symlink():
        resolved = control_plane.resolve()
        raise SigningError(
            f".runspecimen must not be a symlink: {control_plane} -> {resolved}"
        )

    # SECURITY: Reject ANY symlinked keys directory
    if kdir.exists() and kdir.is_symlink():
        resolved = kdir.resolve()
        raise SigningError(
            f"keys directory must not be a symlink: {kdir} -> {resolved}"
        )

    return kdir.resolve() if kdir.exists() else kdir


def _safe_key_path(workspace: Path, key_id: str) -> Path:
    """Compute and validate the key file path, ensuring it stays inside workspace.

    Raises SigningError if key_id is invalid, keys dir is insecure, or path would escape.
    """
    validate_key_id(key_id)

    workspace = workspace.resolve()
    kdir = _validate_keys_dir_security(workspace)
    kdir_resolved = kdir.resolve() if kdir.exists() else (workspace / ".runspecimen" / "keys")
    key_path = (kdir_resolved / f"{key_id}.key")

    # Ensure the resolved path stays inside the workspace
    key_path_resolved = key_path.resolve() if key_path.exists() else key_path
    try:
        key_path_resolved.relative_to(workspace)
    except ValueError:
        raise SigningError(f"key path escapes workspace: {key_id}")

    return key_path


def save_signing_key(workspace: Path, key: SigningKey) -> Path:
    """Save a signing key to the workspace keys directory.

    The key file is chmod 0600 to limit read access.
    Uses exclusive file creation to prevent race conditions.

    Args:
        workspace: Workspace root path
        key: The signing key to save

    Raises:
        SigningError: If key_id is invalid, path escapes, key exists, or security check fails
    """
    workspace = workspace.resolve()

    # Security: validate keys dir is not a symlink escape
    _validate_keys_dir_security(workspace)

    kdir = keys_dir(workspace)
    ensure_dir(kdir)

    # Re-validate after directory creation
    _validate_keys_dir_security(workspace)

    key_path = _safe_key_path(workspace, key.key_id)

    key_data = {
        "key_id": key.key_id,
        "algorithm": key.algorithm,
        "key_hex": key.to_hex(),
    }

    # Use exclusive creation to prevent race conditions and overwrites
    import json
    try:
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, json.dumps(key_data, indent=2).encode("utf-8"))
        finally:
            os.close(fd)
    except FileExistsError:
        raise SigningError(
            f"key {key.key_id!r} already exists; key rotation is not supported"
        )
    except OSError as e:
        raise SigningError(f"failed to create key file: {e}") from e

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
    Rejects symlinked control-plane directories.

    Raises:
        SigningError: If .runspecimen or keys directory is a symlink
    """
    workspace = workspace.resolve()

    # SECURITY: Validate keys directory is not symlinked
    _validate_keys_dir_security(workspace)

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
    from runspecimen.schema import certificate_id_material

    return sha256_bytes(canonical_json_bytes(certificate_id_material(cert)))


def validate_certificate_schema(cert: dict[str, Any]) -> tuple[bool, str]:
    """Validate that a certificate has the required schema.

    Checks:
    - Receipt schema_version is supported (absent ≡ legacy 1)
    - All required fields are present
    - certificate_id matches recomputed value

    Returns (ok, message).
    """
    if not isinstance(cert, dict):
        return False, "certificate must be a JSON object"

    from runspecimen.errors import CertificateError
    from runspecimen.schema import assert_supported_receipt_schema

    try:
        assert_supported_receipt_schema(cert)
    except CertificateError as exc:
        return False, str(exc)

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
) -> SignedCertificate:
    """Sign a RunSpecimen certificate with the given key.

    This function ALWAYS validates the certificate schema before signing.
    It refuses to sign arbitrary JSON as a RunSpecimen receipt.

    Args:
        certificate: The certificate to sign (must be a valid RunSpecimen certificate)
        key: The signing key

    Raises:
        SigningError: If certificate validation fails

    Note: This provides shared-secret authentication only. Anyone with the
    key can both sign and verify. For independent third-party verification,
    use asymmetric cryptography.
    """
    # ALWAYS validate - never sign arbitrary JSON as a receipt
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
    schema_valid: bool  # Does the certificate match RunSpecimen schema?
    certificate_id_valid: bool  # Does certificate_id match recomputed value?
    message: str

    @property
    def ok(self) -> bool:
        """Verification passed: all three checks must pass."""
        return self.mac_valid and self.schema_valid and self.certificate_id_valid


def verify_signature(
    signed_cert: SignedCertificate,
    key: SigningKey,
) -> SignatureVerificationResult:
    """Verify a signed certificate against a key.

    This ALWAYS verifies all of:
    1. MAC validity: The signature matches the certificate content
    2. Schema validity: The certificate has required RunSpecimen fields
    3. Certificate ID validity: The certificate_id matches recomputed value

    Args:
        signed_cert: The signed certificate to verify
        key: The key to verify against

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

    # MAC is valid - ALWAYS validate schema for RunSpecimen receipts
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
) -> Path:
    """Sign a certificate file and write the signed version.

    This function ALWAYS validates the certificate schema before signing.
    It refuses to sign arbitrary JSON as a RunSpecimen receipt.

    Args:
        cert_path: Path to the certificate file
        key: The signing key
        output_path: Output path (default: {cert_path.stem}.signed.json)

    Returns:
        Path to the signed certificate file

    Raises:
        SigningError: If certificate validation fails or file operations fail
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

    This function ALWAYS validates the certificate schema.
    It refuses to accept arbitrary JSON as a valid RunSpecimen receipt.

    Args:
        signed_path: Path to the signed certificate file
        key: The key to verify against

    Returns:
        (ok, message, certificate or None)

        ok is True only if MAC is valid AND the certificate has a valid
        RunSpecimen schema with matching certificate_id.

    Note: MAC validity alone does NOT prove the certificate is a legitimate
    RunSpecimen receipt. Full receipt verification against workspace evidence
    is required for true validation.
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

    result = verify_signature(signed_cert, key)
    return result.ok, result.message, signed_cert.certificate if result.ok else None
