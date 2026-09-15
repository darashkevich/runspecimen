#!/usr/bin/env bash
# Optional PyInstaller freeze of the RunSpecimen CLI into Helpers/payload/.
#
# Default: no-op / skip when PyInstaller is missing (CI-safe).
# Enable explicitly:
#   RS_FREEZE_HELPER=1 ./Scripts/freeze_helper.sh
#   ./Scripts/freeze_helper.sh --enable
#
# Without Developer ID signing the frozen binary is local-smoke only.
# Prefer ./Scripts/stage_helper.sh --from-src for daily Prefer Bundled Helper tests.
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

usage() {
  cat <<'EOF'
Usage: ./Scripts/freeze_helper.sh [--enable] [--verify] [-h]

  --enable   Attempt a PyInstaller onefile freeze (or set RS_FREEZE_HELPER=1).
  --verify   After freeze, run payload/runspecimen --version.
  -h         Show help.

Without --enable / RS_FREEZE_HELPER=1 this script exits 0 after printing blockers
so CI and default smoke stay green when PyInstaller is absent.

Blockers (current):
  - PyInstaller not bundled as a repo dependency (optional local install only)
  - Frozen Mach-O still needs Developer ID + helper inherit entitlements to ship
  - CPython NOTICE attribution required before redistributing a freeze
  - --from-src package tree remains the supported Prefer Bundled Helper path
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable) ENABLE=1; shift ;;
    --verify) VERIFY=1; shift ;;
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
  print_blockers
  exit 0
fi

if ! PYI="$(find_pyinstaller)"; then
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

This binary embeds a CPython runtime via PyInstaller. Before redistribution:
  - Attribute PyInstaller bootloader (Apache-2.0) and bundled CPython licenses
  - Codesign with Entitlements/RunSpecimen.helper.entitlements (inherit)
  - Notarize with Developer ID (see NOTARIZATION.md)

Local Prefer Bundled Helper smoke does not require notarization.
EOF

echo "Staged frozen helper: $DEST"
ls -la "$DEST"

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
