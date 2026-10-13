#!/usr/bin/env bash
# Development-signed Mac QA build.
#
# The Store package (Apple Distribution + "RunSpecimen MAS" profile) is not a
# local launch artifact. taskgated reports that profile as ineligible and kills
# the process before main. This script signs the same sandboxed app with the
# Apple Development certificate and writes it somewhere other than
# /Applications and the Store candidate directory.
#
# It does not upload, install over /Applications, or replace a Store archive.
# It does not strip App Sandbox or the other Mac App Store entitlements.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${RS_QA_DERIVED_DATA:-/private/tmp/rs-local-qa/DerivedData}"
TEAM="${RS_NOTARY_TEAM_ID:-UN6KF8636A}"
IDENTITY="${RS_QA_SIGN_IDENTITY:-Apple Development}"

case "$OUT_DIR" in
  /Applications|/Applications/*)
    echo "ERROR: QA output must not replace /Applications." >&2
    exit 1
    ;;
  *runspecimen-candidates*)
    echo "ERROR: QA output must not write into the Store candidate directory." >&2
    exit 1
    ;;
esac

case "$IDENTITY" in
  *"Apple Distribution"*|*"3rd Party Mac Developer"*|*"Developer ID"*)
    echo "ERROR: local QA refuses a distribution identity ($IDENTITY)." >&2
    echo "Use Apple Development. Store export stays on ./Scripts/archive_mas.sh." >&2
    exit 1
    ;;
esac

if ! security find-identity -v -p codesigning | grep -q "Apple Development"; then
  echo "ERROR: no Apple Development identity in the keychain." >&2
  echo "Install the UN6KF8636A Apple Development certificate, then re-run." >&2
  exit 1
fi

PROVISION_FLAGS=(-allowProvisioningUpdates)
if [[ "${RS_QA_REGISTER_DEVICE:-0}" == "1" ]]; then
  PROVISION_FLAGS+=(-allowProvisioningDeviceRegistration)
fi

echo "==> Local QA build"
echo "    identity: $IDENTITY"
echo "    team: $TEAM"
echo "    derived data: $OUT_DIR"
echo "    Store package and /Applications are left untouched."

mkdir -p "$(dirname "$OUT_DIR")"
xcodebuild \
  -project "$ROOT/RunSpecimen.xcodeproj" \
  -scheme RunSpecimen \
  -configuration Release \
  -destination 'platform=macOS,arch=arm64' \
  -derivedDataPath "$OUT_DIR" \
  CODE_SIGN_STYLE=Automatic \
  DEVELOPMENT_TEAM="$TEAM" \
  "CODE_SIGN_IDENTITY=$IDENTITY" \
  "${PROVISION_FLAGS[@]}" \
  build

APP="$OUT_DIR/Build/Products/Release/RunSpecimen.app"
test -d "$APP"

# The embed script always re-signs the helper. An incremental xcodebuild can
# skip the outer CodeSign step afterward, which leaves the bundle seal stale.
echo "==> Re-seal app after helper embed"
codesign --force --sign "$IDENTITY" --preserve-metadata=identifier,entitlements,flags,runtime "$APP"

echo "==> Verify development signature"
set +o pipefail
AUTHORITY="$(codesign -dv --verbose=4 "$APP" 2>&1 | awk -F= '/^Authority=/{print substr($0,11); exit}')"
set -o pipefail
echo "    authority: $AUTHORITY"
case "$AUTHORITY" in
  "Apple Development:"*) ;;
  *)
    echo "ERROR: expected Apple Development authority, got: $AUTHORITY" >&2
    exit 1
    ;;
esac
codesign --verify --deep --strict "$APP"
codesign --verify --strict "$APP/Contents/Resources/RunSpecimenEngine/runspecimen"

ENT="$(codesign -d --entitlements :- "$APP" 2>/dev/null || true)"
python3 - "$ENT" <<'PY'
import plistlib, sys
raw = sys.argv[1].encode()
# codesign may prefix a non-plist line.
start = raw.find(b"<?xml")
if start < 0:
    start = raw.find(b"<plist")
data = plistlib.loads(raw[start:])
if data.get("com.apple.security.app-sandbox") is not True:
    raise SystemExit("ERROR: App Sandbox is not enabled.")
if "com.apple.security.network.server" in data:
    raise SystemExit("ERROR: network.server entitlement is present.")
print("    sandbox=true network.server=absent")
PY
CHANNEL="$(/usr/libexec/PlistBuddy -c 'Print :RSDistributionChannel' "$APP/Contents/Info.plist")"
[[ "$CHANNEL" == "mas" ]] || {
  echo "ERROR: QA build must keep the Store channel (got $CHANNEL)." >&2
  exit 1
}

PROFILE="$APP/Contents/embedded.provisionprofile"
if [[ -f "$PROFILE" ]]; then
  DECODED="$(mktemp -t rs-qa-profile)"
  security cms -D -i "$PROFILE" >"$DECODED"
  python3 - "$DECODED" <<'PY'
import plistlib, sys
p = plistlib.load(open(sys.argv[1], "rb"))
kind = p.get("ProfileDistributionType")
if kind == "STORE":
    raise SystemExit("ERROR: embedded profile is a Mac App Store profile. Local QA cannot use it.")
devices = p.get("ProvisionedDevices") or []
print(f"    profile: {p.get('Name')} type={kind} devices={len(devices)}")
PY
  rm -f "$DECODED"
else
  echo "WARNING: Xcode embedded no provisioning profile (PROVISIONING_PROFILE_REQUIRED=NO)." >&2
  echo "WARNING: This Development signature can launch on a developer Mac. It is not the Store package." >&2
  echo "WARNING: A STORE profile must not be substituted. To register this Mac and request a development profile, re-run with RS_QA_REGISTER_DEVICE=1." >&2
fi

echo "QA APP: $APP"
echo "version: $(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist") ($(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP/Contents/Info.plist"))"
