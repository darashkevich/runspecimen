#!/usr/bin/env bash
# Build a runnable RunSpecimen.app without requiring a full Xcode.app install.
# Archive / notarization / Mac App Store upload still need Xcode + signing identities.
# See NOTARIZATION.md and Scripts/sign_and_notarize.sh for Developer ID ship path.
#
# Prefers SwiftPM when available; falls back to single-module swiftc (CLT-friendly).
#
# Helper packaging (optional):
#   ./Scripts/build_app.sh                  # uses Helpers/payload if already staged
#   ./Scripts/build_app.sh --from-src       # stage Apache-2.0 package tree, then build
#   ./Scripts/build_app.sh --frozen-helper  # try PyInstaller freeze; fall back to --from-src
#   RS_FREEZE_HELPER=1 ./Scripts/freeze_helper.sh --verify && ./Scripts/build_app.sh
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
STAGE_FROM_SRC=0
STAGE_FROZEN=0

usage() {
  cat <<'EOF'
Usage: ./Scripts/build_app.sh [--from-src] [--frozen-helper] [-h]

  (default)         Compile app; copy Helpers/payload into Contents/Helpers if present
  --from-src        Run stage_helper.sh --from-src --verify, then build
  --frozen-helper   Prefer PyInstaller freeze into Helpers/payload; if PyInstaller is
                    missing or freeze is disabled/skips, fall back to --from-src with
                    a clear log line. Does not require Developer ID.
  -h                Show help

Environment:
  RS_FREEZE_HELPER=1   Same intent as --frozen-helper when set before this script
                       (also used by freeze_helper.sh directly).

CI / default smoke stay on --from-src (or pre-staged payload). Freeze is optional.
See Helpers/README.md and RELEASE_CHECKLIST.md.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-src) STAGE_FROM_SRC=1; shift ;;
    --frozen-helper) STAGE_FROZEN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

# RS_FREEZE_HELPER=1 alone should also prefer the freeze-oriented staging path.
if [[ "${RS_FREEZE_HELPER:-0}" == "1" ]]; then
  STAGE_FROZEN=1
fi

if [[ "$STAGE_FROZEN" -eq 1 && "$STAGE_FROM_SRC" -eq 1 ]]; then
  echo "Use either --frozen-helper or --from-src, not both." >&2
  exit 2
fi

prepare_helper_payload() {
  if [[ "$STAGE_FROZEN" -eq 1 ]]; then
    echo "==> --frozen-helper: attempting optional PyInstaller freeze"
    # freeze_helper exits 0 when PyInstaller is absent (CI-safe). Detect a real
    # freeze via its success marker — not merely a leftover payload.
    local freeze_log freeze_rc=0
    freeze_log="$(mktemp -t rs-freeze.XXXXXX)"
    set +e
    RS_FREEZE_HELPER=1 "$ROOT/Scripts/freeze_helper.sh" --enable --verify >"$freeze_log" 2>&1
    freeze_rc=$?
    set -e
    cat "$freeze_log"
    if [[ "$freeze_rc" -eq 0 ]] && grep -q "Staged frozen helper:" "$freeze_log"; then
      rm -f "$freeze_log"
      echo "==> Using frozen helper payload (PyInstaller onefile)"
      return 0
    fi
    rm -f "$freeze_log"
    echo "==> freeze unavailable or skipped — falling back to stage_helper.sh --from-src"
    "$ROOT/Scripts/stage_helper.sh" --from-src --verify
    return 0
  fi
  if [[ "$STAGE_FROM_SRC" -eq 1 ]]; then
    echo "==> Staging helper via --from-src"
    "$ROOT/Scripts/stage_helper.sh" --from-src --verify
  fi
}

prepare_helper_payload

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
    # Avoid copying Finder/Box xattrs that break codesign (rsync -a can preserve them).
    if rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' --no-xattrs \
         "$STAGED_LIB/" "$HELPERS_OUT/lib/" 2>/dev/null; then
      :
    else
      rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$STAGED_LIB/" "$HELPERS_OUT/lib/"
    fi
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
clear_codesign_xattrs() {
  xattr -cr "$APP" 2>/dev/null || true
  find "$APP" -exec xattr -c {} + 2>/dev/null || true
  # Drop AppleDouble / resource-fork sidecars if present.
  find "$APP" \( -name '._*' -o -name '.DS_Store' \) -delete 2>/dev/null || true
  command -v dot_clean >/dev/null 2>&1 && dot_clean -m "$APP" 2>/dev/null || true
}
clear_codesign_xattrs

# Ad-hoc sign.
# - --from-src (package tree under Helpers/lib): use --deep so nested files seal.
# - Frozen Mach-O helper: --deep alone stamps *app* sandbox entitlements onto the
#   helper and breaks shell smoke (exit 133). Sign deep, then re-sign the helper
#   without sandbox entitlements, then reseal the .app (no --deep).
# Developer ID shipping uses inside-out signing in Scripts/sign_and_notarize.sh.
adhoc_sign() {
  local helper="$HELPERS_OUT/runspecimen"
  clear_codesign_xattrs
  if [[ -x "$helper" ]] && file "$helper" | grep -q 'Mach-O'; then
    codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP"
    codesign --force --sign - "$helper"
    codesign --force --sign - --entitlements "$ENTITLEMENTS" "$APP"
    echo "Ad-hoc signed frozen helper (sandbox stamp cleared; shell-smoke safe)."
  else
    codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP"
  fi
}

if command -v codesign >/dev/null 2>&1; then
  if adhoc_sign 2>/tmp/rs-codesign.err; then
    echo "Ad-hoc signed with entitlements."
  else
    echo "Entitlements sign failed; retrying after xattr clear…"
    cat /tmp/rs-codesign.err >&2 || true
    clear_codesign_xattrs
    if adhoc_sign; then
      echo "Ad-hoc signed with entitlements (retry)."
    else
      clear_codesign_xattrs
      codesign --force --deep --sign - "$APP" && echo "Ad-hoc signed without entitlements (fallback)." || true
    fi
  fi
fi

echo "Built: $APP"
echo "Entitlements source: $ENTITLEMENTS"
echo "Open with: open \"$APP\""
echo "Helper staging: ./Scripts/stage_helper.sh --from-src   # or: ./Scripts/build_app.sh --frozen-helper"
echo "Freeze e2e: RS_FREEZE_HELPER=1 ./Scripts/freeze_helper.sh --verify && ./Scripts/build_app.sh"
echo "Notarize (when certs exist): ./Scripts/check_signing_identity.sh && ./Scripts/sign_and_notarize.sh all"
echo "Operator checklist: RELEASE_CHECKLIST.md"
