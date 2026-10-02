#!/bin/bash
# Stage a separate RunSpecimen Holder package.
# install, update, rollback, and uninstall are refused unless
# RS_HOLDER_INSTALL_CONSENT=yes, and this engineering pass still does not
# perform them. Does not touch /Applications/RunSpecimen.app.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
# shellcheck source=holder_stage_lib.sh
source "$ROOT/apps/holder/Scripts/holder_stage_lib.sh"

cmd="${1:-stage}"
case "$cmd" in
  install|update|rollback|uninstall)
    echo "REFUSING: $cmd is a consented installed operation and was not run" >&2
    exit 4
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
cp "$RS_HOLDER_RUNTIME_SOURCE" "$APP/Contents/Resources/Runtime/bin/python3"
chmod 755 "$APP/Contents/Resources/Runtime/bin/python3"

if [[ "${RS_HOLDER_STAGE_FIXTURES:-}" == "1" ]]; then
  printf 'fixture\n' > "$APP/Contents/MacOS/RunSpecimenHolder"
  chmod 755 "$APP/Contents/MacOS/RunSpecimenHolder"
else
  echo "REFUSING: a compiled stage is not run from this pass. Set RS_HOLDER_STAGE_FIXTURES=1 to stage a layout without installing." >&2
  exit 2
fi

rsync -a \
  --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT/src/runspecimen/" "$APP/Contents/Resources/Python/runspecimen/"
cp "$ROOT/apps/holder/Resources/Info.plist" "$APP/Contents/Info.plist"

cat > "$BUILD/ownership-plan.txt" <<'EOF'
This stage is not installed. A later consented install would require a
root-owned copy under /Applications/RunSpecimen Holder.app, mode 0755 for the
bundle and 0700 for the holder state directory. This file is the plan. It does
not change ownership and it does not replace the Store app.
EOF

echo "STAGED=$APP"
echo "EMBEDDED=$APP/Contents/Resources/Runtime/bin/python3"
echo "NOT_INSTALLED=1"
