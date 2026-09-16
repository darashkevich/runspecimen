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
# MAS Store builds MUST use a frozen Mach-O (no host Python). Local/CI may use --from-src.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
PAYLOAD="$ROOT/Helpers/payload"
DEST="$PAYLOAD/runspecimen"
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

  --enable   Attempt a PyInstaller onefile freeze (or set RS_FREEZE_HELPER=1).
  --verify   After freeze, run payload/runspecimen --version.
  --require  Fail (exit 1) if PyInstaller is missing or freeze fails (MAS path).
             Also set by RS_MAS_BUILD=1.
  -h         Show help.

Without --enable / RS_FREEZE_HELPER=1 this script exits 0 after printing blockers
so CI and default smoke stay green when PyInstaller is absent — unless --require.

MAS Store builds (./Scripts/build_app.sh --mas) always --require a Mach-O freeze.
Local Prefer Bundled Helper may still use --from-src (host Python).
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

echo "==> PyInstaller onefile freeze (local experiment)"
echo "    tool: $PYI"
# Entry via -m runspecimen requires a tiny trampoline for onefile.
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
  --onefile \
  --name runspecimen \
  --paths "$REPO/src" \
  --distpath "$DIST" \
  --workpath "$WORKDIR" \
  --specpath "$SPEC_DIR" \
  --console \
  "$TRAMPOLINE"

if [[ ! -x "$DIST/runspecimen" ]]; then
  echo "PyInstaller did not produce $DIST/runspecimen" >&2
  exit 1
fi

# Drop any previous package-tree payload so build_app does not mix modes.
rm -rf "$PAYLOAD/lib"
cp -f "$DIST/runspecimen" "$DEST"
chmod +x "$DEST"
cat >"$PAYLOAD/NOTICE.txt" <<EOF
RunSpecimen helper payload (PyInstaller freeze)
===============================================

Frozen on: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Host: $(uname -srm)
Tool: $PYI

This binary embeds a CPython runtime via PyInstaller. Before Mac App Store /
redistribution:
  - Attribute PyInstaller bootloader (Apache-2.0) and bundled CPython licenses
    (ship Helpers/NOTICE.txt inside the .app; keep CPython license texts with the build)
  - Codesign helper with Entitlements/RunSpecimen.helper.entitlements (inherit)
  - Sign the app with Apple Distribution (MAS) or Developer ID (direct)
  - App Sandbox confines the UI + inherit helper — it does NOT OS-sandbox the payload
  - Never auto-type APPROVE; approval stays on a real human PTY

Local Prefer Bundled Helper smoke does not require Store signing.
EOF

echo "Staged frozen helper: $DEST"
ls -la "$DEST"
if ! file "$DEST" | grep -q 'Mach-O'; then
  echo "freeze_helper: expected Mach-O at $DEST" >&2
  file "$DEST" >&2 || true
  exit 1
fi
# Ensure no leftover package-tree lib/ for MAS self-containment.
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
