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
import sys
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
    ) -> None:
        if allow_test_double and installed_protection:
            raise ValueError("a software test double cannot claim installed protection")
        self.root = Path(root)
        self.allow_test_double = allow_test_double
        self.installed_protection = bool(installed_protection)
        self.bootstrap_secret = bootstrap_secret
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
        if human.get("method") == "software-test-double":
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
            "attestation_class": "device-ed25519-not-hardware",
        }
        path_map, payload_digest, snapshot_root = self._bind(
            nonce,
            workspace,
            files,
            executable=str(envelope["executable"]),
            argv=[str(item) for item in envelope["argv"]],
        )
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
        spent.append(
            {
                "nonce": nonce,
                "payload_digest": payload_digest,
                "policy": policy,
                "generation": self.generation,
                "holder_id": self.holder_id,
                "key_generation": self.key_generation,
                "binding": envelope,
            }
        )
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
                "attestation_class": "device-ed25519-not-hardware",
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
            try:
                proc, release_payload = self._spawn_dropped(launch, cwd=cwd, uid=run_uid, gid=run_gid)
                watch = self._arm_payload_watch(int(proc.pid))
                if not watch["armed"]:
                    self._signal_matching_identity(int(proc.pid), watch.get("started"), 9)
                    raise HolderRefusal("holder supervision could not be armed")
                release_payload()
            except (OSError, HolderRefusal) as exc:
                self._disable_child_subreaper()
                self._write("lease.json", {"held": False, "token": token, "child": "spawn-failed"})
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
                "attestation_class": "device-ed25519-not-hardware",
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
        )

        signatures = human.get("signatures")
        if not isinstance(signatures, dict) or not signatures:
            raise HolderRefusal("cryptographic device signatures are missing")
        devices = self._devices()
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
        message = digest_challenge(challenge)
        for device_id, signature in signatures.items():
            record = devices.get(device_id)
            if not isinstance(record, dict) or record.get("revoked") is True:
                raise HolderRefusal("a signing device is missing or revoked")
            public_key = record.get("public_key")
            if not isinstance(public_key, str) or not public_key:
                raise HolderRefusal("device public key is missing")
            if not isinstance(signature, str) or not verify_device_signature(
                public_key, signature, message
            ):
                raise HolderRefusal("device signature verification failed")
            role = record.get("role")
            if role in required_roles:
                covered_roles.add(str(role))
        if covered_roles != required_roles:
            raise HolderRefusal("required device signatures are incomplete")
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
        root.mkdir(parents=True, exist_ok=False)
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

    def _spawn_dropped(
        self,
        launch: list[str],
        *,
        cwd: Path,
        uid: int,
        gid: int,
    ) -> tuple[subprocess.Popen, Any]:
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

        def release() -> None:
            try:
                os.write(gate_w, b"\0")
            finally:
                os.close(gate_w)

        return proc, release

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
    return seal(secret, caller_id="holder", body=result)


def unlink_replay_history(root: Path) -> None:
    """Test helper: remove only the replay file from an initialized holder."""
    path = Path(root) / "spent.json"
    os.unlink(path)
