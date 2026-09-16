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

import contextlib
import json
import os
import secrets
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.errors import SigningError
from runspecimen.hashutil import canonical_json_bytes
from runspecimen.paths import ensure_dir
from runspecimen.schema import assert_supported_receipt_schema
from runspecimen.signing import (
    validate_certificate_schema,
    validate_key_id,
)

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]

ED25519_ALGORITHM = "ed25519-v1"
_PRIVATE_SUFFIX = ".ed25519"
_PUBLIC_SUFFIX = ".ed25519.pub"
_ROTATE_TMP_MARK = ".rotating"
_ROTATE_BAK_MARK = ".bak"
_KEYS_LOCK_NAME = "keys.op.lock"
_JOURNAL_SUFFIX = ".ed25519.rotate.journal"
_JOURNAL_VERSION = 1

# Test-only hook: called after durable journal commits at named phases.
# Production code never sets this. Fault-injection tests may SIGKILL here.
_CRASH_AFTER_PHASE: Callable[[str], None] | None = None


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


def _readonly_nofollow_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _is_symlink_open_error(exc: OSError) -> bool:
    """True when open(O_NOFOLLOW) refused a symlink (ELOOP) or equivalent."""
    import errno as errno_mod

    errno = getattr(exc, "errno", None)
    return errno in {errno_mod.ELOOP, errno_mod.EPERM} or "symbolic link" in str(exc).lower()


def _write_exclusive_bytes(path: Path, data: bytes, *, mode: int) -> None:
    """Create ``path`` exclusively with ``mode`` from creation; refuse symlinks.

    Uses O_CREAT|O_EXCL(|O_NOFOLLOW) so the mode applies at create time and
    existing files / symlink destinations cannot be overwritten in place.
    Data is fsynced before the fd is closed.
    """
    if path.is_symlink():
        raise SigningError(f"refusing to write through symlink: {path}")
    try:
        fd = os.open(str(path), _exclusive_create_flags(), mode)
    except FileExistsError as exc:
        raise SigningError(f"refusing to overwrite existing path: {path}") from exc
    except OSError as exc:
        if _is_symlink_open_error(exc):
            raise SigningError(f"refusing to write through symlink: {path}") from exc
        raise SigningError(f"failed to create key file {path}: {exc}") from exc
    try:
        # Re-check mode in case umask cleared bits; restore intended mode.
        os.fchmod(fd, mode)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise SigningError(f"key path is not a regular file after create: {path}")
        os.write(fd, data)
        os.fsync(fd)
    except Exception:
        os.close(fd)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    else:
        os.close(fd)


def _read_nofollow_bytes(
    path: Path,
    *,
    label: str,
    require_private_perms: bool = False,
) -> bytes:
    """Open ``path`` without following symlinks; validate the opened fd, then read.

    Closes the check-then-read race: type and permission checks use ``fstat`` on
    the same fd that is read, not a separate path-based ``lstat``.
    """
    try:
        fd = os.open(str(path), _readonly_nofollow_flags())
    except FileNotFoundError as exc:
        raise SigningError(f"{label} not found: {path}") from exc
    except OSError as exc:
        if _is_symlink_open_error(exc) or path.is_symlink():
            raise SigningError(f"{label} must not be a symlink: {path}") from exc
        raise SigningError(f"cannot open {label}: {path}: {exc}") from exc
    try:
        st = os.fstat(fd)
        if stat.S_ISLNK(st.st_mode):
            raise SigningError(f"{label} must not be a symlink: {path}")
        if not stat.S_ISREG(st.st_mode):
            raise SigningError(f"{label} must be a regular file: {path}")
        if require_private_perms and (st.st_mode & 0o077):
            raise SigningError(
                f"Ed25519 private key permissions too open (want 0600): {path} "
                f"mode={oct(st.st_mode & 0o777)}"
            )
        chunks: list[bytes] = []
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            chunks.append(block)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _fsync_dir(dir_path: Path) -> None:
    try:
        dir_fd = os.open(str(dir_path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def _unique_sidecar(path: Path, mark: str) -> Path:
    token = f"{int(time.time_ns())}.{os.getpid()}.{secrets.token_hex(4)}"
    return path.with_name(f".{path.name}{mark}.{token}")


def _rename_nofollow(src: Path, dst: Path) -> None:
    """Rename ``src`` → ``dst``; refuse if either path is a symlink."""
    if src.is_symlink() or dst.is_symlink():
        raise SigningError(f"refusing rename involving symlink: {src} -> {dst}")
    if dst.exists():
        raise SigningError(f"refusing rename onto existing path: {dst}")
    try:
        os.rename(str(src), str(dst))
    except OSError as exc:
        raise SigningError(f"failed to rename {src} -> {dst}: {exc}") from exc


def _replace_file(src: Path, dst: Path) -> None:
    """Atomically replace ``dst`` with ``src`` (POSIX ``rename`` over existing)."""
    if src.is_symlink() or (dst.exists() and dst.is_symlink()):
        raise SigningError(f"refusing replace involving symlink: {src} -> {dst}")
    try:
        os.replace(str(src), str(dst))
    except OSError as exc:
        raise SigningError(f"failed to replace {dst} with {src}: {exc}") from exc


def _unlink_quiet(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _path_is_present(path: Path) -> bool:
    """True if path exists including as a broken symlink."""
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return path.exists() or path.is_symlink()


def _maybe_crash(phase: str) -> None:
    """Invoke the optional test crash hook after a durable phase commit."""
    hook = _CRASH_AFTER_PHASE
    if hook is not None:
        hook(phase)


def _keys_lock_path(workspace: Path) -> Path:
    return workspace.resolve() / ".runspecimen" / _KEYS_LOCK_NAME


def _ensure_control_plane(workspace: Path) -> Path:
    """Ensure ``.runspecimen`` exists and is not a symlink; return its path."""
    workspace = workspace.resolve()
    control = workspace / ".runspecimen"
    if control.exists() and control.is_symlink():
        raise SigningError(
            f".runspecimen must not be a symlink: {control} -> {control.resolve()}"
        )
    if not control.exists():
        try:
            control.mkdir(mode=0o755, exist_ok=True)
        except OSError as exc:
            raise SigningError(f"cannot create control plane {control}: {exc}") from exc
    if control.is_symlink():
        raise SigningError(
            f".runspecimen must not be a symlink: {control} -> {control.resolve()}"
        )
    return control


@contextlib.contextmanager
def hold_keys_dir_lock(
    workspace: Path,
    *,
    blocking: bool = True,
) -> Iterator[None]:
    """Exclusive cross-process lock for key-directory create/list/rotate/load/sign I/O.

    Serializes concurrent Ed25519 key operations so directory creation, listing,
    rotation, and reads cannot interleave mid-mutation. Uses ``fcntl.flock`` on
    ``.runspecimen/keys.op.lock`` (same posture as the execution lease).
    """
    if fcntl is None:
        raise SigningError("Ed25519 key locks require a POSIX platform with fcntl")
    control = _ensure_control_plane(workspace)
    lock_path = control / _KEYS_LOCK_NAME
    lock_path.touch(exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR)
    flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        fcntl.flock(fd, flags)
    except OSError as exc:
        os.close(fd)
        raise SigningError(
            "Ed25519 keys directory is busy (another process holds keys.op.lock)"
        ) from exc
    try:
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _rotation_journal_path(workspace: Path, key_id: str) -> Path:
    validate_key_id(key_id)
    return keys_dir(workspace) / f".{key_id}{_JOURNAL_SUFFIX}"


def _write_rotation_journal(path: Path, payload: dict[str, Any]) -> None:
    """Durably write the rotation journal (exclusive create or atomic replace)."""
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    parent = path.parent
    ensure_dir(parent)
    tmp = _unique_sidecar(path, _ROTATE_TMP_MARK + "-journal")
    try:
        _write_exclusive_bytes(tmp, data, mode=0o644)
        os.replace(str(tmp), str(path))
        _fsync_dir(parent)
    except Exception:
        _unlink_quiet(tmp)
        raise


def _read_rotation_journal(path: Path) -> dict[str, Any] | None:
    if not _path_is_present(path):
        return None
    try:
        raw = _read_nofollow_bytes(path, label="Ed25519 rotation journal")
        data = json.loads(raw.decode("utf-8"))
    except (SigningError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _restore_from_bak(bak: Path | None, final: Path) -> None:
    if bak is None or not _path_is_present(bak):
        return
    if _path_is_present(final) and not final.is_symlink():
        _unlink_quiet(final)
    try:
        _rename_nofollow(bak, final)
    except SigningError:
        # Last resort: replace if rename blocked by leftover final.
        if _path_is_present(bak):
            try:
                os.replace(str(bak), str(final))
            except OSError:
                pass


def _recover_one_rotation_journal(workspace: Path, journal_path: Path) -> str:
    """Recover a single interrupted rotation. Returns action taken."""
    data = _read_rotation_journal(journal_path)
    if data is None:
        _unlink_quiet(journal_path)
        return "discarded_corrupt_journal"

    key_id = str(data.get("key_id") or "")
    phase = str(data.get("phase") or "")
    try:
        validate_key_id(key_id)
    except SigningError:
        _unlink_quiet(journal_path)
        return "discarded_invalid_key_id"

    priv = private_key_path(workspace, key_id)
    pub = public_key_path(workspace, key_id)
    priv_tmp = Path(str(data["priv_tmp"])) if data.get("priv_tmp") else None
    pub_tmp = Path(str(data["pub_tmp"])) if data.get("pub_tmp") else None
    priv_bak = Path(str(data["priv_bak"])) if data.get("priv_bak") else None
    pub_bak = Path(str(data["pub_bak"])) if data.get("pub_bak") else None

    # All-or-nothing: until both new finals are installed, roll back to the
    # previous working pair. After priv_installed, complete cleanup only.
    if phase in {"intent", "staged", ""}:
        _unlink_quiet(priv_tmp)
        _unlink_quiet(pub_tmp)
        _unlink_quiet(journal_path)
        return f"rolled_back_pre_commit:{key_id}"

    if phase == "fresh_priv_installed":
        # Fresh create crashed after private install — drop incomplete pair.
        _unlink_quiet(priv)
        _unlink_quiet(pub)
        _unlink_quiet(priv_tmp)
        _unlink_quiet(pub_tmp)
        _unlink_quiet(journal_path)
        return f"rolled_back_fresh_incomplete:{key_id}"

    if phase in {"pub_backed", "pub_installed", "priv_backed"}:
        # Prefer old pair from bak sidecars; never leave a mixed new/old pair.
        _unlink_quiet(priv_tmp)
        _unlink_quiet(pub_tmp)
        if phase == "priv_backed" or (
            phase == "pub_installed" and priv_bak is not None and _path_is_present(priv_bak)
        ):
            _restore_from_bak(priv_bak, priv)
        elif phase == "pub_installed" and not _path_is_present(priv):
            # Should not happen with ordered steps, but restore if possible.
            _restore_from_bak(priv_bak, priv)
        # Always restore old public when we have a bak (new public may be live).
        _restore_from_bak(pub_bak, pub)
        # If pub was backed up but not yet replaced, pub_bak restore is enough.
        # If only pub_backed and final pub missing, restore covers it.
        if phase == "pub_backed" and not _path_is_present(pub):
            _restore_from_bak(pub_bak, pub)
        if not _path_is_present(priv) and priv_bak is not None:
            _restore_from_bak(priv_bak, priv)
        _unlink_quiet(priv_bak)
        _unlink_quiet(pub_bak)
        _unlink_quiet(journal_path)
        return f"rolled_back_to_previous:{key_id}:{phase}"

    if phase in {"priv_installed", "complete"}:
        # New pair is fully installed; drop leftovers and journal.
        _unlink_quiet(priv_tmp)
        _unlink_quiet(pub_tmp)
        _unlink_quiet(priv_bak)
        _unlink_quiet(pub_bak)
        _unlink_quiet(journal_path)
        return f"committed_cleanup:{key_id}"

    # Unknown phase: safest is roll back if baks exist, else drop temps.
    _unlink_quiet(priv_tmp)
    _unlink_quiet(pub_tmp)
    _restore_from_bak(priv_bak, priv)
    _restore_from_bak(pub_bak, pub)
    _unlink_quiet(priv_bak)
    _unlink_quiet(pub_bak)
    _unlink_quiet(journal_path)
    return f"rolled_back_unknown_phase:{key_id}:{phase}"


def recover_interrupted_ed25519_keys(workspace: Path) -> list[str]:
    """Automatically resume/roll back crash-interrupted Ed25519 rotations.

    Scans the keys directory for durable rotation journals and orphaned
    ``.bak`` / ``.rotating`` sidecars. Safe to call on every open/use; holds the
    keys-directory lock.
    """
    workspace = workspace.resolve()
    actions: list[str] = []
    with hold_keys_dir_lock(workspace):
        actions.extend(_recover_interrupted_ed25519_keys_unlocked(workspace))
    return actions


def _recover_interrupted_ed25519_keys_unlocked(workspace: Path) -> list[str]:
    actions: list[str] = []
    try:
        kdir = _validate_keys_dir_security(workspace)
    except SigningError:
        return actions
    if not kdir.is_dir() or kdir.is_symlink():
        return actions

    journals = sorted(
        p for p in kdir.iterdir() if p.name.startswith(".") and p.name.endswith(_JOURNAL_SUFFIX)
    )
    for journal_path in journals:
        actions.append(_recover_one_rotation_journal(workspace, journal_path))

    # Orphaned sidecars without a journal: restore bak when the live final is
    # missing; otherwise drop leftover rotating temps / committed baks.
    for path in sorted(kdir.iterdir()):
        name = path.name
        if not name.startswith("."):
            continue
        if name.endswith(_JOURNAL_SUFFIX):
            continue
        if _ROTATE_TMP_MARK in name:
            _unlink_quiet(path)
            actions.append(f"dropped_orphan_temp:{name}")
            continue
        # Sidecar: .{final_name}.bak-priv.{token} or .{final_name}.bak-pub.{token}
        for kind in ("bak-priv", "bak-pub"):
            needle = f".{kind}."
            if needle not in name:
                continue
            # name = ".{final}.{kind}.{token}" → strip leading "." then split
            body = name[1:]
            final_name, _sep, _rest = body.partition(needle)
            if not final_name:
                break
            final = kdir / final_name
            if not _path_is_present(final):
                _restore_from_bak(path, final)
                actions.append(f"restored_orphan_bak:{final_name}")
            else:
                _unlink_quiet(path)
                actions.append(f"dropped_orphan_bak:{name}")
            break
    return actions


def _commit_phase(
    journal_path: Path,
    base: dict[str, Any],
    phase: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(base)
    payload["phase"] = phase
    if extra:
        payload.update(extra)
    _write_rotation_journal(journal_path, payload)
    _maybe_crash(phase)
    return payload


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

    Rotation (``overwrite=True``) is crash-safe and all-or-nothing:
    a durable journal plus exclusive temps/backups record each transition so a
    killed process can automatically roll back to the previous working pair (or
    finish cleanup after both new finals are installed) on the next open/use.
    Concurrent key operations are excluded via ``keys.op.lock``.
    """
    require_ed25519()
    workspace = workspace.resolve()
    with hold_keys_dir_lock(workspace):
        _recover_interrupted_ed25519_keys_unlocked(workspace)
        return _save_ed25519_keypair_unlocked(workspace, pair, overwrite=overwrite)


def _save_ed25519_keypair_unlocked(
    workspace: Path,
    pair: Ed25519KeyPair,
    *,
    overwrite: bool,
) -> tuple[Path, Path]:
    kdir = _validate_keys_dir_security(workspace)
    ensure_dir(kdir)
    _validate_keys_dir_security(workspace)

    priv = private_key_path(workspace, pair.key_id)
    pub = public_key_path(workspace, pair.key_id)

    for path, label in ((priv, "private key"), (pub, "public key")):
        if path.is_symlink():
            raise SigningError(f"refusing to write {label} through symlink: {path}")

    priv_exists = _path_is_present(priv)
    pub_exists = _path_is_present(pub)
    if (priv_exists or pub_exists) and not overwrite:
        raise SigningError(
            f"Ed25519 key {pair.key_id!r} already exists; pass overwrite to rotate"
        )

    priv_data = (pair.private_hex() + "\n").encode("utf-8")
    pub_data = (pair.public_hex() + "\n").encode("utf-8")

    priv_tmp = _unique_sidecar(priv, _ROTATE_TMP_MARK + "-priv")
    pub_tmp = _unique_sidecar(pub, _ROTATE_TMP_MARK + "-pub")
    journal_path = _rotation_journal_path(workspace, pair.key_id)
    priv_bak: Path | None = None
    pub_bak: Path | None = None

    base_journal: dict[str, Any] = {
        "version": _JOURNAL_VERSION,
        "key_id": pair.key_id,
        "phase": "intent",
        "priv_tmp": str(priv_tmp),
        "pub_tmp": str(pub_tmp),
        "priv_bak": None,
        "pub_bak": None,
    }

    def _rollback_in_process() -> None:
        if priv_bak is not None and _path_is_present(priv_bak):
            if _path_is_present(priv) and not priv.is_symlink():
                _unlink_quiet(priv)
            try:
                _rename_nofollow(priv_bak, priv)
            except SigningError:
                pass
        if pub_bak is not None and _path_is_present(pub_bak):
            if _path_is_present(pub) and not pub.is_symlink():
                _unlink_quiet(pub)
            try:
                _rename_nofollow(pub_bak, pub)
            except SigningError:
                pass
        _unlink_quiet(priv_tmp)
        _unlink_quiet(pub_tmp)
        _unlink_quiet(journal_path)

    try:
        _commit_phase(journal_path, base_journal, "intent")
        _write_exclusive_bytes(priv_tmp, priv_data, mode=0o600)
        _write_exclusive_bytes(pub_tmp, pub_data, mode=0o644)
        _fsync_dir(kdir)
        _commit_phase(journal_path, base_journal, "staged")

        if not priv_exists and not pub_exists:
            # Fresh create: journal each install so a crash cannot leave a
            # private-only orphan that recovery would treat as a working key.
            _rename_nofollow(priv_tmp, priv)
            base_journal = _commit_phase(journal_path, base_journal, "fresh_priv_installed")
            try:
                _rename_nofollow(pub_tmp, pub)
            except Exception:
                _unlink_quiet(priv)
                raise
            _fsync_dir(kdir)
            _commit_phase(journal_path, base_journal, "complete")
            _unlink_quiet(journal_path)
            _maybe_crash("fresh_complete")
            return priv, pub

        # Rotation transitions (journal fsynced before each dangerous window):
        # pub_backed → pub_installed → priv_backed → priv_installed → complete
        if pub_exists:
            pub_bak = _unique_sidecar(pub, _ROTATE_BAK_MARK + "-pub")
            _rename_nofollow(pub, pub_bak)
            base_journal = _commit_phase(
                journal_path, base_journal, "pub_backed", extra={"pub_bak": str(pub_bak)}
            )
        try:
            _rename_nofollow(pub_tmp, pub)
        except Exception:
            if pub_bak is not None:
                _rename_nofollow(pub_bak, pub)
                pub_bak = None
            raise
        base_journal = _commit_phase(journal_path, base_journal, "pub_installed")

        if priv_exists:
            priv_bak = _unique_sidecar(priv, _ROTATE_BAK_MARK + "-priv")
            _rename_nofollow(priv, priv_bak)
            base_journal = _commit_phase(
                journal_path,
                base_journal,
                "priv_backed",
                extra={"priv_bak": str(priv_bak)},
            )
        try:
            _rename_nofollow(priv_tmp, priv)
        except Exception:
            _unlink_quiet(priv)
            if priv_bak is not None:
                _rename_nofollow(priv_bak, priv)
                priv_bak = None
            _unlink_quiet(pub)
            if pub_bak is not None:
                _rename_nofollow(pub_bak, pub)
                pub_bak = None
            raise
        base_journal = _commit_phase(journal_path, base_journal, "priv_installed")

        _unlink_quiet(priv_bak)
        _unlink_quiet(pub_bak)
        priv_bak = None
        pub_bak = None
        _fsync_dir(kdir)
        _commit_phase(journal_path, base_journal, "complete")
        _unlink_quiet(journal_path)
        return priv, pub
    except Exception:
        _rollback_in_process()
        raise


def load_ed25519_public_key_bytes(workspace: Path, key_id: str) -> bytes:
    """Load only the public key file (never opens the private seed)."""
    require_ed25519()
    workspace = workspace.resolve()
    with hold_keys_dir_lock(workspace):
        _recover_interrupted_ed25519_keys_unlocked(workspace)
        return _load_ed25519_public_key_bytes_unlocked(workspace, key_id)


def load_ed25519_keypair(workspace: Path, key_id: str) -> Ed25519KeyPair:
    require_ed25519()
    workspace = workspace.resolve()
    with hold_keys_dir_lock(workspace):
        _recover_interrupted_ed25519_keys_unlocked(workspace)
        _validate_keys_dir_security(workspace)
        priv = private_key_path(workspace, key_id)
        pub = public_key_path(workspace, key_id)
        try:
            seed = bytes.fromhex(
                _read_nofollow_bytes(
                    priv,
                    label=f"Ed25519 private key {key_id!r}",
                    require_private_perms=True,
                )
                .decode("utf-8")
                .strip()
            )
            public = bytes.fromhex(
                _read_nofollow_bytes(pub, label=f"Ed25519 public key {key_id!r}")
                .decode("utf-8")
                .strip()
            )
        except ValueError as exc:
            raise SigningError(f"invalid Ed25519 key encoding for {key_id}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise SigningError(f"invalid Ed25519 key encoding for {key_id}: {exc}") from exc
        nacl_signing = require_ed25519()
        sk = nacl_signing.SigningKey(seed)
        if bytes(sk.verify_key) != public:
            raise SigningError(
                f"Ed25519 public key does not match private seed for {key_id}"
            )
        return Ed25519KeyPair(key_id=key_id, private_seed=seed, public_key=public)


def load_ed25519_public_key_file(path: Path) -> bytes:
    require_ed25519()
    try:
        raw = _read_nofollow_bytes(path, label="Ed25519 public key file")
        return bytes.fromhex(raw.decode("utf-8").strip())
    except SigningError:
        raise
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise SigningError(f"cannot load Ed25519 public key from {path}: {exc}") from exc


def export_ed25519_public_key(workspace: Path, key_id: str, output: Path) -> Path:
    """Export the workspace public key file without reading the private seed."""
    with hold_keys_dir_lock(workspace):
        _recover_interrupted_ed25519_keys_unlocked(workspace.resolve())
        public = _load_ed25519_public_key_bytes_unlocked(workspace.resolve(), key_id)
    output = output.resolve()
    if output.is_symlink():
        raise SigningError(f"refusing to write public key through symlink: {output}")
    if _path_is_present(output):
        if output.is_symlink():
            raise SigningError(f"refusing to overwrite symlink: {output}")
        tmp = _unique_sidecar(output, _ROTATE_TMP_MARK + "-export")
        try:
            _write_exclusive_bytes(tmp, (public.hex() + "\n").encode("utf-8"), mode=0o644)
            _replace_file(tmp, output)
        except Exception:
            _unlink_quiet(tmp)
            raise
        return output
    _write_exclusive_bytes(output, (public.hex() + "\n").encode("utf-8"), mode=0o644)
    return output


def _load_ed25519_public_key_bytes_unlocked(workspace: Path, key_id: str) -> bytes:
    _validate_keys_dir_security(workspace)
    pub = public_key_path(workspace, key_id)
    try:
        raw = _read_nofollow_bytes(pub, label=f"Ed25519 public key {key_id!r}")
        return bytes.fromhex(raw.decode("utf-8").strip())
    except ValueError as exc:
        raise SigningError(f"invalid Ed25519 public key encoding for {key_id}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise SigningError(f"invalid Ed25519 public key encoding for {key_id}: {exc}") from exc


def list_ed25519_key_ids(workspace: Path) -> list[str]:
    workspace = workspace.resolve()
    with hold_keys_dir_lock(workspace):
        _recover_interrupted_ed25519_keys_unlocked(workspace)
        try:
            kdir = _validate_keys_dir_security(workspace)
        except SigningError:
            raise
        if not kdir.is_dir() or kdir.is_symlink():
            return []
        ids: list[str] = []
        for path in kdir.iterdir():
            if path.name.endswith(_PRIVATE_SUFFIX) and not path.name.endswith(_PUBLIC_SUFFIX):
                if path.name.startswith("."):
                    continue
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
