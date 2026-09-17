#!/usr/bin/env bash
# Mac App Store export — fail closed unless Apple Distribution + team + profile.
# Developer ID is not sufficient. Does not Submit for Review.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ARCHIVE_PATH="${RS_ARCHIVE_PATH:-/tmp/runspecimen-mas/RunSpecimen.xcarchive}"
EXPORT_DIR="${RS_EXPORT_DIR:-/tmp/runspecimen-mas/export-mas}"
EXPORT_PLIST="${RS_EXPORT_OPTIONS_PLIST:-$ROOT/Config/ExportOptions.mas.plist}"

echo "==> assert_store_export_ready (fail closed)"
READY_OUT="$(./Scripts/assert_store_export_ready.sh)"
echo "$READY_OUT"
TEAM="$(printf '%s\n' "$READY_OUT" | awk -F= '/^READY_TEAM=/{print $2; exit}')"

# Keep ExportOptions teamID in sync when still placeholder (local only; do not commit secrets).
PLIST_TEAM="$(/usr/libexec/PlistBuddy -c 'Print :teamID' "$EXPORT_PLIST" 2>/dev/null || true)"
if [[ "$PLIST_TEAM" == "TEAMID" && -n "$TEAM" ]]; then
  echo "Updating local ExportOptions.mas.plist teamID → $TEAM (operator machine only)"
  /usr/libexec/PlistBuddy -c "Set :teamID $TEAM" "$EXPORT_PLIST"
fi

[[ -d "$ARCHIVE_PATH" ]] || {
  echo "ERROR: archive missing at $ARCHIVE_PATH — run ./Scripts/archive_mas.sh first" >&2
  exit 1
}

rm -rf "$EXPORT_DIR"
mkdir -p "$EXPORT_DIR"

echo "==> xcodebuild -exportArchive (App Store Connect)"
xcodebuild -exportArchive \
  -archivePath "$ARCHIVE_PATH" \
  -exportPath "$EXPORT_DIR" \
  -exportOptionsPlist "$EXPORT_PLIST"

echo "EXPORT OK → $EXPORT_DIR"
echo "Upload may continue via Transporter / Xcode. Do NOT Submit for Review without Codex QA + Yahor decision."
