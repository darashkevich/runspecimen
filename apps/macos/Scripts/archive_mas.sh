#!/usr/bin/env bash
# Produce a real xcodebuild Archive for the MAS path.
# Without Apple Distribution identities, archives with ad-hoc signing (-) to prove
# the project is structurally archivable. Does not upload or Submit for Review.
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
HELPER_VER="$(Helpers/payload/runspecimen --version 2>&1)"
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

SIGN_ARGS=(
  CODE_SIGN_STYLE=Manual
  CODE_SIGN_IDENTITY=-
  CODE_SIGNING_ALLOWED=YES
  AD_HOC_CODE_SIGNING_ALLOWED=YES
  DEVELOPMENT_TEAM=
)
SIGNING_MODE="ad-hoc"
if echo "$IDENTITIES" | grep -Eq 'Apple Distribution|3rd Party Mac Developer Application|Apple Development'; then
  # Prefer Automatic when any Apple identity exists; operator still needs MAS profile for export.
  SIGN_ARGS=(CODE_SIGN_STYLE=Automatic)
  SIGNING_MODE="Automatic"
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
test -x "$APP_IN_ARCHIVE/Contents/Helpers/runspecimen"
file "$APP_IN_ARCHIVE/Contents/Helpers/runspecimen" | grep -q 'Mach-O'
ARCH_HELPER_VER="$("$APP_IN_ARCHIVE/Contents/Helpers/runspecimen" --version 2>&1)"
echo "Archive helper --version → $ARCH_HELPER_VER"
echo "$ARCH_HELPER_VER" | grep -F "$REPO_VER" >/dev/null
CHANNEL="$(/usr/libexec/PlistBuddy -c "Print :RSDistributionChannel" "$APP_IN_ARCHIVE/Contents/Info.plist" 2>/dev/null || true)"
echo "RSDistributionChannel=${CHANNEL}"
test -f "$APP_IN_ARCHIVE/Contents/Resources/AppIcon.icns"
test -f "$APP_IN_ARCHIVE/Contents/Resources/PrivacyInfo.xcprivacy"

echo "==> codesign -dv (archive app)"
codesign -dv --verbose=2 "$APP_IN_ARCHIVE" 2>&1 | head -40 || true

# Convenience symlink inside apps/macos/build for operators (best-effort).
mkdir -p "$ROOT/build"
rm -rf "$LOCAL_ARCHIVE_LINK" 2>/dev/null || true
ln -sfn "$ARCHIVE_PATH" "$LOCAL_ARCHIVE_LINK" 2>/dev/null || true

echo "==> exportArchive probe (expected to fail without ASC/team)"
EXPORT_DIR="${RS_EXPORT_DIR:-/tmp/runspecimen-mas/export-mas}"
EXPORT_PLIST="$ROOT/Config/ExportOptions.mas.plist"
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
  echo "exportArchive succeeded unexpectedly — inspect $EXPORT_DIR"
else
  echo "exportArchive failed as expected without distribution certs/team (exit $EXPORT_RC)."
  tail -30 "/tmp/runspecimen-mas/export-mas.log" || true
fi

cat <<EOF

ARCHIVE OK
  archive:  $ARCHIVE_PATH
  link:     $LOCAL_ARCHIVE_LINK
  signing:  $SIGNING_MODE (adhoc / Sign to Run Locally when no Apple identity)
  helper:   $ARCH_HELPER_VER
  channel:  ${CHANNEL:-unknown}
  export:   exit $EXPORT_RC (upload still Yahor-only with Apple Distribution + ASC)

Do not Submit for Review or distribute this archive as production.
EOF
