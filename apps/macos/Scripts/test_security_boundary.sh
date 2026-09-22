#!/usr/bin/env bash
# Static + light dynamic checks for the app/CLI/payload security boundary and
# human PTY approval invariant (never auto-type APPROVE).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "OK: $*"; }

echo "==> SecurityBoundary.swift invariants"
grep -q 'neverAutoApprove = true' \
  "$ROOT/Sources/RunSpecimenCore/SecurityBoundary.swift" || fail "neverAutoApprove"
grep -q 'notConfinedByAppUISandboxAlone' \
  "$ROOT/Sources/RunSpecimenCore/SecurityBoundary.swift" || fail "payload not confined list"
grep -qi 'payload' \
  "$ROOT/Sources/RunSpecimenCore/SecurityBoundary.swift" || fail "payload wording"

echo "==> PTY approval never auto-types APPROVE"
grep -q 'never auto-types APPROVE\|Never auto-types APPROVE\|never auto-type APPROVE\|Never auto-submits APPROVE' \
  "$ROOT/Sources/RunSpecimenApp/Services/PTYApprovalSession.swift" \
  "$ROOT/Sources/RunSpecimenApp/Views/Sheets/ApproveSheet.swift" || fail "PTY never-auto docs"

# Ensure sendInput does not inject APPROVE.
python3 - <<'PY' || exit 1
from pathlib import Path
text = Path("Sources/RunSpecimenApp/Views/Sheets/ApproveSheet.swift").read_text()
# The send path must use only sheet.input — no hardcoded APPROVE write.
assert "session?.sendLine(line)" in text or "session?.sendLine(sheet.input" in text
assert "Deliberately do not auto-detect or coerce APPROVE" in text
# No call that auto-sends the literal APPROVE token.
banned = [
    'sendLine("APPROVE")',
    "sendLine(\"APPROVE\")",
    "send(\"APPROVE\\n\")",
    "send(\"APPROVE\")",
    'sendLine("APPROVE\\n")',
]
for b in banned:
    assert b not in text, b
print("ApproveSheet send path OK")
PY

echo "==> MAS channel fail-closed (no PATH when mas)"
grep -q 'allowsPATHProbe' "$ROOT/Sources/RunSpecimenCore/DistributionChannel.swift" || fail "channel"
grep -q 'requiresBundledHelper' "$ROOT/Sources/RunSpecimenApp/AppModel.swift" || fail "AppModel MAS"
grep -q 'fail closed' "$ROOT/Sources/RunSpecimenApp/AppModel.swift" || fail "fail closed copy"
grep -q 'does not select a host CLI' "$ROOT/Sources/RunSpecimenApp/AppModel.swift" || fail "MAS chooseCLI must refuse a host binary"
python3 - <<'PY' || exit 1
from pathlib import Path
settings = Path("Sources/RunSpecimenApp/Views/Sheets/SettingsView.swift").read_text()
menu = Path("Sources/RunSpecimenApp/RunSpecimenApp.swift").read_text()
# Host CLI picker is local/Developer ID only. Store builds must not offer it.
for label, text in (("Settings", settings), ("Engine menu", menu)):
    if "Select runspecimen" not in text:
        raise SystemExit(f"{label} lost the local CLI picker")
    if "requiresBundledHelper" not in text:
        raise SystemExit(f"{label} does not hide the CLI picker on MAS")
print("MAS hides host CLI picker")
PY

echo "==> SECURITY_BOUNDARY.md documents sandbox vs payload"
test -f "$ROOT/docs/SECURITY_BOUNDARY.md"
grep -q 'What the app sandbox does \*\*not\*\* do\|does \*\*not\*\*' "$ROOT/docs/SECURITY_BOUNDARY.md" \
  || grep -qi 'does not' "$ROOT/docs/SECURITY_BOUNDARY.md" || fail "doc negative claims"
grep -qi 'payload' "$ROOT/docs/SECURITY_BOUNDARY.md" || fail "doc payload"
grep -qi 'APPROVE' "$ROOT/docs/SECURITY_BOUNDARY.md" || fail "doc APPROVE"

echo "==> Entitlements: MAS has sandbox; helper has inherit"
grep -q 'com.apple.security.app-sandbox' "$ROOT/Entitlements/RunSpecimen.mas.entitlements"
grep -q 'com.apple.security.inherit' "$ROOT/Entitlements/RunSpecimen.helper.entitlements"
# Release entitlements must not enable get-task-allow
if grep -q 'get-task-allow' "$ROOT/Entitlements/"*.entitlements 2>/dev/null; then
  fail "get-task-allow present"
fi
# Nested sign must not hard-code ad-hoc identity in Xcode phases.
if grep -E 'codesign --force --sign -' "$ROOT/project.yml" >/dev/null 2>&1; then
  fail "project.yml hard-codes codesign --sign - (use sign_nested_helper.sh)"
fi
grep -q 'sign_nested_helper.sh' "$ROOT/project.yml" || fail "project.yml must call sign_nested_helper.sh"
test -x "$ROOT/Scripts/sign_nested_helper.sh"
test -x "$ROOT/Scripts/resolve_codesign_identity.sh"
test -x "$ROOT/Scripts/assert_archive_signing.sh"

pass "security boundary checks"
