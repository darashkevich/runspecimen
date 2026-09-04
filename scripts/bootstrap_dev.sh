#!/bin/sh
# Install a working local CLI from a fresh clone.
#
# This deliberately uses a regular install rather than ``-e``: some Python
# builds ignore the hidden ``__editable__*.pth`` file emitted by setuptools,
# leaving the console script present but unable to import ``runspecimen``.
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"

python="${PYTHON:-python3}"
if ! "$python" -c '
import re
import setuptools

match = re.match(r"(\d+(?:\.\d+)*)", setuptools.__version__)
raise SystemExit(0 if match and tuple(map(int, match.group(1).split("."))) >= (77,) else 1)
'; then
    "$python" -m pip install --upgrade "setuptools>=77" wheel
fi
"$python" -m pip install --no-build-isolation .

echo "Bootstrap complete: setuptools>=77 and a working runspecimen CLI install."
