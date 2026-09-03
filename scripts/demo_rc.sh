#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
demo_dir=$(mktemp -d "${TMPDIR:-/tmp}/runspecimen-demo.XXXXXX")
mkdir -p "$demo_dir/work" "$demo_dir/outputs"
cp "$repo_dir/examples/demo_contract.json" "$demo_dir/contract.json"
cp "$repo_dir/work/compute.py" "$demo_dir/work/compute.py"

echo "Demo workspace: $demo_dir"
runspecimen doctor --workspace "$demo_dir"
runspecimen validate --workspace "$demo_dir" --contract "$demo_dir/contract.json"
runspecimen approve --workspace "$demo_dir" --contract "$demo_dir/contract.json"

cp "$demo_dir/work/compute.py" "$demo_dir/work/compute.original.py"
printf '\n# deliberate provenance drift\n' >> "$demo_dir/work/compute.py"
if runspecimen preflight --workspace "$demo_dir" --contract "$demo_dir/contract.json"; then
  echo "ERROR: source drift was not refused" >&2
  exit 1
else
  echo "Expected refusal: source drift was blocked."
fi
mv "$demo_dir/work/compute.original.py" "$demo_dir/work/compute.py"

runspecimen preflight --workspace "$demo_dir" --contract "$demo_dir/contract.json"
runspecimen run --workspace "$demo_dir" --contract "$demo_dir/contract.json"
runspecimen postflight --workspace "$demo_dir" --contract "$demo_dir/contract.json"
runspecimen verify --workspace "$demo_dir" --contract "$demo_dir/contract.json" \
  --campaign-id demo-campaign --run-id run-001

if runspecimen run --workspace "$demo_dir" --contract "$demo_dir/contract.json"; then
  echo "ERROR: second launch was not refused" >&2
  exit 1
else
  echo "Expected refusal: second launch was blocked."
fi

echo "RunSpecimen RC demo passed. Evidence remains in $demo_dir/.runspecimen"
