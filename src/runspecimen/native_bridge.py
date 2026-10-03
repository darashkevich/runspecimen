"""Native enrollment bridge.

The isolated double can enroll, pair, and sign when a caller supplies a
verifier pin and the binary's team identifier and designated requirement
match that pin. Installed protection refuses that double. A caller
``boundary_double`` flag is not a trusted native boundary. Production wire
input, environment, and config cannot select the software double.
``production_verifier_pin`` is the confirmed Developer ID holder identity.
A display name that contains "Developer ID" is not that pin. A pin match
checks verifier code only. It does not authorize a software key. The Store
app does not carry this pin.

This module does not create a Secure Enclave key and it does not prompt.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

PRODUCTION_BRIDGE = "native-production-bridge"
LABELED_TEST_DOUBLE = "labeled-native-bridge-double-not-hardware"
ISOLATED_DOUBLE = "isolated-native-bridge-double-not-hardware"
BOUNDARY_DOUBLE = "production-boundary-double-not-hardware"
VERIFIER_RELATIVE = Path("runspecimen/platform/darwin_arm64/native_p256_verify")
_SIGNED_KINDS = frozenset({"adhoc", "codesign"})


class TrustedNativeBoundary:
    """In-process test double. JSON, environment, and config cannot construct it."""

    def __init__(self) -> None:
        self._issued: dict[str, dict[str, object]] = {}

    def issue(self, *, public_key: str, role: str, policy: str, generation: int) -> None:
        if not isinstance(public_key, str) or not public_key:
            raise ValueError("injected boundary public key is missing")
        self._issued[public_key] = {
            "public_key": public_key,
            "role": role,
            "policy": policy,
            "generation": generation,
            "hardware": False,
            "origin": "injected-trusted-native-boundary",
        }

    def lookup(self, public_key: str) -> dict[str, object] | None:
        found = self._issued.get(public_key)
        if found is None:
            return None
        return dict(found)


class HumanNativeSigner:
    """Software signer. Not the human-operated native adapter.

    Subclasses implement ``public_key`` and ``sign``. ``hardware`` is false
    because this object is a software key. A dict, environment variable, or
    config file cannot become this object. Installed protection refuses it.
    The production unattended call does not construct a Secure Enclave key
    and does not prompt.
    """

    hardware = False

    def public_key(self, role: str) -> str:
        raise NotImplementedError(role)

    def sign(self, role: str, message: bytes) -> str:
        raise NotImplementedError(role)


class HumanOperatedNativeAdapter:
    """Software injection point. An origin string is not production trust.

    This is not ``HumanNativeSigner``. Wire JSON, an environment variable, and
    a config dict cannot construct it. A subclass implements ``public_key``
    and ``sign``. Installed protection refuses this object, including when the
    persisted origin is ``human-operated-native-adapter`` and the verifier pin
    matches. This class does not call ``SecureEnclave.P256.Signing.PrivateKey``
    and does not prompt. Constructing it does not close E2.
    """

    origin = "human-operated-native-adapter"
    bridge = "human-operated-native-adapter"
    biometric_invoked = False
    e2_closed = False

    def public_key(self, role: str) -> str:
        raise NotImplementedError(role)

    def sign(self, role: str, message: bytes) -> str:
        raise NotImplementedError(role)


class UserInvokedSecureEnclaveControl:
    """In-process control a person invokes. A string, bool, or dict is not this object."""

    def __init__(self, action: str) -> None:
        if action not in {"local", "companion", "dual"}:
            raise ValueError("secure enclave control action is not local, companion, or dual")
        self.action = action


# Each live signature requires the current biometric set. Unattended code does
# not evaluate this policy and does not prompt.
BIOMETRIC_ACCESS_POLICY = "biometry-current-set-on-each-signature"


class OsBoundaryKey:
    """OS key handle kept for later signing. Public bytes alone are not this object."""

    def __init__(self, public_key: str, sign, *, access_policy: str = BIOMETRIC_ACCESS_POLICY) -> None:
        if not isinstance(public_key, str) or not public_key:
            raise ValueError("OS boundary public key is missing")
        if not callable(sign):
            raise ValueError("OS boundary sign function is missing")
        if access_policy != BIOMETRIC_ACCESS_POLICY:
            raise ValueError("biometric access policy is not the session policy")
        self.public_key = public_key
        self._sign = sign
        self.access_policy = access_policy

    def sign(self, message: bytes) -> str:
        signed = self._sign(message)
        if not isinstance(signed, str) or not signed:
            raise ValueError("OS boundary signature is missing")
        return signed


class UserSessionKeyCustody:
    """User-session custody. The private signing capability stays on the handle."""

    def __init__(self) -> None:
        self._keys: dict[str, OsBoundaryKey] = {}

    def keep(self, role: str, key: OsBoundaryKey) -> None:
        if not isinstance(key, OsBoundaryKey):
            raise TypeError("session custody keeps an OS key handle, not public bytes")
        if role not in {"mac", "phone"}:
            raise ValueError("session custody role is not mac or phone")
        self._keys[role] = key

    def key(self, role: str) -> OsBoundaryKey | None:
        return self._keys.get(role)

    def public_key(self, role: str) -> str | None:
        held = self._keys.get(role)
        return None if held is None else held.public_key

    def sign(self, role: str, message: bytes) -> str:
        held = self._keys.get(role)
        if held is None:
            raise KeyError(role)
        return held.sign(message)

    def drop(self, role: str) -> None:
        self._keys.pop(role, None)


class PhonePeer:
    """A paired phone key. A local Mac key with a phone label is not this object."""

    def __init__(self, public_key: str, sign) -> None:
        if not isinstance(public_key, str) or not public_key:
            raise ValueError("phone peer public key is missing")
        if not callable(sign):
            raise ValueError("phone peer sign function is missing")
        self.public_key = public_key
        self._sign = sign

    def sign(self, message: bytes) -> str:
        signed = self._sign(message)
        if not isinstance(signed, str) or not signed:
            raise ValueError("phone peer signature is missing")
        return signed

    def as_os_key(self) -> OsBoundaryKey:
        return OsBoundaryKey(self.public_key, self._sign)


class OsBoundaryNotInvoked(RuntimeError):
    """The unpatched OS boundary was called. No biometric prompt was raised."""


def os_secure_enclave_create_key(role: str) -> OsBoundaryKey:
    """Secure Enclave / CryptoKit / XPC boundary.

    The holder calls this only from ``enroll_user_invoked_secure_enclave``
    after a ``UserInvokedSecureEnclaveControl``. The live
    ``SecureEnclave.P256.Signing.PrivateKey`` call sits in the holder app
    button action. This function does not call that API and does not prompt.
    Tests replace this function. The unpatched function fails closed.
    """

    del role
    raise OsBoundaryNotInvoked(
        "Secure Enclave enrollment is the human step and was not invoked"
    )


class VerifierPin:
    """Exact team identifier and designated requirement. Not a display name."""

    def __init__(self, team_identifier: str, designated_requirement: str) -> None:
        if not isinstance(team_identifier, str) or not team_identifier.strip():
            raise ValueError("verifier pin team identifier is missing")
        if not isinstance(designated_requirement, str) or not designated_requirement.strip():
            raise ValueError("verifier pin designated requirement is missing")
        self.team_identifier = team_identifier
        self.designated_requirement = designated_requirement


class VerifierIdentityError(Exception):
    """The verifier binary did not match the pinned team and requirement."""


# Yahor confirmed this pair for the Developer ID holder. Do not weaken it.
# A match authenticates verifier code. It is not biometric origin and not
# the Store app's guarantee.
_CONFIRMED_TEAM_ID = "UN6KF8636A"
_CONFIRMED_DESIGNATED_REQUIREMENT = (
    'identifier "com.darashkevich.runspecimen.native-p256-verify" '
    "and anchor apple generic "
    "and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ "
    "and certificate leaf[field.1.2.840.113635.100.6.1.13] /* exists */ "
    "and certificate leaf[subject.OU] = UN6KF8636A"
)


def production_verifier_pin() -> VerifierPin | None:
    """Confirmed Developer ID holder pin. Not a Store-app claim.

    The designated requirement is the exact confirmed string. Display text,
    Apple Development, and a wildcard identifier are not this pin.
    """

    return VerifierPin(_CONFIRMED_TEAM_ID, _CONFIRMED_DESIGNATED_REQUIREMENT)


def effective_verifier_pin(injected: VerifierPin | None) -> VerifierPin | None:
    """An injected test pin wins. Otherwise the confirmed holder pin is used."""

    if injected is not None:
        return injected
    return production_verifier_pin()


def supported_verifier_architecture(binary: Path | None = None) -> str:
    """The packaged verifier is arm64. Other slices are unsupported.

    This does not invent a publisher. A missing binary is ``absent``.
    """

    path = binary if binary is not None else platform_verifier_binary()
    if path is None or not path.is_file():
        return "absent"
    if sys.platform != "darwin":
        return "unverified"
    try:
        described = subprocess.run(
            ["/usr/bin/file", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unverified"
    text = described.stdout
    if "arm64" in text and "x86_64" not in text:
        return "arm64"
    return "unsupported"


def platform_verifier_binary() -> Path | None:
    """Path the holder execs. The pure py3-none-any wheel does not carry it."""

    binary = Path(__file__).resolve().parent / "platform" / "darwin_arm64" / "native_p256_verify"
    if binary.is_file():
        return binary
    return None


def platform_verifier_provenance() -> Path | None:
    path = (
        Path(__file__).resolve().parent
        / "platform"
        / "darwin_arm64"
        / "native_p256_verify.provenance.json"
    )
    if path.is_file():
        return path
    return None


def parse_codesign_identity(details: str, requirement_text: str) -> dict[str, str]:
    """Read TeamIdentifier and the designated requirement. Ignore display text."""

    team = ""
    for line in details.splitlines():
        if line.startswith("TeamIdentifier="):
            value = line.split("=", 1)[1].strip()
            team = "" if value in {"", "not set"} else value
            break
    requirement = ""
    marker = "designated =>"
    for line in requirement_text.splitlines():
        if marker in line:
            requirement = line.split(marker, 1)[1].strip()
    return {"team_identifier": team, "designated_requirement": requirement}


def identity_matches(parsed: Mapping[str, str], pin: VerifierPin | None) -> bool:
    """True only when team and designated requirement both match the pin."""

    if pin is None:
        return False
    return (
        parsed.get("team_identifier") == pin.team_identifier
        and parsed.get("designated_requirement") == pin.designated_requirement
    )


def read_verifier_identity(binary: Path | None = None) -> dict[str, str]:
    """Codesign facts for the platform verifier. Display lines are not returned."""

    path = binary if binary is not None else platform_verifier_binary()
    empty = {"team_identifier": "", "designated_requirement": ""}
    if path is None or sys.platform != "darwin" or not path.is_file():
        return empty
    try:
        details = subprocess.run(
            ["/usr/bin/codesign", "-dvvv", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        requirement = subprocess.run(
            ["/usr/bin/codesign", "-d", "-r-", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return empty
    return parse_codesign_identity(
        f"{details.stdout}\n{details.stderr}",
        f"{requirement.stdout}\n{requirement.stderr}",
    )


def verifier_signature_strict(binary: Path | None = None) -> bool:
    path = binary if binary is not None else platform_verifier_binary()
    if path is None or sys.platform != "darwin" or not path.is_file():
        return False
    try:
        checked = subprocess.run(
            ["/usr/bin/codesign", "--verify", "--strict", str(path)],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return checked.returncode == 0


def require_verifier_identity(pin: VerifierPin | None, binary: Path | None = None) -> None:
    """Refuse unless the verifier matches the pin and its signature."""

    parsed = read_verifier_identity(binary)
    if pin is None:
        raise VerifierIdentityError("verifier team and designated requirement are not pinned")
    if parsed.get("team_identifier") != pin.team_identifier:
        raise VerifierIdentityError("verifier team identifier does not match the pin")
    if parsed.get("designated_requirement") != pin.designated_requirement:
        raise VerifierIdentityError("verifier designated requirement does not match the pin")
    target = binary if binary is not None else platform_verifier_binary()
    if not verifier_signature_strict(target):
        raise VerifierIdentityError("verifier signature did not satisfy codesign --verify --strict")


def resolve_verifier(root: Path) -> Path | None:
    """Holder load path inside a Developer ID artifact. Absent is None."""

    candidate = Path(root) / VERIFIER_RELATIVE
    if candidate.is_file():
        return candidate
    return None


def _signature_kind(binary: Path) -> str:
    """``adhoc`` or ``codesign``. Display text is not a signature kind."""

    if not binary.is_file():
        return "unpinned"
    if sys.platform != "darwin":
        return "adhoc"
    try:
        details = subprocess.run(
            ["/usr/bin/codesign", "-dvvv", str(binary)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unpinned"
    text = f"{details.stdout}\n{details.stderr}"
    if "Signature=adhoc" in text:
        return "adhoc"
    for line in text.splitlines():
        if line.startswith("TeamIdentifier="):
            value = line.split("=", 1)[1].strip()
            if value and value != "not set":
                return "codesign"
    return "unpinned"


def refresh_verifier_provenance(binary: Path) -> Path:
    """Rewrite provenance beside this binary. Does not set the production pin.

    The recorded ``signed`` value is ``adhoc`` or ``codesign``. A display name
    that contains "Developer ID" is not stored.
    """

    import hashlib
    import json

    binary = Path(binary)
    if not binary.is_file():
        raise FileNotFoundError("platform verifier is absent")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    signed = _signature_kind(binary)
    if signed not in _SIGNED_KINDS:
        raise VerifierIdentityError("verifier signature kind is not adhoc or codesign")
    body = {
        "algorithm": "p256-cryptokit",
        "identifier": "com.darashkevich.runspecimen.native-p256-verify",
        "not_secure_enclave": True,
        "platform": "darwin-arm64",
        "sha256": digest,
        "signed": signed,
    }
    path = binary.parent / "native_p256_verify.provenance.json"
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def assemble_developer_id_artifact(destination: Path, source: Path | None = None) -> Path:
    """Place the verifier where the holder resolves it. Does not set the pin."""

    import shutil

    binary = source if source is not None else platform_verifier_binary()
    if binary is None or not binary.is_file():
        raise FileNotFoundError("platform verifier is absent")
    dest = Path(destination) / VERIFIER_RELATIVE
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, dest)
    refresh_verifier_provenance(dest)
    return dest


def platform_verifier_report(root: Path | None = None) -> dict[str, object]:
    """What the CLI and plugin do when the Mach-O is not in the pure package."""

    if root is None:
        present = platform_verifier_binary() is not None
    else:
        present = resolve_verifier(root) is not None
    return {
        "present": present,
        "pure_wheel_includes_verifier": False,
        "production_pin": "confirmed-developer-id-holder",
        "enrollment": "fail-closed",
        "cli_when_absent": (
            "doctor, validate, and status do not enroll a device. "
            "They keep working and report the platform verifier as absent. "
            "Production enrollment fails closed."
        ),
        "plugin_when_absent": (
            "The plugin does not ship native_p256_verify, does not pass a holder, "
            "and cannot enroll. It only calls the CLI."
        ),
    }


def packaged_verifier_publisher() -> dict[str, object]:
    """Identity of the platform verifier. A Developer ID display name is not enough."""

    binary = platform_verifier_binary()
    if binary is None:
        return {"present": False, "signed": "absent", "publisher_trusted": False}
    parsed = read_verifier_identity(binary)
    trusted = identity_matches(parsed, production_verifier_pin()) and verifier_signature_strict(binary)
    return {
        "present": True,
        "signed": "pinned" if trusted else "unpinned",
        "publisher_trusted": trusted,
        "team_identifier": parsed.get("team_identifier", ""),
    }


def production_enrollment_refusal() -> str:
    """Why installed protection will not store a software or isolated key."""

    return (
        "native production enrollment is not accepted. A display name containing "
        "Developer ID is not a verifier identity. A verifier pin does not "
        "authorize a software key. A caller boundary_double flag is refused "
        "when installed protection is on. The "
        f"{LABELED_TEST_DOUBLE} path and the {ISOLATED_DOUBLE} path are "
        "refused when installed protection is on. software P-256 is not a "
        "Secure Enclave. Secure Enclave key creation was not called."
    )


def native_signers_connected(devices: Mapping[str, Any] | None = None) -> dict[str, bool]:
    """Roles that completed the isolated or production bridge. Empty means neither."""

    local = False
    companion = False
    for record in (devices or {}).values():
        if not isinstance(record, dict) or record.get("revoked") is True:
            continue
        if record.get("hardware") is True:
            continue
        provenance = record.get("provenance")
        if not isinstance(provenance, dict) or provenance.get("not_hardware") is not True:
            continue
        bridge = provenance.get("bridge")
        if bridge == ISOLATED_DOUBLE:
            pass
        elif bridge == PRODUCTION_BRIDGE and provenance.get("boundary_double") is True:
            pass
        else:
            continue
        role = record.get("role")
        if role == "mac":
            local = True
        elif role == "phone":
            companion = True
    return {"local": local, "companion": companion}
