#!/usr/bin/env bash
# Resolve nested codesign identity for Helpers/runspecimen.
#
# Prints two lines:
#   IDENTITY=<string>   # "-" for ad-hoc local smoke
#   MODE=<adhoc|development|distribution>
#
# Preference order:
#   1. RS_SIGN_IDENTITY (from env / Config/signing.env)
#   2. Xcode EXPANDED_CODE_SIGN_IDENTITY_NAME / CODE_SIGN_IDENTITY (when not "-")
#   3. Keychain: Apple Distribution | 3rd Party Mac Developer Application
#   4. Keychain: Developer ID Application (direct-download path)
#   5. Keychain: Apple Development (local device builds)
#   6. Ad-hoc "-" (local structural smoke only — clearly labeled by callers)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/Config/signing.env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
fi

classify() {
  local id="$1"
  case "$id" in
    -|"")
      echo adhoc
      ;;
    *"Apple Distribution"*|*"3rd Party Mac Developer Application"*|*"Developer ID Application"*)
      echo distribution
      ;;
    *"Apple Development"*|*"Mac Developer"*)
      echo development
      ;;
    *)
      # Hex CDHash-style expanded identity from Xcode — treat as non-adhoc.
      if [[ "$id" =~ ^[0-9A-Fa-f]{40}$ ]]; then
        echo development
      else
        echo distribution
      fi
      ;;
  esac
}

emit() {
  local identity="$1"
  local mode
  mode="$(classify "$identity")"
  echo "IDENTITY=$identity"
  echo "MODE=$mode"
}

# 1) Explicit override
if [[ -n "${RS_SIGN_IDENTITY:-}" ]]; then
  emit "$RS_SIGN_IDENTITY"
  exit 0
fi

# 2) Xcode build-settings (nested sign must follow the outer target identity)
for cand in \
  "${EXPANDED_CODE_SIGN_IDENTITY_NAME:-}" \
  "${CODE_SIGN_IDENTITY:-}" \
  "${EXPANDED_CODE_SIGN_IDENTITY:-}"
do
  if [[ -n "$cand" && "$cand" != "-" && "$cand" != "Sign to Run Locally" ]]; then
    emit "$cand"
    exit 0
  fi
done

# 3–5) Keychain scan
IDENTITIES="$(security find-identity -v -p codesigning 2>/dev/null || true)"
pick_quoted() {
  local pattern="$1"
  echo "$IDENTITIES" | grep -E "$pattern" | head -1 | sed -n 's/.*"\(.*\)".*/\1/p'
}

# grep exits 1 on no match — keep set -e from aborting the resolver.
line="$(pick_quoted 'Apple Distribution|3rd Party Mac Developer Application' || true)"
if [[ -n "$line" ]]; then
  emit "$line"
  exit 0
fi
line="$(pick_quoted 'Developer ID Application' || true)"
if [[ -n "$line" ]]; then
  emit "$line"
  exit 0
fi
line="$(pick_quoted 'Apple Development|Mac Developer' || true)"
if [[ -n "$line" ]]; then
  emit "$line"
  exit 0
fi

# 6) Ad-hoc local smoke
emit "-"
