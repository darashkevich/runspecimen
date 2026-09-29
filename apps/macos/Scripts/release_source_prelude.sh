#!/usr/bin/env bash
# Release source gate before helper freeze and Xcode project generation.
#
# RS_RELEASE_GATE=1 checks the caller's checkout first. A dirty tree or a
# commit other than RS_EXPECTED_GIT_COMMIT exits before freeze. A passing
# check creates a detached git worktree of that commit and continues there.
# Freeze and project generation consume that snapshot. A commit move or a
# dirty edit inside the snapshot fails the release. The caller's later edits
# are not the built source.
#
# The recorded snapshots are integrity records of git metadata the script
# read. They are not an independent cryptographic source attestation.
#
# Leave RS_RELEASE_GATE unset for a development build. That path freezes the
# tree in place and may be dirty. Export still rejects it.
#
# Orchestration tests set RS_PRELUDE_ONLY=1, RS_FREEZE_CMD, and
# RS_GENERATE_CMD. Production callers leave those unset.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
export RS_REPO="${RS_REPO:-$DEFAULT_REPO}"
VERIFY="$SCRIPT_DIR/verify_mas_runtime.py"

_RS_ISOLATED_REPO=""
_RS_ISOLATED_PARENT=""
_RS_ISOLATED_PATH=""

cleanup_isolated() {
  if [[ -n "$_RS_ISOLATED_PATH" && -n "$_RS_ISOLATED_REPO" ]]; then
    git -C "$_RS_ISOLATED_REPO" worktree remove --force "$_RS_ISOLATED_PATH" >/dev/null 2>&1 || true
  fi
  if [[ -n "$_RS_ISOLATED_PARENT" ]]; then
    rm -rf "$_RS_ISOLATED_PARENT"
  fi
}

run_freeze() {
  if [[ -n "${RS_FREEZE_CMD:-}" ]]; then
    bash -c "$RS_FREEZE_CMD"
  else
    (
      cd "$RS_REPO/apps/macos"
      RS_FREEZE_HELPER=1 RS_MAS_BUILD=1 ./Scripts/freeze_helper.sh --enable --require --verify
    )
  fi
}

run_generate() {
  if [[ -n "${RS_GENERATE_CMD:-}" ]]; then
    bash -c "$RS_GENERATE_CMD"
  else
    (
      cd "$RS_REPO/apps/macos"
      ./Scripts/generate_xcodeproj.sh
    )
  fi
}

require_expected_sha() {
  if [[ ! "${RS_EXPECTED_GIT_COMMIT:-}" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ERROR: RS_RELEASE_GATE requires RS_EXPECTED_GIT_COMMIT to be the reviewed 40-character SHA" >&2
    exit 1
  fi
}

snapshot_release() {
  python3 "$VERIFY" snapshot-source \
    --repo "$RS_REPO" \
    --out "$1" \
    --release-gate \
    --expected-commit "$RS_EXPECTED_GIT_COMMIT"
}

snapshot_observed() {
  python3 "$VERIFY" snapshot-source --repo "$RS_REPO" --out "$1"
}

isolate_and_reexec() {
  require_expected_sha
  local preflight
  preflight="$(mktemp)"
  python3 "$VERIFY" snapshot-source \
    --repo "$RS_REPO" \
    --out "$preflight" \
    --release-gate \
    --expected-commit "$RS_EXPECTED_GIT_COMMIT"
  rm -f "$preflight"

  _RS_ISOLATED_REPO="$RS_REPO"
  _RS_ISOLATED_PARENT="$(mktemp -d)"
  _RS_ISOLATED_PATH="$_RS_ISOLATED_PARENT/candidate"
  trap cleanup_isolated EXIT
  git -C "$RS_REPO" worktree add --detach "$_RS_ISOLATED_PATH" "$RS_EXPECTED_GIT_COMMIT"

  local status
  set +e
  if [[ "${RS_PRELUDE_ONLY:-}" == "1" ]]; then
    RS_RELEASE_ISOLATED=1 RS_REPO="$_RS_ISOLATED_PATH" "$SCRIPT_DIR/release_source_prelude.sh"
  else
    env -u RS_REPO RS_RELEASE_ISOLATED=1 "$_RS_ISOLATED_PATH/apps/macos/Scripts/archive_mas.sh"
  fi
  status=$?
  set -e
  exit "$status"
}

if [[ "${RS_RELEASE_GATE:-}" == "1" && "${RS_RELEASE_ISOLATED:-}" != "1" ]]; then
  isolate_and_reexec
fi

STATE_DIR="${RS_SOURCE_STATE_DIR:-$(mktemp -d)}"
mkdir -p "$STATE_DIR"

if [[ "${RS_RELEASE_GATE:-}" == "1" ]]; then
  echo "==> release source snapshot before helper freeze (isolated candidate; integrity record, not a source attestation)"
  snapshot_release "$STATE_DIR/source-before-freeze.json"
fi

echo "==> Ensure frozen Mach-O helper from this source tree"
run_freeze

if [[ "${RS_RELEASE_GATE:-}" == "1" ]]; then
  snapshot_observed "$STATE_DIR/source-after-freeze.json"
  python3 "$VERIFY" check-source-stable \
    --before "$STATE_DIR/source-before-freeze.json" \
    --after "$STATE_DIR/source-after-freeze.json"
fi

echo "==> Ensure Xcode project"
run_generate

if [[ "${RS_RELEASE_GATE:-}" == "1" ]]; then
  snapshot_observed "$STATE_DIR/source-after-generate.json"
  python3 "$VERIFY" check-source-stable \
    --before "$STATE_DIR/source-before-freeze.json" \
    --after "$STATE_DIR/source-after-generate.json"
fi
