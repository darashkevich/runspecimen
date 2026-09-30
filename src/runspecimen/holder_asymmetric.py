"""Asymmetric device signatures for holder local/companion/dual.

Uses Ed25519. Prefer PyNaCl when installed; otherwise a compact stdlib-only
fallback. Device-HMAC is not used for real local/companion/dual authorization.
Software test doubles stay labeled not-hardware. An imported secure-enclave
label is not attestation. This is not functional biometric execution.
Unprivileged tests do not prove installed protection.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Tuple


class AsymmetricError(Exception):
    """Key or signature operation failed."""


def _try_nacl():
    try:
        from nacl import signing as nacl_signing  # type: ignore[import-untyped]
        from nacl.exceptions import BadSignatureError  # type: ignore[import-untyped]
    except ImportError:
        return None
    return nacl_signing, BadSignatureError


# --- Compact Ed25519 (public-domain style reference arithmetic) ---------------
# Used only when PyNaCl is absent so stdlib CI can exercise asymmetric verify.

_B = 256
_Q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493


def _inv(x: int) -> int:
    return pow(x, _Q - 2, _Q)


_D = -121665 * _inv(121666) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if ((x * x - xx) % _Q) != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_BY = 4 * _inv(5)
_BX = _xrecover(_BY)
_BPOINT = (_BX % _Q, _BY % _Q)


def _edwards(p: Tuple[int, int], q: Tuple[int, int]) -> Tuple[int, int]:
    x1, y1 = p
    x2, y2 = q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + _D * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - _D * x1 * x2 * y1 * y2)
    return (x3 % _Q, y3 % _Q)


def _scalarmult(p: Tuple[int, int], e: int) -> Tuple[int, int]:
    if e == 0:
        return (0, 1)
    q = _scalarmult(p, e // 2)
    q = _edwards(q, q)
    if e & 1:
        q = _edwards(q, p)
    return q


def _encodeint(y: int) -> bytes:
    return y.to_bytes(32, "little")


def _encodepoint(p: Tuple[int, int]) -> bytes:
    x, y = p
    bits = bytearray(_encodeint(y))
    bits[-1] |= 0x80 if x & 1 else 0
    return bytes(bits)


def _bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def _hint(m: bytes) -> int:
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def _publickey_raw(sk: bytes) -> bytes:
    h = hashlib.sha512(sk).digest()
    a = 2 ** (_B - 2) + sum(2**i * _bit(h, i) for i in range(3, _B - 2))
    return _encodepoint(_scalarmult(_BPOINT, a))


def _sign_raw(message: bytes, sk: bytes) -> bytes:
    h = hashlib.sha512(sk).digest()
    a = 2 ** (_B - 2) + sum(2**i * _bit(h, i) for i in range(3, _B - 2))
    r = _hint(h[_B // 8 : _B // 4] + message)
    r_point = _scalarmult(_BPOINT, r)
    r_bytes = _encodepoint(r_point)
    pk = _encodepoint(_scalarmult(_BPOINT, a))
    s = (r + _hint(r_bytes + pk + message) * a) % _L
    return r_bytes + _encodeint(s)


def _decodeint(s: bytes) -> int:
    return int.from_bytes(s, "little")


def _is_on_curve(p: Tuple[int, int]) -> bool:
    x, y = p
    return ((-x * x + y * y - 1 - _D * x * x * y * y) % _Q) == 0


def _decodepoint(s: bytes) -> Tuple[int, int]:
    y = _decodeint(s) & ((1 << 255) - 1)
    x = _xrecover(y)
    if bool(x & 1) != bool(s[-1] >> 7):
        x = _Q - x
    p = (x, y)
    if not _is_on_curve(p):
        raise AsymmetricError("point is not on curve")
    return p


def _verify_raw(message: bytes, signature: bytes, public: bytes) -> bool:
    if len(signature) != 64 or len(public) != 32:
        return False
    try:
        r = _decodepoint(signature[:32])
        a = _decodepoint(public)
    except AsymmetricError:
        return False
    s = _decodeint(signature[32:])
    h = _hint(signature[:32] + public + message)
    return _scalarmult(_BPOINT, s) == _edwards(r, _scalarmult(a, h))


def generate_device_keypair() -> tuple[str, str]:
    """Return (private_hex, public_hex)."""
    nacl = _try_nacl()
    if nacl is not None:
        nacl_signing, _bad = nacl
        key = nacl_signing.SigningKey.generate()
        return key.encode().hex(), key.verify_key.encode().hex()
    sk = os.urandom(32)
    return sk.hex(), _publickey_raw(sk).hex()


def sign_device_challenge(private_hex: str, message: bytes) -> str:
    nacl = _try_nacl()
    if nacl is not None:
        nacl_signing, _bad = nacl
        key = nacl_signing.SigningKey(bytes.fromhex(private_hex))
        return key.sign(message).signature.hex()
    return _sign_raw(message, bytes.fromhex(private_hex)).hex()


def verify_device_signature(public_hex: str, signature_hex: str, message: bytes) -> bool:
    nacl = _try_nacl()
    if nacl is not None:
        nacl_signing, bad = nacl
        try:
            vk = nacl_signing.VerifyKey(bytes.fromhex(public_hex))
            vk.verify(message, bytes.fromhex(signature_hex))
            return True
        except (bad, ValueError, TypeError):
            return False
    try:
        return _verify_raw(message, bytes.fromhex(signature_hex), bytes.fromhex(public_hex))
    except (ValueError, TypeError, AsymmetricError):
        return False


def constant_time_label_ok(attestation_class: object, *, hardware: object) -> None:
    """Refuse hardware claims for software / non-SE paths."""
    if hardware is True:
        raise AsymmetricError("asymmetric device signatures are not hardware attestation")
    if attestation_class not in {
        None,
        "device-ed25519-not-hardware",
        "software-test-double-not-hardware",
    }:
        raise AsymmetricError("device signatures must stay labeled not-hardware")


def digest_challenge(payload: dict) -> bytes:
    """Canonical challenge bytes for signatures (exact authorized content)."""
    from runspecimen.hashutil import canonical_json_bytes

    return canonical_json_bytes(payload)
