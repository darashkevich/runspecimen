#!/bin/sh
# Human Touch ID checklist for LocalSecureEnclaveEnrollment.
# This script does not enroll, sign, prompt, or revoke. Yahor runs those steps.
set -eu
echo "Touch ID harness: not executed."
echo "Run these yourself against a development build. Do not point them at /Applications/RunSpecimen.app."
echo "1. Enroll a Secure Enclave key and complete the Touch ID prompt."
echo "2. Sign one canonical request with that key and complete Touch ID again."
echo "3. Quit and relaunch, then sign a second request so the key is loaded from the keychain."
echo "4. Start a sign and cancel the prompt. The request must not be stored as approved."
echo "5. Revoke the key. A later sign must fail, and a failed keychain delete must leave the record active."
echo "Unit tests do not call LocalSecureEnclaveEnrollment.enroll or sign."
exit 2
