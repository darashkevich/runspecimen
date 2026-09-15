#!/usr/bin/env bash
# Stage an optional runspecimen helper into Helpers/payload for bundling.
#
# Preferred local / Developer ID path (legally clear):
#   ./Scripts/stage_helper.sh --from-src
# Copies the Apache-2.0 stdlib-only package tree + a launcher that uses a host
# Python 3.9+. No third-party Python deps; no PyInstaller runtime in the bundle.
#
# Dry-run / experiment:
#   ./Scripts/stage_helper.sh --from "$(command -v runspecimen)"
# Copies an existing executable as-is (shebang may be machine-local).
#
# Full MAS freeze (optional later): PyInstaller onefile — see LICENSE NOTES below.
# Never commit Helpers/payload/ artifacts. Never auto-type APPROVE.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
HELPERS="$ROOT/Helpers"
PAYLOAD="$HELPERS/payload"
DEST="$PAYLOAD/runspecimen"
LIB="$PAYLOAD/lib"
NOTICE="$PAYLOAD/NOTICE.txt"
SRC_PKG="$REPO/src/runspecimen"

mkdir -p "$PAYLOAD"

usage() {
  cat <<'EOF'
Usage: ./Scripts/stage_helper.sh [options]

  --from-src        Stage relocatable package tree from repo src/runspecimen
                    + launcher (host Python 3.9+). Recommended for local tests.
  --from PATH       Copy an existing runspecimen executable into payload/
                    (local experiment; absolute shebangs may not relocate).
  --check           Exit 0 if payload/runspecimen is executable; else 1.
  --verify          Run staged helper --version (requires host Python for --from-src).
  -h, --help        Show this help.

Without flags, creates Helpers/payload/ and prints packaging steps + license notes.
EOF
}

cmd_check() {
  if [[ -x "$DEST" ]]; then
    echo "OK: staged helper at $DEST"
    ls -la "$DEST"
    if [[ -d "$LIB/runspecimen" ]]; then
      echo "OK: package tree at $LIB/runspecimen"
    fi
    exit 0
  fi
  echo "No executable helper at $DEST (expected until packaging lands)."
  exit 1
}

cmd_verify() {
  if [[ ! -x "$DEST" ]]; then
    echo "No staged helper to verify at $DEST" >&2
    exit 1
  fi
  echo "==> $DEST --version"
  OUT="$("$DEST" --version 2>&1)" || {
    echo "Helper --version failed:" >&2
    echo "$OUT" >&2
    exit 1
  }
  echo "$OUT"
  echo "$OUT" | grep -qi runspecimen
  echo "OK: staged helper reports a RunSpecimen version"
}

write_launcher() {
  cat >"$DEST" <<'LAUNCHER'
#!/usr/bin/env bash
# Bundled RunSpecimen helper — Apache-2.0 package tree under lib/ (stdlib only).
# Uses a host Python 3.9+ interpreter. For a fully self-contained MAS binary,
# freeze with PyInstaller later (see Helpers/README.md). Never auto-types APPROVE.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$HERE/lib${PYTHONPATH:+:$PYTHONPATH}"

pick_python() {
  local c
  # Absolute fallbacks first — App Sandbox children sometimes see a stripped PATH.
  for c in \
    /usr/bin/python3 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3
  do
    if [[ "$c" == /* ]]; then
      [[ -x "$c" ]] || continue
    else
      command -v "$c" >/dev/null 2>&1 || continue
    fi
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 1
}

PY="$(pick_python)" || {
  echo "runspecimen helper: need Python 3.9+ on PATH (bundled package is stdlib-only)." >&2
  exit 127
}
exec "$PY" -m runspecimen "$@"
LAUNCHER
  chmod +x "$DEST"
}

write_notice() {
  cat >"$NOTICE" <<EOF
RunSpecimen helper payload
==========================

This directory stages a local copy of the RunSpecimen CLI package for embedding
under RunSpecimen.app/Contents/Helpers (ADR-002).

License: Apache License 2.0 (same as https://github.com/darashkevich/runspecimen)
Python dependencies: none (stdlib only) — see pyproject.toml dependencies = []

Host Python: the --from-src launcher requires a system/user Python 3.9+ on PATH.
That is intentional for local / Developer ID experiments without shipping a
frozen interpreter. A future PyInstaller (or equivalent) freeze may replace the
launcher for Mac App Store self-containment; audit bootloader + CPython notices
before redistributing a freeze.

Invariants preserved by the helper:
  - No product telemetry / phone-home
  - Interactive TTY approval (never auto-type APPROVE)
  - Receipts remain hash-chained / HMAC — not asymmetric digital signatures

Staged: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Source package: $SRC_PKG
EOF
}

stage_from_src() {
  if [[ ! -d "$SRC_PKG" ]]; then
    echo "Missing package sources at $SRC_PKG" >&2
    exit 1
  fi
  if [[ ! -f "$SRC_PKG/__main__.py" && ! -f "$SRC_PKG/cli.py" ]]; then
    echo "Does not look like runspecimen package: $SRC_PKG" >&2
    exit 1
  fi

  rm -rf "$LIB"
  mkdir -p "$LIB"
  # Copy package without caches / junk.
  rsync -a --delete \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '*.pyo' \
    --exclude '.DS_Store' \
    "$SRC_PKG/" "$LIB/runspecimen/"

  # Ensure namespace package is importable.
  if [[ ! -f "$LIB/runspecimen/__init__.py" ]]; then
    echo "Copy failed — no __init__.py under $LIB/runspecimen" >&2
    exit 1
  fi

  write_launcher
  write_notice

  echo "Staged --from-src helper:"
  echo "  launcher: $DEST"
  echo "  package:  $LIB/runspecimen"
  echo "  notice:   $NOTICE"
  echo "Verify:     ./Scripts/stage_helper.sh --verify"
  echo "Rebuild:    ./Scripts/build_app.sh   # copies into Contents/Helpers/"
}

stage_from_path() {
  local FROM="$1"
  if [[ ! -x "$FROM" ]]; then
    echo "Not executable: $FROM" >&2
    exit 1
  fi
  rm -f "$DEST"
  # Drop any previous package tree so build_app does not mix modes.
  rm -rf "$LIB"
  cp -f "$FROM" "$DEST"
  chmod +x "$DEST"
  cat >"$NOTICE" <<EOF
RunSpecimen helper payload (copied executable)
==============================================

Copied from: $FROM
Staged: $(date -u +%Y-%m-%dT%H:%M:%SZ)

WARNING: console_script copies often embed an absolute shebang and depend on
that interpreter's site-packages. Prefer --from-src for a relocatable Apache-2.0
package tree. This mode is for local dry-run of Contents/Helpers discovery only.
EOF
  if head -1 "$DEST" | grep -q '^#!' && head -1 "$DEST" | grep -qv 'env '; then
    echo "Note: shebang looks absolute — may not relocate to other Macs." >&2
  fi
  echo "Staged helper: $DEST"
  echo "Rebuild with: ./Scripts/build_app.sh   # copies into Contents/Helpers/"
}

print_packaging_steps() {
  cat <<EOF
Helpers layout ready under:
  $HELPERS
  $PAYLOAD/   (gitignored — place experiments here)

LICENSE NOTES (why --from-src is the default packaging path)
  - RunSpecimen is Apache-2.0 with dependencies = [] (stdlib only).
  - Staging a copy of src/runspecimen + launcher redistributes only Apache-2.0
    project code; no third-party Python wheels to audit.
  - PyInstaller freeze is optional for MAS self-containment (bundles CPython).
    PyInstaller bootloader is Apache-2.0; still ship CPython + NOTICE attribution
    and re-audit before App Store submission. Not required for local Helpers tests.
    Optional script: RS_FREEZE_HELPER=1 ./Scripts/freeze_helper.sh (no-ops without
    PyInstaller so CI stays green).

Exact next packaging steps (ADR-002):
  1. Stage a helper (pick one):
       a) ./Scripts/stage_helper.sh --from-src          # recommended local path
       b) ./Scripts/stage_helper.sh --from \$(command -v runspecimen)  # dry-run copy
       c) RS_FREEZE_HELPER=1 ./Scripts/freeze_helper.sh --verify       # optional freeze
  2. ./Scripts/stage_helper.sh --verify   # (or freeze --verify)
  3. Codesign the helper with the same Team ID as the app using
       Entitlements/RunSpecimen.helper.entitlements (inherit), e.g.:
       codesign --force --options runtime --timestamp \\
         --entitlements Entitlements/RunSpecimen.helper.entitlements \\
         --sign \"\$IDENTITY\" Helpers/payload/runspecimen
  4. ./Scripts/build_app.sh   # copies payload → Contents/Helpers/
  5. Sign + notarize the whole .app (needs Developer ID):
       ./Scripts/sign_and_notarize.sh all
  6. Verify discovery: Engine → Prefer Bundled Helper → Source = “Bundled Helpers”
  7. Update APP_STORE.md review notes with helper path + demo steps.

Current status: --from-src package-tree staging implemented; freeze_helper optional
and CI-safe; Developer ID notarization still blocked without Apple certs.
EOF
}

FROM=""
FROM_SRC=0
CHECK=0
VERIFY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="${2:-}"; shift 2 ;;
    --from-src) FROM_SRC=1; shift ;;
    --check) CHECK=1; shift ;;
    --verify) VERIFY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "$CHECK" -eq 1 ]]; then
  cmd_check
fi

if [[ "$FROM_SRC" -eq 1 && -n "$FROM" ]]; then
  echo "Use either --from-src or --from PATH, not both." >&2
  exit 2
fi

if [[ "$FROM_SRC" -eq 1 ]]; then
  stage_from_src
  if [[ "$VERIFY" -eq 1 ]]; then
    cmd_verify
  fi
  exit 0
fi

if [[ -n "$FROM" ]]; then
  stage_from_path "$FROM"
  if [[ "$VERIFY" -eq 1 ]]; then
    cmd_verify
  fi
  exit 0
fi

if [[ "$VERIFY" -eq 1 ]]; then
  cmd_verify
  exit 0
fi

print_packaging_steps
