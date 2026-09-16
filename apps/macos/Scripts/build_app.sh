#!/usr/bin/env bash
# Build a runnable RunSpecimen.app without requiring a full Xcode.app install.
# Mac App Store Archive / upload still need full Xcode + Apple Distribution certs.
# See APP_STORE.md, RELEASE_CHECKLIST.md, and Scripts/sign_and_notarize.sh.
#
# Helper packaging:
#   ./Scripts/build_app.sh                  # uses Helpers/payload if already staged
#   ./Scripts/build_app.sh --from-src       # host-Python package tree (local / CI)
#   ./Scripts/build_app.sh --frozen-helper  # try PyInstaller; fall back to --from-src
#   ./Scripts/build_app.sh --mas            # MAS-first: frozen helper REQUIRED (fail closed)
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
CHANNEL="${RS_DISTRIBUTION_CHANNEL:-local}"
STAGE_FROM_SRC=0
STAGE_FROZEN=0
MAS_MODE=0
REQUIRE_HELPER=0

usage() {
  cat <<'EOF'
Usage: ./Scripts/build_app.sh [--from-src] [--frozen-helper] [--mas] [-h]

  (default)         Compile app; copy Helpers/payload into Contents/Helpers if present
  --from-src        Stage Apache-2.0 package tree (host Python) then build — local/CI
  --frozen-helper   Prefer PyInstaller freeze; fall back to --from-src if unavailable
  --mas             Mac App Store packaging path (PRIMARY ship target):
                      * Entitlements/RunSpecimen.mas.entitlements
                      * RSDistributionChannel=mas
                      * Frozen Mach-O helper REQUIRED (no host Python; fail closed)
                      * Fail if helper missing after freeze
  -h                Show help

Environment:
  RS_FREEZE_HELPER=1           Prefer freeze (same as --frozen-helper unless --mas)
  RS_DISTRIBUTION_CHANNEL=…    Override channel stamp (mas|developer-id|local)
  RS_ENTITLEMENTS=path         Override entitlements plist
  RS_REQUIRE_HELPER=1          Fail if Contents/Helpers/runspecimen not staged

CI smoke stays on --from-src. Store submissions MUST use --mas.
See Helpers/README.md, APP_STORE.md, RELEASE_CHECKLIST.md.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-src) STAGE_FROM_SRC=1; shift ;;
    --frozen-helper) STAGE_FROZEN=1; shift ;;
    --mas) MAS_MODE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "${RS_FREEZE_HELPER:-0}" == "1" && "$MAS_MODE" -eq 0 ]]; then
  STAGE_FROZEN=1
fi
if [[ "${RS_REQUIRE_HELPER:-0}" == "1" ]]; then
  REQUIRE_HELPER=1
fi

if [[ "$MAS_MODE" -eq 1 ]]; then
  CHANNEL="mas"
  ENTITLEMENTS="$ROOT/Entitlements/RunSpecimen.mas.entitlements"
  STAGE_FROZEN=1
  STAGE_FROM_SRC=0
  REQUIRE_HELPER=1
  echo "==> MAS channel: frozen helper required (fail closed); entitlements=$(basename "$ENTITLEMENTS")"
fi

if [[ -n "${RS_DISTRIBUTION_CHANNEL:-}" && "$MAS_MODE" -eq 0 ]]; then
  CHANNEL="$RS_DISTRIBUTION_CHANNEL"
fi

if [[ "$STAGE_FROZEN" -eq 1 && "$STAGE_FROM_SRC" -eq 1 ]]; then
  echo "Use either --frozen-helper/--mas or --from-src, not both." >&2
  exit 2
fi

prepare_helper_payload() {
  if [[ "$MAS_MODE" -eq 1 ]]; then
    echo "==> --mas: freezing self-contained helper (no --from-src fallback)"
    local freeze_log freeze_rc=0
    freeze_log="$(mktemp -t rs-freeze.XXXXXX)"
    set +e
    RS_FREEZE_HELPER=1 RS_MAS_BUILD=1 "$ROOT/Scripts/freeze_helper.sh" --enable --verify --require >"$freeze_log" 2>&1
    freeze_rc=$?
    set -e
    cat "$freeze_log"
    if [[ "$freeze_rc" -ne 0 ]] || ! grep -q "Staged frozen helper:" "$freeze_log"; then
      rm -f "$freeze_log"
      echo "ERROR: MAS build requires a frozen Mach-O helper. Install PyInstaller and retry:" >&2
      echo "  python3 -m pip install --user 'pyinstaller>=6'" >&2
      echo "  ./Scripts/build_app.sh --mas" >&2
      exit 1
    fi
    rm -f "$freeze_log"
    echo "==> Using frozen helper payload for MAS"
    return 0
  fi
  if [[ "$STAGE_FROZEN" -eq 1 ]]; then
    echo "==> --frozen-helper: attempting optional PyInstaller freeze"
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

# Info.plist with channel stamp (do not mutate the source template permanently).
cp "$ROOT/Resources/Info.plist" "$CONTENTS/Info.plist"
/usr/libexec/PlistBuddy -c "Set :RSDistributionChannel $CHANNEL" "$CONTENTS/Info.plist" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :RSDistributionChannel string $CHANNEL" "$CONTENTS/Info.plist"

cp "$ROOT/Resources/PrivacyInfo.xcprivacy" "$RES/PrivacyInfo.xcprivacy"

# App icon (marketplace brand assets — opaque RGB, not pre-rounded).
if [[ -f "$ROOT/Resources/AppIcon.icns" ]]; then
  if cp -X /etc/hosts /tmp/.rs-cp-x-test 2>/dev/null; then
    CP_ICON=(cp -X)
    rm -f /tmp/.rs-cp-x-test
  else
    CP_ICON=(cp)
  fi
  "${CP_ICON[@]}" -f "$ROOT/Resources/AppIcon.icns" "$RES/AppIcon.icns"
  echo "Bundled app icon: $RES/AppIcon.icns"
else
  echo "WARNING: Resources/AppIcon.icns missing — Dock/Finder will show generic icon." >&2
fi
if [[ -f "$ROOT/Resources/AppIcon-1024.png" ]]; then
  cp -f "$ROOT/Resources/AppIcon-1024.png" "$RES/AppIcon-1024.png" 2>/dev/null || true
fi

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
  "${CP[@]}" "$ROOT/Helpers/README.md" "$HELPERS_OUT/README.md"
  echo "No staged helper (Helpers/payload/runspecimen). Contents/Helpers reserved — see Scripts/stage_helper.sh"
fi

if [[ "$REQUIRE_HELPER" -eq 1 ]]; then
  if [[ ! -x "$HELPERS_OUT/runspecimen" ]]; then
    echo "ERROR: helper required but missing at $HELPERS_OUT/runspecimen (fail closed)." >&2
    exit 1
  fi
  if [[ "$MAS_MODE" -eq 1 ]]; then
    if [[ -d "$HELPERS_OUT/lib" ]]; then
      echo "ERROR: MAS build must not ship host-Python package-tree lib/ — freeze failed?" >&2
      exit 1
    fi
    if ! file "$HELPERS_OUT/runspecimen" | grep -q 'Mach-O'; then
      echo "ERROR: MAS helper must be a Mach-O frozen binary, not a shell launcher." >&2
      file "$HELPERS_OUT/runspecimen" >&2 || true
      exit 1
    fi
  fi
fi

# Clear Finder/Box xattrs that break codesign on cloud-synced trees.
clear_codesign_xattrs() {
  xattr -cr "$APP" 2>/dev/null || true
  find "$APP" -exec xattr -c {} + 2>/dev/null || true
  find "$APP" \( -name '._*' -o -name '.DS_Store' \) -delete 2>/dev/null || true
  command -v dot_clean >/dev/null 2>&1 && dot_clean -m "$APP" 2>/dev/null || true
}
clear_codesign_xattrs

# Nested / outer signing.
# - --from-src (package tree under Helpers/lib): --deep seals nested files; shell
#   launcher stays shell-smoke runnable.
# - Frozen Mach-O helper (MAS / --frozen-helper): NEVER stamp app entitlements onto
#   the helper via --deep. Sign helper first with RunSpecimen.helper.entitlements
#   (app-sandbox + inherit) via sign_nested_helper.sh, then seal the .app (no --deep).
#   Inherit-signed helpers exit non-zero when launched from an unsandboxed shell —
#   version gates run on Helpers/payload BEFORE this step.
# - Identity: resolve_codesign_identity.sh (Apple Distribution when present; ad-hoc
#   "-" only for local smoke, clearly labeled). Store export still needs Yahor's certs.
sign_bundle() {
  local helper="$HELPERS_OUT/runspecimen"
  clear_codesign_xattrs
  if [[ -x "$helper" ]] && file "$helper" | grep -q 'Mach-O'; then
    # Pre-sign version gate (fail closed) against the staged payload / helper copy.
    local ver
    ver="$("$helper" --version 2>&1)" || {
      # If already inherit-signed from a prior run, gate via payload instead.
      ver="$("$ROOT/Helpers/payload/runspecimen" --version 2>&1)" || {
        echo "ERROR: cannot read helper version (helper + payload both failed)" >&2
        exit 1
      }
    }
    echo "Helper pre-sign --version → $ver"
    if [[ "$MAS_MODE" -eq 1 ]]; then
      local repo_ver
      repo_ver="$(
        python3 -c 'import pathlib,re,sys; t=pathlib.Path(sys.argv[1],"src/runspecimen/__init__.py").read_text(); m=re.search(r"__version__\s*=\s*\"([^\"]+)\"", t); assert m; print(m.group(1))' \
          "$(cd "$ROOT/../.." && pwd)"
      )"
      echo "$ver" | grep -F "$repo_ver" >/dev/null || {
        echo "ERROR: MAS helper version must match repo $repo_ver (got: $ver)" >&2
        exit 1
      }
    fi
    "$ROOT/Scripts/sign_nested_helper.sh" "$helper"
    # Seal app without --deep so helper keeps inherit entitlements.
    local resolve_out identity mode
    resolve_out="$("$ROOT/Scripts/resolve_codesign_identity.sh")"
    identity="$(printf '%s\n' "$resolve_out" | awk -F= '/^IDENTITY=/{print substr($0,10); exit}')"
    mode="$(printf '%s\n' "$resolve_out" | awk -F= '/^MODE=/{print $2; exit}')"
    if [[ "$mode" == "adhoc" || "$identity" == "-" ]]; then
      echo "AD-HOC app signing (local smoke only; TeamIdentifier unset)." >&2
      codesign --force --sign - --entitlements "$ENTITLEMENTS" "$APP"
    else
      echo "Signing app with identity ($mode): $identity"
      codesign --force --options runtime --timestamp \
        --entitlements "$ENTITLEMENTS" \
        --sign "$identity" \
        "$APP"
    fi
    echo "Signed frozen helper with sandbox+inherit; app sealed ($mode)."
  else
    codesign --force --deep --sign - --entitlements "$ENTITLEMENTS" "$APP"
  fi
}

if command -v codesign >/dev/null 2>&1; then
  if sign_bundle 2>/tmp/rs-codesign.err; then
    echo "Signed with entitlements."
  else
    echo "Entitlements sign failed; retrying after xattr clear…"
    cat /tmp/rs-codesign.err >&2 || true
    clear_codesign_xattrs
    if sign_bundle; then
      echo "Signed with entitlements (retry)."
    else
      if [[ "$MAS_MODE" -eq 1 ]]; then
        echo "ERROR: MAS signing failed closed (no bare ad-hoc fallback)." >&2
        exit 1
      fi
      clear_codesign_xattrs
      codesign --force --deep --sign - "$APP" && echo "Ad-hoc signed without entitlements (local non-MAS fallback)." || true
    fi
  fi
fi

echo "Built: $APP"
echo "Channel: $CHANNEL"
echo "Entitlements source: $ENTITLEMENTS"
echo "Open with: open \"$APP\""
echo "MAS packaging: ./Scripts/build_app.sh --mas"
echo "Local helper:  ./Scripts/build_app.sh --from-src"
echo "Archive/upload (needs Xcode + Apple Distribution): see APP_STORE.md / RELEASE_CHECKLIST.md"
