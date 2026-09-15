#!/usr/bin/env bash
# Stage an optional runspecimen helper into Helpers/payload for bundling.
# Does NOT freeze a Python runtime in this script — that packaging choice is
# documented below. Safe to run when no helper exists (creates layout only).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HELPERS="$ROOT/Helpers"
PAYLOAD="$HELPERS/payload"
DEST="$PAYLOAD/runspecimen"

mkdir -p "$PAYLOAD"

usage() {
  cat <<'EOF'
Usage: ./Scripts/stage_helper.sh [--from PATH] [--check]

  --from PATH   Copy/symlink an existing runspecimen executable into
                Helpers/payload/runspecimen for local experiments.
  --check       Exit 0 if payload/runspecimen is executable; else 1.

Without flags, creates Helpers/payload/ and prints exact next packaging steps.

Never commit Helpers/payload/ artifacts (gitignored). Never auto-type APPROVE.
EOF
}

cmd_check() {
  if [[ -x "$DEST" ]]; then
    echo "OK: staged helper at $DEST"
    ls -la "$DEST"
    exit 0
  fi
  echo "No executable helper at $DEST (expected until packaging lands)."
  exit 1
}

FROM=""
CHECK=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="${2:-}"; shift 2 ;;
    --check) CHECK=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "$CHECK" -eq 1 ]]; then
  cmd_check
fi

if [[ -n "$FROM" ]]; then
  if [[ ! -x "$FROM" ]]; then
    echo "Not executable: $FROM" >&2
    exit 1
  fi
  rm -f "$DEST"
  cp -f "$FROM" "$DEST"
  chmod +x "$DEST"
  echo "Staged helper: $DEST"
  echo "Rebuild with: ./Scripts/build_app.sh   # copies into Contents/Helpers/"
  exit 0
fi

cat <<EOF
Helpers layout ready under:
  $HELPERS
  $PAYLOAD/   (gitignored — place experiments here)

Exact next packaging steps (ADR-002 / Mac App Store stretch):
  1. Choose packaging:
       a) PyInstaller onefile → name entrypoint runspecimen
       b) python-build-standalone + zipapp / shiv launcher named runspecimen
       c) Future compiled helper (Go/Rust) exposing the same CLI surface
  2. License-audit the bundled runtime; keep Apache-2.0 app notices accurate.
  3. Place the executable at:
       $DEST
     Or: ./Scripts/stage_helper.sh --from /path/to/runspecimen
  4. Codesign the helper with the same Team ID as the app using
       Entitlements/RunSpecimen.helper.entitlements (inherit), e.g.:
       codesign --force --options runtime --timestamp \\
         --entitlements Entitlements/RunSpecimen.helper.entitlements \\
         --sign \"\$IDENTITY\" Helpers/payload/runspecimen
  5. ./Scripts/build_app.sh   # copies payload → Contents/Helpers/runspecimen
  6. Sign + notarize the whole .app (Target B practice):
       ./Scripts/sign_and_notarize.sh all
  7. Verify discovery: app Settings → Source = “Bundled Helpers”
  8. Update APP_STORE.md review notes with helper path + demo steps.

Current status: discovery + Contents/Helpers wiring are implemented; no frozen
helper binary ships in-repo until packaging + Developer ID certs are available.
EOF
