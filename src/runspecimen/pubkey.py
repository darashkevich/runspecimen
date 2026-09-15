"""Optional Ed25519 public-key signatures for RunSpecimen receipts.

Requires the optional dependency::

    python3 -m pip install 'runspecimen[ed25519]'
    # or: python3 -m pip install 'runspecimen[signing]'

This provides offline public-key verification without sharing the private key.
It does **not** provide absolute non-repudiation (soft keys on disk; custody
matters) and does **not** prove scientific or engineering claims.

HMAC-SHA256 in ``signing.py`` remains the shared-secret authentication path.
An HMAC MAC cannot satisfy Ed25519 verification, and vice versa.

Trust model
-----------
A signature that verifies under a public key *embedded in the signed document*
proves only **signature consistency** (the receipt is self-consistent under
that key). That is **not** trusted success: an attacker can forge a receipt,
embed their own public key, and sign it.

**Trusted success** requires verifying against an **externally trusted** public
key (user-supplied file, workspace ``*.ed25519.pub`` from a prior trusted
keygen, or another explicit trust policy). The CLI refuses to report
``ok: true`` without such a trust anchor.
"""

from __future__ import annotations

import os
import stat
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
            "(or 'runspecimen[signing]'; Community/default installs remain "
            "stdlib-only without this extra)."
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


def _validate_keys_dir_security(workspace: Path) -> Path:
    """Reject symlinked control-plane / keys directories (same posture as HMAC)."""
    workspace = workspace.resolve()
    control_plane = workspace / ".runspecimen"
    kdir = control_plane / "keys"

    if control_plane.exists() and control_plane.is_symlink():
        raise SigningError(
            f".runspecimen must not be a symlink: {control_plane} -> {control_plane.resolve()}"
        )
    if kdir.exists() and kdir.is_symlink():
        raise SigningError(
            f"keys directory must not be a symlink: {kdir} -> {kdir.resolve()}"
        )
    return kdir


def _exclusive_create_flags() -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _write_exclusive_bytes(path: Path, data: bytes, *, mode: int) -> None:
    """Create ``path`` exclusively with ``mode`` from creation; refuse symlinks.

    Uses O_CREAT|O_EXCL(|O_NOFOLLOW) so the mode applies at create time and
    existing files / symlink destinations cannot be overwritten in place.
    """
    if path.is_symlink():
        raise SigningError(f"refusing to write through symlink: {path}")
    try:
        fd = os.open(str(path), _exclusive_create_flags(), mode)
    except FileExistsError as exc:
        raise SigningError(f"refusing to overwrite existing path: {path}") from exc
    except OSError as exc:
        # Some platforms surface ELOOP / EEXIST for symlink races.
        raise SigningError(f"failed to create key file {path}: {exc}") from exc
    try:
        # Re-check mode in case umask cleared bits; restore intended mode.
        os.fchmod(fd, mode)
        os.write(fd, data)
    finally:
        os.close(fd)


def _assert_regular_file(path: Path, *, label: str) -> None:
    if path.is_symlink():
        raise SigningError(f"{label} must not be a symlink: {path}")
    if not path.is_file():
        raise SigningError(f"{label} not found: {path}")
    try:
        st = path.lstat()
    except OSError as exc:
        raise SigningError(f"cannot stat {label}: {path}: {exc}") from exc
    if stat.S_ISLNK(st.st_mode):
        raise SigningError(f"{label} must not be a symlink: {path}")
    if not stat.S_ISREG(st.st_mode):
        raise SigningError(f"{label} must be a regular file: {path}")


def _assert_private_key_permissions(path: Path) -> None:
    """Refuse group/other-readable private key files."""
    st = path.lstat()
    if st.st_mode & 0o077:
        raise SigningError(
            f"Ed25519 private key permissions too open (want 0600): {path} "
            f"mode={oct(st.st_mode & 0o777)}"
        )


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
    """Result of Ed25519 verification with an explicit trust distinction.

    ``signature_consistent`` means the signature verifies under the key used
    for the crypto check (trusted key when supplied, otherwise the embedded
    key). ``trusted`` is True only when an externally supplied trust anchor
    was used and the signature verified under that key.

    ``ok`` / trusted success requires ``trusted`` plus schema checks — never
    embedded-key-only consistency.
    """

    signature_consistent: bool
    schema_valid: bool
    certificate_id_valid: bool
    public_key_match: bool
    trusted: bool
    message: str

    @property
    def signature_valid(self) -> bool:
        """Alias for signature_consistent (CLI / older callers)."""
        return self.signature_consistent

    @property
    def ok(self) -> bool:
        return (
            self.trusted
            and self.signature_consistent
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
    """Persist private (0600 from creation) and public key files.

    Returns (private, public) paths. Refuses symlink paths and uses exclusive
    create (O_EXCL|O_NOFOLLOW when available).
    """
    require_ed25519()
    workspace = workspace.resolve()
    kdir = _validate_keys_dir_security(workspace)
    ensure_dir(kdir)
    _validate_keys_dir_security(workspace)

    priv = private_key_path(workspace, pair.key_id)
    pub = public_key_path(workspace, pair.key_id)

    for path, label in ((priv, "private key"), (pub, "public key")):
        if path.is_symlink():
            raise SigningError(f"refusing to write {label} through symlink: {path}")
        if path.exists() and not overwrite:
            raise SigningError(
                f"Ed25519 key {pair.key_id!r} already exists; pass overwrite to rotate"
            )
        if path.exists() and overwrite:
            if path.is_symlink():
                raise SigningError(f"refusing to overwrite symlink {label}: {path}")
            try:
                path.unlink()
            except OSError as exc:
                raise SigningError(f"failed to remove existing {label}: {exc}") from exc

    _write_exclusive_bytes(priv, (pair.private_hex() + "\n").encode("utf-8"), mode=0o600)
    _write_exclusive_bytes(pub, (pair.public_hex() + "\n").encode("utf-8"), mode=0o644)
    return priv, pub


def load_ed25519_public_key_bytes(workspace: Path, key_id: str) -> bytes:
    """Load only the public key file (never opens the private seed)."""
    require_ed25519()
    workspace = workspace.resolve()
    _validate_keys_dir_security(workspace)
    pub = public_key_path(workspace, key_id)
    _assert_regular_file(pub, label=f"Ed25519 public key {key_id!r}")
    try:
        return bytes.fromhex(pub.read_text(encoding="utf-8").strip())
    except ValueError as exc:
        raise SigningError(f"invalid Ed25519 public key encoding for {key_id}: {exc}") from exc


def load_ed25519_keypair(workspace: Path, key_id: str) -> Ed25519KeyPair:
    require_ed25519()
    workspace = workspace.resolve()
    _validate_keys_dir_security(workspace)
    priv = private_key_path(workspace, key_id)
    pub = public_key_path(workspace, key_id)
    _assert_regular_file(priv, label=f"Ed25519 private key {key_id!r}")
    _assert_regular_file(pub, label=f"Ed25519 public key {key_id!r}")
    _assert_private_key_permissions(priv)
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
    _assert_regular_file(path, label="Ed25519 public key file")
    try:
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise SigningError(f"cannot load Ed25519 public key from {path}: {exc}") from exc


def export_ed25519_public_key(workspace: Path, key_id: str, output: Path) -> Path:
    """Export the workspace public key file without reading the private seed."""
    public = load_ed25519_public_key_bytes(workspace, key_id)
    output = output.resolve()
    if output.is_symlink():
        raise SigningError(f"refusing to write public key through symlink: {output}")
    if output.exists():
        if output.is_symlink():
            raise SigningError(f"refusing to overwrite symlink: {output}")
        output.unlink()
    _write_exclusive_bytes(output, (public.hex() + "\n").encode("utf-8"), mode=0o644)
    return output


def list_ed25519_key_ids(workspace: Path) -> list[str]:
    workspace = workspace.resolve()
    try:
        kdir = _validate_keys_dir_security(workspace)
    except SigningError:
        raise
    if not kdir.is_dir() or kdir.is_symlink():
        return []
    ids: list[str] = []
    for path in kdir.iterdir():
        if path.name.endswith(_PRIVATE_SUFFIX) and not path.name.endswith(_PUBLIC_SUFFIX):
            key_id = path.name[: -len(_PRIVATE_SUFFIX)]
            try:
                validate_key_id(key_id)
            except SigningError:
                continue
            pub = public_key_path(workspace, key_id)
            if pub.is_file() and not pub.is_symlink() and not path.is_symlink():
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
    """Verify Ed25519 signature with an explicit trust distinction.

    When ``public_key`` is omitted, only **signature consistency** against the
    embedded key is evaluated; ``trusted`` and ``ok`` remain False.

    When ``public_key`` is supplied (externally trusted), trusted success
    requires the signature to verify under that key and match the embedded
    public key field.
    """
    nacl_signing = require_ed25519()

    try:
        assert_supported_receipt_schema(signed.certificate)
        ok, msg = validate_certificate_schema(signed.certificate)
    except Exception as exc:  # noqa: BLE001 — surface as verify result
        return Ed25519VerifyResult(
            signature_consistent=False,
            schema_valid=False,
            certificate_id_valid=False,
            public_key_match=False,
            trusted=False,
            message=str(exc),
        )
    if not ok:
        return Ed25519VerifyResult(
            signature_consistent=False,
            schema_valid=False,
            certificate_id_valid=False,
            public_key_match=False,
            trusted=False,
            message=msg,
        )

    try:
        embedded = bytes.fromhex(signed.public_key)
    except ValueError:
        return Ed25519VerifyResult(
            False,
            True,
            True,
            False,
            False,
            "embedded public_key is not valid hex",
        )

    trusted_anchor = public_key is not None
    if trusted_anchor:
        assert public_key is not None
        pub_match = public_key == embedded
        if not pub_match:
            return Ed25519VerifyResult(
                False,
                True,
                True,
                False,
                False,
                "trusted public key does not match signed document public_key",
            )
        verify_bytes = public_key
    else:
        pub_match = True  # no external key to disagree with
        verify_bytes = embedded

    try:
        sig = bytes.fromhex(signed.signature)
        vk = nacl_signing.VerifyKey(verify_bytes)
        vk.verify(canonical_json_bytes(signed.certificate), sig)
    except Exception as exc:  # noqa: BLE001
        return Ed25519VerifyResult(
            False,
            True,
            True,
            pub_match,
            False,
            f"signature verification failed: {exc}",
        )

    if not trusted_anchor:
        return Ed25519VerifyResult(
            True,
            True,
            True,
            True,
            False,
            "signature consistent with embedded public key only; "
            "not trusted without an external trust anchor "
            "(--public-key or workspace key id)",
        )

    return Ed25519VerifyResult(
        True,
        True,
        True,
        True,
        True,
        "Ed25519 signature valid under trusted public key; "
        "certificate schema and certificate_id verified",
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
