#!/usr/bin/env bash
# Non-GUI smoke for the macOS companion app.
# Runs version-gate checks + bundle layout checks + optional CLI --version probe.
# Uses `swift test` when SwiftPM works (Xcode); otherwise a Python parity check.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"

echo "==> CLIVersionGate checks"
# Box/Finder xattrs break ad-hoc codesign of .xctest bundles on cloud-synced trees.
xattr -cr "$ROOT/.build" 2>/dev/null || true
find "$ROOT/.build" \( -name '._*' -o -name '.DS_Store' \) -delete 2>/dev/null || true
if swift package --package-path "$ROOT" describe >/dev/null 2>&1; then
  echo "SwiftPM OK — running swift test"
  # Retry once after xattr clear if codesign detritus fails.
  if ! swift test --package-path "$ROOT"; then
    echo "swift test failed — clearing xattrs and retrying once"
    rm -rf "$ROOT/.build"
    xattr -cr "$ROOT" 2>/dev/null || true
    swift test --package-path "$ROOT"
  fi
else
  echo "SwiftPM unavailable — running Python parity checks for CLIVersionGate"
  python3 - <<'PY'
import re

def parse(text: str):
    lowered = text.lower()
    m = re.search(r"(\d+)\.(\d+)\.(\d+)(?:[-.]?(?:rc|a|b|alpha|beta)\.?(\d+))?", lowered)
    if not m:
        return None
    maj, minor, patch = map(int, m.group(1, 2, 3))
    if m.group(4) is not None:
        return (maj, minor, patch, 0, int(m.group(4)))
    return (maj, minor, patch, 1, 0)

minimum = (0, 2, 0, 0, 9)
assert parse("runspecimen 0.2.0rc9") == minimum
assert parse("0.2.0-rc.9") == minimum
assert parse("0.2.0") == (0, 2, 0, 1, 0)
assert parse("0.2.0rc9") >= minimum
assert parse("0.2.0rc8") < minimum
assert parse("0.2.0") > minimum
assert parse("not-a-version") is None
print("CLIVersionGate Python parity OK")
PY
fi

echo "==> App icon assets"
./Scripts/verify_app_icon.sh

echo "==> security boundary + PTY never-auto-APPROVE"
./Scripts/test_security_boundary.sh

echo "==> stage_helper (docs / layout)"
./Scripts/stage_helper.sh >/tmp/rs-stage-helper.out
grep -q "Exact next packaging steps" /tmp/rs-stage-helper.out
grep -q "LICENSE NOTES" /tmp/rs-stage-helper.out

echo "==> stage_helper --from-src + --verify (package-tree helper)"
./Scripts/stage_helper.sh --from-src --verify
./Scripts/stage_helper.sh --check

echo "==> freeze interpreter selection (no Apple Python, no lost export)"
./Scripts/test_freeze_python_select.sh

echo "==> freeze_helper default skip (CI-safe without PyInstaller)"
./Scripts/freeze_helper.sh >/tmp/rs-freeze.out
grep -q "skipped (optional)" /tmp/rs-freeze.out
grep -q "stage_helper.sh --from-src" /tmp/rs-freeze.out

echo "==> build_app.sh --help documents --frozen-helper and --mas"
./Scripts/build_app.sh -h >/tmp/rs-build-help.out
grep -q -- "--frozen-helper" /tmp/rs-build-help.out
grep -q -- "--from-src" /tmp/rs-build-help.out
grep -q -- "--mas" /tmp/rs-build-help.out
test -f "$ROOT/RELEASE_CHECKLIST.md"
grep -qi "Mac App Store" "$ROOT/RELEASE_CHECKLIST.md"

echo "==> build_app.sh (with staged helper)"
./Scripts/build_app.sh

APP="$ROOT/build/RunSpecimen.app"
HELPER="$APP/Contents/Helpers/runspecimen"
if [[ ! -x "$HELPER" ]]; then
  HELPER="$APP/Contents/Resources/RunSpecimenEngine/runspecimen"
fi
test -x "$APP/Contents/MacOS/RunSpecimen"
test -f "$APP/Contents/Info.plist"
test -f "$APP/Contents/Resources/PrivacyInfo.xcprivacy"
test -d "$APP/Contents/Helpers"
test -x "$HELPER"
if [[ "$HELPER" == *"/Helpers/runspecimen" ]]; then
  test -d "$APP/Contents/Helpers/lib/runspecimen"
  test -f "$APP/Contents/Helpers/NOTICE.txt"
fi

echo "==> bundled helper --version (Contents/Helpers preferred path)"
HELPER_VER="$("$HELPER" --version 2>&1)"
echo "Helpers/runspecimen --version → $HELPER_VER"
echo "$HELPER_VER" | grep -qi runspecimen
python3 - <<'PY' "$HELPER_VER"
import re, sys
text = sys.argv[1].lower()
m = re.search(r"(\d+)\.(\d+)\.(\d+)(?:[-.]?(?:rc|a|b|alpha|beta)\.?(\d+))?", text)
assert m, f"unparseable helper version: {text!r}"
maj, minor, patch = map(int, m.group(1, 2, 3))
pre = m.group(4)
pre_kind = 0 if pre is not None else 1
pre_num = int(pre) if pre is not None else 0
found = (maj, minor, patch, pre_kind, pre_num)
minimum = (0, 2, 0, 0, 9)
assert found >= minimum, f"helper CLI too old: {found} < {minimum}"
print("Bundled helper version gate OK")
PY

echo "==> Prefer Bundled Helper e2e: doctor/status + host-python + spaces"
SHOWCASE="$REPO/examples/showcase"
python3 - "$HELPER" "$SHOWCASE" <<'PY'
import json, os, subprocess, sys, tempfile
from pathlib import Path

helper, showcase = sys.argv[1:3]
assert "/Contents/Helpers/runspecimen" in helper or "/RunSpecimenEngine/runspecimen" in helper

# Absolute /usr/bin/python3 must work even with stripped PATH (sandbox-ish).
env = {"PATH": "/usr/bin:/bin", "HOME": os.path.expanduser("~")}
r = subprocess.run([helper, "--version"], capture_output=True, text=True, env=env)
assert r.returncode == 0 and "runspecimen" in (r.stdout + r.stderr).lower(), (r.stdout, r.stderr)

# Explicit /bin/bash invocation (matches CLIService.processInvocation for scripts)
r = subprocess.run(["/bin/bash", helper, "doctor", "--workspace", showcase], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
doc = json.loads(r.stdout)
assert doc.get("ok") is True, doc

ws = Path(tempfile.mkdtemp(prefix="rs prefer bundled ")) / "ws"
ws.mkdir()
r = subprocess.run(
    ["/bin/bash", helper, "doctor", "--workspace", str(ws)],
    capture_output=True,
    text=True,
)
assert r.returncode == 0, r.stderr
assert json.loads(r.stdout).get("ok") is True

r = subprocess.run(
    ["/bin/bash", helper, "status", "--workspace", str(ws), "--campaign-id", "demo", "--run-id", "1"],
    capture_output=True,
    text=True,
)
assert r.returncode == 0, (r.stdout, r.stderr)
print("Prefer Bundled Helper doctor/status OK")
PY

echo "==> discovery preference: Helpers path is executable under Contents/Helpers"
# ADR-002: when no Open-panel bookmark, app resolves Contents/Helpers before PATH.
# Non-GUI assertion: the built helper exists at the exact path CLIService probes.
python3 - <<'PY' "$APP"
import os, sys
app = sys.argv[1]
helper = os.path.join(app, "Contents", "Helpers", "runspecimen")
assert os.path.isfile(helper) and os.access(helper, os.X_OK), helper
# Refuse tiny stubs (< 64 bytes) the same way CLIService does.
assert os.path.getsize(helper) >= 64, os.path.getsize(helper)
print("Helpers discovery target OK:", helper)
PY

echo "==> Prefer Bundled vs bookmark race guards present in sources"
grep -q 'never persist PATH probes as bookmarks' \
  "$ROOT/Sources/RunSpecimenApp/AppModel.swift"
grep -q 'Does not fall through to PATH' \
  "$ROOT/Sources/RunSpecimenApp/AppModel.swift"
grep -q 'isShellScript' \
  "$ROOT/Sources/RunSpecimenApp/Services/CLIService.swift"
grep -q 'isShellScript' \
  "$ROOT/Sources/RunSpecimenApp/Services/PTYApprovalSession.swift"
grep -q 'Copied' \
  "$ROOT/Sources/RunSpecimenApp/Views/Screens/EvidenceInspectorView.swift"

echo "==> Info.plist CFBundleIdentifier + About version keys + icon + channel"
/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP/Contents/Info.plist" | grep -q .
/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist" | grep -q .
/usr/libexec/PlistBuddy -c 'Print :CFBundleIconFile' "$APP/Contents/Info.plist" | grep -q AppIcon
test -f "$APP/Contents/Resources/AppIcon.icns"
/usr/libexec/PlistBuddy -c 'Print :RSDistributionChannel' "$APP/Contents/Info.plist" | grep -Eq 'local|developer-id|mas'
test -f "$ROOT/Sources/RunSpecimenApp/Views/Sheets/AboutView.swift"
grep -q 'runspecimen.darashkevich.com/privacy' \
  "$ROOT/Sources/RunSpecimenApp/Views/Sheets/AboutView.swift" \
  "$ROOT/Sources/RunSpecimenApp/Views/Sheets/SettingsView.swift"

echo "==> optional PATH CLI integration (no GUI)"
if command -v runspecimen >/dev/null 2>&1; then
  VER="$(runspecimen --version 2>&1 || true)"
  echo "runspecimen --version → $VER"
  python3 - <<'PY' "$VER"
import re, sys
text = sys.argv[1].lower()
m = re.search(r"(\d+)\.(\d+)\.(\d+)(?:[-.]?(?:rc|a|b|alpha|beta)\.?(\d+))?", text)
assert m, f"unparseable: {text!r}"
maj, minor, patch = map(int, m.group(1, 2, 3))
pre = m.group(4)
pre_kind = 0 if pre is not None else 1
pre_num = int(pre) if pre is not None else 0
found = (maj, minor, patch, pre_kind, pre_num)
minimum = (0, 2, 0, 0, 9)
assert found >= minimum, f"CLI too old: {found} < {minimum}"
print("CLI version gate OK")
PY
  SHOWCASE="$REPO/examples/showcase"
  if [[ -d "$SHOWCASE" ]]; then
    echo "==> helper doctor --workspace examples/showcase"
    if "$HELPER" doctor --workspace "$SHOWCASE" >/tmp/rs-doctor.out 2>&1; then
      if python3 -c 'import json; json.load(open("/tmp/rs-doctor.out"))' 2>/dev/null; then
        echo "helper doctor JSON OK"
      else
        echo "helper doctor ran (non-JSON output acceptable for smoke)"
      fi
    else
      echo "helper doctor exited non-zero (acceptable if workspace not initialized)"
    fi
  fi
else
  echo "runspecimen not on PATH — skipping live PATH probe (bundled helper already verified)."
fi

echo "==> build_app.sh --frozen-helper (freeze if PyInstaller else --from-src fallback)"
# Runs after the --from-src Prefer Bundled e2e so a local freeze cannot break those checks.
# Unset RS_FREEZE_HELPER so this invocation is driven only by --frozen-helper.
env -u RS_FREEZE_HELPER ./Scripts/build_app.sh --frozen-helper >/tmp/rs-frozen-build.out 2>&1 || {
  cat /tmp/rs-frozen-build.out >&2
  exit 1
}
cat /tmp/rs-frozen-build.out
grep -E "Using frozen helper payload|falling back to stage_helper" /tmp/rs-frozen-build.out
# Frozen onedir lives under Resources/RunSpecimenEngine; --from-src fallback under Helpers.
if [[ -x "$APP/Contents/Resources/RunSpecimenEngine/runspecimen" ]]; then
  HELPER="$APP/Contents/Resources/RunSpecimenEngine/runspecimen"
elif [[ -x "$APP/Contents/Helpers/runspecimen" ]]; then
  HELPER="$APP/Contents/Helpers/runspecimen"
else
  echo "ERROR: no bundled helper after --frozen-helper" >&2
  exit 1
fi
test -x "$HELPER"
# Frozen path: no package-tree lib/. Fallback --from-src: lib/ present.
if grep -q "Using frozen helper payload" /tmp/rs-frozen-build.out; then
  test ! -d "$APP/Contents/Helpers/lib"
  test -d "$APP/Contents/Resources/RunSpecimenEngine/_internal"
  file "$APP/Contents/Resources/RunSpecimenEngine/runspecimen" | grep -q 'Mach-O'
  # Inherit-signed Mach-O must not be shell-exec'd; gate version via payload + entitlements.
  PAYLOAD_VER="$("$ROOT/Helpers/payload/runspecimen" --version 2>&1)"
  echo "post --frozen-helper payload --version → $PAYLOAD_VER"
  echo "$PAYLOAD_VER" | grep -qi runspecimen
  HELP_ENT="$(codesign -d --entitlements - "$APP/Contents/Resources/RunSpecimenEngine/runspecimen" 2>/dev/null || true)"
  echo "$HELP_ENT" | grep -q 'com.apple.security.app-sandbox'
  echo "$HELP_ENT" | grep -q 'com.apple.security.inherit'
  echo "OK: frozen Mach-O onedir helper in bundle (sandbox+inherit; RunSpecimenEngine; no lib/ tree)"
else
  FROZEN_VER="$("$APP/Contents/Helpers/runspecimen" --version 2>&1)" || {
    echo "Bundled helper after --frozen-helper fallback failed (exit $?):" >&2
    echo "$FROZEN_VER" >&2
    exit 1
  }
  echo "post --frozen-helper --version → $FROZEN_VER"
  echo "$FROZEN_VER" | grep -qi runspecimen
  test -d "$APP/Contents/Helpers/lib/runspecimen"
  echo "OK: --frozen-helper fell back to --from-src package tree"
fi

echo "==> MAS packaging path (frozen helper required; fail closed)"
if python3 -c 'import PyInstaller' 2>/dev/null || command -v pyinstaller >/dev/null 2>&1; then
  ./Scripts/build_app.sh --mas >/tmp/rs-mas-build.out 2>&1 || {
    cat /tmp/rs-mas-build.out >&2
    exit 1
  }
  cat /tmp/rs-mas-build.out
  grep -q "Using frozen helper payload for MAS" /tmp/rs-mas-build.out
  test -x "$APP/Contents/Resources/RunSpecimenEngine/runspecimen"
  test -d "$APP/Contents/Resources/RunSpecimenEngine/_internal"
  test ! -d "$APP/Contents/Helpers/lib"
  test ! -d "$APP/Contents/Helpers/_internal"
  file "$APP/Contents/Resources/RunSpecimenEngine/runspecimen" | grep -q 'Mach-O'
  /usr/libexec/PlistBuddy -c 'Print :RSDistributionChannel' "$APP/Contents/Info.plist" | grep -qx mas
  REPO_VER=$(
    python3 -c 'import pathlib,re,sys; t=pathlib.Path(sys.argv[1],"src/runspecimen/__init__.py").read_text(); m=re.search(r"__version__\s*=\s*\"([^\"]+)\"", t); assert m; print(m.group(1))' \
      "$REPO"
  )
  PAYLOAD_VER="$("$ROOT/Helpers/payload/runspecimen" --version 2>&1)"
  echo "MAS payload --version → $PAYLOAD_VER"
  echo "$PAYLOAD_VER" | grep -F "$REPO_VER" >/dev/null || {
    echo "ERROR: MAS helper must match repo engine $REPO_VER (got: $PAYLOAD_VER)" >&2
    exit 1
  }
  HELP_ENT="$(codesign -d --entitlements - "$APP/Contents/Resources/RunSpecimenEngine/runspecimen" 2>/dev/null || true)"
  echo "$HELP_ENT" | grep -q 'com.apple.security.app-sandbox' || {
    echo "ERROR: MAS helper missing app-sandbox entitlement" >&2
    exit 1
  }
  echo "$HELP_ENT" | grep -q 'com.apple.security.inherit' || {
    echo "ERROR: MAS helper missing inherit entitlement" >&2
    exit 1
  }
  # Runtime sandbox probe: inherit helper must fail from unsandboxed shell.
  set +e
  "$APP/Contents/Resources/RunSpecimenEngine/runspecimen" --version >/tmp/rs-mas-helper-shell.out 2>&1
  MAS_HELPER_RC=$?
  set -e
  if [[ "$MAS_HELPER_RC" -eq 0 ]]; then
    echo "ERROR: inherit-signed MAS helper ran from shell (expected non-zero)" >&2
    cat /tmp/rs-mas-helper-shell.out >&2
    exit 1
  fi
  echo "OK: MAS frozen helper bundle matches repo $REPO_VER (sandbox+inherit; shell rc=$MAS_HELPER_RC)"

  echo "==> Store export gate unit fixtures (fail-closed profile parse)"
  ./Scripts/test_store_export_gate.sh

  echo "==> Store export fail-closed without Apple Distribution"
  if ./Scripts/assert_store_export_ready.sh >/tmp/rs-export-gate.out 2>&1; then
    echo "NOTE: Apple Distribution appears present on this host — export gate opened"
    cat /tmp/rs-export-gate.out
  else
    grep -q 'STORE EXPORT BLOCKED' /tmp/rs-export-gate.out \
      || grep -qi 'Apple Distribution' /tmp/rs-export-gate.out \
      || {
        echo "ERROR: assert_store_export_ready should fail closed with a clear block message" >&2
        cat /tmp/rs-export-gate.out >&2
        exit 1
      }
    echo "OK: Store export blocked without Apple Distribution + team + profile"
  fi

  echo "==> MAS sandboxed app e2e (bookmark / dashboard / PTY wait)"
  # Prefer a sealed Archive product when present; build_app seals are structural but
  # Xcode Archive is the Store-shaped subject under test.
  if [[ -d /tmp/runspecimen-mas/RunSpecimen.xcarchive/Products/Applications/RunSpecimen.app ]]; then
    ./Scripts/test_mas_sandbox_e2e.sh /tmp/runspecimen-mas/RunSpecimen.xcarchive/Products/Applications/RunSpecimen.app
  else
    ./Scripts/test_mas_sandbox_e2e.sh "$APP"
  fi
else
  echo "PyInstaller absent — verifying --mas fails closed"
  if ./Scripts/build_app.sh --mas >/tmp/rs-mas-fail.out 2>&1; then
    echo "ERROR: --mas should fail without PyInstaller" >&2
    cat /tmp/rs-mas-fail.out >&2
    exit 1
  fi
  grep -Eiq 'requires a frozen|PyInstaller required|ERROR' /tmp/rs-mas-fail.out
  echo "OK: --mas fail-closed without PyInstaller"
fi

# Restore CI-default package-tree helper so a subsequent local open matches smoke.
./Scripts/stage_helper.sh --from-src --verify >/dev/null
./Scripts/build_app.sh >/dev/null

echo "SMOKE OK"
