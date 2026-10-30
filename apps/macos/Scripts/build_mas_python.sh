#!/usr/bin/env bash
# Private CPython for PyInstaller: omit the unused built-in disk-space APIs.
# No host interpreter, keychain, provisioning, or signing settings are changed.
set -euo pipefail

if [[ $# != 1 || "$1" != /* ]]; then
  echo "Usage: $0 /absolute/new/private-prefix" >&2
  exit 2
fi
[[ "$(uname -s)" == Darwin ]] || { echo "macOS required" >&2; exit 1; }
PREFIX="$1"
[[ ! -e "$PREFIX" ]] || { echo "Refusing existing prefix: $PREFIX" >&2; exit 1; }
VERSION=3.12.15
# python.org's published .tar.xz.sigstore messageDigest, SHA2_256.
SHA256=c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a
OPENSSL="$(brew --prefix openssl@3)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rs-mas-python.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
curl --fail --location --proto '=https' --tlsv1.2 \
  "https://www.python.org/ftp/python/$VERSION/Python-$VERSION.tar.xz" \
  --output "$WORK/python.tar.xz"
printf '%s  %s\n' "$SHA256" "$WORK/python.tar.xz" | shasum -a 256 --check
tar -xf "$WORK/python.tar.xz" -C "$WORK"
cd "$WORK/Python-$VERSION"
# posix is built into libpython; --exclude-module cannot remove these functions.
# Use upstream configure switches, rather than editing or hiding Mach-O imports.
export ac_cv_func_statvfs=no ac_cv_func_fstatvfs=no
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-13.0}"
LDFLAGS="${LDFLAGS:-} -Wl,-rpath,$PREFIX/lib" ./configure \
  --prefix="$PREFIX" --enable-shared --disable-test-modules \
  --with-openssl="$OPENSSL" --with-openssl-rpath=auto
make -j "$(sysctl -n hw.ncpu)"
make install
"$PREFIX/bin/python3.12" - <<'PY'
import os, ssl, sysconfig
for name in ('statvfs', 'fstatvfs'):
    if hasattr(os, name) or sysconfig.get_config_var('HAVE_' + name.upper()):
        raise SystemExit('DiskSpace API was not excluded: ' + name)
print('Private CPython: DiskSpace APIs excluded;', ssl.OPENSSL_VERSION)
PY
echo "Install PyInstaller into $PREFIX, then set RS_FREEZE_PYTHON=$PREFIX/bin/python3.12"
