#!/bin/bash
# Per-invocation evidence directories for isolated holder and macOS smoke runs.
# Sourcing this file does not create a directory, run swift, install, or
# contact a holder daemon.

rs_evidence_create() {
  local prefix="${1:-}"
  if [[ ! "$prefix" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$ ]]; then
    echo "REFUSED: evidence prefix" >&2
    return 2
  fi
  local root="${TMPDIR:-/tmp}"
  root="${root%/}"
  if [[ ! -d "$root" ]]; then
    echo "REFUSED: evidence root is not a directory" >&2
    return 2
  fi
  mktemp -d "${root}/${prefix}.XXXXXX"
}

rs_evidence_cleanup() {
  local target="${1:-}"
  local prefix="${2:-}"
  if [[ -z "$target" || -z "$prefix" ]]; then
    echo "REFUSED: cleanup needs the directory this invocation created" >&2
    return 2
  fi
  if [[ ! "$prefix" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$ ]]; then
    echo "REFUSED: evidence prefix" >&2
    return 2
  fi
  if [[ -L "$target" || ! -d "$target" ]]; then
    echo "REFUSED: cleanup target is not a directory created for this invocation" >&2
    return 2
  fi
  local root="${TMPDIR:-/tmp}"
  root="${root%/}"
  local parent_resolved root_resolved base
  parent_resolved="$(cd "$(dirname "$target")" && pwd -P)"
  root_resolved="$(cd "$root" && pwd -P)"
  base="$(basename "$target")"
  if [[ "$parent_resolved" != "$root_resolved" ]]; then
    echo "REFUSED: cleanup target is outside this invocation's evidence root" >&2
    return 2
  fi
  if [[ "$parent_resolved/$base" == "$root_resolved" || "$base" == "$prefix" ]]; then
    echo "REFUSED: cleanup would remove a shared directory" >&2
    return 2
  fi
  local suffix="${base#"$prefix".}"
  if [[ "$base" != "$prefix.$suffix" || ! "$suffix" =~ ^[A-Za-z0-9]{6,}$ ]]; then
    echo "REFUSED: cleanup target is not this invocation's evidence directory" >&2
    return 2
  fi
  rm -rf -- "$target"
}

# Copy regular files (the logs) to a new exclusive directory. Skip subdirectories
# such as a Swift scratch path so a failure does not duplicate a build tree.
# Prints the kept directory. Does not delete the source.
rs_evidence_preserve_files() {
  local source="${1:-}"
  local prefix="${2:-}"
  if [[ -z "$source" || -L "$source" || ! -d "$source" ]]; then
    echo "REFUSED: nothing to preserve" >&2
    return 2
  fi
  local dest copied=0 name
  dest="$(rs_evidence_create "$prefix")" || return 2
  for name in "$source"/*; do
    [[ -e "$name" ]] || continue
    if [[ -L "$name" || -d "$name" ]]; then
      continue
    fi
    cp -p "$name" "$dest/" || {
      echo "REFUSED: could not preserve $name" >&2
      return 2
    }
    copied=1
  done
  if [[ "$copied" -ne 1 ]]; then
    rs_evidence_cleanup "$dest" "$prefix" || true
    echo "REFUSED: no log files to preserve" >&2
    return 2
  fi
  printf '%s\n' "$dest"
}

rs_log_has_executed_tests() {
  local log="${1:-}"
  [[ -f "$log" && ! -L "$log" ]] || return 1
  grep -E 'Executed [1-9][0-9]* tests?' "$log" >/dev/null
}

# Prints ok, retry, or assertion. A non-zero first pass retries only for
# Apple codesign detritus with no XCTest or Swift Testing assertion in the log.
rs_smoke_first_pass_disposition() {
  local rc="${1:-1}"
  local log="${2:-}"
  local codesign_re='resource fork, Finder information, or similar detritus not allowed|code object is not signed at path|code object is not signed at all'
  local assertion_re='XCTAssert|error: -\[.*\] : |Test Case .* failed|Issue recorded'
  if [[ "$rc" -eq 0 ]]; then
    printf '%s\n' ok
    return 0
  fi
  if [[ -f "$log" && ! -L "$log" ]] \
     && grep -E "$codesign_re" "$log" >/dev/null 2>&1 \
     && ! grep -E "$assertion_re" "$log" >/dev/null 2>&1; then
    printf '%s\n' retry
    return 0
  fi
  printf '%s\n' assertion
}
