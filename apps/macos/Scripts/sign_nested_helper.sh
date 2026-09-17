#!/usr/bin/env bash
# Sign Contents/Helpers/runspecimen with App Sandbox + inherit entitlements.
# For PyInstaller onedir, also ad-hoc/distribution-signs nested Mach-Os under
# Contents/Helpers/_internal (inside-out) before sealing the entrypoint.
#
# Usage:
#   ./Scripts/sign_nested_helper.sh <helper-path> [--require-distribution]
#
# - Resolves identity via resolve_codesign_identity.sh (Xcode env / keychain / ad-hoc).
# - Always applies Entitlements/RunSpecimen.helper.entitlements (app-sandbox + inherit)
#   to the entrypoint helper.
# - Ad-hoc ("-") is allowed only for local structural smoke; labeled on stderr.
# - Does NOT execute the helper after signing: inherit-signed Mach-Os fail when
#   launched from an unsandboxed shell (exit 133) — version gates must run pre-sign.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HELPER="${1:-}"
REQUIRE_DIST=0
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <helper-path> [--require-distribution]" >&2
  exit 2
fi
shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-distribution) REQUIRE_DIST=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$HELPER" || ! -e "$HELPER" ]]; then
  echo "ERROR: helper path required and must exist: ${HELPER:-<empty>}" >&2
  exit 1
fi
if ! file "$HELPER" | grep -q 'Mach-O'; then
  echo "ERROR: sign_nested_helper expects a Mach-O helper (not a shell launcher): $HELPER" >&2
  file "$HELPER" >&2 || true
  exit 1
fi

HELPER_ENTITLEMENTS="$ROOT/Entitlements/RunSpecimen.helper.entitlements"
test -f "$HELPER_ENTITLEMENTS"

RESOLVE_OUT="$("$ROOT/Scripts/resolve_codesign_identity.sh")"
IDENTITY="$(printf '%s\n' "$RESOLVE_OUT" | awk -F= '/^IDENTITY=/{print substr($0,10); exit}')"
MODE="$(printf '%s\n' "$RESOLVE_OUT" | awk -F= '/^MODE=/{print $2; exit}')"

if [[ "$REQUIRE_DIST" -eq 1 && "$MODE" == "adhoc" ]]; then
  echo "ERROR: distribution signing required but only ad-hoc identity is available." >&2
  echo "Install Apple Distribution (or set RS_SIGN_IDENTITY) — see APP_STORE.md." >&2
  exit 1
fi

xattr -cr "$HELPER" 2>/dev/null || true
HELPER_DIR="$(cd "$(dirname "$HELPER")" && pwd)"
INTERNAL="$HELPER_DIR/_internal"

sign_file() {
  local path="$1"
  local with_entitlements="${2:-0}"
  xattr -cr "$path" 2>/dev/null || true
  if [[ "$MODE" == "adhoc" || "$IDENTITY" == "-" ]]; then
    if [[ "$with_entitlements" == "1" ]]; then
      codesign --force --sign - --options runtime --timestamp=none \
        --entitlements "$HELPER_ENTITLEMENTS" \
        "$path"
    else
      codesign --force --sign - --options runtime --timestamp=none "$path"
    fi
  else
    if [[ "$with_entitlements" == "1" ]]; then
      codesign --force --sign "$IDENTITY" --options runtime --timestamp \
        --entitlements "$HELPER_ENTITLEMENTS" \
        "$path"
    else
      codesign --force --sign "$IDENTITY" --options runtime --timestamp "$path"
    fi
  fi
}

# Inside-out: sign nested dylibs / .so / Mach-O bins under _internal first.
# Non-Mach-O files must NOT keep the executable bit — Xcode's outer app codesign
# otherwise treats them as unsigned nested code (e.g. py.typed) and fails Archive.
if [[ -d "$INTERNAL" ]]; then
  echo "Signing onedir _internal runtime under $INTERNAL"
  xattr -cr "$INTERNAL" 2>/dev/null || true
  while IFS= read -r -d '' f; do
    if file "$f" 2>/dev/null | grep -q 'Mach-O'; then
      sign_file "$f" 0
    else
      chmod a-x "$f" 2>/dev/null || true
    fi
  done < <(find "$INTERNAL" -type f -print0)
fi

if [[ "$MODE" == "adhoc" || "$IDENTITY" == "-" ]]; then
  echo "AD-HOC nested helper signing (local smoke only; TeamIdentifier will be unset)." >&2
  echo "Store export requires Apple Distribution — nested sign will then use that identity." >&2
else
  echo "Signing nested helper with identity ($MODE): $IDENTITY"
fi
sign_file "$HELPER" 1

# Fail-closed entitlement assertions
ENT_XML="$(codesign -d --entitlements - "$HELPER" 2>/dev/null || true)"
echo "$ENT_XML" | grep -q 'com.apple.security.app-sandbox' || {
  echo "ERROR: helper missing com.apple.security.app-sandbox after sign" >&2
  codesign -d --entitlements - "$HELPER" 2>&1 || true
  exit 1
}
echo "$ENT_XML" | grep -q 'com.apple.security.inherit' || {
  echo "ERROR: helper missing com.apple.security.inherit after sign" >&2
  codesign -d --entitlements - "$HELPER" 2>&1 || true
  exit 1
}

codesign --verify --verbose=2 "$HELPER" 2>&1 | tail -5
echo "OK: nested helper signed ($MODE) with sandbox+inherit: $HELPER"
