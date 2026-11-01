#!/usr/bin/env bash
# Unsigned / ad-hoc Release archive for CI and local structural smoke.
#
# This is not the upload binary. It never creates profiles, never talks to
# App Store Connect, and never enables automatic provisioning updates.
# It does not re-freeze the helper (call freeze_helper.sh / smoke first).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"

for arg in "$@"; do
  case "$arg" in
    *allowProvisioningUpdates*)
      echo "ERROR: allowProvisioningUpdates is forbidden" >&2
      exit 2
      ;;
  esac
done

ARCHIVE_PATH="${RS_UNSIGNED_ARCHIVE_PATH:-/tmp/runspecimen-unsigned/RunSpecimen.xcarchive}"
DERIVED="${RS_UNSIGNED_DERIVED_DATA:-/tmp/runspecimen-unsigned/DerivedData}"
SCHEME="RunSpecimen"
CONFIG="Release"

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "ERROR: xcodebuild is required for the unsigned Release archive" >&2
  exit 1
fi

test -d "$ROOT/RunSpecimen.xcodeproj" || {
  echo "ERROR: missing RunSpecimen.xcodeproj" >&2
  exit 1
}

HELPER="$ROOT/Helpers/payload/runspecimen"
test -x "$HELPER" || {
  echo "ERROR: Helpers/payload/runspecimen missing — freeze first (freeze_helper.sh --enable --require --verify)" >&2
  exit 1
}

HELPER_VER="$("$HELPER" --version 2>&1)" || {
  echo "ERROR: Helpers/payload/runspecimen --version failed" >&2
  exit 1
}
REPO_VER=$(
  python3 -c 'import pathlib,re,sys; t=pathlib.Path(sys.argv[1],"src/runspecimen/__init__.py").read_text(); m=re.search(r"__version__\s*=\s*\"([^\"]+)\"", t); assert m; print(m.group(1))' \
    "$REPO"
)
echo "Frozen helper: $HELPER_VER"
echo "Repo engine: $REPO_VER"
echo "$HELPER_VER" | grep -F "$REPO_VER" >/dev/null || {
  echo "ERROR: frozen helper version does not match repo $REPO_VER" >&2
  echo "  helper: $HELPER_VER" >&2
  exit 1
}

mkdir -p "$(dirname "$ARCHIVE_PATH")"
for path in "$ARCHIVE_PATH" "$DERIVED"; do
  if [[ -e "$path" ]]; then
    chmod -R u+w "$path" 2>/dev/null || true
    rm -rf "$path"
  fi
done

echo "==> xcodebuild archive (ad-hoc unsigned Release; CODE_SIGN_IDENTITY=-)"
xcodebuild \
  -project "$ROOT/RunSpecimen.xcodeproj" \
  -scheme "$SCHEME" \
  -configuration "$CONFIG" \
  -destination "generic/platform=macOS" \
  -archivePath "$ARCHIVE_PATH" \
  -derivedDataPath "$DERIVED" \
  CODE_SIGN_STYLE=Manual \
  CODE_SIGN_IDENTITY=- \
  CODE_SIGNING_ALLOWED=YES \
  AD_HOC_CODE_SIGNING_ALLOWED=YES \
  DEVELOPMENT_TEAM= \
  archive

test -d "$ARCHIVE_PATH"
APP_IN_ARCHIVE="$ARCHIVE_PATH/Products/Applications/RunSpecimen.app"
test -x "$APP_IN_ARCHIVE/Contents/MacOS/RunSpecimen"
ENGINE="$APP_IN_ARCHIVE/Contents/Resources/RunSpecimenEngine/runspecimen"
test -x "$ENGINE"
file "$ENGINE" | grep -q 'Mach-O'
test -d "$APP_IN_ARCHIVE/Contents/Resources/RunSpecimenEngine/_internal" || {
  echo "ERROR: archived app missing onedir _internal" >&2
  exit 1
}
test ! -d "$APP_IN_ARCHIVE/Contents/Helpers/lib"
test ! -d "$APP_IN_ARCHIVE/Contents/Helpers/_internal"
test -f "$APP_IN_ARCHIVE/Contents/Resources/AppIcon.icns"
test -f "$APP_IN_ARCHIVE/Contents/Resources/PrivacyInfo.xcprivacy"
test -f "$APP_IN_ARCHIVE/Contents/Resources/Assets.car" || {
  echo "ERROR: archived app missing Contents/Resources/Assets.car" >&2
  exit 1
}
python3 "$ROOT/Scripts/macos_privacy_gate.py" "$APP_IN_ARCHIVE"
python3 "$ROOT/Scripts/scan_required_reason_apis.py" --check "$APP_IN_ARCHIVE"

SHORT="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP_IN_ARCHIVE/Contents/Info.plist")"
BUILD="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP_IN_ARCHIVE/Contents/Info.plist")"
CHANNEL="$(/usr/libexec/PlistBuddy -c 'Print :RSDistributionChannel' "$APP_IN_ARCHIVE/Contents/Info.plist")"
ENC="$(/usr/libexec/PlistBuddy -c 'Print :ITSAppUsesNonExemptEncryption' "$APP_IN_ARCHIVE/Contents/Info.plist")"
test "$SHORT" = "0.1.6"
test "$BUILD" = "16"
test "$CHANNEL" = "mas"
test "$ENC" = "false"

APP_ENT="$(codesign -d --entitlements - "$APP_IN_ARCHIVE" 2>/dev/null || true)"
echo "$APP_ENT" | grep -q 'com.apple.security.app-sandbox' || {
  echo "ERROR: unsigned archive missing app-sandbox entitlement" >&2
  exit 1
}
if echo "$APP_ENT" | grep -q 'com.apple.security.network.server'; then
  echo "ERROR: rejected network.server entitlement remains in unsigned archive" >&2
  exit 1
fi
HELP_ENT="$(codesign -d --entitlements - "$ENGINE" 2>/dev/null || true)"
echo "$HELP_ENT" | grep -q 'com.apple.security.app-sandbox' || {
  echo "ERROR: helper missing app-sandbox entitlement" >&2
  exit 1
}
echo "$HELP_ENT" | grep -q 'com.apple.security.inherit' || {
  echo "ERROR: helper missing inherit entitlement" >&2
  exit 1
}

cat <<EOF

UNSIGNED RELEASE ARCHIVE OK
  archive:  $ARCHIVE_PATH
  signing:  ad-hoc CODE_SIGN_IDENTITY=-
  version:  $SHORT ($BUILD)
  helper:   engine $REPO_VER
  channel:  $CHANNEL

This archive is structural smoke only. Do not upload it.
Use docs/MACOS_APPSTORE_SUBMISSION.md for Yahor's signed upload.
EOF
