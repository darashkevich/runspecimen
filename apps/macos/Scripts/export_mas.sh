#!/usr/bin/env bash
# Mac App Store export — fail closed unless Apple Distribution + team + profile.
# Developer ID is not sufficient. Does not Submit for Review.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ARCHIVE_PATH="${RS_ARCHIVE_PATH:-/tmp/runspecimen-mas/RunSpecimen.xcarchive}"
EXPORT_DIR="${RS_EXPORT_DIR:-/tmp/runspecimen-mas/export-mas}"
EXPORT_PLIST="${RS_EXPORT_OPTIONS_PLIST:-$ROOT/Config/ExportOptions.mas.plist}"

[[ -d "$ARCHIVE_PATH" ]] || {
  echo "ERROR: archive missing at $ARCHIVE_PATH — run ./Scripts/archive_mas.sh first" >&2
  exit 1
}

# Test-only codesign fixtures must never satisfy production export.
if [[ -n "${RS_TEST_CODESIGN_DV_APP_FILE:-}" \
   || -n "${RS_TEST_CODESIGN_DV_HELPER_FILE:-}" \
   || -n "${RS_ALLOW_TEST_CODESIGN_DV:-}" ]]; then
  echo "ERROR: RS_TEST_CODESIGN_DV_* / RS_ALLOW_TEST_CODESIGN_DV are test-only and are refused by export_mas.sh" >&2
  exit 1
fi

canon_dir() {
  (cd "$1" && pwd -P)
}

# App path is derived exclusively from the archive being exported.
# A separate RS_ARCHIVE_APP override cannot satisfy the gate for a different archive.
DERIVED_APP="$ARCHIVE_PATH/Products/Applications/RunSpecimen.app"
[[ -d "$DERIVED_APP" ]] || {
  echo "ERROR: archived app missing at $DERIVED_APP (under RS_ARCHIVE_PATH=$ARCHIVE_PATH)" >&2
  exit 1
}
DERIVED_CANON="$(canon_dir "$DERIVED_APP")"

if [[ -n "${RS_ARCHIVE_APP:-}" ]]; then
  [[ -d "$RS_ARCHIVE_APP" ]] || {
    echo "ERROR: RS_ARCHIVE_APP is not a directory: $RS_ARCHIVE_APP" >&2
    exit 1
  }
  OVERRIDE_CANON="$(canon_dir "$RS_ARCHIVE_APP")"
  if [[ "$OVERRIDE_CANON" != "$DERIVED_CANON" ]]; then
    echo "ERROR: RS_ARCHIVE_APP ($OVERRIDE_CANON) must equal app inside RS_ARCHIVE_PATH ($DERIVED_CANON). Refusing mismatched override (export-gate bypass)." >&2
    exit 1
  fi
fi

export RS_ARCHIVE_APP="$DERIVED_APP"
# Belt-and-suspenders: never leak test fixtures into the store-export gate.
unset RS_TEST_CODESIGN_DV_APP_FILE RS_TEST_CODESIGN_DV_HELPER_FILE RS_ALLOW_TEST_CODESIGN_DV

echo "==> assert_store_export_ready (fail closed; RS_ARCHIVE_PATH=$ARCHIVE_PATH RS_ARCHIVE_APP=$RS_ARCHIVE_APP)"
READY_OUT="$(RS_ARCHIVE_PATH="$ARCHIVE_PATH" ./Scripts/assert_store_export_ready.sh)"
echo "$READY_OUT"
TEAM="$(printf '%s\n' "$READY_OUT" | awk -F= '/^READY_TEAM=/{print $2; exit}')"

# Keep ExportOptions teamID in sync when still placeholder (local only; do not commit secrets).
PLIST_TEAM="$(/usr/libexec/PlistBuddy -c 'Print :teamID' "$EXPORT_PLIST" 2>/dev/null || true)"
if [[ "$PLIST_TEAM" == "TEAMID" && -n "$TEAM" ]]; then
  echo "Updating local ExportOptions.mas.plist teamID → $TEAM (operator machine only)"
  /usr/libexec/PlistBuddy -c "Set :teamID $TEAM" "$EXPORT_PLIST"
fi

rm -rf "$EXPORT_DIR"
mkdir -p "$EXPORT_DIR"

echo "==> xcodebuild -exportArchive (App Store Connect)"
xcodebuild -exportArchive \
  -archivePath "$ARCHIVE_PATH" \
  -exportPath "$EXPORT_DIR" \
  -exportOptionsPlist "$EXPORT_PLIST"

echo "EXPORT OK → $EXPORT_DIR"
echo "Upload may continue via Transporter / Xcode. Do NOT Submit for Review without Codex QA + Yahor decision."
