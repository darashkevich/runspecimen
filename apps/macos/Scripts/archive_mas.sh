#!/usr/bin/env bash
# Produce a real xcodebuild Archive for the MAS path.
# Without Apple Distribution identities, archives with ad-hoc signing (-) to prove
# the project is structurally archivable — clearly labeled, with helper sandbox+inherit.
# Does not upload or Submit for Review.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"

ARCHIVE_PATH="${RS_ARCHIVE_PATH:-/tmp/runspecimen-mas/RunSpecimen.xcarchive}"
DERIVED="${RS_DERIVED_DATA:-/tmp/runspecimen-mas/DerivedData}"
SCHEME="RunSpecimen"
CONFIG="Release"

mkdir -p /tmp/runspecimen-mas
# Also keep a repo-local pointer for operators browsing apps/macos/build/
LOCAL_ARCHIVE_LINK="$ROOT/build/RunSpecimen.xcarchive"

echo "==> Xcode"
xcodebuild -version
xcode-select -p

echo "==> Ensure frozen Mach-O helper (rc engine from this tree)"
RS_FREEZE_HELPER=1 RS_MAS_BUILD=1 ./Scripts/freeze_helper.sh --enable --require --verify
HELPER_VER="$(Helpers/payload/runspecimen --version 2>&1)" || {
  echo "ERROR: Helpers/payload/runspecimen --version failed" >&2
  exit 1
}
echo "Frozen helper: $HELPER_VER"
REPO_VER=$(
  python3 -c 'import pathlib,re,sys; t=pathlib.Path(sys.argv[1],"src/runspecimen/__init__.py").read_text(); m=re.search(r"__version__\s*=\s*\"([^\"]+)\"", t); assert m; print(m.group(1))' \
    "$REPO"
)
echo "Repo engine: $REPO_VER"
echo "$HELPER_VER" | grep -F "$REPO_VER" >/dev/null || {
  echo "ERROR: frozen helper version does not match repo $REPO_VER" >&2
  echo "  helper: $HELPER_VER" >&2
  exit 1
}

echo "==> Ensure Xcode project"
./Scripts/generate_xcodeproj.sh
test -d "$ROOT/RunSpecimen.xcodeproj"
chmod +x "$ROOT/Scripts/"*.sh

mkdir -p "$ROOT/build"
# Box/cloud sync can leave sticky dirs; force-remove archive + derived data.
for path in "$ARCHIVE_PATH" "$DERIVED"; do
  if [[ -e "$path" ]]; then
    chmod -R u+w "$path" 2>/dev/null || true
    rm -rf "$path" 2>/dev/null || true
    if [[ -e "$path" ]]; then
      echo "WARNING: could not fully remove $path — continuing with clean subdirectory names" >&2
      stamp="$(date +%s)"
      if [[ "$path" == "$ARCHIVE_PATH" ]]; then
        ARCHIVE_PATH="$ROOT/build/RunSpecimen-${stamp}.xcarchive"
      else
        DERIVED="$ROOT/build/DerivedData-${stamp}"
      fi
    fi
  fi
done

IDENTITIES="$(security find-identity -v -p codesigning 2>/dev/null || true)"
echo "==> Codesigning identities:"
echo "$IDENTITIES"

RESOLVE_OUT="$("$ROOT/Scripts/resolve_codesign_identity.sh")"
IDENTITY="$(printf '%s\n' "$RESOLVE_OUT" | awk -F= '/^IDENTITY=/{print substr($0,10); exit}')"
MODE="$(printf '%s\n' "$RESOLVE_OUT" | awk -F= '/^MODE=/{print $2; exit}')"
echo "Resolved nested/app identity: IDENTITY=$IDENTITY MODE=$MODE"

SIGN_ARGS=()
SIGNING_MODE="$MODE"
ASSERT_ARGS=(--expected-version "$REPO_VER")
if [[ "$MODE" == "adhoc" || "$IDENTITY" == "-" ]]; then
  echo "AD-HOC ARCHIVE (local structural smoke only — TeamIdentifier unset)."
  echo "Apple Distribution identity not found; Store export still Yahor-only."
  SIGN_ARGS=(
    CODE_SIGN_STYLE=Manual
    CODE_SIGN_IDENTITY=-
    CODE_SIGNING_ALLOWED=YES
    AD_HOC_CODE_SIGNING_ALLOWED=YES
    DEVELOPMENT_TEAM=
  )
  SIGNING_MODE="ad-hoc"
  ASSERT_ARGS+=(--expect-adhoc)
elif echo "$IDENTITIES" | grep -Eq 'Apple Distribution|3rd Party Mac Developer Application|Apple Development'; then
  # Prefer Automatic when any Apple identity exists; operator still needs MAS profile for export.
  SIGN_ARGS=(CODE_SIGN_STYLE=Automatic)
  SIGNING_MODE="Automatic ($MODE)"
  if [[ -n "${RS_NOTARY_TEAM_ID:-}" ]]; then
    ASSERT_ARGS+=(--expect-team "$RS_NOTARY_TEAM_ID")
  fi
else
  SIGN_ARGS=(
    CODE_SIGN_STYLE=Manual
    "CODE_SIGN_IDENTITY=$IDENTITY"
    CODE_SIGNING_ALLOWED=YES
  )
  SIGNING_MODE="$MODE"
fi

echo "==> xcodebuild archive ($SIGNING_MODE)"
set +e
xcodebuild \
  -project "$ROOT/RunSpecimen.xcodeproj" \
  -scheme "$SCHEME" \
  -configuration "$CONFIG" \
  -destination "generic/platform=macOS" \
  -archivePath "$ARCHIVE_PATH" \
  -derivedDataPath "$DERIVED" \
  "${SIGN_ARGS[@]}" \
  archive
ARCHIVE_RC=$?
set -e

if [[ "$ARCHIVE_RC" -ne 0 ]]; then
  echo "ERROR: xcodebuild archive failed (exit $ARCHIVE_RC)." >&2
  echo "Signing mode attempted: $SIGNING_MODE" >&2
  exit "$ARCHIVE_RC"
fi

test -d "$ARCHIVE_PATH"
APP_IN_ARCHIVE="$ARCHIVE_PATH/Products/Applications/RunSpecimen.app"
test -x "$APP_IN_ARCHIVE/Contents/MacOS/RunSpecimen"
ENGINE="$APP_IN_ARCHIVE/Contents/Resources/RunSpecimenEngine/runspecimen"
test -x "$ENGINE"
file "$ENGINE" | grep -q 'Mach-O'
test -d "$APP_IN_ARCHIVE/Contents/Resources/RunSpecimenEngine/_internal" || {
  echo "ERROR: archived app missing onedir _internal (onefile is not App Sandbox–safe)" >&2
  exit 1
}
test ! -d "$APP_IN_ARCHIVE/Contents/Helpers/lib"
test ! -d "$APP_IN_ARCHIVE/Contents/Helpers/_internal"
CHANNEL="$(/usr/libexec/PlistBuddy -c "Print :RSDistributionChannel" "$APP_IN_ARCHIVE/Contents/Info.plist" 2>/dev/null || true)"
echo "RSDistributionChannel=${CHANNEL}"
test -f "$APP_IN_ARCHIVE/Contents/Resources/AppIcon.icns"
test -f "$APP_IN_ARCHIVE/Contents/Resources/PrivacyInfo.xcprivacy"

echo "==> fail-closed archive signing / entitlement / sandbox assertions"
./Scripts/assert_archive_signing.sh "$APP_IN_ARCHIVE" "${ASSERT_ARGS[@]}"

echo "==> codesign evidence (verbose)"
echo "----- APP codesign -dv --verbose=4 -----"
codesign -dv --verbose=4 "$APP_IN_ARCHIVE" 2>&1
echo "----- APP entitlements -----"
codesign -d --entitlements - "$APP_IN_ARCHIVE" 2>&1
echo "----- HELPER codesign -dv --verbose=4 -----"
codesign -dv --verbose=4 "$ENGINE" 2>&1
echo "----- HELPER entitlements -----"
codesign -d --entitlements - "$ENGINE" 2>&1

# Convenience symlink inside apps/macos/build for operators (best-effort).
mkdir -p "$ROOT/build"
rm -rf "$LOCAL_ARCHIVE_LINK" 2>/dev/null || true
ln -sfn "$ARCHIVE_PATH" "$LOCAL_ARCHIVE_LINK" 2>/dev/null || true

echo "==> Store export gate (fail closed — Apple Distribution + archived app required)"
EXPORT_DIR="${RS_EXPORT_DIR:-/tmp/runspecimen-mas/export-mas}"
EXPORT_PLIST="$ROOT/Config/ExportOptions.mas.plist"
EXPORT_GATE_LOG="/tmp/runspecimen-mas/export-gate.log"
set +e
RS_ARCHIVE_APP="$APP_IN_ARCHIVE" ./Scripts/assert_store_export_ready.sh >"$EXPORT_GATE_LOG" 2>&1
EXPORT_GATE_RC=$?
set -e
if [[ "$EXPORT_GATE_RC" -eq 0 ]]; then
  echo "Store export prerequisites present — running export_mas.sh"
  RS_ARCHIVE_PATH="$ARCHIVE_PATH" RS_ARCHIVE_APP="$APP_IN_ARCHIVE" RS_EXPORT_DIR="$EXPORT_DIR" ./Scripts/export_mas.sh
  EXPORT_RC=0
else
  echo "Store export BLOCKED (fail closed) without Apple Distribution + matching team + profile + Distribution-signed archive:"
  cat "$EXPORT_GATE_LOG" || true
  # Prove we refuse even if someone forces xcodebuild -exportArchive with Developer ID / placeholder team.
  rm -rf "$EXPORT_DIR"
  set +e
  xcodebuild -exportArchive \
    -archivePath "$ARCHIVE_PATH" \
    -exportPath "$EXPORT_DIR" \
    -exportOptionsPlist "$EXPORT_PLIST" \
    >"/tmp/runspecimen-mas/export-mas.log" 2>&1
  EXPORT_RC=$?
  set -e
  if [[ "$EXPORT_RC" -eq 0 ]]; then
    echo "ERROR: exportArchive succeeded despite assert_store_export_ready failure — refuse to treat as OK" >&2
    exit 1
  fi
  echo "exportArchive also failed (exit $EXPORT_RC) — consistent with fail-closed policy."
  EXPORT_RC="$EXPORT_GATE_RC"
fi

cat <<EOF

ARCHIVE OK
  archive:  $ARCHIVE_PATH
  link:     $LOCAL_ARCHIVE_LINK
  signing:  $SIGNING_MODE
  helper:   engine $REPO_VER (payload-gated; inherit-signed — not shell-exec'd)
  channel:  ${CHANNEL:-unknown}
  export:   gate_rc=$EXPORT_GATE_RC (upload still Yahor-only with Apple Distribution + ASC)

Do not Submit for Review or distribute this archive as production.
EOF
