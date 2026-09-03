"""Shared fixtures for RunSpecimen tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Re-export for test modules: `from tests.helpers import SRC`

from runspecimen.approve import approve_contract  # noqa: E402

PYTHON = sys.executable


def write_contract(workspace: Path, name: str, doc: dict[str, Any]) -> Path:
    path = workspace / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def base_contract(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "version": 1,
        "campaign_id": "camp",
        "run_id": "run-a",
        "argv": [PYTHON, "work/job.py"],
        "cwd": ".",
        "source": {"roots": ["work"], "excludes": []},
        "outputs": {"required": ["outputs/out.json"]},
        "caps": {
            "wall_timeout_sec": 10,
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
                {"path": "outputs/out.json", "field": "status", "equals": "ok"}
            ],
            "source_unchanged": True,
        },
    }
    doc.update(overrides)
    return doc


def seed_workspace(job_source: str | None = None) -> tempfile.TemporaryDirectory[str]:
    td = tempfile.TemporaryDirectory(prefix="runspecimen-")
    ws = Path(td.name)
    (ws / "work").mkdir()
    (ws / "outputs").mkdir()
    src = job_source or (
        "import json\n"
        "from pathlib import Path\n"
        "p = Path('outputs/out.json')\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        "p.write_text(json.dumps({'status': 'ok', 'n': 1}) + '\\n')\n"
        "print('done')\n"
    )
    (ws / "work" / "job.py").write_text(src, encoding="utf-8")
    return td


class PhraseReader:
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


class NullWriter:
    def isatty(self) -> bool:
        return True

    def write(self, _s: str) -> int:
        return 0

    def flush(self) -> None:
        return None


def approve(ws: Path, contract_path: Path, **kwargs: Any) -> dict:
    return approve_contract(
        contract_path=contract_path,
        workspace=ws,
        skip_tty_check=True,
        stdin=PhraseReader("APPROVE\n"),
        stdout=NullWriter(),
        **kwargs,
    )


class RunSpecimenTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._td = seed_workspace()
        self.ws = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()
