#!/usr/bin/env bash
# Positive end-to-end test of the sandboxed MAS .app + bundled helper:
#   - workspace security-scoped bookmark
#   - dashboard cleanup
#   - human PTY approval gate waits (never types APPROVE)
#
# Usage:
#   ./Scripts/test_mas_sandbox_e2e.sh [/path/to/RunSpecimen.app]
#
# Defaults to archive app, then build/RunSpecimen.app (must be channel=mas).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_SRC="${1:-}"
if [[ -z "$APP_SRC" ]]; then
  if [[ -d /tmp/runspecimen-mas/RunSpecimen.xcarchive/Products/Applications/RunSpecimen.app ]]; then
    APP_SRC=/tmp/runspecimen-mas/RunSpecimen.xcarchive/Products/Applications/RunSpecimen.app
  elif [[ -d "$ROOT/build/RunSpecimen.xcarchive/Products/Applications/RunSpecimen.app" ]]; then
    APP_SRC="$ROOT/build/RunSpecimen.xcarchive/Products/Applications/RunSpecimen.app"
  elif [[ -d "$ROOT/build/RunSpecimen.app" ]]; then
    APP_SRC="$ROOT/build/RunSpecimen.app"
  else
    echo "ERROR: no RunSpecimen.app found. Pass a path or run ./Scripts/archive_mas.sh / build_app.sh --mas" >&2
    exit 1
  fi
fi

# Copy out of /tmp archives — sandbox launch from /tmp is unreliable.
APP="$ROOT/build/e2e-RunSpecimen.app"
rm -rf "$APP"
mkdir -p "$ROOT/build"
ditto "$APP_SRC" "$APP"
xattr -cr "$APP" 2>/dev/null || true

BIN="$APP/Contents/MacOS/RunSpecimen"
HELPER="$APP/Contents/Resources/RunSpecimenEngine/runspecimen"
if [[ ! -x "$HELPER" ]]; then
  HELPER="$APP/Contents/Helpers/runspecimen"
fi
test -x "$BIN" || { echo "ERROR: missing $BIN" >&2; exit 1; }
test -x "$HELPER" || { echo "ERROR: missing engine helper" >&2; exit 1; }

CHANNEL="$(/usr/libexec/PlistBuddy -c 'Print :RSDistributionChannel' "$APP/Contents/Info.plist" 2>/dev/null || true)"
echo "APP_SRC=$APP_SRC"
echo "APP=$APP"
echo "RSDistributionChannel=$CHANNEL"
[[ "$CHANNEL" == "mas" ]] || {
  echo "ERROR: e2e requires mas channel app (got: ${CHANNEL:-empty}). Rebuild with --mas / archive_mas.sh" >&2
  exit 1
}

echo "==> structural gates (helper sandbox+inherit + PTY static)"
./Scripts/test_security_boundary.sh
HELP_ENT="$(codesign -d --entitlements - "$HELPER" 2>/dev/null || true)"
echo "$HELP_ENT" | grep -q 'com.apple.security.app-sandbox' || {
  echo "ERROR: helper missing app-sandbox" >&2
  exit 1
}
echo "$HELP_ENT" | grep -q 'com.apple.security.inherit' || {
  echo "ERROR: helper missing inherit" >&2
  exit 1
}
if [[ "$APP_SRC" == *".xcarchive"* ]]; then
  echo "==> archive signing assertions (on source archive app)"
  if codesign -dv "$APP_SRC" 2>&1 | grep -q 'Signature=adhoc'; then
    ./Scripts/assert_archive_signing.sh "$APP_SRC" --expect-adhoc
  else
    ./Scripts/assert_archive_signing.sh "$APP_SRC"
  fi
fi

LOG="$(mktemp -t rs-mas-e2e-log)"
SUPPORT_OUT="$HOME/Library/Application Support/RunSpecimenE2E/last-result.json"
rm -f "$SUPPORT_OUT"

echo "==> Launching sandboxed app harness (RS_MAS_E2E=1)"
set +e
# Direct exec keeps stdout/stderr for JSON markers.
RS_MAS_E2E=1 "$BIN" --mas-e2e >"$LOG" 2>&1
RC=$?
set -e

echo "----- harness log (tail) -----"
tail -120 "$LOG" || true

python3 - <<'PY' "$LOG" "$RC" "$SUPPORT_OUT"
import json, re, sys
from pathlib import Path

log_path, rc_s, support = sys.argv[1:4]
rc = int(rc_s)
text = Path(log_path).read_text(errors="replace")
m = re.search(r"E2E_RESULT_JSON_BEGIN\n(.*)\nE2E_RESULT_JSON_END", text, re.S)
doc = None
if m:
    doc = json.loads(m.group(1))
elif Path(support).is_file():
    doc = json.loads(Path(support).read_text())
assert doc is not None, f"no E2E JSON in log or {support}\n--- log ---\n{text[-4000:]}"
print(json.dumps(doc, indent=2, sort_keys=True))
assert doc.get("ok") is True, doc
names = {c["name"] for c in doc.get("checks", []) if c.get("ok")}
for required in (
    "bundled_helper_version",
    "workspace_bookmark",
    "dashboard_cleanup",
    "pty_approval_waits_for_human",
):
    assert required in names, (required, doc)
# Never auto-APPROVE evidence
assert "APPROVE" not in text or "no APPROVE" in text.lower() or "never" in text.lower()
pty = next(c for c in doc.get("checks", []) if c.get("name") == "pty_approval_waits_for_human")
detail = (pty.get("detail") or "").lower()
assert "prompt observed" in detail, ("PTY must require actual approval prompt", pty)
assert "still waiting" in detail, ("PTY must still be waiting (not completed)", pty)
assert "no approve sent" in detail, pty
print("MAS sandbox e2e JSON OK")
if rc != 0:
    raise SystemExit(f"harness exit {rc} despite ok JSON")
PY

if grep -E 'sendLine\("APPROVE"\)|typing APPROVE for' "$LOG" >/dev/null 2>&1; then
  echo "ERROR: log suggests APPROVE automation" >&2
  exit 1
fi

echo "MAS SANDBOX E2E OK"
echo "  app: $APP"
echo "  src: $APP_SRC"
echo "  note: human APPROVE was NOT typed (gate wait asserted)"
