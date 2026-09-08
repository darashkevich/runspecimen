"""Create a fresh, unapproved demo workspace for an installed CLI."""

from __future__ import annotations

import json
from pathlib import Path

from runspecimen.errors import RunSpecimenError


def init_demo(workspace: Path) -> dict:
    """Create only a new directory; never touch an existing run or workspace."""
    workspace = workspace.expanduser().absolute()
    try:
        workspace.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise RunSpecimenError("Demo destination already exists; choose a new directory.") from exc
    (workspace / "work").mkdir()
    (workspace / "outputs").mkdir()
    script = (
        "import json\n"
        "from pathlib import Path\n\n"
        "result = {'status': 'ok', 'sum_of_squares': sum(n * n for n in range(1, 101))}\n"
        "Path('outputs/result.json').write_text(json.dumps(result, indent=2) + '\\n', encoding='utf-8')\n"
        "print(json.dumps(result))\n"
    )
    (workspace / "work" / "compute.py").write_text(script, encoding="utf-8")
    contract = {
        "version": 1,
        "campaign_id": "demo-campaign",
        "run_id": "run-001",
        "argv": ["python3", "work/compute.py"],
        "cwd": ".",
        "source": {"roots": ["work"], "excludes": ["*.pyc", "__pycache__"]},
        "outputs": {"required": ["outputs/result.json"]},
        "caps": {"wall_timeout_sec": 30, "stdout_max_bytes": 65536, "stderr_max_bytes": 65536},
        "approval": {"ttl_sec": 3600},
        "predecessor": None,
        "postflight": {
            "exit_code": 0, "require_outputs": True, "output_sha256": {},
            "json_equals": [
                {"path": "outputs/result.json", "field": "status", "equals": "ok"},
                {"path": "outputs/result.json", "field": "sum_of_squares", "equals": 338350},
            ],
            "source_unchanged": True,
        },
    }
    contract_path = workspace / "contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "workspace": str(workspace), "contract": str(contract_path), "approved": False, "executed": False}
