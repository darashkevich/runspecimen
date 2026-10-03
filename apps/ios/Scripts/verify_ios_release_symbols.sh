#!/bin/sh
# Shipping symbol gate. Does not install an iOS app and does not request
# provisioning updates. Fixture tests and a Debug positive control always run.
# On Darwin the shipping Observe Release product is built without signing and
# scanned. This is not device Release acceptance and not a Face ID proof.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest tests.test_nm_symbol_gate
python3 - "$root" <<'PY'
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "apps" / "ios" / "Scripts"))
import nm_symbol_gate as gate

with tempfile.TemporaryDirectory() as td:
    src = Path(td) / "debug_control.c"
    obj = Path(td) / "debug_control.o"
    src.write_text("void beforeFinalSignatureDecision(void) {}\n", encoding="utf-8")
    built = subprocess.run(["cc", "-c", str(src), "-o", str(obj)], check=False)
    if built.returncode != 0:
        raise SystemExit("cc unavailable for the Debug symbol control")
    try:
        gate.scan_path(obj)
    except gate.SymbolGateError as exc:
        if "beforeFinalSignatureDecision" not in str(exc):
            raise
    else:
        raise SystemExit("Debug control was not rejected")
    clean_src = Path(td) / "clean.c"
    clean_obj = Path(td) / "clean.o"
    clean_src.write_text("int shipping_ok(void){return 1;}\n", encoding="utf-8")
    subprocess.run(["cc", "-c", str(clean_src), "-o", str(clean_obj)], check=True)
    gate.scan_path(clean_obj)
print("ios symbol gate fixtures passed")
PY

if [ "$(uname)" != "Darwin" ]; then
  echo "shipping Observe product scan requires Darwin"
  exit 0
fi

scan_root=$(mktemp -d "${TMPDIR:-/tmp}/rs-ios-symbols.XXXXXX")
cleanup() {
  rm -rf "$scan_root"
}
trap cleanup EXIT

xcodebuild \
  -project "$root/apps/ios/RunSpecimenObserve.xcodeproj" \
  -scheme RunSpecimenObserve \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$scan_root/Release" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  build

xcodebuild \
  -project "$root/apps/ios/RunSpecimenObserve.xcodeproj" \
  -scheme RunSpecimenObserve \
  -configuration Debug \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$scan_root/Debug" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  build

python3 - "$root" "$scan_root" <<'PY'
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "apps" / "ios" / "Scripts"))
import nm_symbol_gate as gate

root = Path(sys.argv[2])

def machos(config: str) -> list[Path]:
    apps = [path for path in root.joinpath(config).rglob("RunSpecimenObserve.app") if path.is_dir()]
    if len(apps) != 1:
        raise SystemExit(f"{config} Observe app was not built: {apps}")
    app = apps[0]
    found = [path for path in app.rglob("*") if path.is_file() and path.suffix in {".dylib", ""}]
    binaries = []
    for path in found:
        if path.name.startswith("RunSpecimenObserve"):
            binaries.append(path)
    if not binaries:
        raise SystemExit(f"{config} Observe product was not built")
    return binaries

release_bins = machos("Release")
for path in release_bins:
    gate.scan_path(path)
rejected = False
for path in machos("Debug"):
    try:
        gate.scan_path(path)
    except gate.SymbolGateError as exc:
        if "beforeFinalSignatureDecision" not in str(exc):
            raise
        rejected = True
if not rejected:
    raise SystemExit("Debug Observe product was not rejected")
release = next(path for path in release_bins if path.suffix == "")
digest = hashlib.sha256(release.read_bytes()).hexdigest()
print(f"ios shipping Observe scan passed {release}")
print(f"unsigned release executable sha256 {digest}")
PY
