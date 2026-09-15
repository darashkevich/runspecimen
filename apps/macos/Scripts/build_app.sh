#!/usr/bin/env bash
# Build a runnable RunSpecimen.app without requiring a full Xcode.app install.
# Archive / notarization / Mac App Store upload still need Xcode + signing identities.
# See NOTARIZATION.md and Scripts/sign_and_notarize.sh for Developer ID ship path.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
APP="$BUILD/RunSpecimen.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RES="$CONTENTS/Resources"
SDK="$(xcrun --show-sdk-path)"
TARGET="${RS_TARGET:-arm64-apple-macosx14.0}"
ENTITLEMENTS="${RS_ENTITLEMENTS:-$ROOT/Entitlements/RunSpecimen.developer-id.entitlements}"

mkdir -p "$MACOS" "$RES"
rm -f "$MACOS/RunSpecimen"

SOURCES=()
while IFS= read -r -d '' f; do
  SOURCES+=("$f")
done < <(find "$ROOT/Sources/RunSpecimenApp" -name '*.swift' -print0 | sort -z)

echo "Compiling ${#SOURCES[@]} Swift sources…"
swiftc -parse-as-library \
  -sdk "$SDK" \
  -target "$TARGET" \
  -O \
  "${SOURCES[@]}" \
  -o "$MACOS/RunSpecimen"

cp "$ROOT/Resources/Info.plist" "$CONTENTS/Info.plist"
cp "$ROOT/Resources/PrivacyInfo.xcprivacy" "$RES/PrivacyInfo.xcprivacy"

# Clear Finder/Box xattrs that break codesign on cloud-synced trees.
xattr -cr "$APP" 2>/dev/null || true

# Ad-hoc sign with entitlements when possible (Developer ID identity replaces this later).
if command -v codesign >/dev/null 2>&1; then
  if codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP"; then
    echo "Ad-hoc signed with entitlements."
  else
    echo "Entitlements sign failed; retrying after xattr clear…"
    xattr -cr "$APP" 2>/dev/null || true
    codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP" \
      || codesign --force --deep --sign - "$APP" || true
  fi
fi

echo "Built: $APP"
echo "Entitlements source: $ENTITLEMENTS"
echo "Open with: open \"$APP\""
echo "Notarize (when certs exist): ./Scripts/check_signing_identity.sh && ./Scripts/sign_and_notarize.sh all"
