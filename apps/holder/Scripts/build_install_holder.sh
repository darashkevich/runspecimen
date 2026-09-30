#!/bin/bash
# Build, Developer-ID-sign, and install the separate RunSpecimen Holder app.
# Does not touch /Applications/RunSpecimen.app. Does not notarize.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
HOLDER_SRC="$ROOT/apps/holder"
BUILD="${HOLDER_BUILD_DIR:-/tmp/rs-holder-build}"
APP_NAME="RunSpecimen Holder.app"
INSTALL_PATH="/Applications/${APP_NAME}"
IDENTITY="Developer ID Application: YAHOR DARASHKEVICH (UN6KF8636A)"
TEAM="UN6KF8636A"
BUNDLE_ID="com.darashkevich.runspecimen.holder"
STORE_MTIME_EXPECTED="2026-09-26 13:56:03"

confirm_store_mtime() {
  local got
  got="$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" /Applications/RunSpecimen.app)"
  if [[ "$got" != "$STORE_MTIME_EXPECTED" ]]; then
    echo "REFUSING: /Applications/RunSpecimen.app mtime is $got (expected $STORE_MTIME_EXPECTED)" >&2
    exit 3
  fi
}

confirm_store_mtime

if [[ -e "$INSTALL_PATH" ]]; then
  echo "REFUSING: $INSTALL_PATH already exists; will not overwrite an unknown app" >&2
  exit 3
fi

if ! security find-identity -p codesigning -v | grep -F "$IDENTITY" >/dev/null; then
  echo "REFUSING: missing codesigning identity: $IDENTITY" >&2
  security find-identity -p codesigning -v >&2 || true
  exit 3
fi

rm -rf "$BUILD"
mkdir -p "$BUILD/bin" "$BUILD/$APP_NAME/Contents/MacOS" \
  "$BUILD/$APP_NAME/Contents/Resources/Python" \
  "$BUILD/$APP_NAME/Contents/Library/LaunchDaemons"

# Compile GUI app and daemon (arm64)
xcrun swiftc -O -parse-as-library -target arm64-apple-macos14.0 \
  -framework AppKit -framework SwiftUI -framework ServiceManagement \
  -o "$BUILD/bin/RunSpecimenHolder" \
  "$HOLDER_SRC/Sources/RunSpecimenHolderApp/main.swift"

xcrun swiftc -O -target arm64-apple-macos14.0 \
  -framework Foundation -framework Security \
  -o "$BUILD/bin/RunSpecimenHolderDaemon" \
  "$HOLDER_SRC/Sources/RunSpecimenHolderDaemon/main.swift"

cp "$BUILD/bin/RunSpecimenHolder" "$BUILD/$APP_NAME/Contents/MacOS/RunSpecimenHolder"
cp "$BUILD/bin/RunSpecimenHolderDaemon" "$BUILD/$APP_NAME/Contents/MacOS/RunSpecimenHolderDaemon"
cp "$HOLDER_SRC/Resources/Info.plist" "$BUILD/$APP_NAME/Contents/Info.plist"
cp "$HOLDER_SRC/Resources/LaunchDaemons/com.darashkevich.runspecimen.holder.daemon.plist" \
  "$BUILD/$APP_NAME/Contents/Library/LaunchDaemons/"

# Bundle Python package sources (software-test-double OFF path uses holder_daemon)
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT/src/runspecimen/" "$BUILD/$APP_NAME/Contents/Resources/Python/runspecimen/"

ENTITLEMENTS="$HOLDER_SRC/Entitlements/RunSpecimenHolder.entitlements"

# Sign nested daemon first, then the app bundle. Hardened runtime. No get-task-allow.
# Skip --timestamp here: notarization is not authorized, and Apple's timestamp
# server can hang this unattended install. Offline Developer ID signatures remain valid.
codesign --force --options runtime \
  --sign "$IDENTITY" \
  --keychain "$HOME/Library/Keychains/login.keychain-db" \
  --entitlements "$ENTITLEMENTS" \
  "$BUILD/$APP_NAME/Contents/MacOS/RunSpecimenHolderDaemon"

codesign --force --options runtime \
  --sign "$IDENTITY" \
  --keychain "$HOME/Library/Keychains/login.keychain-db" \
  --entitlements "$ENTITLEMENTS" \
  "$BUILD/$APP_NAME"

codesign --verify --deep --strict --verbose=4 "$BUILD/$APP_NAME"
codesign -dv --verbose=4 "$BUILD/$APP_NAME" 2>&1 | tee "$BUILD/codesign-app.txt"
codesign -d --entitlements :- "$BUILD/$APP_NAME" 2>/dev/null | tee "$BUILD/entitlements-app.xml" || true
codesign -dv --verbose=4 "$BUILD/$APP_NAME/Contents/MacOS/RunSpecimenHolderDaemon" 2>&1 | tee "$BUILD/codesign-daemon.txt"
codesign -d --entitlements :- "$BUILD/$APP_NAME/Contents/MacOS/RunSpecimenHolderDaemon" 2>/dev/null | tee "$BUILD/entitlements-daemon.xml" || true

# Install by copying the signed separate product only
ditto "$BUILD/$APP_NAME" "$INSTALL_PATH"
codesign --verify --deep --strict "$INSTALL_PATH"

confirm_store_mtime

# Register via launching the app briefly; may require System Settings approval
open "$INSTALL_PATH"
sleep 2

confirm_store_mtime

echo "INSTALLED=$INSTALL_PATH"
echo "BUNDLE_ID=$BUNDLE_ID"
echo "IDENTITY=$IDENTITY"
echo "STORE_MTIME=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" /Applications/RunSpecimen.app)"
