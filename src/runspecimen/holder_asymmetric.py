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
        "software-test-double-not-hardware",
    }:
        raise AsymmetricError("device signatures must stay labeled not-hardware")
