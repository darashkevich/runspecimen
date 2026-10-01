#!/bin/sh
# Shipping symbol gate. Does not install an iOS app and does not request
# provisioning updates. A Debug object that defines a forbidden name must
# fail. A clean object must pass. This is not device Release acceptance
# and not a Face ID proof.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest tests.test_nm_symbol_gate
python3 - "$root" <<'PY'
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "apps" / "ios" / "Scripts"))
import nm_symbol_gate as gate

with tempfile.TemporaryDirectory() as td:
    src = Path(td) / "debug_control.c"
    obj = Path(td) / "debug_control.o"
    src.write_text("void beforeFinalSignatureDecision(void) {}\n", encoding="utf-8")
    built = subprocess.run(["cc", "-c", str(src), "-o", str(obj)], check=False)
    if built.returncode != 0:
        raise SystemExit("cc unavailable for the Debug symbol control")
    try:
        gate.scan_path(obj)
    except gate.SymbolGateError as exc:
        if "beforeFinalSignatureDecision" not in str(exc):
            raise
    else:
        raise SystemExit("Debug control was not rejected")
    clean_src = Path(td) / "clean.c"
    clean_obj = Path(td) / "clean.o"
    clean_src.write_text("int shipping_ok(void){return 1;}\n", encoding="utf-8")
    subprocess.run(["cc", "-c", str(clean_src), "-o", str(clean_obj)], check=True)
    gate.scan_path(clean_obj)
print("ios symbol gate fixtures passed")
PY
