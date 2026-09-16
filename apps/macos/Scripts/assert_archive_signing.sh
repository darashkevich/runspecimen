#!/usr/bin/env bash
# Fail-closed archive / .app signing + entitlement + version assertions.
#
# Usage:
#   ./Scripts/assert_archive_signing.sh <RunSpecimen.app> [--expect-adhoc|--expect-team TEAMID]
#
# Checks:
#   - App + helper signatures verify
#   - App entitlements include App Sandbox (MAS set)
#   - Helper entitlements include App Sandbox + inherit
#   - Helper is Mach-O; version was gated pre-sign (optional --expected-version)
#   - TeamIdentifier matches expectation (adhoc => not set; else TEAMID)
#   - Runtime: inherit-signed helper must NOT run from unsandboxed shell (exit ≠ 0)
#   - PTY never-auto-APPROVE static gate (test_security_boundary.sh)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
APP="${1:-}"
shift || true

EXPECT_ADHOC=0
EXPECT_TEAM=""
EXPECTED_VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --expect-adhoc) EXPECT_ADHOC=1; shift ;;
    --expect-team) EXPECT_TEAM="${2:-}"; shift 2 ;;
    --expected-version) EXPECTED_VERSION="${2:-}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "OK: $*"; }

[[ -n "$APP" && -d "$APP" ]] || fail "app bundle required: $APP"
HELPER="$APP/Contents/Helpers/runspecimen"
[[ -x "$HELPER" ]] || fail "missing helper: $HELPER"
file "$HELPER" | grep -q 'Mach-O' || fail "helper must be Mach-O"

if [[ -z "$EXPECTED_VERSION" ]]; then
  EXPECTED_VERSION="$(
    python3 -c 'import pathlib,re,sys; t=pathlib.Path(sys.argv[1],"src/runspecimen/__init__.py").read_text(); m=re.search(r"__version__\s*=\s*\"([^\"]+)\"", t); assert m; print(m.group(1))' \
      "$REPO"
  )"
fi

echo "==> codesign --verify (app + helper)"
codesign --verify --deep --strict --verbose=2 "$APP" 2>&1 | tail -20
codesign --verify --verbose=2 "$HELPER" 2>&1 | tail -10
pass "signatures verify"

echo "==> app entitlements (App Sandbox)"
APP_ENT="$(codesign -d --entitlements - "$APP" 2>/dev/null || true)"
echo "$APP_ENT" | grep -q 'com.apple.security.app-sandbox' || fail "app missing app-sandbox"
pass "app has app-sandbox"

echo "==> helper entitlements (App Sandbox + inherit)"
HELP_ENT="$(codesign -d --entitlements - "$HELPER" 2>/dev/null || true)"
[[ -n "$HELP_ENT" ]] || fail "helper has NO entitlements (Store inherit required)"
echo "$HELP_ENT" | grep -q 'com.apple.security.app-sandbox' || fail "helper missing app-sandbox"
echo "$HELP_ENT" | grep -q 'com.apple.security.inherit' || fail "helper missing inherit"
pass "helper has sandbox+inherit"

echo "==> TeamIdentifier / signing mode"
APP_DV="$(codesign -dv --verbose=4 "$APP" 2>&1 || true)"
HELP_DV="$(codesign -dv --verbose=4 "$HELPER" 2>&1 || true)"
APP_TEAM="$(printf '%s\n' "$APP_DV" | awk -F= '/^TeamIdentifier=/{print $2; exit}')"
HELP_TEAM="$(printf '%s\n' "$HELP_DV" | awk -F= '/^TeamIdentifier=/{print $2; exit}')"
APP_SIG="$(printf '%s\n' "$APP_DV" | awk -F= '/^Signature=/{print $2; exit}')"
HELP_SIG="$(printf '%s\n' "$HELP_DV" | awk -F= '/^Signature=/{print $2; exit}')"
echo "app TeamIdentifier=$APP_TEAM Signature=$APP_SIG"
echo "helper TeamIdentifier=$HELP_TEAM Signature=$HELP_SIG"

if [[ "$EXPECT_ADHOC" -eq 1 ]]; then
  [[ "$APP_SIG" == "adhoc" ]] || fail "expected ad-hoc app signature, got $APP_SIG"
  [[ "$HELP_SIG" == "adhoc" ]] || fail "expected ad-hoc helper signature, got $HELP_SIG"
  [[ "$APP_TEAM" == "not set" || -z "$APP_TEAM" ]] || fail "adhoc app should have TeamIdentifier not set (got $APP_TEAM)"
  [[ "$HELP_TEAM" == "not set" || -z "$HELP_TEAM" ]] || fail "adhoc helper should have TeamIdentifier not set (got $HELP_TEAM)"
  pass "ad-hoc mode: TeamIdentifier unset as expected (local structural archive only)"
elif [[ -n "$EXPECT_TEAM" ]]; then
  [[ "$APP_TEAM" == "$EXPECT_TEAM" ]] || fail "app TeamIdentifier=$APP_TEAM expected $EXPECT_TEAM"
  [[ "$HELP_TEAM" == "$EXPECT_TEAM" ]] || fail "helper TeamIdentifier=$HELP_TEAM expected $EXPECT_TEAM"
  [[ "$APP_SIG" != "adhoc" ]] || fail "distribution expected but app still adhoc"
  [[ "$HELP_SIG" != "adhoc" ]] || fail "distribution expected but helper still adhoc"
  pass "team $EXPECT_TEAM matches on app + helper"
else
  # Auto: if either side is adhoc, require both adhoc; else require matching non-empty teams.
  if [[ "$APP_SIG" == "adhoc" || "$HELP_SIG" == "adhoc" ]]; then
    [[ "$APP_SIG" == "adhoc" && "$HELP_SIG" == "adhoc" ]] || fail "mixed adhoc/distribution signing"
    pass "auto: ad-hoc archive (no Apple identity on this host)"
  else
    [[ -n "$APP_TEAM" && "$APP_TEAM" != "not set" ]] || fail "missing app TeamIdentifier"
    [[ "$HELP_TEAM" == "$APP_TEAM" ]] || fail "helper team $HELP_TEAM != app team $APP_TEAM"
    pass "auto: distribution team $APP_TEAM on app + helper"
  fi
fi

echo "==> engine version gate (pre-sign payload; archive must match freeze)"
# Inherit-signed helpers must not be executed from an unsandboxed shell.
# Version is asserted against Helpers/payload (same freeze that was embedded).
PAYLOAD="$ROOT/Helpers/payload/runspecimen"
[[ -x "$PAYLOAD" ]] || fail "missing staged payload for version gate: $PAYLOAD"
PAYLOAD_VER="$("$PAYLOAD" --version 2>&1)" || fail "payload --version failed"
echo "payload --version → $PAYLOAD_VER"
echo "$PAYLOAD_VER" | grep -F "$EXPECTED_VERSION" >/dev/null \
  || fail "payload version mismatch: expected $EXPECTED_VERSION in $PAYLOAD_VER"
# Soft size sanity: archived helper should be same order of magnitude as payload.
P_SZ="$(stat -f%z "$PAYLOAD" 2>/dev/null || stat -c%s "$PAYLOAD")"
H_SZ="$(stat -f%z "$HELPER" 2>/dev/null || stat -c%s "$HELPER")"
# codesign can grow the binary slightly; allow 20% delta.
python3 -c "import sys; p=int(sys.argv[1]); h=int(sys.argv[2]); sys.exit(0 if abs(p-h)/max(p,1) < 0.2 else 1)" "$P_SZ" "$H_SZ" \
  || fail "archived helper size $H_SZ diverges from payload $P_SZ"
pass "engine version $EXPECTED_VERSION (payload gated; archive size aligned)"

echo "==> runtime sandbox probe (inherit helper must fail outside parent sandbox)"
set +e
OUT="$("$HELPER" --version 2>&1)"
RC=$?
set -e
if [[ "$RC" -eq 0 ]]; then
  fail "inherit-signed helper ran from unsandboxed shell (rc=0). Entitlements not enforced? output=$OUT"
fi
echo "helper --version from shell exited $RC (expected non-zero; sandbox/inherit active)"
pass "runtime sandbox probe: helper confined when not inheriting a parent sandbox"

echo "==> PTY never auto-types APPROVE"
"$ROOT/Scripts/test_security_boundary.sh"
pass "PTY / security boundary"

echo
echo "ARCHIVE ASSERTIONS OK"
echo "  app:     $APP"
echo "  helper:  $HELPER"
echo "  engine:  $EXPECTED_VERSION"
echo "  app_team=$APP_TEAM helper_team=$HELP_TEAM"
