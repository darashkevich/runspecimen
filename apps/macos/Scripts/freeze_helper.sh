#!/usr/bin/env bash
# PyInstaller freeze of the RunSpecimen CLI into Helpers/payload/.
#
# Default: no-op / skip when PyInstaller is missing (CI-safe) unless --require / RS_MAS_BUILD=1.
# Enable explicitly:
#   RS_FREEZE_HELPER=1 ./Scripts/freeze_helper.sh
#   ./Scripts/freeze_helper.sh --enable
#   ./Scripts/freeze_helper.sh --enable --require   # MAS: fail if freeze impossible
#   ./Scripts/build_app.sh --mas                    # primary Store path (calls --require)
#
# MAS uses **onedir** (not onefile): App Sandbox denies SysV semaphores that the
# onefile bootloader needs (`semctl: Operation not permitted`). onedir keeps a
# Mach-O entrypoint + `_internal/` runtime next to it — still no host Python.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
PAYLOAD="$ROOT/Helpers/payload"
DEST="$PAYLOAD/runspecimen"
DEST_INTERNAL="$PAYLOAD/_internal"
SPEC_DIR="$ROOT/build/pyinstaller"
WORKDIR="$SPEC_DIR/work"
DIST="$SPEC_DIR/dist"

ENABLE="${RS_FREEZE_HELPER:-0}"
VERIFY=0
REQUIRE=0
if [[ "${RS_MAS_BUILD:-0}" == "1" ]]; then
  REQUIRE=1
  ENABLE=1
fi

usage() {
  cat <<'EOF'
Usage: ./Scripts/freeze_helper.sh [--enable] [--verify] [--require] [-h]

  --enable   Attempt a PyInstaller onedir freeze (or set RS_FREEZE_HELPER=1).
  --verify   After freeze, run payload/runspecimen --version.
  --require  Fail (exit 1) if PyInstaller is missing or freeze fails (MAS path).
             Also set by RS_MAS_BUILD=1.
  -h         Show help.

Without --enable / RS_FREEZE_HELPER=1 this script exits 0 after printing blockers
so CI and default smoke stay green when PyInstaller is absent — unless --require.

MAS Store builds (./Scripts/build_app.sh --mas) always --require a Mach-O freeze.
Local Prefer Bundled Helper may still use --from-src (host Python).

Note: onefile is intentionally NOT used — its bootloader needs ipc-sysv-sem,
which App Sandbox denies. onedir is the sandbox-compatible layout.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable) ENABLE=1; shift ;;
    --verify) VERIFY=1; shift ;;
    --require) REQUIRE=1; ENABLE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

find_pyinstaller() {
  if command -v pyinstaller >/dev/null 2>&1; then
    command -v pyinstaller
    return 0
  fi
  if python3 -c 'import PyInstaller' 2>/dev/null; then
    printf '%s\n' "python3 -m PyInstaller"
    return 0
  fi
  return 1
}

print_blockers() {
  cat <<EOF
freeze_helper: skipped (optional).

Why this is not the default Prefer Bundled Helper path:
  1. PyInstaller is not a RunSpecimen dependency — install locally only when experimenting.
  2. No Developer ID certificate on many contributor Macs — cannot notarize a frozen helper.
  3. Freeze ships a CPython runtime; NOTICE / license audit still required for MAS.
  4. Supported local path: ./Scripts/stage_helper.sh --from-src --verify

Enable later:
  python3 -m pip install --user 'pyinstaller>=6'
  RS_FREEZE_HELPER=1 ./Scripts/freeze_helper.sh --verify
  ./Scripts/build_app.sh
EOF
}

if [[ "$ENABLE" != "1" ]]; then
  if [[ "$REQUIRE" == "1" ]]; then
    echo "freeze_helper: --require needs --enable / RS_FREEZE_HELPER=1 / RS_MAS_BUILD=1" >&2
    exit 1
  fi
  print_blockers
  exit 0
fi

if ! PYI="$(find_pyinstaller)"; then
  if [[ "$REQUIRE" == "1" ]]; then
    echo "freeze_helper: PyInstaller required for MAS / --require but not installed." >&2
    print_blockers
    exit 1
  fi
  echo "freeze_helper: PyInstaller not installed; skipping (exit 0)." >&2
  print_blockers
  exit 0
fi

if [[ ! -f "$REPO/src/runspecimen/__main__.py" && ! -f "$REPO/src/runspecimen/cli.py" ]]; then
  echo "Missing runspecimen package under $REPO/src/runspecimen" >&2
  exit 1
fi

mkdir -p "$PAYLOAD" "$WORKDIR" "$DIST"
rm -rf "$DIST" "$WORKDIR"
mkdir -p "$DIST" "$WORKDIR"

echo "==> PyInstaller onedir freeze (App Sandbox–compatible; not onefile)"
echo "    tool: $PYI"
TRAMPOLINE="$WORKDIR/runspecimen_main.py"
cat >"$TRAMPOLINE" <<'PY'
from runspecimen.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
PY

# shellcheck disable=SC2086
$PYI \
  --noconfirm \
  --clean \
  --onedir \
  --name runspecimen \
  --paths "$REPO/src" \
  --distpath "$DIST" \
  --workpath "$WORKDIR" \
  --specpath "$SPEC_DIR" \
  --console \
  "$TRAMPOLINE"

ONEDIR_APP="$DIST/runspecimen/runspecimen"
ONEDIR_INTERNAL="$DIST/runspecimen/_internal"
if [[ ! -x "$ONEDIR_APP" ]]; then
  echo "PyInstaller did not produce $ONEDIR_APP" >&2
  exit 1
fi
if [[ ! -d "$ONEDIR_INTERNAL" ]]; then
  echo "PyInstaller onedir missing _internal at $ONEDIR_INTERNAL" >&2
  exit 1
fi

# Drop any previous package-tree / onefile payload so build_app does not mix modes.
rm -rf "$PAYLOAD/lib" "$DEST_INTERNAL"
rm -f "$DEST"
cp -f "$ONEDIR_APP" "$DEST"
chmod +x "$DEST"
# Preserve _internal next to the Mach-O (PyInstaller layout).
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "$ONEDIR_INTERNAL/" "$DEST_INTERNAL/"
else
  cp -R "$ONEDIR_INTERNAL" "$DEST_INTERNAL"
fi
cat >"$PAYLOAD/NOTICE.txt" <<EOF
RunSpecimen helper payload (PyInstaller onedir freeze)
======================================================

Frozen on: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Host: $(uname -srm)
Tool: $PYI
Layout: onedir (runspecimen + _internal/) — required for App Sandbox

Onefile is intentionally avoided: the onefile bootloader uses SysV semaphores
(semctl) which macOS App Sandbox denies. This onedir layout keeps a self-contained
Mach-O entrypoint with a private CPython runtime under _internal/ (no host Python).

Before Mac App Store / redistribution:
  - Attribute PyInstaller bootloader (Apache-2.0) and bundled CPython licenses
  - Codesign helper + nested Mach-Os (see sign_nested_helper.sh)
  - Sign the app with Apple Distribution (MAS) or Developer ID (direct)
  - App Sandbox confines the UI + inherit helper — it does NOT OS-sandbox the payload
  - Never auto-type APPROVE; approval stays on a real human PTY

Local Prefer Bundled Helper smoke does not require Store signing.
EOF

# App Store rejects PyInstaller's copied CPython framework because its
# Info.plist still says CFBundleIdentifier=com.apple.python3.
python3 - "$DEST_INTERNAL" <<'PY'
import pathlib, plistlib, sys
root = pathlib.Path(sys.argv[1])
changed = 0
for p in root.rglob("Info.plist"):
    try:
        data = plistlib.loads(p.read_bytes())
    except Exception:
        continue
    bid = data.get("CFBundleIdentifier")
    if not isinstance(bid, str):
        continue
    if bid == "com.apple.python3" or bid.startswith("com.apple.python"):
        data["CFBundleIdentifier"] = "com.darashkevich.runspecimen.python3"
        p.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_XML))
        print(f"Rewrote Apple-namespace bundle id {bid} → com.darashkevich.runspecimen.python3 ({p})")
        changed += 1
    elif bid.startswith("com.apple."):
        raise SystemExit(f"Refusing leftover Apple-namespace bundle id {bid} in {p}")
if changed:
    print(f"Rewrote {changed} PyInstaller Python framework Info.plist(s)")
PY

echo "Staged frozen helper: $DEST"
echo "Staged runtime:       $DEST_INTERNAL"
ls -la "$DEST"
du -sh "$DEST_INTERNAL" | awk '{print " _internal size: "$1}'
if ! file "$DEST" | grep -q 'Mach-O'; then
  echo "freeze_helper: expected Mach-O at $DEST" >&2
  file "$DEST" >&2 || true
  exit 1
fi
if [[ -d "$PAYLOAD/lib" ]]; then
  echo "freeze_helper: refusing mixed payload (lib/ present after freeze)" >&2
  exit 1
fi

if [[ "$VERIFY" -eq 1 ]]; then
  echo "==> $DEST --version"
  OUT="$("$DEST" --version 2>&1)" || {
    echo "Frozen helper --version failed:" >&2
    echo "$OUT" >&2
    exit 1
  }
  echo "$OUT"
  echo "$OUT" | grep -qi runspecimen
  echo "OK: frozen helper reports a RunSpecimen version"
fi

echo "Next: ./Scripts/build_app.sh  # copies into Contents/Helpers/"
