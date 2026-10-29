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

SDK_VERSION=$(xcrun --sdk iphonesimulator --show-sdk-version)
SIMULATOR_ID=$(xcrun simctl list devices available -j | python3 "$SCRIPT_DIR/select_ios_simulator.py" "$SDK_VERSION")
xcrun simctl bootstatus "$SIMULATOR_ID" -b
DESTINATION="platform=iOS Simulator,id=$SIMULATOR_ID"

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
  ENABLE_MAIN_THREAD_CHECKER=NO \
  2>&1 | tee "$SCRATCH_DIR/test.log"

TEST_RC=${PIPESTATUS[0]}
set -e

if [[ "$TEST_RC" -ne 0 ]]; then
  echo "iOS tests FAILED with exit code $TEST_RC"
  DIAG_DIR="$SCRATCH_DIR/failure-diagnostics"
  mkdir -p "$DIAG_DIR"
  {
    date -u +%Y-%m-%dT%H:%M:%SZ
    uptime || true
    vm_stat || true
  } > "$DIAG_DIR/host-load.txt" 2>&1 || true
  if [[ -n "${SIMULATOR_ID:-}" ]]; then
    xcrun simctl spawn "$SIMULATOR_ID" launchctl list > "$DIAG_DIR/launchctl.txt" 2>&1 || true
    xcrun simctl spawn "$SIMULATOR_ID" ps -axo pid,stat,etime,pcpu,comm > "$DIAG_DIR/ps.txt" 2>&1 || true
    python3 - "$SIMULATOR_ID" "$DIAG_DIR/sim-log.txt" <<'PY' || true
import subprocess, sys
udid, dest = sys.argv[1], sys.argv[2]
cmd = [
    "xcrun", "simctl", "spawn", udid, "log", "show", "--last", "5m",
    "--predicate",
    'process == "RunSpecimenObserve" OR process == "SharingUIService" OR process == "ShareSheetUI" OR process == "SpringBoard" OR process == "testmanagerd"',
]
try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    open(dest, "w", encoding="utf-8").write(result.stdout + result.stderr)
except subprocess.TimeoutExpired as error:
    open(dest, "w", encoding="utf-8").write("log show truncated: %s\n" % error)
PY
  fi
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
