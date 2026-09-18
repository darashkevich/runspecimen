#!/usr/bin/env bash
# Negative + positive fixtures for assert_store_export_ready.sh / export_mas.sh.
#
# Proves the gate fails closed on: wrong bundle, wrong team, wrong type,
# Developer ID, development, ad-hoc, and malformed profiles — and accepts only
# a Mac App Store–shaped profile with exact application-identifier + team.
# Also requires RS_ARCHIVE_APP (app + nested helper) and proves export_mas
# refuses ad-hoc / Developer ID archives before xcodebuild -exportArchive.
# Proves RS_ARCHIVE_APP cannot bypass the gate for a different RS_ARCHIVE_PATH,
# and that RS_TEST_CODESIGN_DV_* fixtures are refused on the production export path.
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

# --- Archived .app fixtures (required RS_ARCHIVE_APP) -------------------------------

make_min_app() {
  local app="$1"
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/RunSpecimenEngine"
  cat >"$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>com.darashkevich.runspecimen</string>
  <key>CFBundleName</key><string>RunSpecimen</string>
  <key>CFBundleExecutable</key><string>RunSpecimen</string>
  <key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
PLIST
  printf '#!/bin/sh\nexit 0\n' >"$app/Contents/MacOS/RunSpecimen"
  printf '#!/bin/sh\nexit 0\n' >"$app/Contents/Resources/RunSpecimenEngine/runspecimen"
  chmod +x "$app/Contents/MacOS/RunSpecimen" "$app/Contents/Resources/RunSpecimenEngine/runspecimen"
}

write_dv_fixture() {
  local path="$1" authority="$2" team="$3"
  cat >"$path" <<EOF
Executable=/tmp/fixture
Identifier=com.darashkevich.runspecimen
Format=app bundle with Mach-O thin (arm64)
Authority=$authority
Authority=Apple Worldwide Developer Relations Certification Authority
Authority=Apple Root CA
TeamIdentifier=$team
Signature=standard
EOF
}

ADHOC_APP="$TMP/adhoc-app/RunSpecimen.app"
make_min_app "$ADHOC_APP"
codesign --force --sign - "$ADHOC_APP/Contents/Resources/RunSpecimenEngine/runspecimen" >/dev/null 2>&1
codesign --force --sign - "$ADHOC_APP" >/dev/null 2>&1

DIST_APP="$TMP/dist-app/RunSpecimen.app"
make_min_app "$DIST_APP"
write_dv_fixture "$TMP/dv-app-dist.txt" "Apple Distribution: Fixture ($TEAM)" "$TEAM"
write_dv_fixture "$TMP/dv-helper-dist.txt" "Apple Distribution: Fixture ($TEAM)" "$TEAM"

DEVID_APP="$TMP/devid-app/RunSpecimen.app"
make_min_app "$DEVID_APP"
write_dv_fixture "$TMP/dv-app-devid.txt" "Developer ID Application: Fixture ($TEAM)" "$TEAM"
write_dv_fixture "$TMP/dv-helper-devid.txt" "Developer ID Application: Fixture ($TEAM)" "$TEAM"

HELPER_BAD_APP="$TMP/helper-bad-app/RunSpecimen.app"
make_min_app "$HELPER_BAD_APP"
cat >"$TMP/dv-helper-adhoc.txt" <<'EOF'
Executable=/tmp/fixture-helper
Identifier=runspecimen
Format=Mach-O thin (arm64)
Signature=adhoc
TeamIdentifier=not set
EOF

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

echo "==> RS_ARCHIVE_APP required (fail closed)"
set +e
OUT="$(
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  env -u RS_ARCHIVE_APP "$GATE" 2>&1
)"
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "FAIL: gate opened without RS_ARCHIVE_APP" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -q 'RS_ARCHIVE_APP is required' \
  || { echo "FAIL: expected RS_ARCHIVE_APP required message" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: missing RS_ARCHIVE_APP blocked"

set +e
OUT="$(
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  RS_ARCHIVE_APP="$DIST_APP" \
  RS_ALLOW_TEST_CODESIGN_DV=1 \
  RS_TEST_CODESIGN_DV_APP_FILE="$TMP/dv-app-dist.txt" \
  RS_TEST_CODESIGN_DV_HELPER_FILE="$TMP/dv-helper-dist.txt" \
  "$GATE" 2>&1
)"
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "FAIL: gate opened with only bad profiles" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -q 'STORE EXPORT BLOCKED' \
  || { echo "FAIL: expected BLOCKED with bad CMS profiles" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: full gate blocked on wrong/dev/Developer ID CMS profiles"

# Fixtures without RS_ALLOW_TEST_CODESIGN_DV must not stub production-like gate calls.
set +e
OUT="$(
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  RS_ARCHIVE_APP="$DIST_APP" \
  RS_TEST_CODESIGN_DV_APP_FILE="$TMP/dv-app-dist.txt" \
  RS_TEST_CODESIGN_DV_HELPER_FILE="$TMP/dv-helper-dist.txt" \
  env -u RS_ALLOW_TEST_CODESIGN_DV "$GATE" 2>&1
)"
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "FAIL: fixtures without allow flag should block" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -Eqi 'RS_ALLOW_TEST_CODESIGN_DV|test harness only' \
  || { echo "FAIL: expected fixture-allow refusal" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: codesign fixtures refused without RS_ALLOW_TEST_CODESIGN_DV=1"

# Add good profile → should open (mocked Apple Distribution + Distribution-signed archive fixtures).
sign_profile "$TMP/good.plist" "$PROFILES/good.mobileprovision"
OUT="$(
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  RS_ARCHIVE_APP="$DIST_APP" \
  RS_ALLOW_TEST_CODESIGN_DV=1 \
  RS_TEST_CODESIGN_DV_APP_FILE="$TMP/dv-app-dist.txt" \
  RS_TEST_CODESIGN_DV_HELPER_FILE="$TMP/dv-helper-dist.txt" \
  "$GATE" 2>&1
)"
echo "$OUT" | grep -q 'READY_TEAM=' \
  || { echo "FAIL: expected READY with good CMS profile" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -q 'archive helper TeamIdentifier' \
  || { echo "FAIL: expected helper archive check" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: full gate accepts good MAS CMS profile + Distribution archive/helper"

echo "==> Developer ID identity rejected"
set +e
OUT="$(
  RS_SIGN_IDENTITY="Developer ID Application: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  RS_ARCHIVE_APP="$DIST_APP" \
  RS_ALLOW_TEST_CODESIGN_DV=1 \
  RS_TEST_CODESIGN_DV_APP_FILE="$TMP/dv-app-dist.txt" \
  RS_TEST_CODESIGN_DV_HELPER_FILE="$TMP/dv-helper-dist.txt" \
  "$GATE" 2>&1
)"
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "FAIL: Developer ID identity should block" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -Eqi 'Developer ID' \
  || { echo "FAIL: expected Developer ID message" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: Developer ID identity blocked"

echo "==> ad-hoc archive refused (real codesign -)"
set +e
OUT="$(
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  RS_ARCHIVE_APP="$ADHOC_APP" \
  "$GATE" 2>&1
)"
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "FAIL: ad-hoc archive should block" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -Eqi 'ad-hoc|TeamIdentifier unset' \
  || { echo "FAIL: expected ad-hoc archive block" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: ad-hoc archive blocked"

echo "==> Developer ID archive Authority refused (app + helper fixtures)"
set +e
OUT="$(
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  RS_ARCHIVE_APP="$DEVID_APP" \
  RS_ALLOW_TEST_CODESIGN_DV=1 \
  RS_TEST_CODESIGN_DV_APP_FILE="$TMP/dv-app-devid.txt" \
  RS_TEST_CODESIGN_DV_HELPER_FILE="$TMP/dv-helper-devid.txt" \
  "$GATE" 2>&1
)"
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "FAIL: Developer ID archive should block" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -Eqi 'Developer ID' \
  || { echo "FAIL: expected Developer ID archive Authority block" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: Developer ID archive Authority blocked"

echo "==> nested helper ad-hoc refused even when app fixture looks Distribution"
set +e
OUT="$(
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  RS_ARCHIVE_APP="$HELPER_BAD_APP" \
  RS_ALLOW_TEST_CODESIGN_DV=1 \
  RS_TEST_CODESIGN_DV_APP_FILE="$TMP/dv-app-dist.txt" \
  RS_TEST_CODESIGN_DV_HELPER_FILE="$TMP/dv-helper-adhoc.txt" \
  "$GATE" 2>&1
)"
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "FAIL: helper ad-hoc should block" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -Eqi 'helper.*ad-hoc|helper.*TeamIdentifier unset' \
  || { echo "FAIL: expected helper ad-hoc block" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: nested helper ad-hoc blocked"

# --- export_mas.sh refuses before xcodebuild -exportArchive ------------------------

EXPORT_SH=./Scripts/export_mas.sh
chmod +x "$EXPORT_SH"
STUB_BIN="$TMP/stub-bin"
mkdir -p "$STUB_BIN"
XCODEBUILD_MARKER="$TMP/xcodebuild-invoked"
cat >"$STUB_BIN/xcodebuild" <<EOF
#!/bin/bash
echo "INVOKED \$*" >>"$XCODEBUILD_MARKER"
exit 0
EOF
chmod +x "$STUB_BIN/xcodebuild"

make_archive_tree() {
  local archive="$1" src_app="$2"
  rm -rf "$archive"
  mkdir -p "$archive/Products/Applications"
  cp -R "$src_app" "$archive/Products/Applications/RunSpecimen.app"
}

run_export_expect_block() {
  local label="$1"
  shift
  rm -f "$XCODEBUILD_MARKER"
  set +e
  # Use env(1): VAR=val from "$@" are not assignments after expansion.
  OUT="$(
    env PATH="$STUB_BIN:$PATH" "$@" "$EXPORT_SH" 2>&1
  )"
  RC=$?
  set -e
  [[ "$RC" -ne 0 ]] || { echo "FAIL: export_mas should block ($label)" >&2; echo "$OUT" >&2; exit 1; }
  [[ ! -f "$XCODEBUILD_MARKER" ]] \
    || { echo "FAIL: xcodebuild -exportArchive was invoked before gate failure ($label)" >&2; cat "$XCODEBUILD_MARKER" >&2; exit 1; }
  echo "$OUT" | grep -Eqi 'STORE EXPORT BLOCKED|ERROR:|ad-hoc|Developer ID|TeamIdentifier unset|RS_ARCHIVE_APP|export-gate bypass|test-only' \
    || { echo "FAIL: $label missing block evidence" >&2; echo "$OUT" >&2; exit 1; }
  echo "OK export_mas pre-xcodebuild refuse: $label"
}

echo "==> gate refuses RS_ARCHIVE_APP that does not match RS_ARCHIVE_PATH"
MISMATCH_ARCHIVE="$TMP/mismatch-gate.xcarchive"
make_archive_tree "$MISMATCH_ARCHIVE" "$ADHOC_APP"
codesign --force --sign - "$MISMATCH_ARCHIVE/Products/Applications/RunSpecimen.app/Contents/Resources/RunSpecimenEngine/runspecimen" >/dev/null 2>&1
codesign --force --sign - "$MISMATCH_ARCHIVE/Products/Applications/RunSpecimen.app" >/dev/null 2>&1
set +e
OUT="$(
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  RS_ARCHIVE_PATH="$MISMATCH_ARCHIVE" \
  RS_ARCHIVE_APP="$DIST_APP" \
  RS_ALLOW_TEST_CODESIGN_DV=1 \
  RS_TEST_CODESIGN_DV_APP_FILE="$TMP/dv-app-dist.txt" \
  RS_TEST_CODESIGN_DV_HELPER_FILE="$TMP/dv-helper-dist.txt" \
  "$GATE" 2>&1
)"
RC=$?
set -e
[[ "$RC" -ne 0 ]] || { echo "FAIL: mismatched RS_ARCHIVE_APP should block gate" >&2; echo "$OUT" >&2; exit 1; }
echo "$OUT" | grep -Eqi 'export-gate bypass|!= app in RS_ARCHIVE_PATH' \
  || { echo "FAIL: expected bypass refusal" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: gate refused mismatched RS_ARCHIVE_APP vs RS_ARCHIVE_PATH"

echo "==> export_mas refuses ad-hoc archive before xcodebuild -exportArchive"
ADHOC_ARCHIVE="$TMP/adhoc.xcarchive"
make_archive_tree "$ADHOC_ARCHIVE" "$ADHOC_APP"
# Re-sign after copy (cp can invalidate).
codesign --force --sign - "$ADHOC_ARCHIVE/Products/Applications/RunSpecimen.app/Contents/Resources/RunSpecimenEngine/runspecimen" >/dev/null 2>&1
codesign --force --sign - "$ADHOC_ARCHIVE/Products/Applications/RunSpecimen.app" >/dev/null 2>&1
run_export_expect_block "ad-hoc-archive" \
  RS_ARCHIVE_PATH="$ADHOC_ARCHIVE" \
  RS_EXPORT_DIR="$TMP/export-out-adhoc" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES"

echo "==> export_mas refuses unsigned/Developer ID–shaped archive via real codesign (no fixtures)"
DEVID_ARCHIVE="$TMP/devid.xcarchive"
make_archive_tree "$DEVID_ARCHIVE" "$DEVID_APP"
run_export_expect_block "developer-id-archive-real-codesign" \
  RS_ARCHIVE_PATH="$DEVID_ARCHIVE" \
  RS_EXPORT_DIR="$TMP/export-out-devid" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES"

echo "==> export_mas refuses Distribution-looking RS_ARCHIVE_APP override with ad-hoc archive (bypass)"
# Good/fixture-looking app path + bad archive must not reach xcodebuild.
run_export_expect_block "mismatched-archive-app-bypass" \
  RS_ARCHIVE_PATH="$ADHOC_ARCHIVE" \
  RS_ARCHIVE_APP="$DIST_APP" \
  RS_EXPORT_DIR="$TMP/export-out-bypass" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES"

echo "==> export_mas refuses RS_TEST_CODESIGN_DV_* on production export path"
run_export_expect_block "test-codesign-fixtures-refused" \
  RS_ARCHIVE_PATH="$ADHOC_ARCHIVE" \
  RS_EXPORT_DIR="$TMP/export-out-fixtures" \
  RS_EXPORT_OPTIONS_PLIST="$EXPORT_PLIST" \
  RS_SIGN_IDENTITY="Apple Distribution: Fixture ($TEAM)" \
  RS_NOTARY_TEAM_ID="$TEAM" \
  RS_PROFILE_SEARCH_DIRS="$PROFILES" \
  RS_TEST_CODESIGN_DV_APP_FILE="$TMP/dv-app-dist.txt" \
  RS_TEST_CODESIGN_DV_HELPER_FILE="$TMP/dv-helper-dist.txt"

echo "==> default host gate still fail-closed without Apple Distribution / RS_ARCHIVE_APP"
set +e
OUT="$("$GATE" 2>&1)"
RC=$?
set -e
# Host typically lacks RS_ARCHIVE_APP and/or Apple Distribution.
if [[ "$RC" -eq 0 ]]; then
  echo "NOTE: host gate opened (unexpected without archive+certs) — inspect:" >&2
  echo "$OUT" | tail -10 >&2
  exit 1
fi
echo "$OUT" | grep -q 'STORE EXPORT BLOCKED' \
  || { echo "FAIL: default gate should BLOCK" >&2; echo "$OUT" >&2; exit 1; }
echo "OK: default gate blocked"

echo "STORE EXPORT GATE TESTS OK"
