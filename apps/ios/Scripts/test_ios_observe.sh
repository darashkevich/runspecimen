#!/usr/bin/env bash
# Run iOS Observe tests on macOS with an iOS Simulator.
# Requires Xcode and xcodegen.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IOS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$IOS_ROOT/../.." && pwd)"

echo "iOS Observe tests — project $IOS_ROOT"

if ! command -v xcodebuild &>/dev/null; then
  echo "SKIP: xcodebuild not found (requires macOS with Xcode)" >&2
  exit 3
fi

if ! command -v xcodegen &>/dev/null; then
  echo "Installing xcodegen via Homebrew..."
  brew install xcodegen
fi

cd "$IOS_ROOT"

echo "Regenerating Xcode project from project.yml..."
xcodegen generate --spec project.yml

if [[ "${RS_DIAG_VARIANT:-baseline}" == "instrumentation-off" ]]; then
  python3 - <<'SCHEME'
from pathlib import Path
import xml.etree.ElementTree as ET
for path in Path('RunSpecimenObserve.xcodeproj/xcshareddata/xcschemes').glob('RunSpecimenObserve.xcscheme'):
 tree=ET.parse(path);action=tree.getroot().find('TestAction')
 action.set('selectedDebuggerIdentifier','')
 action.set('selectedLauncherIdentifier','Xcode.IDEFoundation.Launcher.PosixSpawn')
 action.set('enableMainThreadChecker','NO')
 action.set('enableThreadPerformanceChecker','NO')
 env=action.find('EnvironmentVariables')
 if env is None:env=ET.SubElement(action,'EnvironmentVariables')
 ET.SubElement(env,'EnvironmentVariable',key='OS_ACTIVITY_DT_MODE',value='NO',isEnabled='YES')
 tree.write(path,encoding='utf-8',xml_declaration=True)
SCHEME
fi

echo "Building and testing ObserveSchemaTests..."

# Preserve the failing UI hierarchy/screenshots and Simulator diagnostics in CI.
# Local runs retain the existing disposable build behavior.
if [[ "${GITHUB_ACTIONS:-}" == "true" && -n "${RUNNER_TEMP:-}" ]]; then
  SCRATCH_DIR="$RUNNER_TEMP/ios-observe-results"
  mkdir -p "$SCRATCH_DIR"
else
  SCRATCH_DIR="$(mktemp -d)"
  trap 'rm -rf "$SCRATCH_DIR"' EXIT
fi
xcodebuild -version > "$SCRATCH_DIR/environment.txt"
xcrun simctl list devices available >> "$SCRATCH_DIR/environment.txt"

DESTINATION=$(xcrun simctl list devices available -j 2>/dev/null | \
  python3 -c "import json,sys; d=json.load(sys.stdin); \
  devs=[(r,n) for r,ds in d.get('devices',{}).items() for n in ds if 'iPhone' in n.get('name','') and n.get('isAvailable',False)]; \
  print(f\"platform=iOS Simulator,id={devs[0][1]['udid']}\") if devs else print('platform=iOS Simulator,name=Any iOS Simulator Device')" 2>/dev/null \
  || echo "platform=iOS Simulator,name=Any iOS Simulator Device")

echo "Using destination: $DESTINATION"

# Capture the test exit code before errexit can leave the script.
set +e
xcodebuild test \
  -project RunSpecimenObserve.xcodeproj \
  -scheme RunSpecimenObserve \
  -destination "$DESTINATION" \
  -derivedDataPath "$SCRATCH_DIR/DerivedData" \
  -resultBundlePath "$SCRATCH_DIR/TestResults.xcresult" \
  CODE_SIGN_IDENTITY="" \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGNING_ALLOWED=NO \
  2>&1 | tee "$SCRATCH_DIR/test.log" | while IFS= read -r line; do
    printf '%s\n' "$line"
    if [[ "$line" == *"error:"* || "$line" == *"failed"* || "$line" == *"Failed"* ]]; then
      if [[ ! -e "$SCRATCH_DIR/failure-capture-started" ]]; then
        touch "$SCRATCH_DIR/failure-capture-started"
        "$SCRIPT_DIR/qa2_failure_diagnostics.sh" "$SCRATCH_DIR/live-failure" &
      fi
    fi
  done

TEST_RC=${PIPESTATUS[0]}
set -e

if [[ "$TEST_RC" -ne 0 ]]; then
  echo "iOS tests FAILED with exit code $TEST_RC"
  exit 1
fi

EXECUTED_COUNT=$(grep -oE 'Executed [0-9]+ test' "$SCRATCH_DIR/test.log" | grep -oE '[0-9]+' | tail -1 || echo "0")
if [[ -z "$EXECUTED_COUNT" ]] || [[ "$EXECUTED_COUNT" -eq 0 ]]; then
  echo "iOS tests FAILED: zero tests executed (guard requires positive count)"
  exit 1
fi

if ! grep -q "Test Suite.*passed" "$SCRATCH_DIR/test.log" && ! grep -qE "Executed [0-9]+ tests?, with 0 failures" "$SCRATCH_DIR/test.log"; then
  echo "iOS tests FAILED: no passing test suite found"
  exit 1
fi

echo "iOS Observe tests PASSED ($EXECUTED_COUNT tests executed)"
