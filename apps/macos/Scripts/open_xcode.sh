#!/usr/bin/env bash
# Open / generate an Xcode project for MAS Archive.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d /Applications/Xcode.app ]]; then
  cat <<EOF >&2
open_xcode: full Xcode.app is required for Archive / App Store Connect upload.

Install Xcode from the Mac App Store, then:
  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
  xcodebuild -version
  ./Scripts/open_xcode.sh

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

./Scripts/generate_xcodeproj.sh
open "$ROOT/RunSpecimen.xcodeproj"
echo "Opened RunSpecimen.xcodeproj — Product → Archive, or ./Scripts/archive_mas.sh"
