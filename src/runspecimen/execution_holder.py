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

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path
from typing import Any

from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.hashutil import canonical_json_bytes
from runspecimen.holder_protocol import LaunchRequest, ProtocolError, bind_execution
from runspecimen.paths import ensure_within

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
    authorization. It does not accept a phrase, and it does not claim a
    Secure Enclave or a paired phone. With the flag off, every human method
    fails closed because no hardware verifier is connected.
    """

    def __init__(
        self,
        root: Path,
        *,
        allow_test_double: bool = False,
        installed_protection: bool = False,
    ) -> None:
        if allow_test_double and installed_protection:
            raise ValueError("a software test double cannot claim installed protection")
        self.root = Path(root)
        self.allow_test_double = allow_test_double
        self.installed_protection = bool(installed_protection)
        self.root.mkdir(parents=True, exist_ok=True)
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
        devices[device_id] = {
            "role": role,
            "fingerprint": fingerprint,
            "revoked": False,
            "attestation": "unverified" if human.get("attestation") else "software-test-double",
            "generation": self.generation,
        }
        self._write("devices.json", devices)
        return {
            "ok": True,
            "device_id": device_id,
            "role": role,
            "attestation": devices[device_id]["attestation"],
            "installed_protection": self.installed_protection,
            "hardware": False,
        }

    def replace_device_key(
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
        self._load()
        self._refuse_lost_history()
        if self._lease_held():
            raise HolderRefusal("a descendant or uncertain child still holds the lease")
        self._human(human, purpose="consume", policy=policy, subject=nonce, now=now)
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
        path_map, payload_digest, snapshot_root = self._bind(
            nonce,
            workspace,
            files,
            executable=str(envelope["executable"]),
            argv=[str(item) for item in envelope["argv"]],
        )
        if payload_digest == self.holder_id:
            raise HolderRefusal("payload digest is not a distinct identity from the holder")
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
        """Human-authorized cancel of an uncertain child before a pid is known."""
        self._load()
        self._human(human, purpose="cancel", policy=human.get("policy"), subject=token, now=now)
        lease = self._read("lease.json") if (self.root / "lease.json").exists() else None
        if not isinstance(lease, dict) or lease.get("token") != token:
            raise HolderRefusal("cancel does not match the recorded child")
        if lease.get("child") != "uncertain":
            raise HolderRefusal("only an uncertain child can be cancelled this way")
        self._write("lease.json", {"held": False, "token": token, "child": "cancelled"})
        return {"ok": True, "cancelled": True, "installed_protection": self.installed_protection}

    def note_child_absent(self, token: str, human: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        """Drop the lease only for the recorded token. This does not signal a pid."""
        self._load()
        self._human(human, purpose="note-absent", policy=human.get("policy"), subject=token, now=now)
        lease = self._read("lease.json") if (self.root / "lease.json").exists() else None
        if not isinstance(lease, dict) or lease.get("token") != token:
            raise HolderRefusal("absent observation does not match the recorded child")
        self._write("lease.json", {"held": False, "token": token, "child": "absent"})
        return {"ok": True, "installed_protection": self.installed_protection}

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
        )
        for key in required:
            if key not in binding:
                raise HolderRefusal(f"consume binding is missing {key}")
        if binding.get("key_generation") != self.key_generation:
            raise HolderRefusal("consume key generation does not match the holder")
        return {
            "contract_hash": binding["contract_hash"],
            "workspace": binding["workspace"],
            "argv": list(binding["argv"]),
            "executable": binding["executable"],
            "policy": binding["policy"],
            "bounds": binding["bounds"],
            "key_generation": binding["key_generation"],
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
        snapshot_root = self.root / "snapshots" / nonce
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
        return path_map, payload_digest, str(snapshot_root)

    def _human(
        self,
        human: dict[str, Any],
        *,
        purpose: str,
        policy: object,
        subject: object,
        now: float | None = None,
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
        # Expiry uses only the holder process clock. A client `now` or other
        # message timestamp must not resurrect an expired authorization.
        if expires <= time.time():
            raise HolderRefusal("human authorization has expired")
        if method == "software-test-double":
            if not self.allow_test_double or human.get("hardware") is not False:
                raise HolderRefusal("software test double is not a human authorization")
            return
        if method in {"local", "companion", "dual"}:
            raise HolderRefusal("human verifier is not connected")
        raise HolderRefusal("human authorization method is not accepted")

    def _read(self, name: str) -> dict[str, Any]:
        value = read_json(self.root / name)
        if not isinstance(value, dict):
            raise HolderRefusal(f"{name} is not a holder record")
        return value

    def _write(self, name: str, value: dict[str, Any]) -> None:
        atomic_write_json(self.root / name, value)


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
) -> dict[str, Any]:
    caller_id = message.get("caller_id") if isinstance(message, dict) else None
    if not isinstance(caller_id, str):
        raise HolderRefusal("caller id is missing")
    secret = bootstrap_secret if caller_id == "bootstrap" else holder.caller_secret(caller_id)
    body = open_sealed(secret, message)
    if body.get("protocol") not in (None, PROTOCOL):
        raise HolderRefusal("holder protocol downgrade or unknown version")
    result = dispatch(holder, body, caller_id=caller_id)
    return seal(secret, caller_id="holder", body=result)


def unlink_replay_history(root: Path) -> None:
    """Test helper: remove only the replay file from an initialized holder."""
    path = Path(root) / "spent.json"
    os.unlink(path)
