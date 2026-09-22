#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p outputs
printf '%s\n' '{"status":"ok"}' > outputs/result.json
