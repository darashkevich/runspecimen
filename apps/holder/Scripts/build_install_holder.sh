#!/bin/bash
# Stage a separate RunSpecimen Holder package and, only with consent, copy it
# into a temp root. A real root install of /Applications still exits 4.
# This script does not replace /Applications/RunSpecimen.app or
# /Applications/RunSpecimen Holder.app.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
# shellcheck source=holder_stage_lib.sh
source "$ROOT/apps/holder/Scripts/holder_stage_lib.sh"

cmd="${1:-stage}"

refuse_consent() {
  echo "REFUSING: $cmd is a consented installed operation and was not run" >&2
  exit 4
}

resolved_dir() {
  local target="$1"
  if [[ -z "$target" || ! -d "$target" ]]; then
    return 1
  fi
  (cd "$target" && pwd -P)
}

assert_temp_root() {
  local root="$1"
  local resolved
  if [[ -L "$root" ]]; then
    refuse_consent
  fi
  resolved="$(resolved_dir "$root")" || refuse_consent
  case "$resolved" in
    /|/Applications|/Applications/*|"${HOME:-}"|"${HOME:-}"/*|"$ROOT"|"$ROOT"/*)
      refuse_consent
      ;;
    /tmp/*|/private/tmp/*) ;;
    *)
      refuse_consent
      ;;
  esac
  printf '%s\n' "$resolved"
}

assert_package() {
  local package="$1"
  local resolved
  if [[ -z "$package" || ! -d "$package" || -L "$package" ]]; then
    refuse_consent
  fi
  resolved="$(resolved_dir "$package")" || refuse_consent
  case "$resolved" in
    /Applications|/Applications/*) refuse_consent ;;
  esac
  printf '%s\n' "$resolved"
}

run_lifecycle() {
  if [[ "${RS_HOLDER_INSTALL_CONSENT:-}" != "yes" ]]; then
    refuse_consent
  fi
  local root package dest saved
  root="$(assert_temp_root "${RS_HOLDER_INSTALL_ROOT:-}")"
  package="$(assert_package "${RS_HOLDER_PACKAGE:-}")"
  dest="$root/RunSpecimen Holder.app"
  saved="$root/rollback/RunSpecimen Holder.app"
  case "$cmd" in
    install)
      if [[ -e "$dest" ]]; then
        refuse_consent
      fi
      cp -R "$package" "$dest"
      ;;
    update)
      if [[ ! -d "$dest" ]]; then
        refuse_consent
      fi
      rm -rf "$root/rollback"
      mkdir -p "$root/rollback"
      mv "$dest" "$saved"
      cp -R "$package" "$dest"
      ;;
    rollback)
      if [[ ! -d "$saved" ]]; then
        refuse_consent
      fi
      rm -rf "$dest"
      mv "$saved" "$dest"
      ;;
    uninstall)
      if [[ ! -d "$dest" ]]; then
        refuse_consent
      fi
      mkdir -p "$root/removed"
      rm -rf "$root/removed/RunSpecimen Holder.app"
      mv "$dest" "$root/removed/RunSpecimen Holder.app"
      ;;
  esac
  echo "LIFECYCLE=$cmd"
  echo "ROOT=$root"
  echo "NOT_LIVE=1"
  echo "NOT_INSTALLED=1"
}

case "$cmd" in
  install|update|rollback|uninstall)
    run_lifecycle
    exit 0
    ;;
  stage) ;;
  *)
    echo "REFUSING: unknown holder command: $cmd" >&2
    exit 2
    ;;
esac

if [[ -n "${HOLDER_BUILD_DIR:-}" ]]; then
  echo "REFUSING: HOLDER_BUILD_DIR is not used. Staging creates a unique directory." >&2
  exit 2
fi

BUILD="$(create_unique_stage_dir)"
APP="$BUILD/RunSpecimen Holder.app"
mkdir -p "$APP/Contents/MacOS" \
  "$APP/Contents/Resources/Runtime/bin" \
  "$APP/Contents/Resources/Python" \
  "$APP/Contents/Library/LaunchDaemons"

if [[ -z "${RS_HOLDER_RUNTIME_SOURCE:-}" || ! -f "$RS_HOLDER_RUNTIME_SOURCE" || -L "$RS_HOLDER_RUNTIME_SOURCE" ]]; then
  echo "REFUSING: RS_HOLDER_RUNTIME_SOURCE must be a regular interpreter file. /usr/bin/python3 is not a fallback." >&2
  exit 2
fi
layout_runnable() {
  local bin="$1"
  local dep rel dir target tdir line
  [[ -e "$bin" ]] || return 1
  dir="$(cd "$(dirname "$bin")" && pwd -P)"
  target="$(/usr/bin/realpath "$bin" 2>/dev/null || printf '%s' "$bin")"
  tdir="$(cd "$(dirname "$target")" && pwd -P)"
  while IFS= read -r line; do
    dep="${line%% (*}"
    dep="${dep#"${dep%%[![:space:]]*}"}"
    dep="${dep%"${dep##*[![:space:]]}"}"
    [[ -z "$dep" || "$dep" == *: ]] && continue
    case "$dep" in
      @executable_path/*)
        rel="${dep#@executable_path/}"
        if [[ ! -e "$dir/$rel" && ! -e "$tdir/$rel" ]]; then
          return 1
        fi
        ;;
      /usr/lib/*|/System/*) ;;
      /*)
        [[ -e "$dep" ]] || return 1
        ;;
    esac
  done < <(/usr/bin/otool -L "$bin" 2>/dev/null | /usr/bin/tail -n +2)
}

if [[ "$(/usr/bin/file -b "$RS_HOLDER_RUNTIME_SOURCE" 2>/dev/null || true)" == *"Mach-O"* ]]; then
  runner="${RS_HOLDER_BUNDLE_RUNNER:-}"
  if [[ -z "$runner" || ! -e "$runner" ]]; then
    echo "REFUSING: the source interpreter was not executed. Set RS_HOLDER_BUNDLE_RUNNER to the intact interpreter before bundle_runtime.py runs." >&2
    exit 2
  fi
  if ! layout_runnable "$runner"; then
    echo "REFUSING: the bundle runner layout is not runnable and the source interpreter was not executed." >&2
    exit 2
  fi
  "$runner" "$ROOT/apps/holder/Scripts/bundle_runtime.py" \
    --source "$RS_HOLDER_RUNTIME_SOURCE" \
    --dest "$APP/Contents/Resources/Runtime"
else
  cp "$RS_HOLDER_RUNTIME_SOURCE" "$APP/Contents/Resources/Runtime/bin/python3"
  chmod 755 "$APP/Contents/Resources/Runtime/bin/python3"
fi

if [[ "${RS_HOLDER_STAGE_FIXTURES:-}" == "1" ]]; then
  printf 'fixture\n' > "$APP/Contents/MacOS/RunSpecimenHolder"
  printf 'fixture-daemon\n' > "$APP/Contents/MacOS/RunSpecimenHolderDaemon"
  chmod 755 "$APP/Contents/MacOS/RunSpecimenHolder" "$APP/Contents/MacOS/RunSpecimenHolderDaemon"
elif [[ "${RS_HOLDER_STAGE_COMPILE:-}" == "1" ]]; then
  /usr/bin/xcrun swiftc -parse-as-library -O \
    -o "$APP/Contents/MacOS/RunSpecimenHolder" \
    "$ROOT/apps/holder/Sources/HolderSocket/HolderSocketClient.swift" \
    "$ROOT/apps/holder/Sources/RunSpecimenHolderApp/main.swift"
  /usr/bin/xcrun swiftc -O \
    -o "$APP/Contents/MacOS/RunSpecimenHolderDaemon" \
    "$ROOT/apps/holder/Sources/RunSpecimenHolderDaemon/main.swift"
  /usr/bin/codesign --force --sign - "$APP/Contents/MacOS/RunSpecimenHolder"
  /usr/bin/codesign --force --sign - "$APP/Contents/MacOS/RunSpecimenHolderDaemon"
else
  echo "REFUSING: set RS_HOLDER_STAGE_FIXTURES=1 or RS_HOLDER_STAGE_COMPILE=1. Neither installs." >&2
  exit 2
fi

rsync -a \
  --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT/src/runspecimen/" "$APP/Contents/Resources/Python/runspecimen/"
cp "$ROOT/apps/holder/Resources/Info.plist" "$APP/Contents/Info.plist"
cp "$ROOT/apps/holder/Resources/LaunchDaemons/com.darashkevich.runspecimen.holder.daemon.plist" \
  "$APP/Contents/Library/LaunchDaemons/com.darashkevich.runspecimen.holder.daemon.plist"

cat > "$BUILD/ownership-plan.txt" <<'EOF'
This stage is not installed. A later consented install would require a
root-owned copy under /Applications/RunSpecimen Holder.app, mode 0755 for the
bundle and 0700 for the holder state directory. This file is the plan. It does
not change ownership and it does not replace the Store app. Copying the stage
into a temp root is package preparation, not installation qualification.
EOF

echo "STAGED=$APP"
echo "EMBEDDED=$APP/Contents/Resources/Runtime/bin/python3"
echo "UI=$APP/Contents/MacOS/RunSpecimenHolder"
echo "DAEMON=$APP/Contents/MacOS/RunSpecimenHolderDaemon"
echo "PLIST=$APP/Contents/Library/LaunchDaemons/com.darashkevich.runspecimen.holder.daemon.plist"
echo "NOT_INSTALLED=1"
