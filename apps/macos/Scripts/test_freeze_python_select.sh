#!/usr/bin/env bash
# MAS freeze must not select Apple/Xcode Python, and the chosen interpreter
# must remain visible after discovery (not trapped in a command substitution).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HELPER="$ROOT/Scripts/freeze_helper.sh"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

run_select() {
  # shellcheck disable=SC2091
  env -u RS_FREEZE_PYTHON "$@" bash "$HELPER" --enable --require
}

echo "==> Apple/Xcode Python on PATH is refused without an unbound-variable crash"
apple_out="$(mktemp)"
if [[ -x /usr/bin/python3 ]]; then
  set +e
  run_select RS_FREEZE_SELECT_ONLY=1 PATH="/usr/bin:/bin:/usr/sbin" >"$apple_out" 2>&1
  apple_rc=$?
  set -e
  [[ "$apple_rc" -ne 0 ]] || fail "Apple PATH python was accepted: $(cat "$apple_out")"
  if grep -q 'unbound variable' "$apple_out"; then
    fail "selector crashed with unbound RS_FREEZE_PYTHON: $(cat "$apple_out")"
  fi
  if grep -q 'Explicit MAS freeze runtime' "$apple_out"; then
    fail "Apple Python reached the MAS runtime gate: $(cat "$apple_out")"
  fi
  grep -Eq 'non-Apple CPython|Apple-provided Python|CPython 3.12' "$apple_out" \
    || fail "missing fail-closed reason: $(cat "$apple_out")"
  echo "OK: Apple Python refused"
else
  echo "skip: /usr/bin/python3 absent"
fi

echo "==> non-Apple Python 3.12 with PyInstaller is selected without a preset RS_FREEZE_PYTHON"
donor="${RS_FREEZE_PYTHON:-}"
if [[ -z "$donor" || ! -x "$donor" ]]; then
  donor=""
fi
if [[ -n "$donor" ]] && ! "$donor" -c 'import PyInstaller' >/dev/null 2>&1; then
  donor=""
fi
if [[ -z "$donor" ]] && command -v python3.12 >/dev/null 2>&1; then
  cand="$(command -v python3.12)"
  if "$cand" -c 'import sys,PyInstaller; raise SystemExit(0 if sys.version_info>=(3,12) else 1)' >/dev/null 2>&1; then
    donor="$cand"
  fi
fi
if [[ -z "$donor" ]]; then
  echo "skip: no non-Apple CPython 3.12 with PyInstaller"
else
  bindir="$(mktemp -d)"
  # A symlink outside the venv drops pyvenv.cfg. Exec the real interpreter.
  cat >"$bindir/python3.12" <<EOF
#!/bin/sh
exec $(printf '%q' "$donor") "\$@"
EOF
  chmod +x "$bindir/python3.12"
  good_out="$(mktemp)"
  # /usr/bin stays on PATH for dirname; python3.12 in bindir is searched first.
  run_select RS_FREEZE_SELECT_ONLY=1 PATH="$bindir:/usr/bin:/bin" >"$good_out"
  resolved="$(tail -n 1 "$good_out")"
  [[ "$resolved" == "$bindir/python3.12" ]] || fail "selected $resolved, expected wrapper ($(cat "$good_out"))"
  grep -q 'Explicit MAS freeze runtime' "$good_out" || fail "runtime gate did not run: $(cat "$good_out")"
  grep -Eq '/Applications/Xcode|/System/Library/|/Library/Developer/' "$good_out" \
    && fail "selected an Apple prefix: $(cat "$good_out")"
  grep -q '3.12' "$good_out" || fail "runtime is not CPython 3.12: $(cat "$good_out")"
  echo "OK: selected $resolved"
fi

echo "==> explicit Apple RS_FREEZE_PYTHON is refused"
if [[ -x /usr/bin/python3 ]]; then
  prefix="$(/usr/bin/python3 -c 'import sys; print(sys.base_prefix)')"
  case "$prefix" in
    /Applications/Xcode*|/Library/Developer/*|/System/Library/*)
      bad_out="$(mktemp)"
      set +e
      RS_FREEZE_PYTHON="/usr/bin/python3" RS_FREEZE_SELECT_ONLY=1 \
        bash "$HELPER" --enable --require >"$bad_out" 2>&1
      bad_rc=$?
      set -e
      [[ "$bad_rc" -ne 0 ]] || fail "explicit Apple python was accepted: $(cat "$bad_out")"
      grep -Eq 'Apple-provided Python|CPython 3.12' "$bad_out" \
        || fail "explicit Apple python missing reason: $(cat "$bad_out")"
      echo "OK: explicit Apple RS_FREEZE_PYTHON refused"
      ;;
    *)
      echo "skip: /usr/bin/python3 is not an Apple prefix ($prefix)"
      ;;
  esac
fi

echo "OK: freeze interpreter selection"
