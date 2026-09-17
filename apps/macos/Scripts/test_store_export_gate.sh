#!/usr/bin/env bash
# Negative + positive fixtures for assert_store_export_ready.sh profile parsing.
#
# Proves the gate fails closed on: wrong bundle, wrong team, wrong type,
# Developer ID, development, ad-hoc, and malformed profiles — and accepts only
# a Mac App Store–shaped profile with exact application-identifier + team.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
GATE=./Scripts/assert_store_export_ready.sh
chmod +x "$GATE"

TMP="$(mktemp -d -t rs-store-gate)"
trap 'rm -rf "$TMP"' EXIT

TEAM=ABCD123456
OTHER=ZYXW987654
BUNDLE=com.darashkevich.runspecimen
openssl req -x509 -newkey rsa:2048 -keyout "$TMP/key.pem" -out "$TMP/cert.pem" \
  -days 1 -nodes -subj "/CN=rs-store-gate-fixture" >/dev/null 2>&1

write_plist() {
  local path="$1"
  cat >"$path"
}

sign_profile() {
  local plist="$1" out="$2"
  openssl smime -sign -in "$plist" -out "$out" -signer "$TMP/cert.pem" \
    -inkey "$TMP/key.pem" -outform der -nodetach 2>/dev/null
}

expect_reject_decoded() {
  local label="$1" plist="$2" team="${3:-$TEAM}"
  local out rc
  set +e
  out="$("$GATE" --validate-decoded-plist "$plist" "$team" "$BUNDLE" 2>&1)"
  rc=$?
  set -e
  if [[ "$rc" -eq 0 ]]; then
    echo "FAIL: expected reject ($label) but gate accepted:" >&2
    echo "$out" >&2
    exit 1
  fi
  echo "$out" | grep -q 'STORE EXPORT BLOCKED' \
    || { echo "FAIL: $label missing STORE EXPORT BLOCKED" >&2; echo "$out" >&2; exit 1; }
  echo "OK reject: $label"
}

expect_accept_decoded() {
  local label="$1" plist="$2" team="${3:-$TEAM}"
  local out
  out="$("$GATE" --validate-decoded-plist "$plist" "$team" "$BUNDLE" 2>&1)"
  echo "$out" | grep -q 'OK:' \
    || { echo "FAIL: expected accept ($label)" >&2; echo "$out" >&2; exit 1; }
  echo "OK accept: $label"
}

echo "==> decoded-plist negatives / positive"

# Good MAS-shaped profile
write_plist "$TMP/good.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Name</key><string>Mac App Store RunSpecimen</string>
  <key>Platform</key><array><string>OSX</string></array>
  <key>TeamIdentifier</key><array><string>$TEAM</string></array>
  <key>ApplicationIdentifierPrefix</key><array><string>$TEAM</string></array>
  <key>Entitlements</key><dict>
    <key>com.apple.application-identifier</key>
    <string>$TEAM.$BUNDLE</string>
    <key>com.apple.developer.team-identifier</key><string>$TEAM</string>
  </dict>
</dict></plist>
EOF
expect_accept_decoded "mas-good" "$TMP/good.plist"

# Wrong bundle
write_plist "$TMP/wrong-bundle.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Name</key><string>Mac App Store OtherApp</string>
  <key>Platform</key><array><string>OSX</string></array>
  <key>TeamIdentifier</key><array><string>$TEAM</string></array>
  <key>Entitlements</key><dict>
    <key>com.apple.application-identifier</key>
    <string>$TEAM.com.example.other</string>
  </dict>
</dict></plist>
EOF
expect_reject_decoded "wrong-bundle" "$TMP/wrong-bundle.plist"

# Wrong team
write_plist "$TMP/wrong-team.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Name</key><string>Mac App Store RunSpecimen</string>
  <key>Platform</key><array><string>OSX</string></array>
  <key>TeamIdentifier</key><array><string>$OTHER</string></array>
  <key>Entitlements</key><dict>
    <key>com.apple.application-identifier</key>
    <string>$OTHER.$BUNDLE</string>
  </dict>
</dict></plist>
EOF
expect_reject_decoded "wrong-team" "$TMP/wrong-team.plist"

# iOS-only platform (wrong type / platform)
write_plist "$TMP/ios-platform.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Name</key><string>App Store iOS</string>
  <key>Platform</key><array><string>iOS</string></array>
  <key>TeamIdentifier</key><array><string>$TEAM</string></array>
  <key>Entitlements</key><dict>
    <key>com.apple.application-identifier</key>
    <string>$TEAM.$BUNDLE</string>
  </dict>
</dict></plist>
EOF
expect_reject_decoded "wrong-platform-ios" "$TMP/ios-platform.plist"

# Development (get-task-allow)
write_plist "$TMP/development.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Name</key><string>Mac Development</string>
  <key>Platform</key><array><string>OSX</string></array>
  <key>TeamIdentifier</key><array><string>$TEAM</string></array>
  <key>ProvisionedDevices</key><array><string>DEVICE1</string></array>
  <key>Entitlements</key><dict>
    <key>com.apple.application-identifier</key>
    <string>$TEAM.$BUNDLE</string>
    <key>get-task-allow</key><true/>
  </dict>
</dict></plist>
EOF
expect_reject_decoded "development" "$TMP/development.plist"

# Ad-hoc (devices, no get-task-allow)
write_plist "$TMP/adhoc.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Name</key><string>Mac Ad Hoc</string>
  <key>Platform</key><array><string>OSX</string></array>
  <key>TeamIdentifier</key><array><string>$TEAM</string></array>
  <key>ProvisionedDevices</key><array><string>DEVICE1</string></array>
  <key>Entitlements</key><dict>
    <key>com.apple.application-identifier</key>
    <string>$TEAM.$BUNDLE</string>
  </dict>
</dict></plist>
EOF
expect_reject_decoded "ad-hoc" "$TMP/adhoc.plist"

# Developer ID named profile
write_plist "$TMP/devid.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Name</key><string>Developer ID Application RunSpecimen</string>
  <key>Platform</key><array><string>OSX</string></array>
  <key>TeamIdentifier</key><array><string>$TEAM</string></array>
  <key>Entitlements</key><dict>
    <key>com.apple.application-identifier</key>
    <string>$TEAM.$BUNDLE</string>
  </dict>
</dict></plist>
EOF
expect_reject_decoded "developer-id" "$TMP/devid.plist"

# Missing TeamIdentifier
write_plist "$TMP/no-team.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Name</key><string>Mac App Store RunSpecimen</string>
  <key>Platform</key><array><string>OSX</string></array>
  <key>Entitlements</key><dict>
    <key>com.apple.application-identifier</key>
    <string>$TEAM.$BUNDLE</string>
  </dict>
</dict></plist>
EOF
expect_reject_decoded "absent-teamidentifier" "$TMP/no-team.plist"

# Substring bait: wrong app id that merely contains bundle string as substring elsewhere
write_plist "$TMP/substring-bait.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Name</key><string>Mac App Store mentions $BUNDLE in name only</string>
  <key>Platform</key><array><string>OSX</string></array>
  <key>TeamIdentifier</key><array><string>$TEAM</string></array>
  <key>Entitlements</key><dict>
    <key>com.apple.application-identifier</key>
    <string>$TEAM.com.not.runspecimen</string>
  </dict>
</dict></plist>
EOF
expect_reject_decoded "substring-bundle-bait" "$TMP/substring-bait.plist"

# Malformed
printf 'not-a-plist{{' >"$TMP/malformed.plist"
expect_reject_decoded "malformed" "$TMP/malformed.plist"

echo "==> CMS-signed profile discovery (RS_PROFILE_SEARCH_DIRS)"
PROFILES="$TMP/profiles"
mkdir -p "$PROFILES"
# Only wrong profiles in dir → full gate must still block (even with mocked Distribution).
sign_profile "$TMP/wrong-bundle.plist" "$PROFILES/wrong.mobileprovision"
sign_profile "$TMP/development.plist" "$PROFILES/dev.mobileprovision"
sign_profile "$TMP/devid.plist" "$PROFILES/devid.mobileprovision"

EXPORT_PLIST="$TMP/ExportOptions.plist"
cat >"$EXPORT_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>teamID</key><string>$TEAM</string>
</dict></plist>
EOF

set +e
OUT="$(
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  "$GATE" 2>&1
)"
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "FAIL: gate opened with only bad profiles" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -q 'STORE EXPORT BLOCKED' \
  || { echo "FAIL: expected BLOCKED with bad CMS profiles" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: full gate blocked on wrong/dev/Developer ID CMS profiles"

# Add good profile → should open (mocked Apple Distribution; no keychain needed).
sign_profile "$TMP/good.plist" "$PROFILES/good.mobileprovision"
OUT="$(
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  "$GATE" 2>&1
)"
echo "$OUT" | grep -q 'READY_TEAM=' \
  || { echo "FAIL: expected READY with good CMS profile" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: full gate accepts good MAS CMS profile"

echo "==> Developer ID identity rejected"
set +e
OUT="$(
  RS_SIGN_IDENTITY="Developer ID Application: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  "$GATE" 2>&1
)"
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "FAIL: Developer ID identity should block" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -Eqi 'Developer ID' \
  || { echo "FAIL: expected Developer ID message" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: Developer ID identity blocked"

echo "==> default host gate still fail-closed without Apple Distribution"
set +e
OUT="$("$GATE" 2>&1)"
RC=$?
set -e
# Host has no Apple Distribution (typical CI / this machine) OR may open if Yahor installs certs.
if [[ "$RC" -eq 0 ]]; then
  echo "NOTE: host has Apple Distribution — gate opened (acceptable on operator machine)"
  echo "$OUT" | tail -5
else
  echo "$OUT" | grep -q 'STORE EXPORT BLOCKED' \
    || { echo "FAIL: default gate should BLOCK without Distribution" >&2; echo "$OUT" >&2; exit 1; }
  echo "OK: default gate blocked without Apple Distribution"
fi

echo "STORE EXPORT GATE TESTS OK"
