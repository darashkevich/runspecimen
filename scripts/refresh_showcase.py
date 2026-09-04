#!/usr/bin/env python3
"""Regenerate examples/showcase receipt without an interactive TTY.

Uses approve_contract(..., skip_tty_check=True) — the same test hook as unit
tests. Do not use this for production approvals; human TTY approve remains the
enforcement path for real work.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.approve import approve_contract  # noqa: E402
from runspecimen.postflight import postflight  # noqa: E402
from runspecimen.preflight import preflight  # noqa: E402
from runspecimen.run import run_contract  # noqa: E402
from runspecimen.certificate import verify_run_receipt  # noqa: E402
from runspecimen.contract import load_contract  # noqa: E402


SHOWCASE = ROOT / "examples" / "showcase"
CAMPAIGN = "showcase-campaign"
RUN_ID = "run-001"

COMPUTE_SRC = '''#!/usr/bin/env python3
"""Tiny showcase compute step."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "result.json"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"status": "ok", "answer": 42}, indent=2) + "\\n", encoding="utf-8")
print("wrote", OUT)
'''


class _PhraseReader:
    def __init__(self, text: str) -> None:
        self._text = text
        self._pos = 0

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        if self._pos >= len(self._text):
            return ""
        self._pos = len(self._text)
        return self._text


class _NullWriter:
    def isatty(self) -> bool:
        return True

    def write(self, _s: str) -> int:
        return 0

    def flush(self) -> None:
        return None


def _wipe_run_artifacts(ws: Path) -> None:
    rs = ws / ".runspecimen"
    if rs.exists():
        shutil.rmtree(rs)
    out = ws / "outputs" / "result.json"
    if out.exists():
        out.unlink()


def main() -> int:
    work = SHOWCASE / "work"
    outputs = SHOWCASE / "outputs"
    work.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)

    compute = work / "compute.py"
    compute.write_text(COMPUTE_SRC, encoding="utf-8")
    compute.chmod(0o755)

    contract_doc = {
        "version": 1,
        "campaign_id": CAMPAIGN,
        "run_id": RUN_ID,
        # PATH command (not absolute) so the committed contract is portable;
        # live verify still binds this host's resolved interpreter hash.
        "argv": ["python3", "work/compute.py"],
        "cwd": ".",
        "source": {"roots": ["work"], "excludes": ["work/tmp", "*.pyc"]},
        "outputs": {"required": ["outputs/result.json"]},
        "caps": {
            "wall_timeout_sec": 30,
            "stdout_max_bytes": 65536,
            "stderr_max_bytes": 65536,
        },
        "approval": {"ttl_sec": 3600},
        "predecessor": None,
        "postflight": {
            "exit_code": 0,
            "require_outputs": True,
            "output_sha256": {},
            "json_equals": [
                {
                    "path": "outputs/result.json",
                    "field": "status",
                    "equals": "ok",
                }
            ],
            "source_unchanged": True,
        },
    }
    contract_path = SHOWCASE / "contract.json"
    contract_path.write_text(
        json.dumps(contract_doc, indent=2) + "\n", encoding="utf-8"
    )

    _wipe_run_artifacts(SHOWCASE)

    approve_contract(
        contract_path=contract_path,
        workspace=SHOWCASE,
        skip_tty_check=True,
        stdin=_PhraseReader("APPROVE\n"),
        stdout=_NullWriter(),
    )
    preflight(contract_path=contract_path, workspace=SHOWCASE)
    run_contract(contract_path=contract_path, workspace=SHOWCASE)
    postflight(contract_path=contract_path, workspace=SHOWCASE)

    contract = load_contract(contract_path)
    result = verify_run_receipt(
        workspace=SHOWCASE,
        campaign_id=CAMPAIGN,
        run_id=RUN_ID,
        contract=contract,
        require_live_provenance=True,
    )
    print(json.dumps({"ok": True, "showcase": str(SHOWCASE), "verify": result}, indent=2))
    print(
        "Note: live verify binds this machine's interpreter hash. "
        "Re-run this script after cloning on another host.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
