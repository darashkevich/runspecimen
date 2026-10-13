#!/usr/bin/env bash
# Isolated holder Swift tests. First pass is the record.
# Does not install, register, launch, or contact a live holder daemon.
# Each invocation keeps its log in a private mktemp directory.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=isolated_evidence.sh
source "$ROOT/Scripts/isolated_evidence.sh"
PRODUCTION_SOCK="/Library/Application Support/com.darashkevich.runspecimen.holder/holder.sock"

if [[ -n "${RS_HOLDER_SOCKET:-}" ]]; then
  echo "REFUSED: RS_HOLDER_SOCKET is set; this job must not contact a live holder" >&2
  exit 2
fi
if [[ "${RS_HOLDER_INSTALL_CONSENT:-}" == "yes" ]]; then
  echo "REFUSED: RS_HOLDER_INSTALL_CONSENT=yes; this job must not install" >&2
  exit 2
fi

echo "HOLDER isolated swift test — package $ROOT"
echo "Does not install SMAppService, does not touch /Applications, does not invoke biometrics."
echo "Does not bind or contact $PRODUCTION_SOCK"
EVIDENCE="$(rs_evidence_create rs-holder-swift)"
cleanup_holder_evidence() {
  local status=$?
  if [[ "$status" -ne 0 && -n "${EVIDENCE:-}" && -d "$EVIDENCE" && ! -L "$EVIDENCE" ]]; then
    local kept=""
    if kept="$(rs_evidence_preserve_files "$EVIDENCE" rs-holder-swift-kept)"; then
      echo "HOLDER_EVIDENCE: $kept" >&2
      rs_evidence_cleanup "$EVIDENCE" rs-holder-swift || true
    fi
  elif [[ -n "${EVIDENCE:-}" ]]; then
    rs_evidence_cleanup "$EVIDENCE" rs-holder-swift || true
  fi
  exit "$status"
}
trap cleanup_holder_evidence EXIT
SCRATCH="$EVIDENCE/scratch"
mkdir "$SCRATCH"
# Build products stay off the source tree so Finder/Box xattrs cannot
# inject detritus into .xctest bundles. This is setup, not a retry.
xattr -cr "$SCRATCH" 2>/dev/null || true

if ! swift package --package-path "$ROOT" describe >/dev/null 2>&1; then
  echo "SwiftPM unavailable — cannot run holder tests on this host"
  exit 3
fi

echo "HOLDER_FIRST_PASS: running swift test --package-path $ROOT --scratch-path $SCRATCH"
FIRST_LOG="$EVIDENCE/first.log"
set +e
swift test --package-path "$ROOT" --scratch-path "$SCRATCH" >"$FIRST_LOG" 2>&1
FIRST_RC=$?
set -e
cat "$FIRST_LOG"
if [[ "$FIRST_RC" -ne 0 ]]; then
  echo "HOLDER_FIRST_PASS: FAIL — not retrying"
  exit 1
fi
# Vacuous success is a failure. XCTest prints "Executed N tests" per suite.
if ! rs_log_has_executed_tests "$FIRST_LOG"; then
  echo "HOLDER_FIRST_PASS: FAIL — zero tests ran" >&2
  exit 1
fi
echo "HOLDER_FIRST_PASS: OK"
