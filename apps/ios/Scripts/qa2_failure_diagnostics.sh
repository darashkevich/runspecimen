#!/usr/bin/env bash
# Diagnostic branch only. Best-effort evidence failures stay visible.
set -u
out="$1"
mkdir -p "$out"
date -u > "$out/captured-at.txt"
/bin/ps -axo pid,ppid,pgid,state,command > "$out/processes.txt" 2> "$out/processes.err"
xcrun simctl list devices booted -j > "$out/booted.json" 2> "$out/booted.err"
# Capture while the failure is live, before test teardown or CI cleanup.
while read -r pid; do
  /usr/sbin/spindump "$pid" 5 1 -file "$out/spindump-$pid.txt" > "$out/spindump-$pid.stdout" 2> "$out/spindump-$pid.stderr" &
done < <(awk '/RunSpecimenObserve|SharingUIService|testmanagerd|xctest/ && !/awk/ {print $1}' "$out/processes.txt")
xcrun simctl spawn booted log collect --last 5m --output "$out/simulator.logarchive" > "$out/log-collect.stdout" 2> "$out/log-collect.stderr" &
wait
