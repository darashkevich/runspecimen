#!/usr/bin/env bash
# Fail-closed gate for Mac App Store export / upload.
#
# Apple Distribution (or legacy "3rd Party Mac Developer Application") + matching
# Team ID + a Mac App Store provisioning profile for com.darashkevich.runspecimen
# are REQUIRED. Developer ID Application is intentionally NOT sufficient.
#
# Exit 0 only when export may proceed. Exit 1 with a clear reason otherwise.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/Config/signing.env"
EXPORT_PLIST="${RS_EXPORT_OPTIONS_PLIST:-$ROOT/Config/ExportOptions.mas.plist}"
BUNDLE_ID="com.darashkevich.runspecimen"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
fi

fail() { echo "STORE EXPORT BLOCKED: $*" >&2; exit 1; }
pass() { echo "OK: $*"; }

echo "==> Store export readiness (Apple Distribution required; Developer ID insufficient)"

IDENTITIES="$(security find-identity -v -p codesigning 2>/dev/null || true)"
echo "$IDENTITIES"

# Prefer explicit RS_SIGN_IDENTITY when it is Apple Distribution.
DIST_LINE=""
if [[ -n "${RS_SIGN_IDENTITY:-}" ]]; then
  case "$RS_SIGN_IDENTITY" in
    *"Apple Distribution"*|*"3rd Party Mac Developer Application"*)
      DIST_LINE="$RS_SIGN_IDENTITY"
      ;;
    *"Developer ID"*)
      fail "RS_SIGN_IDENTITY is Developer ID — not valid for Mac App Store export. Use Apple Distribution."
      ;;
    *)
      fail "RS_SIGN_IDENTITY must be Apple Distribution (or 3rd Party Mac Developer Application); got: $RS_SIGN_IDENTITY"
      ;;
  esac
else
  DIST_LINE="$(echo "$IDENTITIES" | grep -E 'Apple Distribution|3rd Party Mac Developer Application' | head -1 | sed -n 's/.*"\(.*\)".*/\1/p' || true)"
fi

[[ -n "$DIST_LINE" ]] || fail "No Apple Distribution / 3rd Party Mac Developer Application identity in keychain (Developer ID alone is not enough)."

# Reject if the only "distribution-looking" identity is Developer ID and Apple Distribution is absent.
if echo "$IDENTITIES" | grep -q 'Developer ID Application' \
  && ! echo "$IDENTITIES" | grep -Eq 'Apple Distribution|3rd Party Mac Developer Application'; then
  fail "Only Developer ID Application found — Mac App Store export requires Apple Distribution."
fi
pass "Apple Distribution identity: $DIST_LINE"

# Team ID: from env, else extract from identity "(TEAMID)", else ExportOptions.mas.plist.
TEAM="${RS_NOTARY_TEAM_ID:-}"
if [[ -z "$TEAM" ]]; then
  TEAM="$(printf '%s\n' "$DIST_LINE" | sed -n 's/.*(\([A-Z0-9]\{10\}\)).*/\1/p' | head -1 || true)"
fi
PLIST_TEAM="$(/usr/libexec/PlistBuddy -c 'Print :teamID' "$EXPORT_PLIST" 2>/dev/null || true)"
if [[ -z "$TEAM" ]]; then
  TEAM="$PLIST_TEAM"
fi
[[ -n "$TEAM" ]] || fail "Team ID missing. Set RS_NOTARY_TEAM_ID or put teamID in ExportOptions.mas.plist."
[[ "$TEAM" != "TEAMID" ]] || fail "ExportOptions.mas.plist still has placeholder teamID=TEAMID. Replace with your 10-char Apple Team ID."
[[ "$TEAM" =~ ^[A-Z0-9]{10}$ ]] || fail "Team ID must be 10 alphanumeric chars; got: $TEAM"

if [[ -n "$PLIST_TEAM" && "$PLIST_TEAM" != "TEAMID" && "$PLIST_TEAM" != "$TEAM" ]]; then
  fail "ExportOptions teamID=$PLIST_TEAM does not match resolved team $TEAM"
fi

# Identity parenthetical team must match when present.
ID_TEAM="$(printf '%s\n' "$DIST_LINE" | sed -n 's/.*(\([A-Z0-9]\{10\}\)).*/\1/p' | head -1 || true)"
if [[ -n "$ID_TEAM" && "$ID_TEAM" != "$TEAM" ]]; then
  fail "Apple Distribution identity team $ID_TEAM != resolved team $TEAM"
fi
pass "Team ID matches: $TEAM"

# Provisioning profile for Mac App Store + bundle id.
PROFILE_DIRS=(
  "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"
  "$HOME/Library/MobileDevice/Provisioning Profiles"
)
FOUND_PROFILE=""
FOUND_PROFILE_TEAM=""
shopt -s nullglob
for dir in "${PROFILE_DIRS[@]}"; do
  # shellcheck disable=SC2086
  for profile in "$dir"/*.provisionprofile "$dir"/*.mobileprovision; do
    [[ -f "$profile" ]] || continue
    DECODED="$(security cms -D -i "$profile" 2>/dev/null || true)"
    [[ -n "$DECODED" ]] || continue
    echo "$DECODED" | grep -q "$BUNDLE_ID" || continue
    # Mac App Store platforms / get-task-allow false / distribution
    if echo "$DECODED" | grep -Eq 'Apple Distribution|3rd Party Mac Developer Application|Mac App Store|ProvisionedDevices'; then
      :
    fi
    # Exclude ad-hoc / development-only profiles that list get-task-allow true without distribution.
    PROF_TEAM="$(printf '%s\n' "$DECODED" | plutil -extract TeamIdentifier.0 raw -o - -- - 2>/dev/null || true)"
    if [[ -z "$PROF_TEAM" ]]; then
      PROF_TEAM="$(printf '%s\n' "$DECODED" | awk '/TeamIdentifier/,/<\/array>/' | grep -Eo '[A-Z0-9]{10}' | head -1 || true)"
    fi
    # Prefer profiles that mention production / appstore style entitlements (no get-task-allow).
    if echo "$DECODED" | grep -q 'get-task-allow'; then
      # Development profiles often include get-task-allow — skip for Store export.
      continue
    fi
    if [[ -n "$PROF_TEAM" && "$PROF_TEAM" != "$TEAM" ]]; then
      continue
    fi
    FOUND_PROFILE="$profile"
    FOUND_PROFILE_TEAM="$PROF_TEAM"
    break 2
  done
done
shopt -u nullglob

if [[ -z "$FOUND_PROFILE" ]]; then
  fail "No Mac App Store provisioning profile for $BUNDLE_ID matching team $TEAM (download from developer.apple.com / Xcode)."
fi
pass "Provisioning profile: $FOUND_PROFILE (team=${FOUND_PROFILE_TEAM:-$TEAM})"

# method must remain app-store-connect
METHOD="$(/usr/libexec/PlistBuddy -c 'Print :method' "$EXPORT_PLIST" 2>/dev/null || true)"
[[ "$METHOD" == "app-store-connect" || "$METHOD" == "app-store" ]] \
  || fail "ExportOptions method must be app-store-connect (got: ${METHOD:-empty})"

pass "Store export prerequisites satisfied (Apple Distribution + team $TEAM + profile)"
echo "READY_TEAM=$TEAM"
echo "READY_IDENTITY=$DIST_LINE"
echo "READY_PROFILE=$FOUND_PROFILE"
