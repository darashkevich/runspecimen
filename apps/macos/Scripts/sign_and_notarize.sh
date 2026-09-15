#!/usr/bin/env bash
# Sign (Developer ID + Hardened Runtime), notarize, staple, and/or package.
# Fails clearly when certificates or notary credentials are missing.
#
# Usage:
#   ./Scripts/sign_and_notarize.sh check|sign|notarize|staple|package|all
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
APP="${RS_APP_PATH:-$BUILD/RunSpecimen.app}"
ENTITLEMENTS="$ROOT/Entitlements/RunSpecimen.developer-id.entitlements"
ENV_FILE="$ROOT/Config/signing.env"
ZIP="$BUILD/RunSpecimen-macos.zip"
CMD="${1:-all}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
fi

die() {
  echo "ERROR: $*" >&2
  exit 1
}

need_app() {
  [[ -d "$APP" ]] || die "App not found at $APP — run ./Scripts/build_app.sh first."
}

resolve_identity() {
  if [[ -n "${RS_SIGN_IDENTITY:-}" ]]; then
    echo "$RS_SIGN_IDENTITY"
    return
  fi
  local line
  line="$(security find-identity -v -p codesigning 2>/dev/null | grep 'Developer ID Application' | head -1 || true)"
  if [[ -z "$line" ]]; then
    echo ""
    return
  fi
  # Extract quoted identity name.
  echo "$line" | sed -n 's/.*"\(.*\)".*/\1/p'
}

cmd_check() {
  exec "$ROOT/Scripts/check_signing_identity.sh"
}

cmd_sign() {
  need_app
  local identity
  identity="$(resolve_identity)"
  if [[ -z "$identity" ]]; then
    "$ROOT/Scripts/check_signing_identity.sh" || true
    die "Cannot sign: no Developer ID Application identity. See apps/macos/NOTARIZATION.md"
  fi

  echo "Signing with: $identity"
  echo "Entitlements: $ENTITLEMENTS"
  echo "Hardened Runtime: --options runtime"

  xattr -cr "$APP" 2>/dev/null || true
  codesign --force --deep --options runtime --timestamp \
    --entitlements "$ENTITLEMENTS" \
    --sign "$identity" \
    "$APP"

  codesign --verify --deep --strict --verbose=2 "$APP"
  echo
  codesign -dv --verbose=2 "$APP" 2>&1 | grep -E 'Authority|Flags|TeamIdentifier|Runtime|Identifier' || true
  echo "Signed OK: $APP"
}

cmd_notarize() {
  need_app
  local submit_zip="$BUILD/RunSpecimen-notarize-submit.zip"
  rm -f "$submit_zip"
  ditto -c -k --keepParent "$APP" "$submit_zip"

  if [[ -n "${RS_NOTARY_KEY:-}" && -n "${RS_NOTARY_KEY_ID:-}" && -n "${RS_NOTARY_ISSUER:-}" ]]; then
    [[ -f "$RS_NOTARY_KEY" ]] || die "RS_NOTARY_KEY file not found: $RS_NOTARY_KEY"
    echo "Submitting to notarytool (API key)…"
    xcrun notarytool submit "$submit_zip" \
      --key "$RS_NOTARY_KEY" \
      --key-id "$RS_NOTARY_KEY_ID" \
      --issuer "$RS_NOTARY_ISSUER" \
      --wait
  elif [[ -n "${RS_NOTARY_APPLE_ID:-}" && -n "${RS_NOTARY_PASSWORD:-}" && -n "${RS_NOTARY_TEAM_ID:-}" ]]; then
    echo "Submitting to notarytool (Apple ID)…"
    xcrun notarytool submit "$submit_zip" \
      --apple-id "$RS_NOTARY_APPLE_ID" \
      --password "$RS_NOTARY_PASSWORD" \
      --team-id "$RS_NOTARY_TEAM_ID" \
      --wait
  else
    cat <<'EOF' >&2
ERROR: Notary credentials not configured.

Set either:
  RS_NOTARY_KEY + RS_NOTARY_KEY_ID + RS_NOTARY_ISSUER
or:
  RS_NOTARY_APPLE_ID + RS_NOTARY_PASSWORD + RS_NOTARY_TEAM_ID

Copy Config/signing.env.example → Config/signing.env (gitignored) and fill values.
See apps/macos/NOTARIZATION.md
EOF
    exit 1
  fi
  rm -f "$submit_zip"
  echo "Notarization accepted."
}

cmd_staple() {
  need_app
  xcrun stapler staple "$APP"
  xcrun stapler validate "$APP"
  echo "Stapled OK: $APP"
}

cmd_package() {
  need_app
  rm -f "$ZIP"
  ditto -c -k --keepParent "$APP" "$ZIP"
  echo "Packaged: $ZIP"
  ls -lh "$ZIP"
}

case "$CMD" in
  check) cmd_check ;;
  sign) cmd_sign ;;
  notarize) cmd_notarize ;;
  staple) cmd_staple ;;
  package) cmd_package ;;
  all)
    cmd_sign
    cmd_notarize
    cmd_staple
    cmd_package
    ;;
  *)
    echo "Usage: $0 check|sign|notarize|staple|package|all" >&2
    exit 2
    ;;
esac
