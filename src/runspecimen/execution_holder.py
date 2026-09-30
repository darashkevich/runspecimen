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
    ) -> None:
        if allow_test_double and installed_protection:
            raise ValueError("a software test double cannot claim installed protection")
        self.root = Path(root)
        self.allow_test_double = allow_test_double
        self.installed_protection = bool(installed_protection)
        self.bootstrap_secret = bootstrap_secret
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
        # Device HMAC secret is returned once. An imported secure-enclave label is
        # still not attestation of hardware enrollment on this host.
        device_secret = secrets.token_hex(32)
        attestation = "unverified"
        if human.get("method") == "software-test-double":
            attestation = "software-test-double"
        elif human.get("attestation"):
            attestation = "unverified"
        else:
            attestation = "device-hmac"
        devices[device_id] = {
            "role": role,
            "fingerprint": fingerprint,
            "revoked": False,
            "attestation": attestation,
            "device_secret": device_secret,
            "generation": self.generation,
        }
        self._write("devices.json", devices)
        return {
            "ok": True,
            "device_id": device_id,
            "role": role,
            "attestation": attestation,
            "device_secret": device_secret,
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
        """Cancel only before the holder has spawned. Authorization alone is not enough once a pid is recorded."""
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
        atomic_write_json(snapshot_root / "path_map.json", path_map)
        return path_map, payload_digest, str(snapshot_root)

    def execute(
        self,
        *,
        token: str,
        human: dict[str, Any],
        interpreter: str | None = None,
        interpreter_args: list[str] | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Spawn and supervise the consumed snapshot. Lease clears only after wait."""
        self._load()
        self._human(human, purpose="execute", policy=human.get("policy"), subject=token, now=now)
        lease_path = self.root / "lease.json"
        if not lease_path.exists():
            raise HolderRefusal("execute has no lease")
        lease = self._read("lease.json")
        if lease.get("token") != token or lease.get("held") is not True:
            raise HolderRefusal("execute does not match the held lease")
        if lease.get("child") != "uncertain":
            raise HolderRefusal("execute requires an uncertain lease before spawn")
        spent = self._spent()
        record = next((item for item in spent if item.get("nonce") == token), None)
        if not isinstance(record, dict):
            raise HolderRefusal("execute nonce is not in replay history")
        binding = record.get("binding")
        if not isinstance(binding, dict):
            raise HolderRefusal("execute binding is missing")
        bounds = binding.get("bounds")
        if not isinstance(bounds, dict):
            raise HolderRefusal("execute bounds are missing")
        try:
            wall = float(bounds["wall_timeout_sec"])
            out_max = int(bounds["stdout_max_bytes"])
            err_max = int(bounds["stderr_max_bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HolderRefusal("execute bounds are malformed") from exc
        snapshot_root = self.root / "snapshots" / token
        if not snapshot_root.is_dir():
            raise HolderRefusal("execute snapshot root is missing")
        workspace = Path(str(binding["workspace"]))
        executable = str(binding["executable"])
        argv = [str(item) for item in binding["argv"]]
        path_map: dict[str, str] = {}
        for original in snapshot_root.rglob("*"):
            if not original.is_file():
                continue
            # Snapshots store under digest-named paths; rebuild map from spent files via binding reads
        # Prefer path_map reconstructed from snapshot directory index written at consume.
        index_path = snapshot_root / "path_map.json"
        if index_path.is_file():
            loaded = read_json(index_path)
            if not isinstance(loaded, dict):
                raise HolderRefusal("snapshot path map is malformed")
            path_map = {str(k): str(v) for k, v in loaded.items()}
        else:
            raise HolderRefusal("snapshot path map is missing")
        from runspecimen.holder_adapter import rewrite_launch_from_snapshots

        if interpreter:
            launch = [interpreter, *(interpreter_args or []), executable, *argv[1:]]
        else:
            launch = [executable, *argv[1:]]
        launch = rewrite_launch_from_snapshots(
            launch,
            path_map=path_map,
            workspace=workspace,
            live_executable=executable,
        )
        cwd = Path(str(binding.get("cwd") or workspace))
        if not cwd.is_dir():
            raise HolderRefusal("execute cwd is missing")
        # Refuse launching a live workspace file that should have been snapshotted.
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
        self._write(
            "lease.json",
            {"held": True, "token": token, "child": "running", "pid": None},
        )
        try:
            proc = subprocess.Popen(  # noqa: S603
                launch,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                shell=False,
                start_new_session=True,
            )
        except OSError as exc:
            self._write("lease.json", {"held": False, "token": token, "child": "spawn-failed"})
            raise HolderRefusal(f"holder spawn failed: {exc}") from exc
        self._write(
            "lease.json",
            {"held": True, "token": token, "child": "running", "pid": int(proc.pid)},
        )
        stdout = bytearray()
        stderr = bytearray()
        stdout_trunc = False
        stderr_trunc = False
        deadline = time.monotonic() + max(0.1, wall)
        timed_out = False
        assert proc.stdout is not None and proc.stderr is not None
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                ready, _, _ = select.select([proc.stdout, proc.stderr], [], [], min(0.1, remaining))
                for stream in ready:
                    chunk = stream.read(65536)
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
                    # Drain remaining bounded bytes after exit.
                    for stream, bucket, limit, flag_name in (
                        (proc.stdout, stdout, out_max, "stdout"),
                        (proc.stderr, stderr, err_max, "stderr"),
                    ):
                        while True:
                            chunk = stream.read(65536)
                            if not chunk:
                                break
                            if len(bucket) < limit:
                                take = chunk[: limit - len(bucket)]
                                bucket.extend(take)
                                if len(take) < len(chunk):
                                    if flag_name == "stdout":
                                        stdout_trunc = True
                                    else:
                                        stderr_trunc = True
                            else:
                                if flag_name == "stdout":
                                    stdout_trunc = True
                                else:
                                    stderr_trunc = True
                    break
            if timed_out:
                try:
                    os.killpg(proc.pid, 15)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, 9)
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=2)
            else:
                proc.wait(timeout=2)
        finally:
            try:
                proc.stdout.close()
            except OSError:
                pass
            try:
                proc.stderr.close()
            except OSError:
                pass
        # Verified termination only: wait returned.
        exit_code = proc.returncode
        if exit_code is None:
            raise HolderRefusal("holder execute did not observe process termination")
        self._write(
            "lease.json",
            {
                "held": False,
                "token": token,
                "child": "timeout" if timed_out else "exited",
                "pid": int(proc.pid),
                "exit_code": int(exit_code),
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
            "supervisor": "holder",
        }

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
        if method == "bootstrap":
            # Authenticated bootstrap is distinct from human authorization.
            if not isinstance(self.bootstrap_secret, str) or len(self.bootstrap_secret) < 32:
                raise HolderRefusal("bootstrap verifier is not configured")
            proof = human.get("bootstrap_mac")
            challenge = {
                "purpose": purpose,
                "subject": subject,
                "policy": policy,
                "devices": list(devices),
                "expires_at": expires,
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
            self._verify_device_signatures(human, purpose=purpose, policy=str(policy), subject=subject)
            return
        raise HolderRefusal("human authorization method is not accepted")

    def _verify_device_signatures(
        self,
        human: dict[str, Any],
        *,
        purpose: str,
        policy: str,
        subject: object,
    ) -> None:
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
        }
        for device_id, signature in signatures.items():
            record = devices.get(device_id)
            if not isinstance(record, dict) or record.get("revoked") is True:
                raise HolderRefusal("a signing device is missing or revoked")
            secret = record.get("device_secret")
            if not isinstance(secret, str):
                raise HolderRefusal("device signing material is missing")
            if not isinstance(signature, str) or not hmac.compare_digest(
                signature, message_mac(secret, challenge)
            ):
                raise HolderRefusal("device signature verification failed")
            role = record.get("role")
            if role in required_roles:
                covered_roles.add(str(role))
        if covered_roles != required_roles:
            raise HolderRefusal("required device signatures are incomplete")
        if human.get("hardware") is True:
            # Transport signatures are not a biometric attestation claim.
            raise HolderRefusal("device HMAC signatures are not hardware attestation")

    def _read(self, name: str) -> dict[str, Any]:
        value = read_json(self.root / name)
        if not isinstance(value, dict):
            raise HolderRefusal(f"{name} is not a holder record")
        self._validate_record_schema(name, value)
        return value

    def _write(self, name: str, value: dict[str, Any]) -> None:
        self._validate_record_schema(name, value)
        lock_path = self.root / ".holder.op.lock"
        lock_path.touch(exist_ok=True)
        fd = os.open(str(lock_path), os.O_RDWR)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            atomic_write_json(self.root / name, value)
        finally:
            if fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            os.close(fd)

    def _validate_record_schema(self, name: str, value: dict[str, Any]) -> None:
        allowed = {
            "meta.json": {"protocol", "generation", "holder_id", "installed_protection", "key_generation"},
            "enrollment.json": {"caller_id", "policy", "method", "hardware", "generation", "key_generation"},
            "policy.json": {"name", "generation", "method", "hardware", "devices"},
            "lease.json": {"held", "token", "child", "pid", "exit_code"},
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
        interpreter = body.get("interpreter")
        interpreter_args = body.get("interpreter_args")
        return holder.execute(
            token=str(body.get("token")),
            human=human_dict,
            interpreter=str(interpreter) if isinstance(interpreter, str) else None,
            interpreter_args=[str(x) for x in interpreter_args] if isinstance(interpreter_args, list) else None,
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
