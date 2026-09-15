#!/usr/bin/env bash
# Report whether a Developer ID Application identity is available for notarization.
# Exits 0 when ready; non-zero with setup instructions otherwise.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/Config/signing.env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
fi

echo "=== RunSpecimen macOS signing readiness ==="
echo "Host: $(scutil --get ComputerName 2>/dev/null || hostname)"
echo "macOS: $(sw_vers -productVersion)"
echo

IDENTITIES="$(security find-identity -v -p codesigning 2>/dev/null || true)"
echo "Codesigning identities:"
if [[ -z "$(echo "$IDENTITIES" | grep -v '0 valid identities found' | grep 'valid identities found' || true)" ]] \
  && echo "$IDENTITIES" | grep -q '0 valid identities found'; then
  echo "  (none)"
else
  echo "$IDENTITIES" | sed 's/^/  /'
fi
echo

DEV_ID="$(echo "$IDENTITIES" | grep 'Developer ID Application' | head -1 || true)"
if [[ -n "${RS_SIGN_IDENTITY:-}" ]]; then
  echo "RS_SIGN_IDENTITY is set: $RS_SIGN_IDENTITY"
  if echo "$IDENTITIES" | grep -F "$RS_SIGN_IDENTITY" >/dev/null 2>&1; then
    echo "OK: configured identity is present in the keychain."
    exit 0
  fi
  echo "ERROR: RS_SIGN_IDENTITY is not among keychain identities."
  exit 2
fi

if [[ -n "$DEV_ID" ]]; then
  echo "OK: Developer ID Application identity found:"
  echo "  $DEV_ID"
  echo
  echo "Next: ./Scripts/sign_and_notarize.sh all"
  echo "Docs: apps/macos/NOTARIZATION.md"
  exit 0
fi

cat <<'EOF'
NOT READY: no Developer ID Application certificate on this Mac.

Setup:
  1. Join the Apple Developer Program (if needed).
  2. In Xcode → Settings → Accounts → Manage Certificates…
     create "Developer ID Application", OR download it from
     Certificates, Identifiers & Profiles and install in login keychain.
  3. For notarization, create an App Store Connect API key (.p8) or an
     app-specific password; copy Config/signing.env.example → Config/signing.env
     and fill values (never commit signing.env).
  4. Re-run: ./Scripts/check_signing_identity.sh
  5. Ship: ./Scripts/sign_and_notarize.sh all

Local smoke without notarization still works:
  ./Scripts/build_app.sh && open build/RunSpecimen.app

Full steps: apps/macos/NOTARIZATION.md
EOF
exit 1
