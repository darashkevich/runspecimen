"""Developer ID execution holder core.

This is the state machine a separate Developer ID product would run. It is
not installed, not registered, and not a Mac App Store component. The Store
app does not gain this guarantee by importing the module.

An unprivileged test adapter may construct it with ``allow_test_double``.
That adapter runs as the same user, so a passing test is not installed
protection. A typed phrase is never an authorization method. An imported
label such as ``secure-enclave`` is unverified unless this device performed
the enrollment. Administrator or root can still defeat the holder, including an
installed root daemon. That is documented, not denied.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sys
import pwd
import select
import subprocess
import time
from pathlib import Path
from typing import Any

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.hashutil import canonical_json_bytes
from runspecimen.holder_protocol import LaunchRequest, ProtocolError, bind_execution
from runspecimen.paths import ensure_within

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

PROTOCOL = 1
DEVICE_CHALLENGE_DOMAIN = "holder-device-p256-v1"
EXACT_RUN_DOMAIN = "holder-exact-run-v1"
PHONE_RECEIPT_DOMAIN = "holder-phone-receipt-v1"
PHONE_RECEIPT_OUTCOME = "verified-consumed"


def bound_device_message(
    *,
    holder_id: str,
    generation: int,
    role: str,
    expiry: int,
    nonce: str,
    challenge: bytes,
) -> bytes:
    """Canonical bytes a device signature must cover.

    Comparison of these bytes is not signature verification and not hardware
    provenance. ``verify_native_p256`` is the verification step.
    """

    return canonical_json_bytes(
        {
            "challenge": base64.b64encode(challenge).decode("ascii"),
            "domain": DEVICE_CHALLENGE_DOMAIN,
            "expiry": int(expiry),
            "generation": int(generation),
            "holder_id": holder_id,
            "nonce": nonce,
            "role": role,
        }
    )


def bound_phone_receipt(
    *,
    holder_id: str,
    generation: int,
    challenge_id: str,
    challenge: str,
    phone_fingerprint: str,
    mac_public_key: str,
) -> bytes:
    """Canonical holder receipt. A caller verified flag is not this message."""

    return canonical_json_bytes(
        {
            "challenge": challenge,
            "challenge_id": challenge_id,
            "domain": PHONE_RECEIPT_DOMAIN,
            "generation": int(generation),
            "holder_id": holder_id,
            "mac_public_key": mac_public_key,
            "outcome": PHONE_RECEIPT_OUTCOME,
            "phone_fingerprint": phone_fingerprint,
        }
    )


def bound_exact_run(
    *,
    holder_id: str,
    payload_digest: str,
    launch_argv: list[str],
    nonce: str,
    policy: str,
    generation: int,
    key_generation: int,
    expiry: int,
) -> bytes:
    """Canonical bytes for one bounded run. This is not an enrollment challenge.

    The signature covers policy, enrollment generation, key generation, and
    expiry as well as the snapshot payload and launch. Reaching consume and
    execute from this message is not a completed production run.
    """

    return canonical_json_bytes(
        {
            "domain": EXACT_RUN_DOMAIN,
            "expiry": int(expiry),
            "generation": int(generation),
            "holder_id": holder_id,
            "key_generation": int(key_generation),
            "launch_argv": list(launch_argv),
            "nonce": nonce,
            "payload_digest": payload_digest,
            "policy": policy,
        }
    )


POLICIES = frozenset({"local", "companion", "dual"})
_PHRASE = "APPROVE"
_DEVICES = {
    "local": frozenset({"mac"}),
    "companion": frozenset({"phone"}),
    "dual": frozenset({"mac", "phone"}),
}
_RESIDUALS = (
    "The dynamic linker and system libraries are not part of the snapshot.",
    "A system interpreter outside the workspace stays live; only its digest is bound.",
    "Relative writes still use the live workspace cwd; only named workspace inputs are snapshotted.",
    "Administrator or root can still defeat this holder.",
    "Unprivileged tests do not prove installed protection.",
    "A software test double is not hardware and is refused when installed_protection is set.",
)


class HolderRefusal(Exception):
    """The holder will not change state or authorize a launch."""


class ExecutionHolder:
    """Durable enrollment, devices, policy, consume, and lease records.

    ``allow_test_double`` accepts a software stand-in for a human
    authorization and must stay labeled not-hardware. It does not accept a
    phrase, and an imported ``secure-enclave`` label is not attestation.
    Real ``local`` / ``companion`` / ``dual`` methods require cryptographic
    device signatures. Bootstrap enrollment/pairing is authenticated with the
    bootstrap secret and is distinct from human authorization. Unprivileged
    tests do not prove installed protection.
    """

    def __init__(
        self,
        root: Path,
        *,
        allow_test_double: bool = False,
        installed_protection: bool = False,
        bootstrap_secret: str | None = None,
        snapshot_base: Path | None = None,
        verifier_pin: object | None = None,
        verifier_root: Path | None = None,
        trusted_native_boundary: object | None = None,
    ) -> None:
        if allow_test_double and installed_protection:
            raise ValueError("a software test double cannot claim installed protection")
        from runspecimen.native_bridge import TrustedNativeBoundary

        # Environment, config files, and wire JSON cannot construct this object.
        if trusted_native_boundary is not None and not isinstance(
            trusted_native_boundary, TrustedNativeBoundary
        ):
            raise TypeError("trusted native boundary cannot be selected from wire input or config")
        self.root = Path(root)
        self.allow_test_double = allow_test_double
        self.installed_protection = bool(installed_protection)
        self.bootstrap_secret = bootstrap_secret
        self.verifier_pin = verifier_pin
        self.verifier_root = Path(verifier_root) if verifier_root is not None else None
        self.trusted_native_boundary = trusted_native_boundary
        # Per-run payload snapshots live outside the 0700 state tree so a
        # correctly deprivileged payload can read them without seeing
        # enrollment, policy, spent nonces, or leases.
        if snapshot_base is None:
            self.snapshot_base = self.root.parent / "run-snapshots"
        else:
            self.snapshot_base = Path(snapshot_base)
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot_base.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        try:
            # Traverse-only parent. Listing would expose nonce names. Per-run
            # trees are sealed without group or world access.
            os.chmod(self.snapshot_base, 0o711)
        except OSError as exc:
            raise HolderRefusal("payload snapshot directory could not be sealed") from exc
        if not (self.root / "meta.json").exists():
            if _has_history(self.root):
                raise HolderRefusal("holder history is missing its generation record")
            self._write(
                "meta.json",
                {
                    "protocol": PROTOCOL,
                    "generation": 1,
                    "holder_id": secrets.token_hex(32),
                    "installed_protection": self.installed_protection,
                    "key_generation": 1,
                },
            )
            self._write("callers.json", {})
            self._write("devices.json", {})
            self._write("spent.json", {"nonces": []})
        self._load()

    def enroll(self, caller_id: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        with self._transaction():
            return self._enroll_locked(caller_id, human, now=now)

    def _enroll_locked(self, caller_id: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        self._load()
        self._human(
            human,
            purpose="enroll",
            policy=human.get("policy"),
            subject=caller_id,
            now=now,
        )
        if not isinstance(caller_id, str) or not caller_id or caller_id == "bootstrap":
            raise HolderRefusal("caller id is not enrollable")
        callers = self._read("callers.json")
        if caller_id in callers:
            raise HolderRefusal("caller is already enrolled")
        secret = secrets.token_hex(32)
        callers[caller_id] = {"secret": secret, "revoked": False, "key_generation": 1}
        self._write("callers.json", callers)
        record = {
            "caller_id": caller_id,
            "policy": human["policy"],
            "method": human["method"],
            "hardware": False,
            "generation": self.generation,
            "key_generation": 1,
        }
        self._write("enrollment.json", record)
        return {
            "ok": True,
            "caller_secret": secret,
            "holder_id": self.holder_id,
            "installed_protection": self.installed_protection,
            "hardware": False,
            "key_generation": 1,
        }

    def begin_human_secure_enclave_enrollment(
        self,
        signer: object | None = None,
        *,
        policy: str = "local",
    ) -> dict[str, Any]:
        """Pair roles with an injected native signer, or refuse before any prompt.

        ``signer`` must be a ``HumanNativeSigner`` instance. Wire JSON, an
        environment variable, and a config dict are not that object. The
        signer is not hardware. Installed protection still refuses it, because
        a software key is not a Secure Enclave enrollment. This method does
        not call ``SecureEnclave.P256.Signing.PrivateKey``.
        """

        from runspecimen.holder_asymmetric import public_key_fingerprint
        from runspecimen.native_bridge import HumanNativeSigner, production_enrollment_refusal

        if not isinstance(signer, HumanNativeSigner):
            raise HolderRefusal(
                "secure enclave enrollment is the human biometric step and was not invoked"
            )
        if signer.hardware is not False:
            raise HolderRefusal("a caller hardware label is not a native signer")
        if policy not in {"local", "companion", "dual"}:
            raise HolderRefusal("human native enrollment policy is not accepted")
        if self.installed_protection:
            raise HolderRefusal(production_enrollment_refusal())
        roles = {"local": ("mac",), "companion": ("phone",), "dual": ("mac", "phone")}[policy]
        devices = self._devices()
        paired: list[str] = []
        for role in roles:
            public = signer.public_key(role)
            if not isinstance(public, str) or not public:
                raise HolderRefusal("human native signer did not provide a public key")
            device_id = f"{role}-human"
            compared = public_key_fingerprint(public)
            devices[device_id] = {
                "role": role,
                "fingerprint": compared,
                "revoked": False,
                "attestation": "device-p256-not-hardware",
                "algorithm": "p256",
                "public_key": public,
                "generation": self.generation,
                "hardware": False,
                "provenance": {
                    "bridge": "human-native-signer",
                    "role": role,
                    "policy": policy,
                    "generation": self.generation,
                    "fingerprint": compared,
                    "not_hardware": True,
                    "origin": "injected-human-native-signer",
                    "hardware": False,
                },
            }
            paired.append(device_id)
        self._write("devices.json", devices)
        return {
            "ok": True,
            "hardware": False,
            "biometric_invoked": False,
            "policy": policy,
            "devices": paired,
            "origin": "injected-human-native-signer",
        }

    def begin_human_operated_native_adapter(
        self,
        adapter: object | None = None,
        *,
        policy: str = "local",
    ) -> dict[str, Any]:
        """Enroll through the human-operated adapter. Not production trust.

        ``adapter`` must be a ``HumanOperatedNativeAdapter``. A software
        ``HumanNativeSigner``, a boundary double, a dict, an environment
        variable, and a config file are not that object. Installed protection
        refuses it even when the verifier pin matches. A persisted origin
        string is not an authenticated native implementation. This method
        does not call ``SecureEnclave.P256.Signing.PrivateKey`` and does not
        prompt. E2 stays open.
        """

        from runspecimen.holder_asymmetric import public_key_fingerprint
        from runspecimen.native_bridge import (
            HumanNativeSigner,
            HumanOperatedNativeAdapter,
            TrustedNativeBoundary,
            production_enrollment_refusal,
        )

        if isinstance(adapter, (HumanNativeSigner, TrustedNativeBoundary)):
            raise HolderRefusal(production_enrollment_refusal())
        if not isinstance(adapter, HumanOperatedNativeAdapter):
            raise HolderRefusal("human-operated native adapter was not invoked")
        if self.installed_protection:
            raise HolderRefusal(production_enrollment_refusal())
        if getattr(adapter, "hardware", None) is True or adapter.e2_closed is not False:
            raise HolderRefusal("a caller hardware label is not human approval")
        if adapter.biometric_invoked is not False:
            raise HolderRefusal("a caller hardware label is not human approval")
        if policy not in {"local", "companion", "dual"}:
            raise HolderRefusal("human native enrollment policy is not accepted")
        roles = {"local": ("mac",), "companion": ("phone",), "dual": ("mac", "phone")}[policy]
        devices = self._devices()
        paired: list[str] = []
        for role in roles:
            public = adapter.public_key(role)
            if not isinstance(public, str) or not public:
                raise HolderRefusal("human-operated native adapter did not provide a public key")
            device_id = f"{role}-human"
            compared = public_key_fingerprint(public)
            devices[device_id] = {
                "role": role,
                "fingerprint": compared,
                "revoked": False,
                "attestation": "device-p256-not-hardware",
                "algorithm": "p256",
                "public_key": public,
                "generation": self.generation,
                "hardware": False,
                "provenance": {
                    "bridge": HumanOperatedNativeAdapter.bridge,
                    "role": role,
                    "policy": policy,
                    "generation": self.generation,
                    "fingerprint": compared,
                    "not_hardware": True,
                    "boundary_double": False,
                    "origin": HumanOperatedNativeAdapter.origin,
                    "biometric_invoked": False,
                    "e2_closed": False,
                },
            }
            paired.append(device_id)
        self._write("devices.json", devices)
        return {
            "ok": True,
            "hardware": False,
            "biometric_invoked": False,
            "e2_closed": False,
            "policy": policy,
            "devices": paired,
            "origin": HumanOperatedNativeAdapter.origin,
            "installed_protection": self.installed_protection,
        }

    def enroll_user_invoked_secure_enclave(
        self,
        control: object,
        *,
        wait: object | None = None,
        custody: object | None = None,
        phone_peer: object | None = None,
        phone_transport: object | None = None,
        peer_uid: int | None = None,
    ) -> dict[str, Any]:
        """Enroll after a person invokes the control.

        The OS call is ``os_secure_enclave_create_key``. Tests replace that
        function. This method does not call
        ``SecureEnclave.P256.Signing.PrivateKey`` and does not prompt.
        Mutations take the holder lock. Generation and revocation are read
        again after ``wait``. A change during the wait fails closed and does
        not store the key. The Mac signing handle stays in ``custody`` for a
        later signature in this user session. Companion and dual compare a
        phone peer and do not create a local key labeled phone. A software
        double is stored as not-hardware and installed protection refuses it.
        E2 is not closed. A biometric press does not finish missing
        implementation.
        """

        from runspecimen.native_bridge import (
            HumanNativeSigner,
            HumanOperatedNativeAdapter,
            OsBoundaryKey,
            OsBoundaryNotInvoked,
            PhonePeer,
            TrustedNativeBoundary,
            UserInvokedSecureEnclaveControl,
            UserSessionKeyCustody,
            os_secure_enclave_create_key,
            production_enrollment_refusal,
        )

        if os.environ.get("RS_NATIVE_SIGNER") or os.environ.get("RS_HOLDER_NATIVE_ORIGIN"):
            raise HolderRefusal(production_enrollment_refusal())
        if isinstance(control, (HumanNativeSigner, HumanOperatedNativeAdapter, TrustedNativeBoundary, dict, str, bool)):
            raise HolderRefusal(production_enrollment_refusal())
        if not isinstance(control, UserInvokedSecureEnclaveControl):
            raise HolderRefusal("secure enclave enrollment was not invoked by a person")
        if wait is not None and not callable(wait):
            raise HolderRefusal("secure enclave user wait is not a callback")
        if custody is None:
            custody = UserSessionKeyCustody()
        if not isinstance(custody, UserSessionKeyCustody):
            raise TypeError("session custody keeps an OS key handle, not public bytes")
        if peer_uid is None:
            peer_uid = os.getuid()
        if not isinstance(peer_uid, int):
            raise HolderRefusal("ipc peer is missing")
        self._session_custody = custody
        policy = control.action
        roles = {"local": ("mac",), "companion": ("phone",), "dual": ("mac", "phone")}[policy]
        with self._transaction():
            self._load()
            started = self.generation
        peer = phone_peer if isinstance(phone_peer, PhonePeer) else None
        if phone_transport is not None and not (
            callable(getattr(phone_transport, "publish_challenge", None))
            and callable(getattr(phone_transport, "collect_signature", None))
        ):
            raise HolderRefusal("phone companion transport cannot be selected from wire input")
        if policy in {"companion", "dual"} and peer is None and phone_transport is None:
            raise HolderRefusal("companion enrollment requires a phone peer")
        if policy in {"local", "dual"}:
            try:
                created = os_secure_enclave_create_key("mac")
            except OsBoundaryNotInvoked as exc:
                raise HolderRefusal(str(exc)) from exc
            if not isinstance(created, OsBoundaryKey):
                raise HolderRefusal("secure enclave boundary did not return an OS key")
            if peer is not None and peer.public_key == created.public_key:
                raise HolderRefusal("a local key is not a phone peer")
            custody.keep("mac", created)
        if policy == "companion" and peer is not None:
            mac_public = custody.public_key("mac")
            existing = self._devices().get("mac-human")
            existing_public = existing.get("public_key") if isinstance(existing, dict) else None
            if peer.public_key in {mac_public, existing_public}:
                raise HolderRefusal("a local key is not a phone peer")
        if policy in {"companion", "dual"} and (phone_transport is not None or peer is not None):
            challenge = secrets.token_bytes(32)
            challenge_id = secrets.token_hex(8)
            self._phone_challenge = {"bytes": challenge, "generation": started, "id": challenge_id}
            if phone_transport is not None:
                try:
                    phone_transport.publish_challenge(
                        challenge_id=challenge_id,
                        generation=started,
                        challenge=challenge,
                        holder_id=self.holder_id,
                    )
                except Exception as exc:
                    raise HolderRefusal("phone peer comparison failed") from exc
            else:
                try:
                    signature = peer.sign(challenge)
                except Exception as exc:
                    raise HolderRefusal("phone peer comparison failed") from exc
                self._pending_phone = {
                    "signature": signature,
                    "peer": peer,
                    "generation": started,
                    "challenge_id": challenge_id,
                    "signed_bytes": challenge,
                }
        if wait is not None:
            wait()
        if policy in {"companion", "dual"} and phone_transport is not None:
            from runspecimen.companion import ObserveTransportError

            try:
                submission = phone_transport.collect_signature()
            except ObserveTransportError as exc:
                raise HolderRefusal(str(exc)) from exc
            except Exception as exc:
                raise HolderRefusal("phone peer comparison failed") from exc
            if (
                not isinstance(submission, dict)
                or submission.get("challenge_id") != challenge_id
                or submission.get("challenge_bytes") != challenge
            ):
                raise HolderRefusal("stale phone challenge")
            submitted_key = submission.get("public_key")
            submitted_signature = submission.get("signature")
            if not isinstance(submitted_key, str) or not isinstance(submitted_signature, str):
                raise HolderRefusal("phone peer comparison failed")
            if submitted_key == custody.public_key("mac"):
                raise HolderRefusal("a local key is not a phone peer")
            existing = self._devices().get("mac-human")
            existing_public = existing.get("public_key") if isinstance(existing, dict) else None
            if submitted_key == existing_public:
                raise HolderRefusal("a local key is not a phone peer")

            def _submitted(message: bytes, raw: bytes = challenge, signed: str = submitted_signature) -> str:
                if message != raw:
                    raise HolderRefusal("phone peer comparison failed")
                return signed

            peer = PhonePeer(submitted_key, _submitted)
            self._pending_phone = {
                "signature": submitted_signature,
                "peer": peer,
                "generation": started,
                "challenge_id": challenge_id,
                "signed_bytes": challenge,
            }
        public_keys = {}
        for role in roles:
            if role == "phone":
                if peer is None:
                    raise HolderRefusal("companion enrollment requires a phone peer")
                public_keys[role] = peer.public_key
            else:
                public_keys[role] = custody.public_key(role)
        body = {
            "op": "native-enroll",
            "policy": policy,
            "peer_binding": peer_uid,
            "generation": started,
            "public_keys": public_keys,
        }
        try:
            return self.accept_native_ipc(body, peer_uid=peer_uid, custody=custody, started=started)
        except HolderRefusal:
            for role in roles:
                custody.drop(role)
            self._pending_phone = None
            raise

    def sign_with_os_boundary(
        self,
        keys: dict[str, object],
        purpose: str,
        subject: str,
        policy: str,
        authorized: dict[str, Any] | None = None,
        expires_at: int | None = None,
    ) -> dict[str, Any]:
        """Sign with keys the OS boundary returned. An origin string cannot select this."""

        import time

        from runspecimen.holder_asymmetric import digest_challenge
        from runspecimen.native_bridge import OsBoundaryKey

        if not isinstance(keys, dict) or not keys or any(not isinstance(key, OsBoundaryKey) for key in keys.values()):
            raise TypeError("OS boundary keys cannot be selected from wire input or config")
        names = {"local": ["mac"], "companion": ["phone"], "dual": ["mac", "phone"]}[policy]
        devices = self._devices()
        paired = []
        signatures: dict[str, str] = {}
        for device_id, record in sorted(devices.items()):
            if not isinstance(record, dict) or not self._os_boundary_authorizes(device_id, record):
                continue
            provenance = record.get("provenance")
            paired.append(
                {
                    "device_id": device_id,
                    "fingerprint": record.get("fingerprint"),
                    "generation": record.get("generation"),
                    "policy": provenance.get("policy") if isinstance(provenance, dict) else None,
                    "role": record.get("role"),
                }
            )
        if not paired:
            raise HolderRefusal("secure enclave boundary has not enrolled a device")
        when = int(time.time()) + 60 if expires_at is None else expires_at
        challenge = {
            "purpose": purpose,
            "subject": subject,
            "policy": policy,
            "devices": sorted(names),
            "expires_at": when,
            "holder_id": self.holder_id,
            "generation": self.generation,
            "domain": "holder-device-p256-v1",
            "attestation_class": "device-p256-not-hardware",
            "authorized": authorized or {},
            "paired": paired,
        }
        message = digest_challenge(challenge)
        for item in paired:
            role = str(item["role"])
            key = keys.get(role)
            if not isinstance(key, OsBoundaryKey):
                raise HolderRefusal("secure enclave boundary did not sign")
            signatures[str(item["device_id"])] = key.sign(message)
        return {
            "method": policy,
            "purpose": purpose,
            "policy": policy,
            "subject": subject,
            "devices": sorted(names),
            "expires_at": when,
            "hardware": False,
            "biometric_invoked": False,
            "e2_closed": False,
            "attestation_class": "device-p256-not-hardware",
            "signatures": signatures,
        }

    def attach_session(self, custody: object) -> None:
        """Reattach an in-memory signing handle after the holder reloads.

        The private capability is not read from ``os-boundary.json``. That file
        stores only the public key the holder accepted.
        """

        from runspecimen.native_bridge import UserSessionKeyCustody

        if not isinstance(custody, UserSessionKeyCustody):
            raise TypeError("session custody keeps an OS key handle, not public bytes")
        self._session_custody = custody

    def sign_from_session(
        self,
        custody: object,
        purpose: str,
        subject: str,
        policy: str,
        authorized: dict[str, Any] | None = None,
        expires_at: int | None = None,
    ) -> dict[str, Any]:
        """Sign with the handle kept at enrollment. A new public-only value cannot."""

        from runspecimen.native_bridge import UserSessionKeyCustody

        if not isinstance(custody, UserSessionKeyCustody):
            raise TypeError("session custody keeps an OS key handle, not public bytes")
        names = {"local": ["mac"], "companion": ["phone"], "dual": ["mac", "phone"]}[policy]
        keys = {}
        for role in names:
            key = custody.key(role)
            if key is None:
                raise HolderRefusal("session custody has no key for this role")
            keys[role] = key
        return self.sign_with_os_boundary(keys, purpose, subject, policy, authorized, expires_at)

    def issue_device_challenge(self, role: str, *, peer_uid: int, now: float | None = None) -> dict[str, Any]:
        """Issue one bound challenge. The signature is not accepted here."""

        if role not in {"mac", "phone"}:
            raise HolderRefusal("device challenge role is not accepted")
        if not isinstance(peer_uid, int):
            raise HolderRefusal("ipc peer is missing")
        moment = time.time() if now is None else float(now)
        with self._transaction():
            self._load()
            challenge = secrets.token_bytes(32)
            nonce = secrets.token_hex(16)
            expiry = int(moment) + 120
            pending = {
                "role": role,
                "nonce": nonce,
                "expiry": expiry,
                "generation": self.generation,
                "holder_id": self.holder_id,
                "challenge": challenge,
                "peer_uid": peer_uid,
            }
            challenges = getattr(self, "_pending_device_challenges", None)
            if not isinstance(challenges, dict):
                challenges = {}
                self._pending_device_challenges = challenges
            challenges[role] = pending
            message = bound_device_message(
                holder_id=self.holder_id,
                generation=self.generation,
                role=role,
                expiry=expiry,
                nonce=nonce,
                challenge=challenge,
            )
        return {
            "ok": True,
            "enrolled": False,
            "verified": False,
            "hardware": False,
            "not_hardware": True,
            "role": role,
            "nonce": nonce,
            "expiry": expiry,
            "generation": self.generation,
            "holder_id": self.holder_id,
            "challenge": base64.b64encode(challenge).decode("ascii"),
            "bound": base64.b64encode(message).decode("ascii"),
        }

    def cancel_device_challenge(self, role: str, *, peer_uid: int) -> dict[str, Any]:
        if role not in {"mac", "phone"}:
            raise HolderRefusal("device challenge role is not accepted")
        if not isinstance(peer_uid, int):
            raise HolderRefusal("ipc peer is missing")
        with self._transaction():
            self._load()
            challenges = getattr(self, "_pending_device_challenges", None)
            pending = challenges.get(role) if isinstance(challenges, dict) else None
            if not isinstance(pending, dict) or pending.get("peer_uid") != peer_uid:
                raise HolderRefusal("stale device challenge")
            challenges.pop(role, None)
        return {"ok": True, "enrolled": False, "verified": False, "cancelled": True, "hardware": False}

    def submit_device_signature(
        self,
        body: dict[str, Any],
        *,
        peer_uid: int,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Verify P-256 over the bound challenge, then consume it.

        Byte comparison, signature verification, and hardware provenance are
        separate. A nonempty signature string is not accepted. Installed
        protection still refuses the software double after a valid signature.
        """

        from runspecimen.holder_asymmetric import public_key_fingerprint, verify_native_p256
        from runspecimen.native_bridge import production_enrollment_refusal

        if not isinstance(peer_uid, int):
            raise HolderRefusal("ipc peer is missing")
        role = body.get("role")
        if role not in {"mac", "phone"}:
            raise HolderRefusal("device challenge role is not accepted")
        public_key = body.get("public_key")
        signature = body.get("signature")
        if not isinstance(public_key, str) or not public_key:
            raise HolderRefusal("device signature verification failed")
        if not isinstance(signature, str) or not signature:
            raise HolderRefusal("device signature verification failed")
        try:
            submitted_challenge = base64.b64decode(str(body.get("challenge")), validate=True)
        except (ValueError, TypeError) as exc:
            raise HolderRefusal("tampered device challenge") from exc
        nonce = body.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise HolderRefusal("tampered device challenge")
        moment = time.time() if now is None else float(now)
        with self._transaction():
            self._load()
            if nonce in self._spent_device_nonces():
                raise HolderRefusal("replayed device challenge")
            challenges = getattr(self, "_pending_device_challenges", None)
            pending = challenges.get(role) if isinstance(challenges, dict) else None
            if not isinstance(pending, dict):
                raise HolderRefusal("stale device challenge")
            if pending.get("peer_uid") != peer_uid:
                raise HolderRefusal("ipc binding does not match the socket peer")
            if int(moment) > int(pending["expiry"]):
                raise HolderRefusal("stale device challenge")
            if submitted_challenge != pending.get("challenge"):
                raise HolderRefusal("device challenge bytes do not match")
            try:
                submitted = bound_device_message(
                    holder_id=str(body.get("holder_id")),
                    generation=int(body.get("generation")),
                    role=role,
                    expiry=int(body.get("expiry")),
                    nonce=nonce,
                    challenge=submitted_challenge,
                )
                stored = bound_device_message(
                    holder_id=str(pending["holder_id"]),
                    generation=int(pending["generation"]),
                    role=str(pending["role"]),
                    expiry=int(pending["expiry"]),
                    nonce=str(pending["nonce"]),
                    challenge=pending["challenge"],
                )
            except (TypeError, ValueError) as exc:
                raise HolderRefusal("tampered device challenge") from exc
            if submitted != stored or self.generation != pending["generation"]:
                raise HolderRefusal("tampered device challenge")
            if not verify_native_p256(public_key, signature, stored, binary=self._verifier_binary()):
                raise HolderRefusal("device signature verification failed")
            challenges.pop(role, None)
            self._spend_device_nonce(nonce)
            devices = self._devices()
            other = "phone" if role == "mac" else "mac"
            other_device = devices.get(f"{other}-human")
            other_public = other_device.get("public_key") if isinstance(other_device, dict) else None
            if public_key == other_public:
                raise HolderRefusal("a local key is not a phone peer")
            if self.installed_protection:
                raise HolderRefusal(production_enrollment_refusal())
            device_id = f"{role}-human"
            compared = public_key_fingerprint(public_key)
            started = int(pending["generation"])
            proof_id = secrets.token_hex(16)
            devices[device_id] = {
                "role": role,
                "fingerprint": compared,
                "revoked": False,
                "attestation": "device-p256-not-hardware",
                "algorithm": "p256",
                "public_key": public_key,
                "generation": started,
                "hardware": False,
                "provenance": {
                    "bridge": "os-secure-enclave-boundary",
                    "role": role,
                    "policy": "local" if role == "mac" else "companion",
                    "generation": started,
                    "fingerprint": compared,
                    "not_hardware": True,
                    "boundary_double": False,
                    "origin": "os-secure-enclave-boundary",
                    "os_boundary_id": proof_id,
                    "biometric_invoked": False,
                    "e2_closed": False,
                    "access_policy": "biometry-current-set-on-each-signature",
                },
            }
            self._write("devices.json", devices)
            proof_path = self.root / "os-boundary.json"
            proof = read_json(proof_path) if proof_path.exists() else {"keys": {}, "generation": started}
            if not isinstance(proof, dict):
                proof = {"keys": {}, "generation": started}
            keys = proof.get("keys")
            if not isinstance(keys, dict):
                keys = {}
            keys[device_id] = {"id": proof_id, "public_key": public_key, "generation": started}
            atomic_write_json(proof_path, {"keys": keys, "generation": started})
            if role == "mac":
                self._drop_pending_phone_receipt()
            if role == "phone":
                atomic_write_json(
                    self.root / "phone-receipt-pending.json",
                    {
                        "challenge_id": nonce,
                        "challenge": base64.b64encode(pending["challenge"]).decode("ascii"),
                        "holder_id": str(pending["holder_id"]),
                        "generation": int(pending["generation"]),
                        "phone_fingerprint": compared,
                        "phone_public_key": public_key,
                        "sealed": False,
                    },
                )
        return {
            "ok": True,
            "enrolled": True,
            "verified": True,
            "hardware": False,
            "not_hardware": True,
            "consumed": True,
            "device": device_id,
            "e2_closed": False,
            "biometric_invoked": False,
        }

    def _phone_receipt_material(self, body: dict[str, Any]) -> tuple[dict[str, Any], str, bytes]:
        """Rebuild the receipt from holder state. Caller flags are not read."""

        pending_path = self.root / "phone-receipt-pending.json"
        if not pending_path.exists():
            raise HolderRefusal("stale phone receipt")
        pending = read_json(pending_path)
        if not isinstance(pending, dict):
            raise HolderRefusal("stale phone receipt")
        if body.get("challenge_id") != pending.get("challenge_id"):
            raise HolderRefusal("stale phone receipt")
        if int(pending.get("generation")) != self.generation:
            raise HolderRefusal("stale phone receipt")
        if pending.get("challenge_id") not in self._spent_device_nonces():
            raise HolderRefusal("stale phone receipt")
        mac = self._devices().get("mac-human")
        if isinstance(mac, dict) and mac.get("revoked") is True:
            raise HolderRefusal("phone receipt mac key is revoked")
        if not isinstance(mac, dict) or not isinstance(mac.get("public_key"), str):
            raise HolderRefusal("phone receipt has no enrolled mac key")
        phone = self._devices().get("phone-human")
        if not isinstance(phone, dict) or phone.get("revoked") is True:
            raise HolderRefusal("phone receipt phone key is revoked")
        if phone.get("fingerprint") != pending.get("phone_fingerprint") or phone.get("public_key") != pending.get(
            "phone_public_key"
        ):
            raise HolderRefusal("phone receipt fingerprint does not match")
        supplied = body.get("mac_public_key")
        if supplied not in (None, mac["public_key"]):
            raise HolderRefusal("phone receipt key does not match")
        message = bound_phone_receipt(
            holder_id=str(pending["holder_id"]),
            generation=int(pending["generation"]),
            challenge_id=str(pending["challenge_id"]),
            challenge=str(pending["challenge"]),
            phone_fingerprint=str(pending["phone_fingerprint"]),
            mac_public_key=str(mac["public_key"]),
        )
        supplied_receipt = body.get("receipt")
        if supplied_receipt not in (None, base64.b64encode(message).decode("ascii")):
            raise HolderRefusal("tampered phone receipt")
        return pending, str(mac["public_key"]), message

    def prepare_phone_receipt(self, body: dict[str, Any], *, peer_uid: int) -> dict[str, Any]:
        """Return receipt bytes for the enrolled Mac key to sign. This does not enroll."""

        if not isinstance(peer_uid, int):
            raise HolderRefusal("ipc peer is missing")
        if body.get("verified") is True or body.get("consumed") is True:
            raise HolderRefusal("a caller flag is not a holder receipt")
        with self._transaction():
            self._load()
            pending, mac_key, message = self._phone_receipt_material(body)
        return {
            "ok": True,
            "verified": False,
            "consumed": False,
            "enrolled": False,
            "sealed": False,
            "hardware": False,
            "receipt": base64.b64encode(message).decode("ascii"),
            "mac_public_key": mac_key,
            "phone_fingerprint": pending["phone_fingerprint"],
            "challenge_id": pending["challenge_id"],
            "holder_id": pending["holder_id"],
            "generation": pending["generation"],
            "outcome": PHONE_RECEIPT_OUTCOME,
        }

    def seal_phone_receipt(self, body: dict[str, Any], *, peer_uid: int) -> dict[str, Any]:
        """Accept the receipt only when the enrolled Mac key signed it.

        ``verified`` and ``consumed`` in the caller body are ignored. A paired
        mailbox token cannot mint this signature.
        """

        from runspecimen.holder_asymmetric import verify_native_p256

        if not isinstance(peer_uid, int):
            raise HolderRefusal("ipc peer is missing")
        signature = body.get("signature")
        if not isinstance(signature, str) or not signature:
            raise HolderRefusal("a caller flag is not a holder receipt")
        with self._transaction():
            self._load()
            pending, mac_key, message = self._phone_receipt_material(body)
            if pending.get("sealed") is True:
                raise HolderRefusal("replayed phone receipt")
            if not verify_native_p256(mac_key, signature, message, binary=self._verifier_binary()):
                raise HolderRefusal("phone receipt verification failed")
            pending["sealed"] = True
            atomic_write_json(self.root / "phone-receipt-pending.json", pending)
        return {
            "ok": True,
            "verified": True,
            "consumed": True,
            "enrolled": False,
            "sealed": True,
            "hardware": False,
            "not_hardware": True,
            "receipt": base64.b64encode(message).decode("ascii"),
            "signature": signature,
            "mac_public_key": mac_key,
            "phone_fingerprint": pending["phone_fingerprint"],
            "challenge_id": pending["challenge_id"],
            "holder_id": pending["holder_id"],
            "generation": pending["generation"],
            "outcome": PHONE_RECEIPT_OUTCOME,
            "e2_closed": False,
        }

    def issue_exact_run(self, body: dict[str, Any], *, peer_uid: int, now: float | None = None) -> dict[str, Any]:
        """Prepare one snapshot-bound run. The signature is not accepted here.

        This writes the payload snapshot the consume path will keep. It does
        not write spent history or a lease, and it is not a completed run.
        """

        self._refuse_exact_run_labels(body)
        if not isinstance(peer_uid, int):
            raise HolderRefusal("ipc peer is missing")
        policy = body.get("policy")
        if policy not in POLICIES:
            raise HolderRefusal("exact run policy is not accepted")
        workspace = body.get("workspace")
        files = body.get("files")
        binding = body.get("binding")
        if not isinstance(workspace, str) or not workspace:
            raise HolderRefusal("exact run payload is not bound")
        if not isinstance(files, list) or not files:
            raise HolderRefusal("exact run payload is not bound")
        pairs: list[tuple[str, str]] = []
        for item in files:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise HolderRefusal("exact run payload is not bound")
            pairs.append((str(item[0]), str(item[1])))
        moment = time.time() if now is None else float(now)
        with self._transaction():
            self._load()
            if not isinstance(binding, dict):
                raise HolderRefusal("exact run payload is not bound")
            if "key_generation" not in binding:
                binding = dict(binding)
                binding["key_generation"] = self.key_generation
            if binding.get("policy") != policy:
                raise HolderRefusal("exact run policy is not accepted")
            envelope = self._binding_envelope(binding)
            nonce = secrets.token_hex(16)
            path_map, payload_digest, snapshot_root = self._bind(
                nonce,
                Path(workspace),
                pairs,
                executable=str(envelope["executable"]),
                argv=[str(item) for item in envelope["argv"]],
            )
            expiry = int(moment) + 120
            message = bound_exact_run(
                holder_id=self.holder_id,
                payload_digest=payload_digest,
                launch_argv=list(envelope["launch_argv"]),
                nonce=nonce,
                policy=str(policy),
                generation=self.generation,
                key_generation=self.key_generation,
                expiry=expiry,
            )
            self._pending_exact_run = {
                "peer_uid": peer_uid,
                "nonce": nonce,
                "payload_digest": payload_digest,
                "launch_argv": list(envelope["launch_argv"]),
                "bound": message,
                "holder_id": self.holder_id,
                "policy": str(policy),
                "generation": self.generation,
                "key_generation": self.key_generation,
                "expiry": expiry,
                "workspace": workspace,
                "files": pairs,
                "binding": binding,
                "path_map": path_map,
                "snapshot_root": snapshot_root,
            }
        return {
            "ok": True,
            "authorized": False,
            "enrolled": False,
            "verified": False,
            "consumed": False,
            "hardware": False,
            "not_hardware": True,
            "run_integration_complete": False,
            "e2_closed": False,
            "nonce": nonce,
            "bound": base64.b64encode(message).decode("ascii"),
            "payload_digest": payload_digest,
            "launch_argv": list(envelope["launch_argv"]),
            "policy": policy,
            "generation": self.generation,
            "key_generation": self.key_generation,
            "expiry": expiry,
            "enrolled_mac_public_key": self._enrolled_mac_public_key(),
        }

    def session_generation(self) -> dict[str, Any]:
        """Read the live policy and generations. This does not sign or consume."""

        with self._transaction():
            self._load()
            policy = self._active_policy_name() or ""
            generation = self.generation
            key_generation = self.key_generation
        return {
            "ok": True,
            "policy": policy,
            "generation": generation,
            "key_generation": key_generation,
            "hardware": False,
            "not_hardware": True,
            "run_integration_complete": False,
            "e2_closed": False,
        }

    def _enrolled_mac_public_key(self) -> str | None:
        mac = self._devices().get("mac-human")
        if not isinstance(mac, dict) or mac.get("revoked") is True:
            return None
        public_key = mac.get("public_key")
        if not isinstance(public_key, str) or not public_key:
            return None
        return public_key

    def _drop_pending_phone_receipt(self) -> None:
        path = self.root / "phone-receipt-pending.json"
        if path.exists():
            path.unlink()

    def authorize_exact_run(
        self,
        body: dict[str, Any],
        *,
        peer_uid: int,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Feed one verified session signature into consume.

        The consume path writes the snapshot binding, spent history, and the
        uncertain lease that execute recovers. This is not a completed run.
        Installed protection stays fail-closed. A software double, a caller
        hardware label, an origin string, and a pin match are not hardware.
        """

        self._refuse_exact_run_labels(body)
        if not isinstance(peer_uid, int):
            raise HolderRefusal("ipc peer is missing")
        signatures = body.get("signatures")
        if not isinstance(signatures, dict) or not signatures:
            raise HolderRefusal("device signature verification failed")
        moment = time.time() if now is None else float(now)
        with self._transaction():
            self._load()
            pending = getattr(self, "_pending_exact_run", None)
            if not isinstance(pending, dict) or pending.get("peer_uid") != peer_uid:
                raise HolderRefusal("stale exact run")
            if body.get("nonce") not in (None, pending.get("nonce")):
                raise HolderRefusal("tampered exact run")
            if body.get("policy") not in (None, pending.get("policy")):
                raise HolderRefusal("exact run policy is not accepted")
            if int(moment) > int(pending["expiry"]):
                self._pending_exact_run = None
                raise HolderRefusal("exact run has expired")
            if self.generation != pending["generation"] or self.key_generation != pending["key_generation"]:
                self._pending_exact_run = None
                raise HolderRefusal("exact run generation changed")
            human = self._exact_run_human(pending, signatures, purpose="consume")
            self._refuse_untrusted_exact_run(human)
            prepared = {
                "path_map": pending["path_map"],
                "payload_digest": pending["payload_digest"],
                "snapshot_root": pending["snapshot_root"],
            }
            consumed = self._consume_locked(
                nonce=str(pending["nonce"]),
                policy=str(pending["policy"]),
                human=human,
                workspace=Path(str(pending["workspace"])),
                files=list(pending["files"]),
                binding=pending["binding"],
                now=moment,
                prepared=prepared,
            )
            self._pending_exact_run = None
        return {
            "ok": True,
            "authorized": True,
            "enrolled": False,
            "verified": True,
            "consumed": True,
            "hardware": False,
            "not_hardware": True,
            "e2_closed": False,
            "run_integration_complete": False,
            "nonce": consumed["nonce"],
            "payload_digest": consumed["payload_digest"],
            "launch_argv": list(pending["launch_argv"]),
            "policy": consumed["policy"],
            "lease": "uncertain",
            "snapshot_root": consumed["snapshot_root"],
        }

    def exact_run_execute_human(self, nonce: str, signatures: dict[str, str]) -> dict[str, Any]:
        """The same session signatures, for the execute step of that nonce."""

        spent = self._spent()
        record = next((item for item in spent if item.get("nonce") == nonce), None)
        if not isinstance(record, dict) or not record.get("exact_run"):
            raise HolderRefusal("execute nonce is not in replay history")
        pending = {
            "nonce": nonce,
            "policy": record.get("policy"),
            "expiry": record.get("exact_expiry"),
            "generation": record.get("generation"),
            "key_generation": record.get("key_generation"),
            "holder_id": record.get("holder_id"),
            "payload_digest": record.get("payload_digest"),
            "launch_argv": list(record.get("launch_argv") or []),
            "bound": record.get("exact_bound"),
        }
        return self._exact_run_human(pending, signatures, purpose="execute", bound_override=record.get("exact_bound"))

    def _exact_run_human(
        self,
        pending: dict[str, Any],
        signatures: dict[str, Any],
        *,
        purpose: str,
        bound_override: bytes | None = None,
    ) -> dict[str, Any]:
        policy = str(pending["policy"])
        roles = self._exact_run_roles(policy, signatures)
        devices = _DEVICES[policy]
        return {
            "method": "exact-run-session",
            "purpose": purpose,
            "subject": pending["nonce"],
            "policy": policy,
            "devices": sorted(devices),
            "expires_at": int(pending["expiry"]),
            "hardware": False,
            "signatures": {role: signatures[role] for role in roles},
            "generation": int(pending["generation"]),
            "key_generation": int(pending["key_generation"]),
            "holder_id": str(pending["holder_id"]),
            "payload_digest": str(pending["payload_digest"]),
            "launch_argv": list(pending["launch_argv"]),
            "bound": bound_override if bound_override is not None else pending.get("bound"),
        }

    def _exact_run_roles(self, policy: str, signatures: dict[str, Any]) -> tuple[str, ...]:
        if policy == "local":
            if "phone" in signatures:
                raise HolderRefusal("local exact run excludes the phone key")
            if set(signatures) != {"mac"}:
                raise HolderRefusal("local exact run excludes the phone key")
            return ("mac",)
        if policy == "companion":
            if set(signatures) != {"phone"}:
                raise HolderRefusal("companion exact run requires the phone key")
            return ("phone",)
        if policy == "dual":
            if set(signatures) != {"mac", "phone"}:
                raise HolderRefusal("dual exact run requires the mac and phone keys")
            return ("mac", "phone")
        raise HolderRefusal("exact run policy is not accepted")

    def _refuse_untrusted_exact_run(self, human: dict[str, Any]) -> None:
        from runspecimen.native_bridge import production_enrollment_refusal

        if human.get("hardware") is True:
            raise HolderRefusal("software P-256 is not a Secure Enclave")
        for role in human["signatures"]:
            device = self._devices().get(f"{role}-human")
            if not isinstance(device, dict):
                raise HolderRefusal("exact run has no enrolled session key")
            if self.installed_protection and self._session_key_is_software(device):
                raise HolderRefusal(production_enrollment_refusal())
            if self.installed_protection and not self._session_key_is_software(device):
                raise HolderRefusal(
                    "Installed Secure Enclave admission stays fail-closed"
                )

    def _verify_exact_run_session(
        self,
        human: dict[str, Any],
        *,
        purpose: str,
        policy: str,
        subject: object,
        authorized: dict[str, Any] | None,
    ) -> None:
        from runspecimen.holder_asymmetric import verify_native_p256

        if human.get("purpose") != purpose or human.get("subject") != subject:
            raise HolderRefusal("human authorization does not match this operation")
        if human.get("policy") != policy or policy not in POLICIES:
            raise HolderRefusal("human authorization policy is not local, companion, or dual")
        if human.get("hardware") is not False:
            raise HolderRefusal("software P-256 is not a Secure Enclave")
        expires = human.get("expires_at")
        if isinstance(expires, bool) or not isinstance(expires, int) or expires <= time.time():
            raise HolderRefusal("exact run has expired")
        if int(human.get("generation")) != self.generation or int(human.get("key_generation")) != self.key_generation:
            raise HolderRefusal("exact run generation changed")
        signatures = human.get("signatures")
        if not isinstance(signatures, dict):
            raise HolderRefusal("device signature verification failed")
        self._exact_run_roles(policy, signatures)
        raw_bound = human.get("bound")
        if isinstance(raw_bound, str):
            try:
                raw_bound = base64.b64decode(raw_bound, validate=True)
            except (ValueError, TypeError) as exc:
                raise HolderRefusal("tampered exact run") from exc
        if not isinstance(raw_bound, bytes) or not raw_bound:
            raise HolderRefusal("tampered exact run")
        expected = bound_exact_run(
            holder_id=str(human.get("holder_id")),
            payload_digest=str(human.get("payload_digest")),
            launch_argv=list(human.get("launch_argv") or []),
            nonce=str(subject),
            policy=policy,
            generation=int(human.get("generation")),
            key_generation=int(human.get("key_generation")),
            expiry=int(expires),
        )
        if raw_bound != expected:
            raise HolderRefusal("tampered exact run")
        if authorized is not None:
            if authorized.get("payload_digest") != human.get("payload_digest"):
                raise HolderRefusal("tampered exact run")
            if list(authorized.get("launch_argv") or []) != list(human.get("launch_argv") or []):
                raise HolderRefusal("tampered exact run")
        phone = self._devices().get("phone-human")
        for role, signature in signatures.items():
            device = self._devices().get(f"{role}-human")
            if not isinstance(device, dict) or device.get("revoked") is True:
                raise HolderRefusal("exact run device was revoked")
            public_key = device.get("public_key")
            if not isinstance(public_key, str) or not isinstance(signature, str):
                raise HolderRefusal("device signature verification failed")
            if policy == "local" and isinstance(phone, dict) and public_key == phone.get("public_key"):
                raise HolderRefusal("local exact run excludes the phone key")
            if not verify_native_p256(public_key, signature, raw_bound, binary=self._verifier_binary()):
                raise HolderRefusal("device signature verification failed")
        self._refuse_untrusted_exact_run(human)

    def _refuse_exact_run_labels(self, body: dict[str, Any]) -> None:
        if any(name in body for name in ("origin", "config", "signer", "hardware")):
            raise HolderRefusal("exact run refuses caller authority labels")

    def _enrolled_session_device(self, public_key: str) -> dict[str, Any] | None:
        devices = self._devices()
        for device_id in ("mac-human", "phone-human"):
            device = devices.get(device_id)
            if isinstance(device, dict) and device.get("public_key") == public_key:
                return device
        return None

    def _session_key_is_software(self, device: dict[str, Any]) -> bool:
        provenance = device.get("provenance")
        if not isinstance(provenance, dict):
            return True
        if device.get("hardware") is not False:
            return True
        if provenance.get("not_hardware") is not False:
            return True
        if provenance.get("boundary_double") is True:
            return True
        return False

    def _spent_device_nonces(self) -> set[str]:
        path = self.root / "device-nonces.json"
        if not path.exists():
            return set()
        raw = read_json(path)
        values = raw.get("nonces") if isinstance(raw, dict) else None
        if not isinstance(values, list):
            return set()
        return {item for item in values if isinstance(item, str)}

    def _spend_device_nonce(self, nonce: str) -> None:
        spent = sorted(self._spent_device_nonces() | {nonce})
        atomic_write_json(self.root / "device-nonces.json", {"nonces": spent})

    def accept_native_ipc(
        self,
        message: object,
        *,
        peer_uid: int,
        custody: object,
        started: int,
    ) -> dict[str, Any]:
        """Pair keys the session already holds. Wire JSON cannot select this.

        ``peer_uid`` is the socket peer, not a claimed uid inside ``message``.
        An origin string, a hardware label, env, and config are refused.
        Installed protection refuses the software double even when a later pin
        check would match. A phone key is stored only after the challenge
        still matches and the peer signature verifies.
        """

        from runspecimen.holder_asymmetric import public_key_fingerprint, verify_native_p256
        from runspecimen.native_bridge import (
            PhonePeer,
            UserSessionKeyCustody,
            production_enrollment_refusal,
        )

        if os.environ.get("RS_NATIVE_SIGNER") or os.environ.get("RS_HOLDER_NATIVE_ORIGIN"):
            raise HolderRefusal(production_enrollment_refusal())
        if not isinstance(custody, UserSessionKeyCustody):
            raise TypeError("session custody keeps an OS key handle, not public bytes")
        if not isinstance(peer_uid, int):
            raise HolderRefusal("ipc peer is missing")
        if not isinstance(message, dict) or message.get("op") != "native-enroll":
            raise HolderRefusal("native enrollment cannot be selected from wire input")
        if any(key in message for key in ("origin", "config", "signer", "hardware")):
            raise HolderRefusal(production_enrollment_refusal())
        claimed = message.get("claimed_uid")
        if claimed is not None and claimed != peer_uid:
            raise HolderRefusal("ipc binding does not match the socket peer")
        if message.get("peer_binding") != peer_uid:
            raise HolderRefusal("ipc binding does not match the socket peer")
        policy = message.get("policy")
        if policy not in {"local", "companion", "dual"}:
            raise HolderRefusal("human native enrollment policy is not accepted")
        roles = {"local": ("mac",), "companion": ("phone",), "dual": ("mac", "phone")}[policy]
        public_keys = message.get("public_keys")
        if not isinstance(public_keys, dict):
            raise HolderRefusal("ipc public key does not match session custody")
        with self._transaction():
            self._load()
            if self.generation != started or message.get("generation") != started:
                raise HolderRefusal("enrollment generation changed during the user wait")
            devices = self._devices()
            for role in roles:
                current = devices.get(f"{role}-human")
                if isinstance(current, dict) and current.get("revoked") is True:
                    raise HolderRefusal("enrollment device was revoked during the user wait")
            if "phone" in roles:
                pending = getattr(self, "_pending_phone", None)
                challenge = getattr(self, "_phone_challenge", None)
                if not isinstance(pending, dict) or not isinstance(challenge, dict):
                    raise HolderRefusal("companion enrollment requires a phone peer")
                if (
                    challenge.get("generation") != started
                    or pending.get("generation") != started
                    or challenge.get("id") != pending.get("challenge_id")
                    or challenge.get("bytes") != pending.get("signed_bytes")
                ):
                    raise HolderRefusal("stale phone challenge")
                peer = pending.get("peer")
                if not isinstance(peer, PhonePeer) or public_keys.get("phone") != peer.public_key:
                    raise HolderRefusal("a local key is not a phone peer")
                if custody.public_key("mac") == peer.public_key:
                    raise HolderRefusal("a local key is not a phone peer")
                signature = pending.get("signature")
                raw = pending.get("signed_bytes")
                if not isinstance(signature, str) or not isinstance(raw, bytes):
                    raise HolderRefusal("phone peer comparison failed")
                if not verify_native_p256(
                    peer.public_key, signature, raw, binary=self._verifier_binary()
                ):
                    raise HolderRefusal("phone peer comparison failed")
                custody.keep("phone", peer.as_os_key())
            for role in roles:
                if public_keys.get(role) != custody.public_key(role):
                    raise HolderRefusal("ipc public key does not match session custody")
            if self.installed_protection:
                raise HolderRefusal(production_enrollment_refusal())
            proof_id = secrets.token_hex(16)
            proof_keys: dict[str, Any] = {}
            paired: list[str] = []
            for role in roles:
                device_id = f"{role}-human"
                public = custody.public_key(role)
                if not isinstance(public, str) or not public:
                    raise HolderRefusal("session custody has no key for this role")
                compared = public_key_fingerprint(public)
                devices[device_id] = {
                    "role": role,
                    "fingerprint": compared,
                    "revoked": False,
                    "attestation": "device-p256-not-hardware",
                    "algorithm": "p256",
                    "public_key": public,
                    "generation": started,
                    "hardware": False,
                    "provenance": {
                        "bridge": "os-secure-enclave-boundary",
                        "role": role,
                        "policy": policy,
                        "generation": started,
                        "fingerprint": compared,
                        "not_hardware": True,
                        "boundary_double": False,
                        "origin": "os-secure-enclave-boundary",
                        "os_boundary_id": proof_id,
                        "biometric_invoked": False,
                        "e2_closed": False,
                        "access_policy": "biometry-current-set-on-each-signature",
                    },
                }
                proof_keys[device_id] = {
                    "id": proof_id,
                    "public_key": public,
                    "generation": started,
                }
                paired.append(device_id)
            self._write("devices.json", devices)
            atomic_write_json(
                self.root / "os-boundary.json",
                {"keys": proof_keys, "generation": started},
            )
        return {
            "ok": True,
            "hardware": False,
            "biometric_invoked": False,
            "e2_closed": False,
            "policy": policy,
            "devices": paired,
            "paired": True,
            "installed_protection": self.installed_protection,
            "access_policy": "biometry-current-set-on-each-signature",
        }

    def sign_with_human_operated_adapter(
        self,
        adapter: object,
        purpose: str,
        subject: str,
        policy: str,
        authorized: dict[str, Any] | None = None,
        expires_at: int | None = None,
    ) -> dict[str, Any]:
        """Sign a holder challenge with the human-operated native adapter."""

        import time

        from runspecimen.holder_asymmetric import digest_challenge
        from runspecimen.native_bridge import (
            HumanNativeSigner,
            HumanOperatedNativeAdapter,
            TrustedNativeBoundary,
            production_enrollment_refusal,
        )

        if isinstance(adapter, (HumanNativeSigner, TrustedNativeBoundary, dict)):
            raise HolderRefusal(production_enrollment_refusal())
        if not isinstance(adapter, HumanOperatedNativeAdapter):
            raise TypeError("human-operated native adapter cannot be selected from wire input or config")
        if getattr(adapter, "hardware", None) is True:
            raise HolderRefusal("a caller hardware label is not human approval")
        names = {"local": ["mac"], "companion": ["phone"], "dual": ["mac", "phone"]}[policy]
        devices = self._devices()
        paired = []
        signatures: dict[str, str] = {}
        for device_id, record in sorted(devices.items()):
            if not isinstance(record, dict):
                continue
            provenance = record.get("provenance")
            if not isinstance(provenance, dict):
                continue
            if provenance.get("origin") != HumanOperatedNativeAdapter.origin:
                continue
            if provenance.get("bridge") != HumanOperatedNativeAdapter.bridge:
                continue
            if provenance.get("boundary_double") is True or record.get("hardware") is True:
                raise HolderRefusal(production_enrollment_refusal())
            paired.append(
                {
                    "device_id": device_id,
                    "fingerprint": record.get("fingerprint"),
                    "generation": record.get("generation"),
                    "policy": provenance.get("policy"),
                    "role": record.get("role"),
                }
            )
        if not paired:
            raise HolderRefusal("human-operated native adapter has not enrolled a device")
        when = int(time.time()) + 60 if expires_at is None else expires_at
        challenge = {
            "purpose": purpose,
            "subject": subject,
            "policy": policy,
            "devices": sorted(names),
            "expires_at": when,
            "holder_id": self.holder_id,
            "generation": self.generation,
            "domain": "holder-device-p256-v1",
            "attestation_class": "device-p256-not-hardware",
            "authorized": authorized or {},
            "paired": paired,
        }
        message = digest_challenge(challenge)
        for item in paired:
            role = str(item["role"])
            signature = adapter.sign(role, message)
            if not isinstance(signature, str) or not signature:
                raise HolderRefusal("human-operated native adapter did not sign")
            signatures[str(item["device_id"])] = signature
        return {
            "method": policy,
            "purpose": purpose,
            "policy": policy,
            "subject": subject,
            "devices": sorted(names),
            "expires_at": when,
            "hardware": False,
            "biometric_invoked": False,
            "e2_closed": False,
            "attestation_class": "device-p256-not-hardware",
            "signatures": signatures,
            "origin": HumanOperatedNativeAdapter.origin,
        }

    def sign_with_human_native_signer(
        self,
        signer: object,
        purpose: str,
        subject: str,
        policy: str,
        authorized: dict[str, Any] | None = None,
        expires_at: int | None = None,
    ) -> dict[str, Any]:
        """Build a holder authorization and sign it with the injected signer."""

        import time

        from runspecimen.holder_asymmetric import digest_challenge
        from runspecimen.native_bridge import HumanNativeSigner

        if not isinstance(signer, HumanNativeSigner):
            raise TypeError("human native signer cannot be selected from wire input or config")
        if signer.hardware is not False:
            raise HolderRefusal("a caller hardware label is not a native signer")
        names = {"local": ["mac"], "companion": ["phone"], "dual": ["mac", "phone"]}[policy]
        devices = self._devices()
        paired = []
        signatures: dict[str, str] = {}
        for device_id, record in sorted(devices.items()):
            if not isinstance(record, dict):
                continue
            provenance = record.get("provenance")
            if not isinstance(provenance, dict):
                continue
            if provenance.get("origin") != "injected-human-native-signer":
                continue
            if record.get("hardware") is not False:
                raise HolderRefusal("a caller hardware label is not a native signer")
            paired.append(
                {
                    "device_id": device_id,
                    "fingerprint": record.get("fingerprint"),
                    "generation": record.get("generation"),
                    "policy": provenance.get("policy"),
                    "role": record.get("role"),
                }
            )
        if not paired:
            raise HolderRefusal("human native signer has not enrolled a device")
        when = int(time.time()) + 60 if expires_at is None else expires_at
        challenge = {
            "purpose": purpose,
            "subject": subject,
            "policy": policy,
            "devices": sorted(names),
            "expires_at": when,
            "holder_id": self.holder_id,
            "generation": self.generation,
            "domain": "holder-device-p256-v1",
            "attestation_class": "device-p256-not-hardware",
            "authorized": authorized or {},
            "paired": paired,
        }
        message = digest_challenge(challenge)
        for item in paired:
            role = str(item["role"])
            signature = signer.sign(role, message)
            if not isinstance(signature, str) or not signature:
                raise HolderRefusal("human native signer did not sign")
            signatures[str(item["device_id"])] = signature
        return {
            "method": policy,
            "purpose": purpose,
            "policy": policy,
            "subject": subject,
            "devices": sorted(names),
            "expires_at": when,
            "hardware": False,
            "attestation_class": "device-p256-not-hardware",
            "signatures": signatures,
        }

    def pair_device(self, device_id: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        with self._transaction():
            return self._pair_device_locked(device_id, human, now=now)

    def _pair_device_locked(self, device_id: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        self._load()
        self._require_enrollment()
        role = human.get("role") if isinstance(human, dict) else None
        if role not in {"mac", "phone"}:
            raise HolderRefusal("pairing requires a mac or phone role")
        auth_policy = self._active_policy_name() or (
            human.get("policy") if isinstance(human, dict) else None
        )
        self._human(human, purpose="pair", policy=auth_policy, subject=device_id, now=now)
        devices = self._devices()
        if device_id in devices and devices[device_id].get("revoked") is not True:
            raise HolderRefusal("device is already paired")
        fingerprint = human.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise HolderRefusal("pairing fingerprint is missing")
        if human.get("attestation") == "secure-enclave" and human.get("hardware") is not True:
            raise HolderRefusal("imported secure-enclave label is unverified on this holder")
        # Real pairing stores an Ed25519 public key. The private key is returned
        # once. An imported secure-enclave label is still not attestation.
        from runspecimen.holder_asymmetric import generate_device_keypair

        attestation = "unverified"
        private_hex = None
        public_hex = None
        algorithm = "ed25519"
        if human.get("algorithm") == "p256":
            if human.get("hardware") is True:
                raise HolderRefusal("software P-256 is not a Secure Enclave")
            if human.get("attestation") in {"secure-enclave", "touch-id", "face-id"}:
                raise HolderRefusal("software P-256 is not a Secure Enclave")
            from runspecimen.native_bridge import production_enrollment_refusal

            if self.installed_protection:
                raise HolderRefusal(production_enrollment_refusal())
            supplied_p256 = human.get("public_key")
            if not isinstance(supplied_p256, str) or not supplied_p256:
                raise HolderRefusal("pairing public key is missing")
            from runspecimen.holder_asymmetric import (
                _LABELED_NATIVE_BRIDGE,
                public_key_fingerprint,
            )
            from runspecimen.native_bridge import (
                BOUNDARY_DOUBLE,
                ISOLATED_DOUBLE,
                PRODUCTION_BRIDGE,
                TrustedNativeBoundary,
            )

            compared = public_key_fingerprint(supplied_p256)
            if human.get("key_comparison") != compared:
                raise HolderRefusal("human key comparison does not match the public key")
            provenance = human.get("provenance")
            if not isinstance(provenance, dict):
                raise HolderRefusal("pairing public key provenance is missing")
            policy_name = auth_policy if isinstance(auth_policy, str) else human.get("policy")
            caller_claims_boundary = (
                provenance.get("bridge") == PRODUCTION_BRIDGE
                or provenance.get("boundary_double") is True
                or provenance.get("backend") == BOUNDARY_DOUBLE
            )
            if caller_claims_boundary:
                issued = None
                boundary = self.trusted_native_boundary
                if isinstance(boundary, TrustedNativeBoundary):
                    issued = boundary.lookup(supplied_p256)
                if issued is None:
                    raise HolderRefusal("a caller boundary flag is not a trusted native boundary")
                if issued.get("role") != role or issued.get("policy") != policy_name:
                    raise HolderRefusal("injected boundary role or policy does not match")
                if issued.get("generation") != self.generation:
                    raise HolderRefusal("injected boundary generation does not match")
                if issued.get("hardware") is not False:
                    raise HolderRefusal("injected boundary is not hardware")
                self._require_production_boundary_identity()
                fingerprint = compared
                devices[device_id] = {
                    "role": role,
                    "fingerprint": fingerprint,
                    "revoked": False,
                    "attestation": "device-p256-not-hardware",
                    "algorithm": "p256",
                    "public_key": supplied_p256,
                    "generation": self.generation,
                    "hardware": False,
                    "provenance": {
                        "bridge": PRODUCTION_BRIDGE,
                        "backend": BOUNDARY_DOUBLE,
                        "role": role,
                        "policy": policy_name,
                        "generation": self.generation,
                        "fingerprint": fingerprint,
                        "not_hardware": True,
                        "boundary_double": True,
                        "origin": "injected-trusted-native-boundary",
                    },
                }
                self._write("devices.json", devices)
                return {
                    "ok": True,
                    "device_id": device_id,
                    "role": role,
                    "attestation": "device-p256-not-hardware",
                    "public_key": supplied_p256,
                    "fingerprint": fingerprint,
                    "generation": self.generation,
                    "installed_protection": self.installed_protection,
                    "hardware": False,
                }
            if self.installed_protection:
                from runspecimen.native_bridge import production_enrollment_refusal

                raise HolderRefusal(production_enrollment_refusal())
            if provenance.get("bridge") == ISOLATED_DOUBLE:
                self._require_isolated_verifier()
                if provenance.get("public_key") != supplied_p256:
                    raise HolderRefusal("pairing public key provenance does not match")
                if provenance.get("role") != role or provenance.get("policy") != policy_name:
                    raise HolderRefusal("pairing provenance role or policy does not match")
                if provenance.get("generation") != self.generation:
                    raise HolderRefusal("pairing provenance generation does not match")
                fingerprint = compared
                devices[device_id] = {
                    "role": role,
                    "fingerprint": fingerprint,
                    "revoked": False,
                    "attestation": "device-p256-not-hardware",
                    "algorithm": "p256",
                    "public_key": supplied_p256,
                    "generation": self.generation,
                    "provenance": {
                        "bridge": ISOLATED_DOUBLE,
                        "role": role,
                        "policy": policy_name,
                        "generation": self.generation,
                        "fingerprint": fingerprint,
                        "not_hardware": True,
                        "isolated_double": True,
                    },
                }
                self._write("devices.json", devices)
                return {
                    "ok": True,
                    "device_id": device_id,
                    "role": role,
                    "attestation": "device-p256-not-hardware",
                    "public_key": supplied_p256,
                    "fingerprint": fingerprint,
                    "generation": self.generation,
                    "installed_protection": self.installed_protection,
                    "hardware": False,
                }
            if provenance.get("bridge") != _LABELED_NATIVE_BRIDGE:
                raise HolderRefusal("native enrollment bridge is not connected")
            if provenance.get("public_key") != supplied_p256:
                raise HolderRefusal("pairing public key provenance does not match")
            if provenance.get("role") != role or provenance.get("policy") != policy_name:
                raise HolderRefusal("pairing provenance role or policy does not match")
            if provenance.get("generation") != self.generation:
                raise HolderRefusal("pairing provenance generation does not match")
            fingerprint = compared
            public_hex = supplied_p256
            attestation = "device-p256-not-hardware"
            algorithm = "p256"
            devices[device_id] = {
                "role": role,
                "fingerprint": fingerprint,
                "revoked": False,
                "attestation": attestation,
                "algorithm": algorithm,
                "public_key": public_hex,
                "generation": self.generation,
                "provenance": {
                    "bridge": _LABELED_NATIVE_BRIDGE,
                    "role": role,
                    "policy": policy_name,
                    "generation": self.generation,
                    "fingerprint": fingerprint,
                    "not_hardware": True,
                },
            }
            self._write("devices.json", devices)
            return {
                "ok": True,
                "device_id": device_id,
                "role": role,
                "attestation": attestation,
                "public_key": public_hex,
                "fingerprint": fingerprint,
                "generation": self.generation,
                "installed_protection": self.installed_protection,
                "hardware": False,
            }
        elif human.get("method") == "software-test-double":
            attestation = "software-test-double"
            # Test double may omit asymmetric material; local/companion/dual cannot.
            public_hex = human.get("public_key") if isinstance(human.get("public_key"), str) else None
        elif human.get("attestation"):
            attestation = "unverified"
            public_hex = human.get("public_key") if isinstance(human.get("public_key"), str) else None
            if not public_hex:
                raise HolderRefusal("pairing public key is missing")
        else:
            attestation = "device-ed25519-not-hardware"
            from runspecimen.holder_asymmetric import AsymmetricError, vetted_verifier_available

            if not vetted_verifier_available():
                raise HolderRefusal("vetted device verifier is not connected")
            supplied = human.get("public_key")
            if isinstance(supplied, str) and supplied:
                public_hex = supplied
            else:
                try:
                    private_hex, public_hex = generate_device_keypair()
                except AsymmetricError as exc:
                    raise HolderRefusal("vetted device verifier is not connected") from exc
        devices[device_id] = {
            "role": role,
            "fingerprint": fingerprint,
            "revoked": False,
            "attestation": attestation,
            "algorithm": algorithm,
            "public_key": public_hex,
            "generation": self.generation,
        }
        self._write("devices.json", devices)
        result = {
            "ok": True,
            "device_id": device_id,
            "role": role,
            "attestation": attestation,
            "public_key": public_hex,
            "installed_protection": self.installed_protection,
            "hardware": False,
        }
        if private_hex is not None:
            result["private_key"] = private_hex
        return result

    def replace_device_key(
        self, device_id: str, human: dict[str, Any], *, now: float | None = None
    ) -> dict[str, Any]:
        with self._transaction():
            return self._replace_device_key_locked(device_id, human, now=now)

    def _replace_device_key_locked(
        self, device_id: str, human: dict[str, Any], *, now: float | None = None
    ) -> dict[str, Any]:
        self._load()
        self._require_enrollment()
        auth_policy = self._authorization_policy_for_mutation(None)
        self._human(human, purpose="replace-key", policy=auth_policy, subject=device_id, now=now)
        devices = self._devices()
        device = devices.get(device_id)
        if not isinstance(device, dict) or device.get("revoked") is True:
            raise HolderRefusal("device is missing or revoked")
        fingerprint = human.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise HolderRefusal("replacement fingerprint is missing")
        device["fingerprint"] = fingerprint
        device["attestation"] = "unverified" if human.get("attestation") else "software-test-double"
        devices[device_id] = device
        self._write("devices.json", devices)
        if device.get("role") in {"mac", "phone"}:
            self._drop_pending_phone_receipt()
        return {
            "ok": True,
            "device_id": device_id,
            "fingerprint": fingerprint,
            "installed_protection": self.installed_protection,
            "hardware": False,
        }

    def rotate_caller(self, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        with self._transaction():
            return self._rotate_caller_locked(human, now=now)

    def _rotate_caller_locked(self, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        self._load()
        enrollment = self._require_enrollment()
        caller_id = str(enrollment["caller_id"])
        self._human(human, purpose="rotate", policy=human.get("policy"), subject=caller_id, now=now)
        callers = self._read("callers.json")
        record = callers.get(caller_id)
        if not isinstance(record, dict) or record.get("revoked") is True:
            raise HolderRefusal("caller is missing or revoked")
        secret = secrets.token_hex(32)
        key_generation = int(record.get("key_generation", 1)) + 1
        callers[caller_id] = {
            "secret": secret,
            "revoked": False,
            "key_generation": key_generation,
        }
        self._write("callers.json", callers)
        meta = self._read("meta.json")
        meta["key_generation"] = key_generation
        self._write("meta.json", meta)
        self._drop_pending_phone_receipt()
        self._load()
        return {
            "ok": True,
            "caller_secret": secret,
            "key_generation": key_generation,
            "installed_protection": self.installed_protection,
            "hardware": False,
        }

    def revoke_device(self, device_id: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        with self._transaction():
            return self._revoke_device_locked(device_id, human, now=now)

    def _revoke_device_locked(self, device_id: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        self._load()
        self._require_enrollment()
        auth_policy = self._authorization_policy_for_mutation(None)
        self._human(human, purpose="revoke", policy=auth_policy, subject=device_id, now=now)
        devices = self._devices()
        device = devices.get(device_id)
        if not isinstance(device, dict):
            raise HolderRefusal("device is not paired")
        device["revoked"] = True
        devices[device_id] = device
        self._write("devices.json", devices)
        if device.get("role") in {"mac", "phone"} or device_id in {"mac-human", "phone-human"}:
            self._drop_pending_phone_receipt()
        return {
            "ok": True,
            "device_id": device_id,
            "revoked": True,
            "installed_protection": self.installed_protection,
            "hardware": False,
        }

    def set_policy(self, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        with self._transaction():
            return self._set_policy_locked(human, now=now)

    def _set_policy_locked(self, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        self._load()
        self._require_enrollment()
        if not isinstance(human, dict):
            raise HolderRefusal("human authorization is missing")
        destination = human.get("subject")
        if destination not in POLICIES:
            destination = human.get("policy")
        if destination not in POLICIES:
            raise HolderRefusal("policy is not local, companion, or dual")
        auth_policy = self._authorization_policy_for_mutation(str(destination))
        self._human(
            human,
            purpose="set-policy",
            policy=auth_policy,
            subject=str(destination),
            now=now,
        )
        policy = str(destination)
        generation = self.generation + 1
        self._write(
            "policy.json",
            {
                "name": policy,
                "generation": generation,
                "method": human["method"],
                "hardware": False,
                "devices": sorted(_DEVICES[policy]),
            },
        )
        meta = self._read("meta.json")
        meta["generation"] = generation
        self._write("meta.json", meta)
        self._drop_pending_phone_receipt()
        self._load()
        return {
            "ok": True,
            "policy": policy,
            "generation": generation,
            "holder_id": self.holder_id,
            "installed_protection": self.installed_protection,
        }

    def consume(
        self,
        *,
        nonce: str,
        policy: str,
        human: dict[str, Any],
        workspace: Path,
        files: list[tuple[str, str]],
        binding: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        with self._transaction():
            return self._consume_locked(
                nonce=nonce,
                policy=policy,
                human=human,
                workspace=workspace,
                files=files,
                binding=binding,
                now=now,
            )

    def _consume_locked(
        self,
        *,
        nonce: str,
        policy: str,
        human: dict[str, Any],
        workspace: Path,
        files: list[tuple[str, str]],
        binding: dict[str, Any] | None = None,
        now: float | None = None,
        prepared: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._load()
        self._refuse_lost_history()
        if isinstance(human, dict) and human.get("method") == "bootstrap":
            raise HolderRefusal("bootstrap authorization is limited to enroll and pair")
        if self._lease_held():
            raise HolderRefusal("a descendant or uncertain child still holds the lease")
        self._require_live_devices(policy, human)
        active = self._read("policy.json") if (self.root / "policy.json").exists() else None
        if not isinstance(active, dict) or active.get("name") != policy:
            raise HolderRefusal("consume policy does not match the holder policy")
        if not isinstance(nonce, str) or not nonce:
            raise HolderRefusal("nonce is missing")
        spent = self._spent()
        if any(item.get("nonce") == nonce for item in spent):
            raise HolderRefusal("nonce was already consumed")
        envelope = self._binding_envelope(binding)
        mutation_digest = hashlib.sha256(
            canonical_json_bytes(
                {
                    "files": [[a, b] for a, b in files],
                    "binding": envelope,
                }
            )
        ).hexdigest()
        envelope["mutation_digest"] = mutation_digest
        authorized = {
            "payload_digest": None,
            "launch_argv": list(envelope["launch_argv"]),
            "bounds": envelope["bounds"],
            "mutation_digest": mutation_digest,
            "attestation_class": self._paired_attestation_class(),
        }
        if prepared is None:
            path_map, payload_digest, snapshot_root = self._bind(
                nonce,
                workspace,
                files,
                executable=str(envelope["executable"]),
                argv=[str(item) for item in envelope["argv"]],
            )
        else:
            path_map = prepared["path_map"]
            payload_digest = str(prepared["payload_digest"])
            snapshot_root = str(prepared["snapshot_root"])
            if not isinstance(path_map, dict) or not snapshot_root:
                raise HolderRefusal("exact run snapshot is missing")
        if isinstance(human, dict) and human.get("method") == "exact-run-session":
            if payload_digest != human.get("payload_digest"):
                raise HolderRefusal("tampered exact run")
            if list(envelope["launch_argv"]) != list(human.get("launch_argv") or []):
                raise HolderRefusal("tampered exact run")
        snapshot_path = Path(snapshot_root)
        os.chmod(snapshot_path, 0o700)
        atomic_write_json(
            snapshot_path / "authorized_launch.json",
            {"launch_argv": [str(item) for item in envelope["launch_argv"]]},
        )
        self._restrict_snapshot_modes(snapshot_path)
        if payload_digest == self.holder_id:
            raise HolderRefusal("payload digest is not a distinct identity from the holder")
        authorized["payload_digest"] = payload_digest
        envelope["mutation_digest"] = mutation_digest
        self._human(
            human,
            purpose="consume",
            policy=policy,
            subject=nonce,
            now=now,
            authorized=authorized,
        )
        spent_record = {
            "nonce": nonce,
            "payload_digest": payload_digest,
            "policy": policy,
            "generation": self.generation,
            "holder_id": self.holder_id,
            "key_generation": self.key_generation,
            "binding": envelope,
        }
        if isinstance(human, dict) and human.get("method") == "exact-run-session":
            raw_bound = human.get("bound")
            if isinstance(raw_bound, bytes):
                raw_bound = base64.b64encode(raw_bound).decode("ascii")
            spent_record["exact_run"] = True
            spent_record["exact_bound"] = raw_bound
            spent_record["exact_expiry"] = human.get("expires_at")
            spent_record["launch_argv"] = list(human.get("launch_argv") or [])
            spent_record["hardware"] = False
            spent_record["not_hardware"] = True
        spent.append(spent_record)
        self._write("spent.json", {"nonces": spent})
        self._write(
            "lease.json",
            {"held": True, "token": nonce, "child": "uncertain"},
        )
        return {
            "ok": True,
            "nonce": nonce,
            "policy": policy,
            "payload_digest": payload_digest,
            "holder_id": self.holder_id,
            "generation": self.generation,
            "key_generation": self.key_generation,
            "snapshot_root": snapshot_root,
            "path_map": path_map,
            "binding": envelope,
            "residuals": list(_RESIDUALS),
            "installed_protection": self.installed_protection,
            "hardware": False,
        }

    def cancel_uncertain(self, token: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        """Cancel only before the holder has spawned. Authorization alone is not enough once a pid is recorded."""
        with self._transaction():
            return self._cancel_uncertain_locked(token, human, now=now)

    def _cancel_uncertain_locked(self, token: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        self._load()
        self._human(human, purpose="cancel", policy=human.get("policy"), subject=token, now=now)
        lease = self._read("lease.json") if (self.root / "lease.json").exists() else None
        if not isinstance(lease, dict) or lease.get("token") != token:
            raise HolderRefusal("cancel does not match the recorded child")
        if lease.get("child") != "uncertain":
            raise HolderRefusal("only an uncertain child can be cancelled this way")
        if lease.get("pid") is not None:
            raise HolderRefusal("cancel cannot clear a lease after the holder has spawned")
        spent = self._spent()
        record = next((item for item in spent if item.get("nonce") == token), None)
        if isinstance(record, dict) and record.get("exact_run") is True:
            raise HolderRefusal("an uncertain exact-run lease stays held until verified termination")
        self._write("lease.json", {"held": False, "token": token, "child": "cancelled"})
        return {"ok": True, "cancelled": True, "installed_protection": self.installed_protection}

    def note_child_absent(self, token: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        """Refuse client assertions that a child is gone. Lease release requires verified termination."""
        with self._transaction():
            return self._note_child_absent_locked(token, human, now=now)

    def _note_child_absent_locked(self, token: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        self._load()
        self._human(human, purpose="note-absent", policy=human.get("policy"), subject=token, now=now)
        lease = self._read("lease.json") if (self.root / "lease.json").exists() else None
        if not isinstance(lease, dict) or lease.get("token") != token:
            raise HolderRefusal("absent observation does not match the recorded child")
        if lease.get("child") == "uncertain" and lease.get("pid") is None:
            # Pre-spawn uncertain lease may be cleared only via cancel_uncertain.
            raise HolderRefusal(
                "note-absent cannot release a lease; cancel before spawn or wait for holder execute"
            )
        raise HolderRefusal(
            "lease release requires verified termination inside the holder"
        )

    def caller_secret(self, caller_id: str) -> str:
        callers = self._read("callers.json")
        record = callers.get(caller_id)
        if isinstance(record, str):
            return record
        if not isinstance(record, dict) or record.get("revoked") is True:
            raise HolderRefusal("caller is not enrolled")
        secret = record.get("secret")
        if not isinstance(secret, str):
            raise HolderRefusal("caller is not enrolled")
        return secret

    @property
    def holder_id(self) -> str:
        return str(self._meta["holder_id"])

    @property
    def generation(self) -> int:
        return int(self._meta["generation"])

    @property
    def key_generation(self) -> int:
        return int(self._meta.get("key_generation", 1))

    def _load(self) -> None:
        self._refuse_lost_history()
        meta = self._read("meta.json")
        if not isinstance(meta, dict) or meta.get("protocol") != PROTOCOL:
            raise HolderRefusal("holder protocol is missing or downgraded")
        if bool(meta.get("installed_protection")) != self.installed_protection:
            raise HolderRefusal("holder installed-protection flag does not match this process")
        policy_path = self.root / "policy.json"
        if policy_path.exists():
            policy = self._read("policy.json")
            if not isinstance(policy, dict) or policy.get("generation") != meta.get("generation"):
                raise HolderRefusal("holder generation does not match the policy record")
        self._meta = meta

    def _paired_attestation_class(self) -> str:
        """Challenge label follows the paired algorithm. It is not hardware."""
        algorithms = set()
        for record in self._devices().values():
            if not isinstance(record, dict) or record.get("revoked") is True:
                continue
            if not record.get("public_key"):
                continue
            algorithms.add(str(record.get("algorithm") or "ed25519"))
        if algorithms == {"p256"}:
            return "device-p256-not-hardware"
        return "device-ed25519-not-hardware"

    def _active_policy_name(self) -> str | None:
        path = self.root / "policy.json"
        if not path.exists():
            return None
        policy = self._read("policy.json")
        name = policy.get("name")
        if name not in POLICIES:
            raise HolderRefusal("stored policy is not local, companion, or dual")
        return str(name)

    def _authorization_policy_for_mutation(self, destination: str | None) -> str:
        """Policy under which a mutation must be authorized.

        Dropping a required factor needs authorization under the current policy.
        Adding or keeping factors may authorize under the destination. Revoke and
        replace without a destination authorize under the current policy.
        """
        current = self._active_policy_name()
        if current is None:
            if destination in POLICIES:
                return str(destination)
            raise HolderRefusal("human authorization policy is not local, companion, or dual")
        if destination is None:
            return current
        if destination not in POLICIES:
            raise HolderRefusal("policy is not local, companion, or dual")
        current_devices = _DEVICES[current]
        destination_devices = _DEVICES[str(destination)]
        if not current_devices.issubset(destination_devices):
            return current
        return str(destination)

    def _require_enrollment(self) -> dict[str, Any]:
        if not (self.root / "enrollment.json").exists():
            raise HolderRefusal("policy requires an enrolled caller")
        return self._read("enrollment.json")

    def _refuse_lost_history(self) -> None:
        if (self.root / "enrollment.json").exists() and not (self.root / "spent.json").exists():
            raise HolderRefusal("replay history is missing from an initialized holder")

    def _lease_held(self) -> bool:
        """True when a well-formed lease is held. Missing file is unused.

        An existing but unreadable or malformed lease fails closed. It is not
        treated as free.
        """
        path = self.root / "lease.json"
        if not path.exists():
            return False
        try:
            lease = read_json(path)
        except (OSError, ValueError, TypeError) as exc:
            raise HolderRefusal("lease record is unreadable") from exc
        if not isinstance(lease, dict):
            raise HolderRefusal("lease record is malformed")
        held = lease.get("held")
        if not isinstance(held, bool):
            raise HolderRefusal("lease held flag is malformed")
        return held

    def _spent(self) -> list[dict[str, Any]]:
        raw = self._read("spent.json")
        items = raw.get("nonces") if isinstance(raw, dict) else None
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise HolderRefusal("replay history is unreadable")
        return list(items)

    def _devices(self) -> dict[str, Any]:
        path = self.root / "devices.json"
        if not path.exists():
            return {}
        raw = self._read("devices.json")
        return raw

    def _require_live_devices(self, policy: str, human: dict[str, Any]) -> None:
        required = _DEVICES[policy]
        devices = self._devices()
        live_roles = {
            str(item.get("role"))
            for item in devices.values()
            if isinstance(item, dict) and item.get("revoked") is not True
        }
        if not required.issubset(live_roles):
            # Test doubles may exercise consume before pairing when the method
            # is the software stand-in. Hardware policies still require live roles.
            if human.get("method") != "software-test-double":
                raise HolderRefusal("required approval devices are missing or revoked")
        named = human.get("device_ids")
        if isinstance(named, list):
            for device_id in named:
                record = devices.get(device_id)
                if not isinstance(record, dict) or record.get("revoked") is True:
                    raise HolderRefusal("a named approval device is missing or revoked")

    def _binding_envelope(self, binding: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(binding, dict):
            raise HolderRefusal("consume binding is missing")
        required = (
            "contract_hash",
            "workspace",
            "argv",
            "executable",
            "policy",
            "bounds",
            "key_generation",
            "launch_argv",
        )
        for key in required:
            if key not in binding:
                raise HolderRefusal(f"consume binding is missing {key}")
        if binding.get("key_generation") != self.key_generation:
            raise HolderRefusal("consume key generation does not match the holder")
        launch_argv = binding.get("launch_argv")
        if not isinstance(launch_argv, list) or not launch_argv:
            raise HolderRefusal("consume binding launch_argv is malformed")
        return {
            "contract_hash": binding["contract_hash"],
            "workspace": binding["workspace"],
            "argv": list(binding["argv"]),
            "executable": binding["executable"],
            "policy": binding["policy"],
            "bounds": binding["bounds"],
            "key_generation": binding["key_generation"],
            "launch_argv": [str(item) for item in launch_argv],
            "cwd": binding.get("cwd"),
            "reads": list(binding.get("reads") or []),
            "mutation_digest": binding.get("mutation_digest"),
        }

    def _bind(
        self,
        nonce: str,
        workspace: Path,
        files: list[tuple[str, str]],
        *,
        executable: str | None = None,
        argv: list[str] | None = None,
    ) -> tuple[dict[str, str], str, str]:
        if not files:
            raise HolderRefusal("consume has no inputs to bind")
        fingerprints: dict[str, str] = {}
        ordered: list[str] = []
        for rel, digest in files:
            if not isinstance(rel, str) or not isinstance(digest, str):
                raise HolderRefusal("input binding is malformed")
            path = Path(rel)
            if path.is_absolute():
                key = str(path.resolve())
            else:
                key = str(ensure_within(workspace, path, label="execution input"))
            fingerprints[key] = digest
            ordered.append(key)
        executable_path = (
            executable if isinstance(executable, str) and executable else ordered[0]
        )
        if executable_path not in fingerprints:
            raise HolderRefusal("binding executable is not in the snapshot set")
        ws = workspace.resolve()
        try:
            Path(executable_path).resolve().relative_to(ws)
            executable_in_workspace = True
        except ValueError:
            executable_in_workspace = False
        # System interpreters stay live at launch. Snapshot only workspace files.
        # Their digests remain in the binding and path_map for audit.
        snap_executable = executable_path
        argv_paths: list[str] = []
        if executable_in_workspace:
            argv_paths.append(executable_path)
        if isinstance(argv, list):
            for token in argv[1:] if executable_in_workspace else argv[1:]:
                candidate = Path(str(token))
                if not candidate.is_absolute():
                    candidate = (ws / candidate).resolve()
                else:
                    candidate = candidate.resolve()
                key = str(candidate)
                if key in fingerprints and key not in argv_paths:
                    try:
                        candidate.relative_to(ws)
                    except ValueError:
                        continue
                    argv_paths.append(key)
        if not argv_paths:
            # No workspace argv paths: snapshot dependencies only via a sentinel.
            # Bind the first workspace file as the executable for the binder.
            workspace_files = []
            for key in ordered:
                try:
                    Path(key).resolve().relative_to(ws)
                except ValueError:
                    continue
                workspace_files.append(key)
            if not workspace_files:
                raise HolderRefusal("consume has no workspace inputs to snapshot")
            snap_executable = workspace_files[0]
            argv_paths = [snap_executable]
            inputs = tuple(workspace_files[1:])
            dependencies = ()
        else:
            snap_executable = argv_paths[0]
            inputs = tuple(path for path in argv_paths[1:] if path in fingerprints)
            dependencies = tuple(
                path
                for path in ordered
                if path != snap_executable
                and path not in inputs
                and path != executable_path
            )
            # Keep outside-workspace executable fingerprint without snapshotting it
            # into argv0 when it is a system interpreter.
            if not executable_in_workspace:
                dependencies = tuple(
                    path for path in ordered if path not in (snap_executable, *inputs)
                    and path != executable_path
                )
        request_fingerprints = {
            key: value
            for key, value in fingerprints.items()
            if key != executable_path or executable_in_workspace
        }
        # Always retain workspace fingerprints; drop only the live system binary
        # from the binder request so dyld is not asked to exec a copied framework.
        if not executable_in_workspace and executable_path in fingerprints:
            request_fingerprints = {
                key: value
                for key, value in fingerprints.items()
                if key != executable_path
            }
        request = LaunchRequest(
            nonce=nonce,
            argv=tuple(argv_paths),
            executable=snap_executable,
            inputs=inputs,
            dependencies=dependencies,
            fingerprints=request_fingerprints,
        )
        if not executable_in_workspace:
            expected = fingerprints[executable_path]
            live = Path(executable_path)
            try:
                fd = os.open(live, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            except OSError as exc:
                raise HolderRefusal(f"cannot open bound executable: {executable_path}") from exc
            try:
                data = b""
                while True:
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    data += chunk
            finally:
                os.close(fd)
            if hashlib.sha256(data).hexdigest() != expected:
                raise HolderRefusal("live executable does not match the bound digest")
        snapshot_root = self._prepare_payload_snapshot(nonce)
        try:
            bound = bind_execution(request, snapshot_root)
        except ProtocolError as exc:
            raise HolderRefusal(f"input snapshot does not match: {exc}") from exc
        try:
            path_map = {item.original: item.path for item in bound.snapshots}
            digests = tuple(item.digest for item in bound.snapshots)
        finally:
            bound.close()
        payload_digest = hashlib.sha256(canonical_json_bytes(list(digests))).hexdigest()
        atomic_write_json(snapshot_root / "path_map.json", path_map)
        self._restrict_snapshot_modes(snapshot_root)
        return path_map, payload_digest, str(snapshot_root)

    def execute(
        self,
        *,
        token: str,
        human: dict[str, Any],
        now: float | None = None,
        peer_uid: int | None = None,
        peer_gid: int | None = None,
    ) -> dict[str, Any]:
        """Spawn from the signed binding only. Lease clears after descendants are gone.

        Caller-supplied interpreter overrides are refused. When running as root,
        the payload drops to the mapped console user. Unprivileged tests do not
        prove installed protection. This is not functional biometric execution.
        """
        with self._transaction():
            self._load()
            lease_path = self.root / "lease.json"
            if not lease_path.exists():
                raise HolderRefusal("execute has no lease")
            lease = self._read("lease.json")
            if lease.get("token") != token or lease.get("held") is not True:
                raise HolderRefusal("execute does not match the held lease")
            if lease.get("child") != "uncertain":
                raise HolderRefusal("execute requires an uncertain lease before spawn")
            if lease.get("launch_started") is True:
                raise HolderRefusal("execute is already in progress for this lease")
            if isinstance(human, dict) and human.get("method") == "bootstrap":
                raise HolderRefusal("bootstrap authorization is limited to enroll and pair")
            spent = self._spent()
            record = next((item for item in spent if item.get("nonce") == token), None)
            if not isinstance(record, dict):
                raise HolderRefusal("execute nonce is not in replay history")
            binding = record.get("binding")
            if not isinstance(binding, dict):
                raise HolderRefusal("execute binding is missing")
            authorized = {
                "payload_digest": record.get("payload_digest"),
                "launch_argv": list(binding.get("launch_argv") or []),
                "bounds": binding.get("bounds"),
                "mutation_digest": binding.get("mutation_digest"),
                "attestation_class": self._paired_attestation_class(),
            }
            self._human(
                human,
                purpose="execute",
                policy=human.get("policy"),
                subject=token,
                now=now,
                authorized=authorized,
            )
            bounds = binding.get("bounds")
            if not isinstance(bounds, dict):
                raise HolderRefusal("execute bounds are missing")
            try:
                wall = float(bounds["wall_timeout_sec"])
                out_max = int(bounds["stdout_max_bytes"])
                err_max = int(bounds["stderr_max_bytes"])
            except (KeyError, TypeError, ValueError) as exc:
                raise HolderRefusal("execute bounds are malformed") from exc
            snapshot_root = self.snapshot_base / token
            if not snapshot_root.is_dir():
                raise HolderRefusal("execute snapshot root is missing")
            workspace = Path(str(binding["workspace"]))
            launch_argv = binding.get("launch_argv")
            if not isinstance(launch_argv, list) or not launch_argv:
                raise HolderRefusal("execute binding is missing launch_argv")
            launch_argv = [str(item) for item in launch_argv]
            sealed_launch_path = snapshot_root / "authorized_launch.json"
            if not sealed_launch_path.is_file():
                raise HolderRefusal("sealed launch vector is missing")
            sealed_launch = read_json(sealed_launch_path)
            if not isinstance(sealed_launch, dict):
                raise HolderRefusal("sealed launch vector is malformed")
            sealed_argv = sealed_launch.get("launch_argv")
            if not isinstance(sealed_argv, list) or [str(item) for item in sealed_argv] != launch_argv:
                raise HolderRefusal("launch vector mutated after consume")
            index_path = snapshot_root / "path_map.json"
            if not index_path.is_file():
                raise HolderRefusal("snapshot path map is missing")
            loaded = read_json(index_path)
            if not isinstance(loaded, dict):
                raise HolderRefusal("snapshot path map is malformed")
            path_map = {str(k): str(v) for k, v in loaded.items()}
            from runspecimen.holder_adapter import rewrite_launch_from_snapshots

            launch = rewrite_launch_from_snapshots(
                launch_argv,
                path_map=path_map,
                workspace=workspace,
                live_executable=str(binding.get("executable") or ""),
            )
            if not launch or not os.path.isabs(launch[0]) or not os.path.isfile(launch[0]):
                raise HolderRefusal("launch executable is not an absolute file")
            # Detect mutation of the authorized launch vector after consume.
            if [str(x) for x in launch_argv] != [str(x) for x in binding["launch_argv"]]:
                raise HolderRefusal("launch vector mutated after consume")
            cwd = Path(str(binding.get("cwd") or workspace))
            if not cwd.is_dir():
                raise HolderRefusal("execute cwd is missing")
            ws = workspace.resolve()
            for token_path in launch:
                candidate = Path(token_path)
                try:
                    resolved = candidate.resolve()
                except OSError:
                    continue
                try:
                    resolved.relative_to(ws)
                except ValueError:
                    continue
                if str(resolved) in path_map and str(resolved) == token_path:
                    raise HolderRefusal("execute refused a live workspace path after consume")
            run_uid, run_gid = self._payload_identity(peer_uid=peer_uid, peer_gid=peer_gid)
            # Snapshot tree must be readable by the deprivileged payload without
            # exposing the 0700 state directory.
            try:
                self._seal_payload_snapshot(snapshot_root, uid=run_uid, gid=run_gid)
            except OSError as exc:
                raise HolderRefusal(f"payload snapshot could not be sealed: {exc}") from exc
            self._write(
                "lease.json",
                {
                    "held": True,
                    "token": token,
                    "child": "running",
                    "pid": None,
                    "launch_started": True,
                    "run_uid": run_uid,
                    "run_gid": run_gid,
                },
            )
            proc: subprocess.Popen | None = None
            abort_payload = None
            try:
                proc, release_payload, abort_payload = self._spawn_dropped(
                    launch, cwd=cwd, uid=run_uid, gid=run_gid
                )
                watch = self._arm_payload_watch(int(proc.pid))
                if not watch["armed"]:
                    raise HolderRefusal("holder supervision could not be armed")
                release_payload()
                abort_payload = None
            except (OSError, HolderRefusal) as exc:
                self._disable_child_subreaper()
                try:
                    if proc is not None:
                        self._reap_unreleased_child(
                            proc, abort_payload, token, run_uid, run_gid
                        )
                    else:
                        # No child exists yet. That is not a confirmed death
                        # and not a clean release. Keep the pre-spawn uncertain
                        # lease. A spawned child that is then confirmed dead
                        # still records spawn-failed inside _reap_unreleased_child.
                        self._write(
                            "lease.json",
                            {
                                "held": True,
                                "token": token,
                                "child": "uncertain",
                                "pid": None,
                                "launch_started": False,
                            },
                        )
                finally:
                    if proc is not None:
                        self._close_child_streams(proc)
                if proc is None:
                    raise HolderRefusal(
                        "holder spawn failed before a child existed; uncertain lease retained"
                    ) from exc
                raise HolderRefusal(f"holder spawn failed: {exc}") from exc
            observed_pids: set[int] = {int(proc.pid)}
            observed_uncertain = False
            try:
                tracked = self._descendants_of(int(proc.pid))
                tracked.add(int(proc.pid))
                observed_pids |= tracked
            except HolderRefusal:
                observed_uncertain = True
                tracked = set(observed_pids)
            self._write(
                "lease.json",
                {
                    "held": True,
                    "token": token,
                    "child": "running",
                    "pid": int(proc.pid),
                    "pgid": int(proc.pid),
                    "launch_started": True,
                    "run_uid": run_uid,
                    "run_gid": run_gid,
                    "tracked_pids": sorted(tracked),
                },
            )
            stdout = bytearray()
            stderr = bytearray()
            stdout_trunc = False
            stderr_trunc = False
            deadline = time.monotonic() + max(0.1, wall)
            timed_out = False
            assert proc.stdout is not None and proc.stderr is not None
            for stream in (proc.stdout, proc.stderr):
                os.set_blocking(stream.fileno(), False)
            try:
                while True:
                    self._poll_payload_watch(watch)
                    try:
                        snap = self._process_table()
                        if snap is None:
                            observed_uncertain = True
                        else:
                            observed_pids |= self._descendants_of(int(proc.pid), snap)
                    except HolderRefusal:
                        observed_uncertain = True
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                    ready, _, _ = select.select(
                        [proc.stdout, proc.stderr], [], [], min(0.1, remaining)
                    )
                    for stream in ready:
                        try:
                            chunk = stream.read(65536) or b""
                        except BlockingIOError:
                            chunk = b""
                        if not chunk:
                            continue
                        if stream is proc.stdout:
                            if len(stdout) < out_max:
                                take = chunk[: out_max - len(stdout)]
                                stdout.extend(take)
                                if len(take) < len(chunk):
                                    stdout_trunc = True
                            else:
                                stdout_trunc = True
                        else:
                            if len(stderr) < err_max:
                                take = chunk[: err_max - len(stderr)]
                                stderr.extend(take)
                                if len(take) < len(chunk):
                                    stderr_trunc = True
                            else:
                                stderr_trunc = True
                    if proc.poll() is not None:
                        # Capture reparented children while the subreaper is still set.
                        watch["reparented"] = self._reparented_still_alive(watch)
                        # Bounded nonblocking drain; never exceed the wall deadline.
                        drain_deadline = min(deadline, time.monotonic() + 0.2)
                        while time.monotonic() < drain_deadline:
                            ready, _, _ = select.select(
                                [proc.stdout, proc.stderr],
                                [],
                                [],
                                max(0.0, drain_deadline - time.monotonic()),
                            )
                            if not ready:
                                break
                            progressed = False
                            for stream in ready:
                                try:
                                    chunk = stream.read(65536) or b""
                                except BlockingIOError:
                                    chunk = b""
                                if not chunk:
                                    continue
                                progressed = True
                                bucket = stdout if stream is proc.stdout else stderr
                                limit = out_max if stream is proc.stdout else err_max
                                if len(bucket) < limit:
                                    take = chunk[: limit - len(bucket)]
                                    bucket.extend(take)
                                    if len(take) < len(chunk):
                                        if stream is proc.stdout:
                                            stdout_trunc = True
                                        else:
                                            stderr_trunc = True
                                else:
                                    if stream is proc.stdout:
                                        stdout_trunc = True
                                    else:
                                        stderr_trunc = True
                            if not progressed:
                                break
                        break
                if timed_out:
                    try:
                        os.killpg(proc.pid, 15)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=min(2.0, max(0.1, deadline - time.monotonic())))
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, 9)
                        except ProcessLookupError:
                            pass
                        try:
                            proc.wait(timeout=1)
                        except subprocess.TimeoutExpired as exc:
                            raise HolderRefusal("holder could not stop the process group") from exc
                else:
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired as exc:
                        raise HolderRefusal("holder parent wait did not complete") from exc
            finally:
                self._disable_child_subreaper()
                for stream in (proc.stdout, proc.stderr):
                    try:
                        stream.close()
                    except OSError:
                        pass
            exit_code = proc.returncode
            if exit_code is None:
                raise HolderRefusal("holder execute did not observe process termination")
            self._poll_payload_watch(watch)
            # A fork note without a child identity, or a reparented child of this
            # supervisor, means a setsid descendant cannot be excluded. Do not
            # mark descendants absent and do not signal a pid we cannot match.
            if watch["fork_seen"] or watch.get("reparented") or self._reparented_still_alive(watch):
                self._retain_uncertain_lease(
                    token,
                    proc.pid,
                    run_uid,
                    run_gid,
                    exit_code,
                    identities=list(watch["identities"]),
                )
                raise HolderRefusal("holder supervision is uncertain; lease retained")
            # Process-group absence is not descendant absence. Pids observed
            # while the parent was alive are required because setsid reparents
            # children to init before a post-wait scan. Inspection failure retains
            # the lease.
            if observed_uncertain:
                self._retain_uncertain_lease(token, proc.pid, run_uid, run_gid, exit_code)
                raise HolderRefusal("holder supervision is uncertain; lease retained")
            try:
                table = self._process_table()
                if table is None:
                    raise HolderRefusal("holder process inspection failed; lease retained")
                tracked = set(observed_pids)
                tracked |= self._descendants_of(int(proc.pid), table)
                tracked.add(int(proc.pid))
            except HolderRefusal:
                self._retain_uncertain_lease(token, proc.pid, run_uid, run_gid, exit_code)
                raise
            lingering = {pid for pid in tracked if pid != int(proc.pid) and not self._pid_absent(pid)}
            if lingering or not self._process_group_absent(int(proc.pid)):
                try:
                    os.killpg(proc.pid, 9)
                except ProcessLookupError:
                    pass
                for pid in list(tracked):
                    if pid == int(proc.pid):
                        continue
                    started = self._start_token(pid)
                    if started is None:
                        continue
                    try:
                        self._signal_matching_identity(pid, started, 9)
                    except PermissionError:
                        self._retain_uncertain_lease(token, proc.pid, run_uid, run_gid, exit_code)
                        raise HolderRefusal("holder could not signal a descendant; lease retained")
                still = {pid for pid in tracked if pid != int(proc.pid) and not self._pid_absent(pid)}
                if still or not self._process_group_absent(int(proc.pid)):
                    self._retain_uncertain_lease(token, proc.pid, run_uid, run_gid, exit_code)
                    raise HolderRefusal(
                        "holder descendants are still alive (setsid-aware tree); lease not released"
                    )
            self._write(
                "lease.json",
                {
                    "held": False,
                    "token": token,
                    "child": "timeout" if timed_out else "exited",
                    "pid": int(proc.pid),
                    "pgid": int(proc.pid),
                    "exit_code": int(exit_code),
                    "launch_started": True,
                    "descendants_absent": True,
                    "run_uid": run_uid,
                    "run_gid": run_gid,
                },
            )
            return {
                "ok": True,
                "token": token,
                "exit_code": int(exit_code),
                "timed_out": bool(timed_out),
                "stdout_b64": base64.b64encode(bytes(stdout)).decode("ascii"),
                "stderr_b64": base64.b64encode(bytes(stderr)).decode("ascii"),
                "stdout_truncated": bool(stdout_trunc),
                "stderr_truncated": bool(stderr_trunc),
                "installed_protection": self.installed_protection,
                "hardware": False,
                "attestation_class": self._paired_attestation_class(),
                "supervisor": "holder",
                "run_uid": run_uid,
                "run_gid": run_gid,
            }

    def _human(
        self,
        human: dict[str, Any],
        *,
        purpose: str,
        policy: object,
        subject: object,
        now: float | None = None,
        authorized: dict[str, Any] | None = None,
    ) -> None:
        if not isinstance(human, dict):
            raise HolderRefusal("human authorization is missing")
        if any(value == _PHRASE for value in human.values()):
            raise HolderRefusal("a typed phrase cannot authorize the holder")
        method = human.get("method")
        if method == "phrase" or not isinstance(method, str):
            raise HolderRefusal("human authorization method is not accepted")
        if human.get("purpose") != purpose or human.get("subject") != subject:
            raise HolderRefusal("human authorization does not match this operation")
        if policy not in POLICIES or human.get("policy") != policy:
            raise HolderRefusal("human authorization policy is not local, companion, or dual")
        devices = human.get("devices")
        if not isinstance(devices, list) or set(devices) != _DEVICES[str(policy)]:
            raise HolderRefusal("human authorization devices do not match the policy")
        expires = human.get("expires_at")
        if isinstance(expires, bool) or not isinstance(expires, int) or expires < 0:
            raise HolderRefusal("human authorization expiry is invalid")
        if expires <= time.time():
            raise HolderRefusal("human authorization has expired")
        if method == "exact-run-session":
            self._verify_exact_run_session(
                human,
                purpose=purpose,
                policy=str(policy),
                subject=subject,
                authorized=authorized,
            )
            return
        if method == "software-test-double":
            if not self.allow_test_double or human.get("hardware") is not False:
                raise HolderRefusal("software test double is not a human authorization")
            if human.get("attestation_class") not in {None, "software-test-double-not-hardware"}:
                raise HolderRefusal("software test double must stay labeled not-hardware")
            return
        if method == "bootstrap":
            if purpose not in {"enroll", "pair"}:
                raise HolderRefusal("bootstrap authorization is limited to enroll and pair")
            if not isinstance(self.bootstrap_secret, str) or len(self.bootstrap_secret) < 32:
                raise HolderRefusal("bootstrap verifier is not configured")
            proof = human.get("bootstrap_mac")
            challenge = {
                "purpose": purpose,
                "subject": subject,
                "policy": policy,
                "devices": list(devices),
                "expires_at": expires,
                "domain": "holder-bootstrap-v1",
            }
            expected = message_mac(self.bootstrap_secret, challenge)
            if not isinstance(proof, str) or not hmac.compare_digest(proof, expected):
                raise HolderRefusal("bootstrap authentication failed")
            if human.get("hardware") is True:
                raise HolderRefusal("bootstrap authorization is not hardware")
            return
        if method in {"local", "companion", "dual"}:
            if method != policy:
                raise HolderRefusal("human authorization method does not match policy")
            self._verify_device_signatures(
                human,
                purpose=purpose,
                policy=str(policy),
                subject=subject,
                authorized=authorized,
            )
            return
        raise HolderRefusal("human authorization method is not accepted")

    def _verifier_binary(self) -> Path | None:
        from runspecimen.native_bridge import platform_verifier_binary, resolve_verifier

        if self.verifier_root is not None:
            return resolve_verifier(self.verifier_root)
        return platform_verifier_binary()

    def _require_isolated_verifier(self) -> None:
        from runspecimen.native_bridge import VerifierIdentityError, require_verifier_identity

        try:
            require_verifier_identity(self.verifier_pin, self._verifier_binary())
        except VerifierIdentityError as exc:
            raise HolderRefusal(str(exc)) from exc

    def _require_production_boundary_identity(self) -> None:
        from runspecimen.native_bridge import (
            VerifierIdentityError,
            effective_verifier_pin,
            require_verifier_identity,
        )

        try:
            require_verifier_identity(effective_verifier_pin(self.verifier_pin), self._verifier_binary())
        except VerifierIdentityError as exc:
            raise HolderRefusal(str(exc)) from exc

    def _os_boundary_authorizes(self, device_id: str, record: dict[str, Any]) -> bool:
        """True only when the holder wrote this public key after the OS call.

        The origin string is not consulted. A caller-supplied
        ``human-operated-native-adapter`` or ``secure-enclave-human-prompt``
        value does not authorize the device.
        """

        proof_path = self.root / "os-boundary.json"
        if not proof_path.is_file():
            return False
        try:
            proof = read_json(proof_path)
        except (OSError, ValueError):
            return False
        keys = proof.get("keys") if isinstance(proof, dict) else None
        entry = keys.get(device_id) if isinstance(keys, dict) else None
        provenance = record.get("provenance") if isinstance(record, dict) else None
        if not isinstance(entry, dict) or not isinstance(provenance, dict):
            return False
        if record.get("revoked") is True:
            return False
        return (
            provenance.get("os_boundary_id") == entry.get("id")
            and record.get("public_key") == entry.get("public_key")
            and provenance.get("generation") == entry.get("generation")
            and isinstance(entry.get("id"), str)
            and bool(entry.get("id"))
        )

    def _require_installed_production_boundary(self, human: dict[str, Any], devices: dict[str, Any]) -> None:
        from runspecimen.native_bridge import production_enrollment_refusal

        if human.get("hardware") is True:
            raise HolderRefusal("software P-256 is not a Secure Enclave")
        signatures = human.get("signatures")
        if not isinstance(signatures, dict) or not signatures:
            raise HolderRefusal(production_enrollment_refusal())
        for device_id in signatures:
            record = devices.get(device_id)
            provenance = record.get("provenance") if isinstance(record, dict) else None
            if not isinstance(provenance, dict) or not isinstance(record, dict):
                raise HolderRefusal(production_enrollment_refusal())
            # A pin match authenticates verifier code later. It does not make
            # a persisted origin string into a native key.
            if (
                provenance.get("boundary_double") is True
                or provenance.get("not_hardware") is True
                or not self._os_boundary_authorizes(str(device_id), record)
            ):
                raise HolderRefusal(production_enrollment_refusal())
        self._require_production_boundary_identity()

    def _verify_device_signatures(
        self,
        human: dict[str, Any],
        *,
        purpose: str,
        policy: str,
        subject: object,
        authorized: dict[str, Any] | None,
    ) -> None:
        from runspecimen.holder_asymmetric import (
            AsymmetricError,
            constant_time_label_ok,
            digest_challenge,
            verify_device_signature,
            verify_native_p256,
        )

        devices = self._devices()
        if self.installed_protection:
            self._require_installed_production_boundary(human, devices)
        signatures = human.get("signatures")
        if not isinstance(signatures, dict) or not signatures:
            raise HolderRefusal("cryptographic device signatures are missing")
        required_roles = set(_DEVICES[policy])
        covered_roles: set[str] = set()
        challenge = {
            "purpose": purpose,
            "subject": subject,
            "policy": policy,
            "devices": sorted(required_roles),
            "expires_at": human.get("expires_at"),
            "holder_id": self.holder_id,
            "generation": self.generation,
            "domain": "holder-device-ed25519-v1",
            "attestation_class": "device-ed25519-not-hardware",
            "authorized": authorized or {},
        }
        algorithms = set()
        for device_id in signatures:
            record = devices.get(device_id)
            if isinstance(record, dict):
                algorithms.add(str(record.get("algorithm") or "ed25519"))
        if algorithms == {"p256"}:
            challenge["domain"] = "holder-device-p256-v1"
            challenge["attestation_class"] = "device-p256-not-hardware"
            paired: list[dict[str, Any]] = []
            for device_id in sorted(signatures):
                record = devices.get(device_id)
                if not isinstance(record, dict):
                    continue
                provenance = record.get("provenance")
                os_authorized = self._os_boundary_authorizes(device_id, record)
                if not isinstance(provenance, dict) or (
                    provenance.get("not_hardware") is not True and not os_authorized
                ):
                    raise HolderRefusal("pairing public key provenance is missing")
                paired.append(
                    {
                        "device_id": device_id,
                        "fingerprint": record.get("fingerprint"),
                        "generation": record.get("generation"),
                        "policy": provenance.get("policy"),
                        "role": record.get("role"),
                    }
                )
            challenge["paired"] = paired
        elif algorithms and algorithms != {"ed25519"}:
            raise HolderRefusal("device signature algorithms disagree")
        message = digest_challenge(challenge)
        for device_id, signature in signatures.items():
            record = devices.get(device_id)
            if not isinstance(record, dict) or record.get("revoked") is True:
                raise HolderRefusal("a signing device is missing or revoked")
            public_key = record.get("public_key")
            if not isinstance(public_key, str) or not public_key:
                raise HolderRefusal("device public key is missing")
            if not isinstance(signature, str):
                raise HolderRefusal("device signature verification failed")
            if record.get("algorithm") == "p256":
                provenance = record.get("provenance")
                from runspecimen.native_bridge import ISOLATED_DOUBLE

                if isinstance(provenance, dict) and provenance.get("bridge") == ISOLATED_DOUBLE:
                    self._require_isolated_verifier()
                if (
                    isinstance(provenance, dict)
                    and provenance.get("bridge") == "native-production-bridge"
                    and provenance.get("boundary_double") is True
                ):
                    self._require_production_boundary_identity()
                verified = verify_native_p256(
                    public_key, signature, message, binary=self._verifier_binary()
                )
            else:
                verified = verify_device_signature(public_key, signature, message)
            if not verified:
                raise HolderRefusal("device signature verification failed")
            role = record.get("role")
            if role in required_roles:
                covered_roles.add(str(role))
        if covered_roles != required_roles:
            raise HolderRefusal("required device signatures are incomplete")
        if human.get("attestation_class") != challenge["attestation_class"]:
            raise HolderRefusal("device signatures must stay labeled not-hardware")
        try:
            constant_time_label_ok(human.get("attestation_class"), hardware=human.get("hardware"))
        except AsymmetricError as exc:
            raise HolderRefusal(str(exc)) from exc

    def _restrict_snapshot_modes(self, snapshot_root: Path) -> None:
        """Remove group and world access. Failure is not ignored."""
        try:
            for dirpath, _dirnames, filenames in os.walk(snapshot_root):
                os.chmod(dirpath, 0o500)
                st_dir = os.stat(dirpath)
                if st_dir.st_mode & 0o077:
                    raise HolderRefusal("payload snapshot is readable by other users")
                for name in filenames:
                    fpath = Path(dirpath) / name
                    mode = 0o500 if os.access(fpath, os.X_OK) else 0o400
                    os.chmod(fpath, mode)
                    if os.stat(fpath).st_mode & 0o077:
                        raise HolderRefusal("payload snapshot is readable by other users")
        except OSError as exc:
            raise HolderRefusal("payload snapshot could not be sealed") from exc

    def _apply_read_acl(self, path: Path, uid: int) -> None:
        """Grant read and traverse without write. Never changes ownership."""
        if sys.platform == "darwin":
            spec = f"user:{uid} allow read,execute,file_inherit,directory_inherit"
            argv = ["chmod", "+a", spec, str(path)]
        else:
            argv = ["setfacl", "-m", f"u:{uid}:rX", str(path)]
        try:
            proc = subprocess.run(argv, check=False, capture_output=True, text=True)
        except OSError as exc:
            raise HolderRefusal("payload snapshot read grant failed") from exc
        if proc.returncode != 0:
            raise HolderRefusal("payload snapshot read grant failed")

    def _seal_payload_snapshot(self, snapshot_root: Path, *, uid: int, gid: int | None = None) -> None:
        """Keep the snapshot owned by the holder. The payload must not own it.

        An owner can chmod 0500/0400 back to writable and change approved bytes.
        Mode bits do not stop that. When the holder is root, read and traverse
        are granted with an ACL and ownership stays root. Enrollment, policy,
        spent nonces, and leases stay in the 0700 state directory.
        """
        del gid
        if uid == 0:
            raise HolderRefusal("payload snapshot refuses uid 0")
        self._restrict_snapshot_modes(snapshot_root)
        if os.geteuid() != 0:
            return
        holder_uid = os.geteuid()
        try:
            paths = [snapshot_root]
            for dirpath, _dirnames, filenames in os.walk(snapshot_root):
                paths.append(Path(dirpath))
                paths.extend(Path(dirpath) / name for name in filenames)
            for path in paths:
                if os.stat(path).st_uid != holder_uid:
                    raise HolderRefusal("payload snapshot ownership escaped the holder")
                self._apply_read_acl(path, uid)
        except OSError as exc:
            raise HolderRefusal("payload snapshot could not be sealed") from exc

    def _prepare_payload_snapshot(self, token: str) -> Path:
        """Create an immutable-for-payload snapshot dir outside 0700 state."""
        root = self.snapshot_base / token
        if root.exists():
            raise HolderRefusal("payload snapshot token already exists")
        try:
            root.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise HolderRefusal("payload snapshot token already exists") from exc
        try:
            os.chmod(root, 0o700)
        except OSError as exc:
            raise HolderRefusal("payload snapshot could not be sealed") from exc
        return root

    def _payload_identity(self, *, peer_uid: int | None = None, peer_gid: int | None = None) -> tuple[int, int]:
        """Map payload execution to an authenticated non-root peer identity.

        Environment UID overrides are not an authenticated peer mapping and are
        refused. UID 0 is never accepted as the payload identity.
        """
        if peer_uid is not None:
            if peer_uid == 0:
                raise HolderRefusal("payload identity refuses root peer uid")
            gid = int(peer_gid) if peer_gid is not None and peer_gid >= 0 else peer_uid
            if gid == 0 and os.geteuid() == 0:
                raise HolderRefusal("payload identity refuses root peer gid")
            return int(peer_uid), int(gid)
        if os.geteuid() != 0:
            uid, gid = os.getuid(), os.getgid()
            if uid == 0:
                raise HolderRefusal("payload identity refuses uid 0")
            return uid, gid
        # Root daemon: require an authenticated peer from the connection.
        raise HolderRefusal("holder requires authenticated non-root peer identity for payload")

    def _close_child_streams(self, proc: subprocess.Popen) -> None:
        """Close holder-owned pipes even when spawn aborts before the read loop."""
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass

    def _reap_unreleased_child(
        self,
        proc: subprocess.Popen,
        abort: Any,
        token: str,
        run_uid: int,
        run_gid: int,
    ) -> None:
        """Close the gate, reap the paused child, and keep the lease if it remains.

        The go byte is not written. A cleared lease means the child is gone.
        """
        if abort is not None:
            try:
                abort()
            except OSError:
                pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, 9)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._retain_uncertain_lease(token, int(proc.pid), run_uid, run_gid, None)
                raise HolderRefusal(
                    "holder spawn failed and the child is still alive; lease retained"
                ) from None
        if proc.poll() is None or not self._pid_absent(int(proc.pid)):
            self._retain_uncertain_lease(token, int(proc.pid), run_uid, run_gid, None)
            raise HolderRefusal(
                "holder spawn failed and the child is still alive; lease retained"
            )
        # Definite non-start: the child was spawned and then confirmed dead
        # before the payload was released. This release is not the pre-spawn
        # uncertain lease, which execute keeps when no child exists.
        self._write("lease.json", {"held": False, "token": token, "child": "spawn-failed"})

    def _spawn_dropped(
        self,
        launch: list[str],
        *,
        cwd: Path,
        uid: int,
        gid: int,
    ) -> tuple[subprocess.Popen, Any, Any]:
        """Spawn paused until supervision is armed. Never use preexec_fn."""
        if uid == 0:
            raise HolderRefusal("payload identity refuses uid 0")
        supervise = Path(__file__).resolve().with_name("holder_supervise_exec.py")
        drop = Path(__file__).resolve().with_name("holder_drop_exec.py")
        if not supervise.is_file() or not drop.is_file():
            raise HolderRefusal("holder exec helper is missing")
        if os.geteuid() != 0:
            if os.getuid() != uid:
                raise HolderRefusal("unprivileged holder cannot impersonate another uid")
            payload = list(launch)
        else:
            payload = [
                sys.executable,
                "-I",
                str(drop),
                "--uid",
                str(uid),
                "--gid",
                str(gid),
                "--cwd",
                str(cwd),
                "--",
                *launch,
            ]
        from runspecimen.holder_supervise_exec import GO_BYTE

        gate_r, gate_w = os.pipe()
        argv = [sys.executable, "-I", str(supervise), str(gate_r), "--", *payload]
        try:
            proc = subprocess.Popen(  # noqa: S603
                argv,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                shell=False,
                start_new_session=True,
                pass_fds=(gate_r,),
            )
        except OSError:
            os.close(gate_r)
            os.close(gate_w)
            raise
        os.close(gate_r)
        gate = {"fd": gate_w}

        def release() -> None:
            fd = gate["fd"]
            if fd is None:
                return
            gate["fd"] = None
            try:
                os.write(fd, GO_BYTE)
            finally:
                os.close(fd)

        def abort() -> None:
            """Close the gate without the go byte. EOF is not permission to exec."""
            fd = gate["fd"]
            if fd is None:
                return
            gate["fd"] = None
            os.close(fd)

        return proc, release, abort

    def _arm_payload_watch(self, pid: int) -> dict[str, Any]:
        """Register a fork watch before the payload is released.

        Darwin kqueue NOTE_FORK does not report the child pid. A fork note
        therefore makes supervision uncertain. Linux uses a child subreaper so
        a setsid grandchild is reparented here instead of disappearing.
        """
        watch: dict[str, Any] = {
            "armed": False,
            "fork_seen": False,
            "kq": None,
            "started": self._start_token(pid),
            "baseline": self._child_pids(os.getpid()) or set(),
            "payload_pid": pid,
            "identities": [],
        }
        watch["baseline"].add(pid)
        if hasattr(select, "kqueue"):
            try:
                kq = select.kqueue()
                event = select.kevent(
                    pid,
                    select.KQ_FILTER_PROC,
                    select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                    select.KQ_NOTE_EXIT | select.KQ_NOTE_FORK,
                )
                kq.control([event], 0)
                watch["kq"] = kq
                watch["armed"] = True
            except (AttributeError, OSError):
                watch["kq"] = None
        if sys.platform == "linux" and self._enable_child_subreaper():
            watch["armed"] = True
        return watch

    def _enable_child_subreaper(self) -> bool:
        if sys.platform != "linux":
            return False
        try:
            import ctypes

            libc = ctypes.CDLL(None, use_errno=True)
            libc.prctl.argtypes = [
                ctypes.c_int,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.c_ulong,
            ]
            libc.prctl.restype = ctypes.c_int
            return libc.prctl(36, 1, 0, 0, 0) == 0
        except (AttributeError, OSError):
            return False

    def _disable_child_subreaper(self) -> None:
        """Drop the subreaper so later tests are not the parent of foreign orphans."""
        if sys.platform != "linux":
            return
        try:
            import ctypes

            libc = ctypes.CDLL(None, use_errno=True)
            libc.prctl.argtypes = [
                ctypes.c_int,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.c_ulong,
            ]
            libc.prctl.restype = ctypes.c_int
            libc.prctl(36, 0, 0, 0, 0)
        except (AttributeError, OSError):
            return

    def _poll_payload_watch(self, watch: dict[str, Any]) -> None:
        kq = watch.get("kq")
        if kq is None:
            return
        try:
            events = kq.control(None, 32, 0)
        except OSError:
            watch["fork_seen"] = True
            return
        note_fork = getattr(select, "KQ_NOTE_FORK", 0)
        for event in events:
            if note_fork and event.fflags & note_fork:
                watch["fork_seen"] = True

    def _child_pids(self, parent: int) -> set[int] | None:
        table = self._process_table()
        if table is None:
            return None
        return {pid for pid, ppid in table.items() if ppid == parent}

    def _start_token(self, pid: int) -> str | None:
        """Process start stamp. A reused pid has a different stamp."""
        try:
            out = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "lstart="],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            return None
        token = out.strip()
        return token or None

    def _signal_matching_identity(self, pid: int, started: str | None, sig: int) -> None:
        """Signal only when the start stamp still matches. Never a reused pid."""
        if started is None:
            return
        current = self._start_token(pid)
        if current != started:
            return
        os.kill(pid, sig)

    def _reparented_still_alive(self, watch: dict[str, Any]) -> bool:
        """True when a child of this supervisor appeared after the launch."""
        current = self._child_pids(os.getpid())
        if current is None:
            return True
        extra = set(current) - set(watch["baseline"])
        extra.discard(int(watch["payload_pid"]))
        identities: list[dict[str, Any]] = []
        alive = False
        for pid in sorted(extra):
            started = self._start_token(pid)
            if started is None:
                continue
            identities.append({"pid": int(pid), "started": started})
            alive = True
        watch["identities"] = identities
        return alive

    def _process_table(self) -> dict[int, int] | None:
        """Return pid -> ppid, or None when inspection fails.

        An empty or failed process table is supervision uncertainty. It is not
        proof that descendants are gone.
        """
        table: dict[int, int] = {}
        try:
            import subprocess as _sp

            out = _sp.check_output(["ps", "-axo", "pid=,ppid="], text=True)
        except (OSError, _sp.SubprocessError):
            return None
        if not out.strip():
            return None
        for line in out.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            try:
                table[int(parts[0])] = int(parts[1])
            except ValueError:
                continue
        return table

    def _descendants_of(self, root_pid: int, table: dict[int, int] | None = None) -> set[int]:
        """Collect the ppid-tree under root_pid.

        ``table is None`` means inspection failed. Callers must retain the lease
        instead of treating that as an empty descendant set. setsid reparents
        children, so callers must also keep pids observed before the parent exits.
        """
        if table is None:
            table = self._process_table()
        if table is None:
            raise HolderRefusal("holder process inspection failed; lease retained")
        children: dict[int, list[int]] = {}
        for pid, ppid in table.items():
            children.setdefault(ppid, []).append(pid)
        seen: set[int] = set()
        stack = [root_pid]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(children.get(current, []))
        return seen

    def _pid_absent(self, pid: int) -> bool:
        if pid <= 0:
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def _retain_uncertain_lease(
        self,
        token: str,
        pid: int,
        run_uid: int,
        run_gid: int,
        exit_code: int | None,
        identities: list[dict[str, Any]] | None = None,
    ) -> None:
        """Keep the lease. Uncertainty is not a release and not descendant absence."""
        record: dict[str, Any] = {
            "held": True,
            "token": token,
            "child": "supervision-uncertain",
            "pid": int(pid),
            "pgid": int(pid),
            "exit_code": exit_code,
            "launch_started": True,
            "descendants_absent": False,
            "run_uid": run_uid,
            "run_gid": run_gid,
        }
        if identities:
            record["tracked_identities"] = identities
        self._write("lease.json", record)

    def _pids_absent(self, pids: set[int]) -> bool:
        for pid in pids:
            if pid <= 0:
                continue
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            except PermissionError:
                return False
            else:
                return False
        return True

    def _process_group_absent(self, pgid: int) -> bool:
        """Process-group absence alone does not prove setsid descendants are gone."""
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def _transaction(self):
        lock_path = self.root / ".holder.op.lock"
        lock_path.touch(exist_ok=True)
        fd = os.open(str(lock_path), os.O_RDWR)

        class _Lock:
            def __enter__(self_inner):
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                if fcntl is not None:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
                os.close(fd)
                return False

        return _Lock()

    def _read(self, name: str) -> dict[str, Any]:
        value = read_json(self.root / name)
        if not isinstance(value, dict):
            raise HolderRefusal(f"{name} is not a holder record")
        self._validate_record_schema(name, value)
        return value

    def _write(self, name: str, value: dict[str, Any]) -> None:
        self._validate_record_schema(name, value)
        # Individual writes still go through the open transaction when callers hold it.
        atomic_write_json(self.root / name, value)

    def _validate_record_schema(self, name: str, value: dict[str, Any]) -> None:
        allowed = {
            "meta.json": {"protocol", "generation", "holder_id", "installed_protection", "key_generation"},
            "enrollment.json": {"caller_id", "policy", "method", "hardware", "generation", "key_generation"},
            "policy.json": {"name", "generation", "method", "hardware", "devices"},
            "lease.json": {
                "held",
                "token",
                "child",
                "pid",
                "pgid",
                "exit_code",
                "launch_started",
                "descendants_absent",
                "run_uid",
                "run_gid",
                "tracked_pids",
                "tracked_identities",
            },
            "spent.json": {"nonces"},
            "callers.json": None,
            "devices.json": None,
        }
        keys = allowed.get(name)
        if keys is None:
            return
        unknown = set(value) - keys
        if unknown:
            raise HolderRefusal(f"{name} has unknown fields: {sorted(unknown)}")


def message_mac(secret_hex: str, payload: dict[str, Any]) -> str:
    try:
        key = bytes.fromhex(secret_hex)
    except ValueError as exc:
        raise HolderRefusal("caller secret is not hex") from exc
    return hmac.new(key, canonical_json_bytes(payload), hashlib.sha256).hexdigest()


def seal(secret_hex: str, *, caller_id: str, body: dict[str, Any]) -> dict[str, Any]:
    covered = {"protocol": PROTOCOL, "caller_id": caller_id, "body": body}
    return {**covered, "mac": message_mac(secret_hex, covered)}


def open_sealed(secret_hex: str, message: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(message, dict):
        raise HolderRefusal("holder message is not an object")
    if message.get("protocol") != PROTOCOL:
        raise HolderRefusal("holder protocol downgrade or unknown version")
    mac = message.get("mac")
    covered = {
        "protocol": message.get("protocol"),
        "caller_id": message.get("caller_id"),
        "body": message.get("body"),
    }
    if not isinstance(mac, str) or not hmac.compare_digest(mac, message_mac(secret_hex, covered)):
        raise HolderRefusal("caller authentication failed")
    body = message.get("body")
    if not isinstance(body, dict):
        raise HolderRefusal("holder body is missing")
    return body


def _has_history(root: Path) -> bool:
    return any(
        (root / name).exists()
        for name in ("enrollment.json", "policy.json", "spent.json", "lease.json", "devices.json")
    )


def dispatch(holder: ExecutionHolder, body: dict[str, Any], *, caller_id: str) -> dict[str, Any]:
    op = body.get("op")
    # Ignore any client-supplied clock. Expiry uses time.time() in the holder.
    clock = None
    if op == "native-enroll":
        raise HolderRefusal("native enrollment cannot be selected from wire input")
    if op == "issue-device-challenge":
        peer = body.get("_peer_uid")
        if not isinstance(peer, int):
            raise HolderRefusal("ipc peer is missing")
        return holder.issue_device_challenge(str(body.get("role")), peer_uid=peer)
    if op == "cancel-device-challenge":
        peer = body.get("_peer_uid")
        if not isinstance(peer, int):
            raise HolderRefusal("ipc peer is missing")
        return holder.cancel_device_challenge(str(body.get("role")), peer_uid=peer)
    if op == "submit-device-signature":
        peer = body.get("_peer_uid")
        if not isinstance(peer, int):
            raise HolderRefusal("ipc peer is missing")
        return holder.submit_device_signature(body, peer_uid=peer)
    if op == "prepare-phone-receipt":
        peer = body.get("_peer_uid")
        if not isinstance(peer, int):
            raise HolderRefusal("ipc peer is missing")
        return holder.prepare_phone_receipt(body, peer_uid=peer)
    if op == "seal-phone-receipt":
        peer = body.get("_peer_uid")
        if not isinstance(peer, int):
            raise HolderRefusal("ipc peer is missing")
        return holder.seal_phone_receipt(body, peer_uid=peer)
    if op == "session-generation":
        return holder.session_generation()
    if op == "issue-exact-run":
        peer = body.get("_peer_uid")
        if not isinstance(peer, int):
            raise HolderRefusal("ipc peer is missing")
        return holder.issue_exact_run(body, peer_uid=peer)
    if op == "authorize-exact-run":
        peer = body.get("_peer_uid")
        if not isinstance(peer, int):
            raise HolderRefusal("ipc peer is missing")
        return holder.authorize_exact_run(body, peer_uid=peer)
    if op == "execute-exact-run":
        signatures = body.get("signatures")
        if not isinstance(signatures, dict):
            raise HolderRefusal("device signature verification failed")
        peer_uid = body.get("_peer_uid")
        peer_gid = body.get("_peer_gid")
        human = holder.exact_run_execute_human(str(body.get("nonce")), signatures)
        result = holder.execute(
            token=str(body.get("nonce")),
            human=human,
            peer_uid=int(peer_uid) if isinstance(peer_uid, int) else None,
            peer_gid=int(peer_gid) if isinstance(peer_gid, int) else None,
        )
        result = dict(result)
        result["run_integration_complete"] = False
        result["e2_closed"] = False
        return result
    if op == "enroll":
        if caller_id != "bootstrap":
            raise HolderRefusal("only the bootstrap caller can enroll")
        human = body.get("human")
        return holder.enroll(
            str(body.get("new_caller_id")),
            human if isinstance(human, dict) else {},
            now=clock,
        )
    if caller_id == "bootstrap":
        raise HolderRefusal("bootstrap caller cannot operate after enroll")
    human = body.get("human")
    human_dict = human if isinstance(human, dict) else {}
    if op == "set-policy":
        return holder.set_policy(human_dict, now=clock)
    if op == "pair":
        return holder.pair_device(str(body.get("device_id")), human_dict, now=clock)
    if op == "replace-key":
        return holder.replace_device_key(str(body.get("device_id")), human_dict, now=clock)
    if op == "rotate":
        return holder.rotate_caller(human_dict, now=clock)
    if op == "revoke":
        return holder.revoke_device(str(body.get("device_id")), human_dict, now=clock)
    if op == "consume":
        files = body.get("files")
        if not isinstance(files, list):
            raise HolderRefusal("consume files are missing")
        pairs = [(str(item[0]), str(item[1])) for item in files if isinstance(item, list) and len(item) == 2]
        if len(pairs) != len(files):
            raise HolderRefusal("consume files are malformed")
        binding = body.get("binding")
        return holder.consume(
            nonce=str(body.get("nonce")),
            policy=str(body.get("policy")),
            human=human_dict,
            workspace=Path(str(body.get("workspace"))),
            files=pairs,
            binding=binding if isinstance(binding, dict) else None,
            now=clock,
        )
    if op == "execute":
        if "interpreter" in body or "interpreter_args" in body:
            raise HolderRefusal("execute refuses caller-supplied interpreter overrides")
        peer_uid = body.get("_peer_uid")
        peer_gid = body.get("_peer_gid")
        if "run_uid" in body or "run_gid" in body:
            raise HolderRefusal("execute refuses caller-supplied payload identity")
        return holder.execute(
            token=str(body.get("token")),
            human=human_dict,
            now=clock,
            peer_uid=int(peer_uid) if isinstance(peer_uid, int) else None,
            peer_gid=int(peer_gid) if isinstance(peer_gid, int) else None,
        )
    if op == "cancel":
        return holder.cancel_uncertain(str(body.get("token")), human_dict, now=clock)
    if op == "note-absent":
        return holder.note_child_absent(str(body.get("token")), human_dict, now=clock)
    raise HolderRefusal("unknown holder operation")


def handle_message(
    holder: ExecutionHolder,
    message: dict[str, Any],
    *,
    bootstrap_secret: str,
    peer_uid: int | None = None,
    peer_gid: int | None = None,
) -> dict[str, Any]:
    caller_id = message.get("caller_id") if isinstance(message, dict) else None
    if not isinstance(caller_id, str):
        raise HolderRefusal("caller id is missing")
    secret = bootstrap_secret if caller_id == "bootstrap" else holder.caller_secret(caller_id)
    body = open_sealed(secret, message)
    if body.get("protocol") not in (None, PROTOCOL):
        raise HolderRefusal("holder protocol downgrade or unknown version")
    # Authenticated peer identity is stamped by the transport, never the client.
    if peer_uid is not None:
        body = dict(body)
        body["_peer_uid"] = int(peer_uid)
        if peer_gid is not None:
            body["_peer_gid"] = int(peer_gid)
    result = dispatch(holder, body, caller_id=caller_id)
    if isinstance(result, dict) and isinstance(body.get("request_id"), str):
        result = dict(result)
        result["request_id"] = body["request_id"]
    return seal(secret, caller_id="holder", body=result)


def unlink_replay_history(root: Path) -> None:
    """Test helper: remove only the replay file from an initialized holder."""
    path = Path(root) / "spent.json"
    os.unlink(path)
