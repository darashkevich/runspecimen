"""Native enrollment bridge.

The isolated double can enroll, pair, and sign when a caller supplies a
verifier pin and the binary's team identifier and designated requirement
match that pin. Installed protection refuses that double. Production does
not invent a team identifier or a designated requirement: ``production_verifier_pin``
stays unset, so a display name that contains "Developer ID" is not trusted.

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


def production_verifier_pin() -> VerifierPin | None:
    """Production team and designated requirement are not chosen in this tree.

    Returning None fails closed. This is not a Developer ID display string.
    """

    return None


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


def require_verifier_identity(pin: VerifierPin | None) -> None:
    """Refuse unless the platform verifier matches the pin and its signature."""

    parsed = read_verifier_identity()
    if pin is None:
        raise VerifierIdentityError("verifier team and designated requirement are not pinned")
    if parsed.get("team_identifier") != pin.team_identifier:
        raise VerifierIdentityError("verifier team identifier does not match the pin")
    if parsed.get("designated_requirement") != pin.designated_requirement:
        raise VerifierIdentityError("verifier designated requirement does not match the pin")
    if not verifier_signature_strict():
        raise VerifierIdentityError("verifier signature did not satisfy codesign --verify --strict")


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
        "native production enrollment is not accepted: verifier team and "
        "designated requirement are not pinned. A display name containing "
        "Developer ID is not a verifier identity. The "
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
        if bridge not in {ISOLATED_DOUBLE, PRODUCTION_BRIDGE}:
            continue
        role = record.get("role")
        if role == "mac":
            local = True
        elif role == "phone":
            companion = True
    return {"local": local, "companion": companion}
