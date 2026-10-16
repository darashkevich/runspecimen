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

SCRATCH_DIR="$(mktemp -d)"
trap 'rm -rf "$SCRATCH_DIR"' EXIT

DESTINATION=$(xcrun simctl list devices available -j 2>/dev/null | \
  python3 -c "import json,sys; d=json.load(sys.stdin); \
  devs=[(r,n) for r,ds in d.get('devices',{}).items() for n in ds if 'iPhone' in n.get('name','') and n.get('isAvailable',False)]; \
  print(f\"platform=iOS Simulator,id={devs[0][1]['udid']}\") if devs else print('platform=iOS Simulator,name=Any iOS Simulator Device')" 2>/dev/null \
  || echo "platform=iOS Simulator,name=Any iOS Simulator Device")

echo "Using destination: $DESTINATION"

xcodebuild test \
  -project RunSpecimenObserve.xcodeproj \
  -scheme RunSpecimenObserve \
  -destination "$DESTINATION" \
  -derivedDataPath "$SCRATCH_DIR/DerivedData" \
  -resultBundlePath "$SCRATCH_DIR/TestResults.xcresult" \
  CODE_SIGN_IDENTITY="" \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGNING_ALLOWED=NO \
  2>&1 | tee "$SCRATCH_DIR/test.log"

TEST_RC=${PIPESTATUS[0]}

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
