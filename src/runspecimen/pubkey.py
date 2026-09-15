"""Optional Ed25519 public-key signatures for RunSpecimen receipts.

Requires the optional dependency::

    python3 -m pip install 'runspecimen[ed25519]'

This provides offline public-key verification without sharing the private key.
It does **not** provide absolute non-repudiation (soft keys on disk; custody
matters) and does **not** prove scientific or engineering claims.

HMAC-SHA256 in ``signing.py`` remains the shared-secret authentication path.
An HMAC MAC cannot satisfy Ed25519 verification, and vice versa.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.errors import SigningError
from runspecimen.hashutil import canonical_json_bytes
from runspecimen.paths import ensure_dir
from runspecimen.schema import assert_supported_receipt_schema
from runspecimen.signing import (
    validate_certificate_schema,
    validate_key_id,
)

ED25519_ALGORITHM = "ed25519-v1"
_PRIVATE_SUFFIX = ".ed25519"
_PUBLIC_SUFFIX = ".ed25519.pub"


def require_ed25519() -> Any:
    """Import PyNaCl or raise an actionable SigningError."""
    try:
        from nacl import signing as nacl_signing  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SigningError(
            "Ed25519 support requires the optional dependency PyNaCl. "
            "Install with: python3 -m pip install 'runspecimen[ed25519]' "
            "(Community/default installs remain stdlib-only without this extra)."
        ) from exc
    return nacl_signing


def keys_dir(workspace: Path) -> Path:
    return workspace / ".runspecimen" / "keys"


def private_key_path(workspace: Path, key_id: str) -> Path:
    validate_key_id(key_id)
    return keys_dir(workspace) / f"{key_id}{_PRIVATE_SUFFIX}"


def public_key_path(workspace: Path, key_id: str) -> Path:
    validate_key_id(key_id)
    return keys_dir(workspace) / f"{key_id}{_PUBLIC_SUFFIX}"


@dataclass(frozen=True)
class Ed25519KeyPair:
    """Ed25519 key pair (private seed retained for signing)."""

    key_id: str
    private_seed: bytes
    public_key: bytes
    algorithm: str = ED25519_ALGORITHM

    @classmethod
    def generate(cls, key_id: str | None = None) -> "Ed25519KeyPair":
        nacl_signing = require_ed25519()
        sk = nacl_signing.SigningKey.generate()
        seed = bytes(sk)
        pub = bytes(sk.verify_key)
        if key_id is None:
            key_id = pub.hex()[:16]
        else:
            validate_key_id(key_id)
        return cls(key_id=key_id, private_seed=seed, public_key=pub)

    def signing_key(self) -> Any:
        nacl_signing = require_ed25519()
        return nacl_signing.SigningKey(self.private_seed)

    def verify_key(self) -> Any:
        nacl_signing = require_ed25519()
        return nacl_signing.VerifyKey(self.public_key)

    def sign(self, data: bytes) -> str:
        signed = self.signing_key().sign(data)
        return bytes(signed.signature).hex()

    def public_hex(self) -> str:
        return self.public_key.hex()

    def private_hex(self) -> str:
        return self.private_seed.hex()


@dataclass(frozen=True)
class Ed25519SignedCertificate:
    certificate: dict[str, Any]
    signature: str
    key_id: str
    algorithm: str
    public_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "certificate": self.certificate,
            "key_id": self.key_id,
            "public_key": self.public_key,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Ed25519SignedCertificate":
        if not isinstance(data, dict):
            raise SigningError("signed certificate must be a JSON object")
        algorithm = data.get("algorithm")
        if algorithm != ED25519_ALGORITHM:
            raise SigningError(
                f"expected algorithm {ED25519_ALGORITHM!r}, got {algorithm!r}"
            )
        for field in ("certificate", "signature", "key_id", "public_key"):
            if field not in data:
                raise SigningError(f"signed certificate missing field: {field}")
        if not isinstance(data["certificate"], dict):
            raise SigningError("certificate must be an object")
        return cls(
            certificate=data["certificate"],
            signature=str(data["signature"]),
            key_id=str(data["key_id"]),
            algorithm=str(algorithm),
            public_key=str(data["public_key"]),
        )


@dataclass(frozen=True)
class Ed25519VerifyResult:
    signature_valid: bool
    schema_valid: bool
    certificate_id_valid: bool
    public_key_match: bool
    message: str

    @property
    def ok(self) -> bool:
        return (
            self.signature_valid
            and self.schema_valid
            and self.certificate_id_valid
            and self.public_key_match
        )


def save_ed25519_keypair(
    workspace: Path,
    pair: Ed25519KeyPair,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Persist private (0600) and public key files. Returns (private, public) paths."""
    require_ed25519()
    kdir = keys_dir(workspace.resolve())
    # Refuse symlink control-plane escape (same posture as HMAC keys).
    rs = workspace.resolve() / ".runspecimen"
    if rs.exists() and rs.is_symlink():
        raise SigningError(".runspecimen must not be a symlink")
    ensure_dir(kdir)
    if kdir.is_symlink():
        raise SigningError("keys directory must not be a symlink")

    priv = private_key_path(workspace, pair.key_id)
    pub = public_key_path(workspace, pair.key_id)
    if (priv.exists() or pub.exists()) and not overwrite:
        raise SigningError(
            f"Ed25519 key {pair.key_id!r} already exists; pass overwrite to rotate"
        )

    priv.write_text(pair.private_hex() + "\n", encoding="utf-8")
    os.chmod(priv, 0o600)
    pub.write_text(pair.public_hex() + "\n", encoding="utf-8")
    os.chmod(pub, 0o644)
    return priv, pub


def load_ed25519_keypair(workspace: Path, key_id: str) -> Ed25519KeyPair:
    require_ed25519()
    priv = private_key_path(workspace, key_id)
    pub = public_key_path(workspace, key_id)
    if not priv.is_file():
        raise SigningError(f"Ed25519 private key not found: {key_id}")
    if not pub.is_file():
        raise SigningError(f"Ed25519 public key not found: {key_id}")
    try:
        seed = bytes.fromhex(priv.read_text(encoding="utf-8").strip())
        public = bytes.fromhex(pub.read_text(encoding="utf-8").strip())
    except ValueError as exc:
        raise SigningError(f"invalid Ed25519 key encoding for {key_id}: {exc}") from exc
    nacl_signing = require_ed25519()
    sk = nacl_signing.SigningKey(seed)
    if bytes(sk.verify_key) != public:
        raise SigningError(f"Ed25519 public key does not match private seed for {key_id}")
    return Ed25519KeyPair(key_id=key_id, private_seed=seed, public_key=public)


def load_ed25519_public_key_file(path: Path) -> bytes:
    require_ed25519()
    try:
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise SigningError(f"cannot load Ed25519 public key from {path}: {exc}") from exc


def export_ed25519_public_key(workspace: Path, key_id: str, output: Path) -> Path:
    pair = load_ed25519_keypair(workspace, key_id)
    output = output.resolve()
    output.write_text(pair.public_hex() + "\n", encoding="utf-8")
    os.chmod(output, 0o644)
    return output


def list_ed25519_key_ids(workspace: Path) -> list[str]:
    kdir = keys_dir(workspace.resolve())
    if not kdir.is_dir() or kdir.is_symlink():
        return []
    ids: list[str] = []
    for path in kdir.iterdir():
        if path.suffixes == [".ed25519"] or path.name.endswith(_PRIVATE_SUFFIX):
            # stem of foo.ed25519 is foo
            key_id = path.name[: -len(_PRIVATE_SUFFIX)]
            try:
                validate_key_id(key_id)
            except SigningError:
                continue
            if public_key_path(workspace, key_id).is_file():
                ids.append(key_id)
    return sorted(ids)


def sign_certificate_ed25519(
    certificate: dict[str, Any],
    pair: Ed25519KeyPair,
) -> Ed25519SignedCertificate:
    require_ed25519()
    assert_supported_receipt_schema(certificate)
    ok, msg = validate_certificate_schema(certificate)
    if not ok:
        raise SigningError(f"certificate validation failed: {msg}")
    payload = canonical_json_bytes(certificate)
    signature = pair.sign(payload)
    return Ed25519SignedCertificate(
        certificate=certificate,
        signature=signature,
        key_id=pair.key_id,
        algorithm=ED25519_ALGORITHM,
        public_key=pair.public_hex(),
    )


def verify_certificate_ed25519(
    signed: Ed25519SignedCertificate,
    *,
    public_key: bytes | None = None,
) -> Ed25519VerifyResult:
    """Verify Ed25519 signature using an explicit or embedded public key."""
    nacl_signing = require_ed25519()

    try:
        assert_supported_receipt_schema(signed.certificate)
        ok, msg = validate_certificate_schema(signed.certificate)
    except Exception as exc:  # noqa: BLE001 — surface as verify result
        return Ed25519VerifyResult(
            signature_valid=False,
            schema_valid=False,
            certificate_id_valid=False,
            public_key_match=False,
            message=str(exc),
        )
    if not ok:
        return Ed25519VerifyResult(
            signature_valid=False,
            schema_valid=False,
            certificate_id_valid=False,
            public_key_match=False,
            message=msg,
        )

    try:
        embedded = bytes.fromhex(signed.public_key)
    except ValueError:
        return Ed25519VerifyResult(
            False, True, True, False, "embedded public_key is not valid hex"
        )

    if public_key is None:
        public_key = embedded
        pub_match = True
    else:
        pub_match = public_key == embedded
        if not pub_match:
            return Ed25519VerifyResult(
                False,
                True,
                True,
                False,
                "provided public key does not match signed document public_key",
            )

    try:
        sig = bytes.fromhex(signed.signature)
        vk = nacl_signing.VerifyKey(public_key)
        vk.verify(canonical_json_bytes(signed.certificate), sig)
    except Exception as exc:  # noqa: BLE001
        return Ed25519VerifyResult(
            False, True, True, pub_match, f"signature verification failed: {exc}"
        )

    return Ed25519VerifyResult(
        True,
        True,
        True,
        pub_match,
        "Ed25519 signature valid; certificate schema and certificate_id verified",
    )


def sign_certificate_file_ed25519(
    certificate_path: Path,
    pair: Ed25519KeyPair,
    output_path: Path | None = None,
) -> Path:
    cert = read_json(certificate_path)
    signed = sign_certificate_ed25519(cert, pair)
    if output_path is None:
        output_path = certificate_path.parent / f"{certificate_path.stem}.ed25519.json"
    atomic_write_json(output_path, signed.to_dict())
    return output_path


def verify_rejects_hmac_blob(data: dict[str, Any]) -> None:
    """Fail closed when an HMAC authenticated blob is passed to Ed25519 verify."""
    algo = data.get("algorithm")
    if isinstance(algo, str) and algo.startswith("hmac-"):
        raise SigningError(
            "refusing to Ed25519-verify an HMAC authenticated blob; "
            "use verify-signature --scheme hmac"
        )
