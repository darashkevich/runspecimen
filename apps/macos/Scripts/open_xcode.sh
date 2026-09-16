#!/usr/bin/env bash
# Open / generate an Xcode project for MAS Archive. Fails clearly without Xcode.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d /Applications/Xcode.app ]]; then
  cat <<EOF >&2
open_xcode: full Xcode.app is required for Archive / App Store Connect upload.

This Mac appears CLT-only. Operator steps:
  1. Install Xcode from the Mac App Store
  2. sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
  3. xcodebuild -version   # must print Xcode …
  4. Re-run ./Scripts/open_xcode.sh

Ad-hoc MAS packaging (no Archive) still works:
  ./Scripts/build_app.sh --mas
EOF
  exit 1
fi

if ! xcodebuild -version 2>/dev/null | grep -q '^Xcode'; then
  echo "Xcode.app exists but xcode-select is not pointing at it." >&2
  echo "Run: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer" >&2
  exit 1
fi

if command -v xcodegen >/dev/null 2>&1; then
  echo "==> Generating RunSpecimen.xcodeproj via XcodeGen"
  xcodegen generate --spec "$ROOT/project.yml"
  open "$ROOT/RunSpecimen.xcodeproj"
  exit 0
fi

echo "==> xcodegen not found — opening Package.swift in Xcode"
echo "    Tip: brew install xcodegen && ./Scripts/open_xcode.sh"
echo "    Ensure signing uses Entitlements/RunSpecimen.mas.entitlements and AppIcon.icns"
open -a Xcode "$ROOT/Package.swift"
