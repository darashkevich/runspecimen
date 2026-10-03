#!/bin/sh
# Points at the development Touch ID diagnostic. This script does not call it
# with --human-invoked, so it does not enroll, sign, or prompt.
set -eu
echo "Touch ID diagnostic is apps/macos/Sources/RunSpecimenTouchIDDiagnostic."
echo "It calls LocalSecureEnclaveEnrollment only after --human-invoked."
echo "Example, which you must run yourself:"
echo "  swift run --package-path apps/macos RunSpecimenTouchIDDiagnostic --human-invoked --directory /private/tmp/rs-touchid-diag --key-id diag-yours enroll"
echo "The directory must be /private/tmp/rs-touchid-diag or a directory inside it. /tmp and /private/tmp alone are refused, and a .. path is refused."
echo "Commands: preview, enroll, sign, reload, cancel, revoke."
echo "preview prints a sample request and does not call Secure Enclave. sign, reload, and cancel print the exact request before any Secure Enclave call:"
echo "  swift run --package-path apps/macos RunSpecimenTouchIDDiagnostic preview"
echo "cancel asks you to dismiss the prompt. This script does not type APPROVE and does not start that command."
exit 2
