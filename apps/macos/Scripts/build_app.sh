#!/usr/bin/env bash
# Build a runnable RunSpecimen.app without requiring a full Xcode.app install.
# Archive / notarization / Mac App Store upload still need Xcode + signing identities.
# See NOTARIZATION.md and Scripts/sign_and_notarize.sh for Developer ID ship path.
#
# Prefers SwiftPM when available; falls back to single-module swiftc (CLT-friendly).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
APP="$BUILD/RunSpecimen.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RES="$CONTENTS/Resources"
HELPERS_OUT="$CONTENTS/Helpers"
SDK="$(xcrun --show-sdk-path)"
TARGET="${RS_TARGET:-arm64-apple-macosx14.0}"
ENTITLEMENTS="${RS_ENTITLEMENTS:-$ROOT/Entitlements/RunSpecimen.developer-id.entitlements}"

mkdir -p "$MACOS" "$RES" "$HELPERS_OUT"
rm -f "$MACOS/RunSpecimen"

compile_with_swiftc() {
  local SOURCES=()
  while IFS= read -r -d '' f; do
    SOURCES+=("$f")
  done < <(find "$ROOT/Sources/RunSpecimenCore" "$ROOT/Sources/RunSpecimenApp" -name '*.swift' -print0 | sort -z)
  echo "Compiling ${#SOURCES[@]} Swift sources via swiftc…"
  swiftc -parse-as-library \
    -sdk "$SDK" \
    -target "$TARGET" \
    -O \
    "${SOURCES[@]}" \
    -o "$MACOS/RunSpecimen"
}

if swift package --package-path "$ROOT" describe >/dev/null 2>&1; then
  echo "Building via SwiftPM (release)…"
  if swift build -c release --package-path "$ROOT" --product RunSpecimen; then
    BIN_DIR="$(swift build -c release --package-path "$ROOT" --show-bin-path)"
    cp "$BIN_DIR/RunSpecimen" "$MACOS/RunSpecimen"
    chmod +x "$MACOS/RunSpecimen"
  else
    echo "SwiftPM build failed; falling back to swiftc…"
    compile_with_swiftc
  fi
else
  echo "SwiftPM unavailable (CLT-only hosts); using swiftc…"
  compile_with_swiftc
fi

chmod +x "$MACOS/RunSpecimen"

cp "$ROOT/Resources/Info.plist" "$CONTENTS/Info.plist"
cp "$ROOT/Resources/PrivacyInfo.xcprivacy" "$RES/PrivacyInfo.xcprivacy"

# ADR-002: stage Helpers into the bundle when a payload exists.
STAGED="$ROOT/Helpers/payload/runspecimen"
if [[ -x "$STAGED" ]]; then
  cp -f "$STAGED" "$HELPERS_OUT/runspecimen"
  chmod +x "$HELPERS_OUT/runspecimen"
  echo "Bundled helper: $HELPERS_OUT/runspecimen"
else
  # Keep Contents/Helpers present so packaging paths stay stable.
  cp "$ROOT/Helpers/README.md" "$HELPERS_OUT/README.md"
  echo "No staged helper (Helpers/payload/runspecimen). Contents/Helpers reserved — see Scripts/stage_helper.sh"
fi

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
echo "Helper staging: ./Scripts/stage_helper.sh"
echo "Notarize (when certs exist): ./Scripts/check_signing_identity.sh && ./Scripts/sign_and_notarize.sh all"
