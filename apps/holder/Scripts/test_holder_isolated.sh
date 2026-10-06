#!/usr/bin/env bash
# Isolated holder Swift tests. First pass is the record.
# Does not install, register, launch, or contact a live holder daemon.
# Do not add a packed tests/*.py copy of this script: MANIFEST.in ships tests/
# into the sdist and that would move the committed OPEN-SDIST hash.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -n "${RS_HOLDER_SOCKET:-}" ]]; then
  echo "REFUSED: RS_HOLDER_SOCKET is set; this job must not contact a live holder" >&2
  exit 2
fi

echo "HOLDER isolated swift test — package $ROOT"
echo "Does not install SMAppService, does not touch /Applications, does not invoke biometrics."
xattr -cr "$ROOT/.build" 2>/dev/null || true
find "$ROOT/.build" \( -name '._*' -o -name '.DS_Store' \) -delete 2>/dev/null || true

if ! swift package --package-path "$ROOT" describe >/dev/null 2>&1; then
  echo "SwiftPM unavailable — cannot run holder tests on this host"
  exit 3
fi

echo "HOLDER_FIRST_PASS: running swift test --package-path $ROOT"
if swift test --package-path "$ROOT"; then
  echo "HOLDER_FIRST_PASS: OK"
else
  echo "HOLDER_FIRST_PASS: FAIL — not retrying"
  exit 1
fi
