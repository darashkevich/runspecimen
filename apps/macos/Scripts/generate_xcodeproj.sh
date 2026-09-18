#!/usr/bin/env bash
# Generate / refresh RunSpecimen.xcodeproj from project.yml (XcodeGen).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v xcodegen >/dev/null 2>&1; then
  cat <<EOF >&2
generate_xcodeproj: xcodegen is required to refresh RunSpecimen.xcodeproj.

Install:
  brew install xcodegen

Or use the committed RunSpecimen.xcodeproj if present:
  open "$ROOT/RunSpecimen.xcodeproj"
EOF
  if [[ -d "$ROOT/RunSpecimen.xcodeproj" ]]; then
    echo "Committed project exists; skipping regenerate." >&2
    exit 0
  fi
  exit 1
fi

echo "==> Generating RunSpecimen.xcodeproj via XcodeGen $(xcodegen --version 2>/dev/null || true)"
xcodegen generate --spec "$ROOT/project.yml"
test -d "$ROOT/RunSpecimen.xcodeproj"
echo "OK: $ROOT/RunSpecimen.xcodeproj"
