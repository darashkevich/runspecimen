"""Production native enrollment bridge.

This is not the labeled test double. It does not create a Secure Enclave key
and it does not prompt for Touch ID, Face ID, or a password. An ad-hoc
CryptoKit binary plus a hash file is not a Developer ID publisher.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PRODUCTION_BRIDGE = "native-production-bridge"
LABELED_TEST_DOUBLE = "labeled-native-bridge-double-not-hardware"


def packaged_verifier_publisher() -> dict[str, object]:
    """Read the packaged binary's codesign identity. Does not sign anything."""
    binary = Path(__file__).resolve().parent / "native_p256_verify"
    if sys.platform != "darwin" or not binary.is_file():
        return {"present": False, "signed": "absent", "publisher_trusted": False}
    try:
        checked = subprocess.run(
            ["/usr/bin/codesign", "-dvvv", str(binary)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"present": True, "signed": "unreadable", "publisher_trusted": False}
    text = f"{checked.stdout}\n{checked.stderr}"
    adhoc = "Signature=adhoc" in text
    developer_id = "Developer ID Application:" in text and not adhoc
    if adhoc:
        signed = "ad-hoc"
    elif developer_id:
        signed = "developer-id"
    else:
        signed = "untrusted"
    return {"present": True, "signed": signed, "publisher_trusted": developer_id}


def production_enrollment_refusal() -> str:
    """Why production enrollment cannot store a key. No biometric call."""
    identity = packaged_verifier_publisher()
    signed = identity.get("signed", "absent")
    return (
        "native production bridge refuses enrollment: verifier signature is "
        f"{signed}, not Developer ID. A hash pin beside an ad-hoc binary is not "
        "a trusted publisher. The labeled-native-bridge-double-not-hardware path "
        "is a separate test double and is not this bridge. software P-256 is not "
        "a Secure Enclave. Secure Enclave key creation was not called. "
        "Native local and companion signers are not connected."
    )


def native_signers_connected() -> dict[str, bool]:
    """Production local and companion signers. Both stay disconnected here."""
    return {"local": False, "companion": False}
