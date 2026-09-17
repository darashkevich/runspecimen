#!/usr/bin/env bash
# Fail-closed gate for Mac App Store export / upload.
#
# Apple Distribution (or legacy "3rd Party Mac Developer Application") + matching
# Team ID + a Mac App Store provisioning profile for com.darashkevich.runspecimen
# are REQUIRED. Developer ID Application is intentionally NOT sufficient.
#
# Profile checks are exact (not substring greps on the CMS blob):
#   - application-identifier == TEAM.BUNDLE_ID
#   - TeamIdentifier present and == TEAM
#   - Platform includes OSX / macOS
#   - distribution / Mac App Store shape (no ProvisionedDevices, no get-task-allow)
#   - rejects development, ad-hoc, Developer ID–style, and malformed profiles
#
# Exit 0 only when export may proceed. Exit 1 with a clear reason otherwise.
#
# Required:
#   RS_ARCHIVE_APP           — archived .app path (fail closed if unset / missing)
#                            When RS_ARCHIVE_PATH is also set, RS_ARCHIVE_APP must resolve to
#                            the same path as $RS_ARCHIVE_PATH/Products/Applications/RunSpecimen.app
#                            (canonicalized). Prevents checking a Distribution-signed app while
#                            exporting a different archive.
#
# Optional:
#   RS_ARCHIVE_PATH          — .xcarchive being exported; when set, binds signing checks to it
#
# Test hooks (optional; never for production export_mas.sh):
#   RS_PROFILE_SEARCH_DIRS          — colon-separated dirs of *.mobileprovision / *.provisionprofile
#   RS_SIGN_IDENTITY                — force identity string (still must be Apple Distribution)
#   RS_EXPORT_OPTIONS_PLIST         — ExportOptions plist path
#   RS_TEST_CODESIGN_DV_APP_FILE    — fixture codesign -dv text for the .app (unit tests)
#   RS_TEST_CODESIGN_DV_HELPER_FILE — fixture codesign -dv text for nested helper (unit tests)
#   RS_ALLOW_TEST_CODESIGN_DV=1     — required to honor the fixture files above (harness only)
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

# --- Profile field helpers (decoded XML plist on disk) ----------------------------

plist_raw() {
  local plist="$1" key="$2"
  /usr/libexec/PlistBuddy -c "Print :$key" "$plist" 2>/dev/null || true
}

plist_has_key() {
  local plist="$1" key="$2"
  /usr/libexec/PlistBuddy -c "Print :$key" "$plist" >/dev/null 2>&1
}

# Print entitlement value trying modern + legacy keys.
entitlement() {
  local plist="$1" key="$2"
  local v
  v="$(plist_raw "$plist" "Entitlements:$key")"
  [[ -n "$v" ]] && { printf '%s' "$v"; return 0; }
  return 1
}

# Validate one decoded provisioning profile plist against TEAM + BUNDLE_ID.
# Prints "OK: ..." on success; returns non-zero with reason on stderr via caller.
validate_decoded_mas_profile() {
  local plist="$1"
  local team="$2"
  local bundle="$3"
  local expected_app_id="${team}.${bundle}"
  local name platform0 app_id app_id_legacy team0 get_task provisions_devices
  local platform_blob

  [[ -f "$plist" ]] || { echo "profile plist missing: $plist"; return 1; }

  # Must parse as a real plist dict (malformed → fail).
  if ! /usr/libexec/PlistBuddy -c 'Print' "$plist" >/dev/null 2>&1; then
    echo "malformed profile plist (PlistBuddy cannot parse)"
    return 1
  fi

  name="$(plist_raw "$plist" "Name")"
  team0="$(plist_raw "$plist" "TeamIdentifier:0")"
  if [[ -z "$team0" ]]; then
    echo "TeamIdentifier absent or empty"
    return 1
  fi
  if [[ "$team0" != "$team" ]]; then
    echo "TeamIdentifier=$team0 does not match required team $team"
    return 1
  fi

  # Exact application identifier (prefer com.apple.application-identifier).
  app_id="$(entitlement "$plist" "com.apple.application-identifier" || true)"
  app_id_legacy="$(entitlement "$plist" "application-identifier" || true)"
  if [[ -z "$app_id" ]]; then
    app_id="$app_id_legacy"
  fi
  if [[ -z "$app_id" ]]; then
    echo "application-identifier entitlement missing"
    return 1
  fi
  if [[ "$app_id" == *"*"* ]]; then
    echo "wildcard application-identifier not allowed for Store export: $app_id"
    return 1
  fi
  if [[ "$app_id" != "$expected_app_id" ]]; then
    echo "application-identifier=$app_id != required $expected_app_id"
    return 1
  fi

  # Platform must be Mac (OSX / macOS / MacOSX).
  platform_blob="$(plist_raw "$plist" "Platform" || true)"
  platform0="$(plist_raw "$plist" "Platform:0" || true)"
  if [[ -z "$platform_blob" && -z "$platform0" ]]; then
    echo "Platform missing (need OSX/macOS for Mac App Store)"
    return 1
  fi
  case "${platform_blob} ${platform0}" in
    *OSX*|*macOS*|*MacOSX*|*MacOS*) ;;
    *)
      echo "Platform not Mac App Store capable: ${platform0:-$platform_blob}"
      return 1
      ;;
  esac

  # Development: get-task-allow true.
  get_task="$(entitlement "$plist" "get-task-allow" || true)"
  if [[ "$get_task" == "true" || "$get_task" == "1" ]]; then
    echo "development profile (get-task-allow=true) — not Mac App Store distribution"
    return 1
  fi

  # Development / ad-hoc: device list present.
  if plist_has_key "$plist" "ProvisionedDevices"; then
    echo "profile lists ProvisionedDevices (development/ad-hoc) — not Mac App Store"
    return 1
  fi

  # Developer ID / direct distribution profiles are not MAS.
  # Name + entitlement heuristics (fail closed on explicit Developer ID markers).
  if printf '%s\n' "$name" | grep -Eqi 'Developer ID'; then
    echo "profile Name indicates Developer ID (not Mac App Store): $name"
    return 1
  fi
  # Reject explicit "Developer ID" markers inside Entitlements dump if present.
  local ent_dump
  ent_dump="$(plist_raw "$plist" "Entitlements" || true)"
  if printf '%s\n' "$ent_dump" | grep -Eqi 'Developer ID'; then
    echo "Entitlements mention Developer ID — not Mac App Store"
    return 1
  fi

  # Reject obvious non-store types by name.
  if printf '%s\n' "$name" | grep -Eqi 'development|ad[[:space:]-]?hoc|adhoc'; then
    echo "profile Name indicates non-Store type: $name"
    return 1
  fi
  # Prefer explicit Mac App Store / App Store / Distribution naming when Name is set.
  if [[ -n "$name" ]] && ! printf '%s\n' "$name" | grep -Eqi 'App Store|Mac App Store|Distribution|MAS'; then
    # Allow empty-ish / UUID-only names only if other hard checks passed; still
    # require at least one Store/Distribution marker for fail-closed clarity.
    echo "profile Name lacks Mac App Store/Distribution marker: ${name:-empty}"
    return 1
  fi

  echo "valid MAS profile name=${name:-?} app_id=$app_id team=$team0 platform=${platform0:-ok}"
  return 0
}

decode_profile_to_plist() {
  local profile="$1"
  local out="$2"
  # security cms -D writes XML plist to stdout for Apple + openssl-smime fixtures.
  if ! security cms -D -i "$profile" >"$out" 2>/dev/null; then
    return 1
  fi
  [[ -s "$out" ]] || return 1
  /usr/libexec/PlistBuddy -c 'Print' "$out" >/dev/null 2>&1
}

# --- Main gate --------------------------------------------------------------------

# Unit-test entry: validate a single decoded plist and exit.
if [[ "${1:-}" == "--validate-decoded-plist" ]]; then
  PLIST_PATH="${2:-}"
  TEAM_ARG="${3:-}"
  BUNDLE_ARG="${4:-$BUNDLE_ID}"
  [[ -n "$PLIST_PATH" && -n "$TEAM_ARG" ]] || fail "usage: $0 --validate-decoded-plist PATH TEAM [BUNDLE]"
  if reason="$(validate_decoded_mas_profile "$PLIST_PATH" "$TEAM_ARG" "$BUNDLE_ARG")"; then
    pass "$reason"
    exit 0
  else
    rc=$?
    fail "profile rejected: $reason"
  fi
fi

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
  # Allow override only when RS_SIGN_IDENTITY already pinned an Apple Distribution string
  # that may not yet appear in find-identity (rare); still require the string itself.
  case "$DIST_LINE" in
    *"Apple Distribution"*|*"3rd Party Mac Developer Application"*) ;;
    *)
      fail "Only Developer ID Application found — Mac App Store export requires Apple Distribution."
      ;;
  esac
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

# Required: archived .app + nested helper must be Apple Distribution for TEAM.
# Prefer binding to RS_ARCHIVE_PATH when present so a separate RS_ARCHIVE_APP cannot
# satisfy the gate while a different archive is exported.
canon_dir() {
  (cd "$1" && pwd -P)
}

ARCHIVE_APP="${RS_ARCHIVE_APP:-}"
if [[ -n "${RS_ARCHIVE_PATH:-}" ]]; then
  [[ -d "$RS_ARCHIVE_PATH" ]] || fail "RS_ARCHIVE_PATH is not a directory: $RS_ARCHIVE_PATH"
  DERIVED_APP="$RS_ARCHIVE_PATH/Products/Applications/RunSpecimen.app"
  [[ -d "$DERIVED_APP" ]] || fail "archived app missing under RS_ARCHIVE_PATH: $DERIVED_APP"
  DERIVED_CANON="$(canon_dir "$DERIVED_APP")"
  if [[ -n "$ARCHIVE_APP" ]]; then
    [[ -d "$ARCHIVE_APP" ]] || fail "RS_ARCHIVE_APP not a directory: $ARCHIVE_APP"
    OVERRIDE_CANON="$(canon_dir "$ARCHIVE_APP")"
    [[ "$OVERRIDE_CANON" == "$DERIVED_CANON" ]] \
      || fail "RS_ARCHIVE_APP ($OVERRIDE_CANON) != app in RS_ARCHIVE_PATH ($DERIVED_CANON) — refusing export-gate bypass"
  fi
  ARCHIVE_APP="$DERIVED_APP"
fi
[[ -n "$ARCHIVE_APP" ]] || fail "RS_ARCHIVE_APP is required (path to archived RunSpecimen.app). Export must not proceed without an archive signing check."
[[ -d "$ARCHIVE_APP" ]] || fail "RS_ARCHIVE_APP not a directory: $ARCHIVE_APP"

HELPER="$ARCHIVE_APP/Contents/Resources/RunSpecimenEngine/runspecimen"
if [[ ! -e "$HELPER" ]]; then
  HELPER="$ARCHIVE_APP/Contents/Helpers/runspecimen"
fi
[[ -e "$HELPER" ]] || fail "nested helper missing under RS_ARCHIVE_APP (checked RunSpecimenEngine + Helpers): $ARCHIVE_APP"

# Fixture codesign -dv text is harness-only. Production export_mas refuses these env vars.
codesign_dv_for() {
  local path="$1" fixture="$2"
  if [[ -n "$fixture" && -f "$fixture" ]]; then
    if [[ "${RS_ALLOW_TEST_CODESIGN_DV:-}" != "1" ]]; then
      fail "RS_TEST_CODESIGN_DV_* fixtures require RS_ALLOW_TEST_CODESIGN_DV=1 (test harness only); refusing stub signature for $path"
    fi
    cat "$fixture"
    return 0
  fi
  # Always verify the real binary under the archive path (not metadata stubs).
  codesign -dv --verbose=4 "$path" 2>&1 || true
}

assert_distribution_signed() {
  local label="$1" path="$2" fixture="${3:-}"
  local dv team auth
  dv="$(codesign_dv_for "$path" "$fixture")"
  team="$(printf '%s\n' "$dv" | awk -F= '/^TeamIdentifier=/{print $2; exit}')"
  auth="$(printf '%s\n' "$dv" | awk -F= '/^Authority=/{print $2; exit}')"
  if [[ -z "$team" || "$team" == "not set" ]]; then
    fail "$label TeamIdentifier unset (ad-hoc) — Store export requires Apple Distribution–signed archive matching team $TEAM"
  fi
  [[ "$team" == "$TEAM" ]] || fail "$label TeamIdentifier=$team != team $TEAM"
  case "$auth" in
    *"Apple Distribution"*|*"3rd Party Mac Developer Application"*) ;;
    *"Developer ID"*)
      fail "$label Authority is Developer ID — not valid for Mac App Store: $auth"
      ;;
    *)
      fail "$label Authority must be Apple Distribution; got: ${auth:-empty}"
      ;;
  esac
  pass "$label TeamIdentifier + Apple Distribution Authority match ($team)"
}

assert_distribution_signed "archive app" "$ARCHIVE_APP" "${RS_TEST_CODESIGN_DV_APP_FILE:-}"
assert_distribution_signed "archive helper" "$HELPER" "${RS_TEST_CODESIGN_DV_HELPER_FILE:-}"

# Provisioning profile discovery + strict validation.
PROFILE_DIRS=()
if [[ -n "${RS_PROFILE_SEARCH_DIRS:-}" ]]; then
  IFS=':' read -r -a PROFILE_DIRS <<<"$RS_PROFILE_SEARCH_DIRS"
else
  PROFILE_DIRS=(
    "$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"
    "$HOME/Library/MobileDevice/Provisioning Profiles"
  )
fi

FOUND_PROFILE=""
FOUND_DETAIL=""
REJECT_NOTES=()
DECODE_TMP="$(mktemp -t rs-mas-profile)"
trap 'rm -f "$DECODE_TMP"' EXIT

shopt -s nullglob
for dir in "${PROFILE_DIRS[@]}"; do
  [[ -d "$dir" ]] || continue
  for profile in "$dir"/*.provisionprofile "$dir"/*.mobileprovision; do
    [[ -f "$profile" ]] || continue
    if ! decode_profile_to_plist "$profile" "$DECODE_TMP"; then
      REJECT_NOTES+=("$(basename "$profile"): CMS decode failed / malformed")
      continue
    fi
    if reason="$(validate_decoded_mas_profile "$DECODE_TMP" "$TEAM" "$BUNDLE_ID")"; then
      FOUND_PROFILE="$profile"
      FOUND_DETAIL="$reason"
      break 2
    else
      REJECT_NOTES+=("$(basename "$profile"): $reason")
    fi
  done
done
shopt -u nullglob

if [[ -z "$FOUND_PROFILE" ]]; then
  if ((${#REJECT_NOTES[@]} > 0)); then
    echo "Rejected profiles:" >&2
    for note in "${REJECT_NOTES[@]}"; do
      echo "  - $note" >&2
    done
  fi
  fail "No Mac App Store provisioning profile for exact id ${TEAM}.${BUNDLE_ID} (download Mac App Store distribution profile from developer.apple.com / Xcode)."
fi
pass "Provisioning profile: $FOUND_PROFILE ($FOUND_DETAIL)"

# method must remain app-store-connect
METHOD="$(/usr/libexec/PlistBuddy -c 'Print :method' "$EXPORT_PLIST" 2>/dev/null || true)"
[[ "$METHOD" == "app-store-connect" || "$METHOD" == "app-store" ]] \
  || fail "ExportOptions method must be app-store-connect (got: ${METHOD:-empty})"

pass "Store export prerequisites satisfied (Apple Distribution + team $TEAM + MAS profile)"
echo "READY_TEAM=$TEAM"
echo "READY_IDENTITY=$DIST_LINE"
echo "READY_PROFILE=$FOUND_PROFILE"
