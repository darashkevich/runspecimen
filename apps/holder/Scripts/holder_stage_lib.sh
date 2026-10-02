#!/bin/bash
# Path checks for holder staging. Sourcing this file does not delete or install.
# A deletion runs only through safe_remove_build_dir, and only after the target
# passes refuse_dangerous_deletion_target.

refuse_dangerous_deletion_target() {
  local target="${1:-}"
  local repo="${2:-}"
  if [[ -z "$target" || "$target" == "/" || "$target" == "." ]]; then
    return 1
  fi
  if [[ -L "$target" ]]; then
    return 1
  fi
  local parent base resolved
  parent="$(dirname "$target")"
  base="$(basename "$target")"
  if [[ ! -d "$parent" || -L "$parent" ]]; then
    return 1
  fi
  resolved="$(cd "$parent" && pwd -P)/$base"
  case "$resolved" in
    /|/Users|/Users/*|/Applications|/Applications/*)
      return 1
      ;;
  esac
  if [[ -n "${HOME:-}" && ( "$resolved" == "$HOME" || "$resolved" == "$HOME"/* ) ]]; then
    return 1
  fi
  if [[ -n "$repo" && ( "$resolved" == "$repo" || "$resolved" == "$repo"/* ) ]]; then
    return 1
  fi
  case "$resolved" in
    /tmp/rs-holder-stage.*|/private/tmp/rs-holder-stage.*)
      return 0
      ;;
  esac
  return 1
}

safe_remove_build_dir() {
  local target="$1"
  local repo="$2"
  if ! refuse_dangerous_deletion_target "$target" "$repo"; then
    echo "REFUSING deletion: $target" >&2
    return 2
  fi
  rm -rf -- "$target"
}

create_unique_stage_dir() {
  mktemp -d /tmp/rs-holder-stage.XXXXXX
}
