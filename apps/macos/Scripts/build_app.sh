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
STAGED_LIB="$ROOT/Helpers/payload/lib"
STAGED_NOTICE="$ROOT/Helpers/payload/NOTICE.txt"
# Clear previous helper artifacts so a README-only build cannot leave a stale binary.
rm -rf "$HELPERS_OUT/runspecimen" "$HELPERS_OUT/lib" "$HELPERS_OUT/NOTICE.txt" "$HELPERS_OUT/README.md"
# Prefer cp -X to avoid copying Finder/Box xattrs that break codesign.
if cp -X /etc/hosts /tmp/.rs-cp-x-test 2>/dev/null; then
  CP=(cp -X)
  rm -f /tmp/.rs-cp-x-test
else
  CP=(cp)
fi
if [[ -x "$STAGED" ]]; then
  "${CP[@]}" -f "$STAGED" "$HELPERS_OUT/runspecimen"
  chmod +x "$HELPERS_OUT/runspecimen"
  if [[ -d "$STAGED_LIB" ]]; then
    mkdir -p "$HELPERS_OUT/lib"
    rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$STAGED_LIB/" "$HELPERS_OUT/lib/"
  fi
  if [[ -f "$STAGED_NOTICE" ]]; then
    "${CP[@]}" -f "$STAGED_NOTICE" "$HELPERS_OUT/NOTICE.txt"
  fi
  echo "Bundled helper: $HELPERS_OUT/runspecimen"
  if [[ -d "$HELPERS_OUT/lib/runspecimen" ]]; then
    echo "Bundled package tree: $HELPERS_OUT/lib/runspecimen"
  fi
else
  # Keep Contents/Helpers present so packaging paths stay stable.
  "${CP[@]}" "$ROOT/Helpers/README.md" "$HELPERS_OUT/README.md"
  echo "No staged helper (Helpers/payload/runspecimen). Contents/Helpers reserved — see Scripts/stage_helper.sh"
fi

# Clear Finder/Box xattrs that break codesign on cloud-synced trees.
xattr -cr "$APP" 2>/dev/null || true
find "$APP" -exec xattr -c {} + 2>/dev/null || true

# Ad-hoc sign with entitlements when possible (Developer ID identity replaces this later).
if command -v codesign >/dev/null 2>&1; then
  if codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP" 2>/tmp/rs-codesign.err; then
    echo "Ad-hoc signed with entitlements."
  else
    echo "Entitlements sign failed; retrying after xattr clear…"
    cat /tmp/rs-codesign.err >&2 || true
    xattr -cr "$APP" 2>/dev/null || true
    find "$APP" -exec xattr -c {} + 2>/dev/null || true
    if codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP"; then
      echo "Ad-hoc signed with entitlements (retry)."
    else
      codesign --force --deep --sign - "$APP" && echo "Ad-hoc signed without entitlements (fallback)." || true
    fi
  fi
fi

echo "Built: $APP"
echo "Entitlements source: $ENTITLEMENTS"
echo "Open with: open \"$APP\""
echo "Helper staging: ./Scripts/stage_helper.sh"
echo "Notarize (when certs exist): ./Scripts/check_signing_identity.sh && ./Scripts/sign_and_notarize.sh all"
