"""Device signatures for holder local/companion/dual.

Production verification uses PyNaCl (the vetted Ed25519 implementation) only.
There is no handwritten verifier. If PyNaCl is not installed, verification
fails closed. A software signature is not a Secure Enclave, not Touch ID,
not Face ID, and not a hardware verifier. An imported secure-enclave label
is not attestation. Unprivileged tests do not prove installed protection.
"""

from __future__ import annotations

from typing import Any


class AsymmetricError(Exception):
    """Key or signature operation failed, or no vetted verifier is connected."""


def vetted_verifier_available() -> bool:
    """True only when the vetted PyNaCl verifier can be imported."""
    try:
        import nacl.signing  # noqa: F401
    except ImportError:
        return False
    return True


def _nacl() -> Any:
    try:
        from nacl import signing as nacl_signing
        from nacl.exceptions import BadSignatureError
    except ImportError as exc:
        raise AsymmetricError(
            "vetted Ed25519 verifier is not connected"
        ) from exc
    return nacl_signing, BadSignatureError


def generate_device_keypair() -> tuple[str, str]:
    """Return (private_hex, public_hex) from the vetted verifier only."""
    nacl_signing, _bad = _nacl()
    key = nacl_signing.SigningKey.generate()
    return key.encode().hex(), key.verify_key.encode().hex()


def sign_device_challenge(private_hex: str, message: bytes) -> str:
    nacl_signing, _bad = _nacl()
    try:
        key = nacl_signing.SigningKey(bytes.fromhex(private_hex))
    except Exception as exc:
        raise AsymmetricError("device private key is invalid") from exc
    return key.sign(message).signature.hex()


def verify_device_signature(public_hex: str, signature_hex: str, message: bytes) -> bool:
    """Verify with PyNaCl. Missing verifier, bad key, or bad signature is False.

    The historical handwritten verifier accepted an identity point plus a
    forged signature. That implementation is gone. This function never
    accepts a signature it cannot check with PyNaCl.
    """
    if not vetted_verifier_available():
        return False
    nacl_signing, bad = _nacl()
    try:
        public = bytes.fromhex(public_hex)
        signature = bytes.fromhex(signature_hex)
    except (ValueError, TypeError):
        return False
    if len(public) != 32 or len(signature) != 64:
        return False
    try:
        vk = nacl_signing.VerifyKey(public)
        vk.verify(message, signature)
    except (bad, ValueError, TypeError):
        return False
    return True


_P256_IDENTIFIER = "com.darashkevich.runspecimen.native-p256-verify"
_LABELED_NATIVE_BRIDGE = "labeled-native-bridge-double-not-hardware"


def public_key_fingerprint(public_key: str) -> str:
    """Fingerprint the caller must compare before a native public key is stored."""
    import hashlib

    return hashlib.sha256(public_key.encode("utf-8")).hexdigest()


def verify_native_p256(
    public_b64: str,
    signature_b64: str,
    message: bytes,
    binary: Path | None = None,
) -> bool:
    """Verify a P-256 signature with the packaged CryptoKit binary.

    The binary is hash-pinned and ad-hoc signed at package time. This function
    does not invoke swiftc. A true result is not a Secure Enclave, Touch ID,
    or Face ID approval. A missing binary, a provenance mismatch, or a bad
    signature is false. There is no handwritten verifier in this function.
    """
    import hashlib
    import json
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    if sys.platform != "darwin":
        return False
    if binary is None:
        here = Path(__file__).resolve().parent / "platform" / "darwin_arm64"
        binary = here / "native_p256_verify"
        provenance_path = here / "native_p256_verify.provenance.json"
    else:
        binary = Path(binary)
        provenance_path = binary.parent / "native_p256_verify.provenance.json"
    if not binary.is_file() or not provenance_path.is_file():
        return False
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    except (OSError, json.JSONDecodeError, UnicodeError):
        return False
    if not isinstance(provenance, dict):
        return False
    if provenance.get("sha256") != digest:
        return False
    if provenance.get("identifier") != _P256_IDENTIFIER:
        return False
    if provenance.get("signed") not in {"adhoc", "codesign"}:
        return False
    if provenance.get("not_secure_enclave") is not True:
        return False
    try:
        verified = subprocess.run(
            ["/usr/bin/codesign", "--verify", "--strict", str(binary)],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if verified.returncode != 0:
        return False
    try:
        with tempfile.NamedTemporaryFile(prefix="rs-p256-msg-") as handle:
            handle.write(message)
            handle.flush()
            checked = subprocess.run(
                [str(binary), public_b64, signature_b64, handle.name],
                check=False,
                capture_output=True,
                timeout=10,
            )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return checked.returncode == 0


def digest_challenge(payload: dict) -> bytes:
    """Canonical challenge bytes. Not a verifier."""
    from runspecimen.hashutil import canonical_json_bytes

    return canonical_json_bytes(payload)


def constant_time_label_ok(attestation_class: object, *, hardware: object) -> None:
    """Refuse hardware claims. Software Ed25519 is not a Secure Enclave."""
    if hardware is True:
        raise AsymmetricError(
            "device signatures are not Secure Enclave, Touch ID, Face ID, or a hardware verifier"
        )
    if attestation_class in {"secure-enclave", "touch-id", "face-id"}:
        raise AsymmetricError("an imported hardware label is not attestation")
    if attestation_class not in {
        None,
        "device-ed25519-not-hardware",
        "device-p256-not-hardware",
        "software-test-double-not-hardware",
    }:
        raise AsymmetricError("device signatures must stay labeled not-hardware")
