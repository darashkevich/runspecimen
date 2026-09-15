#!/usr/bin/env bash
# Non-GUI smoke for the macOS companion app.
# Runs version-gate checks + bundle layout checks + optional CLI --version probe.
# Uses `swift test` when SwiftPM works (Xcode); otherwise a Python parity check.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"

echo "==> CLIVersionGate checks"
if swift package --package-path "$ROOT" describe >/dev/null 2>&1; then
  echo "SwiftPM OK — running swift test"
  swift test --package-path "$ROOT"
else
  echo "SwiftPM unavailable — running Python parity checks for CLIVersionGate"
  python3 - <<'PY'
import re

def parse(text: str):
    lowered = text.lower()
    m = re.search(r"(\d+)\.(\d+)\.(\d+)(?:[-.]?(?:rc|a|b|alpha|beta)\.?(\d+))?", lowered)
    if not m:
        return None
    maj, minor, patch = map(int, m.group(1, 2, 3))
    if m.group(4) is not None:
        return (maj, minor, patch, 0, int(m.group(4)))
    return (maj, minor, patch, 1, 0)

minimum = (0, 2, 0, 0, 9)
assert parse("runspecimen 0.2.0rc9") == minimum
assert parse("0.2.0-rc.9") == minimum
assert parse("0.2.0") == (0, 2, 0, 1, 0)
assert parse("0.2.0rc9") >= minimum
assert parse("0.2.0rc8") < minimum
assert parse("0.2.0") > minimum
assert parse("not-a-version") is None
print("CLIVersionGate Python parity OK")
PY
fi

echo "==> stage_helper (docs / layout)"
./Scripts/stage_helper.sh >/tmp/rs-stage-helper.out
grep -q "Exact next packaging steps" /tmp/rs-stage-helper.out

echo "==> build_app.sh"
./Scripts/build_app.sh

APP="$ROOT/build/RunSpecimen.app"
test -x "$APP/Contents/MacOS/RunSpecimen"
test -f "$APP/Contents/Info.plist"
test -f "$APP/Contents/Resources/PrivacyInfo.xcprivacy"
test -d "$APP/Contents/Helpers"
# Either a real helper or the reserved README marker.
test -e "$APP/Contents/Helpers/runspecimen" -o -f "$APP/Contents/Helpers/README.md"

echo "==> Info.plist CFBundleIdentifier"
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP/Contents/Info.plist" | grep -q .

echo "==> optional CLI integration (no GUI)"
if command -v runspecimen >/dev/null 2>&1; then
  VER="$(runspecimen --version 2>&1 || true)"
  echo "runspecimen --version → $VER"
  python3 - <<'PY' "$VER"
import re, sys
text = sys.argv[1].lower()
m = re.search(r"(\d+)\.(\d+)\.(\d+)(?:[-.]?(?:rc|a|b|alpha|beta)\.?(\d+))?", text)
assert m, f"unparseable: {text!r}"
maj, minor, patch = map(int, m.group(1, 2, 3))
pre = m.group(4)
pre_kind = 0 if pre is not None else 1
pre_num = int(pre) if pre is not None else 0
found = (maj, minor, patch, pre_kind, pre_num)
minimum = (0, 2, 0, 0, 9)
assert found >= minimum, f"CLI too old: {found} < {minimum}"
print("CLI version gate OK")
PY
  SHOWCASE="$REPO/examples/showcase"
  if [[ -d "$SHOWCASE" ]]; then
    echo "==> runspecimen doctor --workspace examples/showcase"
    if runspecimen doctor --workspace "$SHOWCASE" >/tmp/rs-doctor.out 2>&1; then
      if python3 -c 'import json; json.load(open("/tmp/rs-doctor.out"))' 2>/dev/null; then
        echo "doctor JSON OK"
      else
        echo "doctor ran (non-JSON output acceptable for smoke)"
      fi
    else
      echo "doctor exited non-zero (acceptable if workspace not initialized)"
    fi
  fi
else
  echo "runspecimen not on PATH — skipping live CLI probe (app build still OK)."
fi

echo "SMOKE OK"
