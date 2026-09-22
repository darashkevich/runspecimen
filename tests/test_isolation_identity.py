"""Isolation tools are hashed, not executed, and a swapped file cannot stay enforced."""

from __future__ import annotations

import contextlib
import io
import os
import stat
import sys
import unittest
from pathlib import Path

from tests.helpers import SRC, RunSpecimenTestCase, approve, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.certificate import load_certificate
from runspecimen.cli import main
from runspecimen.errors import PreflightError
from runspecimen.isolation import confinement_argv, effective_plan
from runspecimen.paths import run_state_dir
from runspecimen.preflight import preflight
from runspecimen.run import run_contract
from runspecimen.contract import IsolationSpec


class IsolationToolIdentityTests(RunSpecimenTestCase):
    def _plant(self, body: str) -> Path:
        bin_dir = self.ws.parent / f"bin-{self.ws.name}"
        bin_dir.mkdir(exist_ok=True)
        tool = bin_dir / "sandbox-exec"
        tool.write_text(body, encoding="utf-8")
        tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
        self.addCleanup(lambda: _rm(bin_dir))
        return tool

    def _path(self, tool: Path) -> None:
        previous = os.environ.get("PATH", "")
        os.environ["PATH"] = str(tool.parent) + os.pathsep + previous
        self.addCleanup(self._restore_path, previous)

    def _restore_path(self, previous: str) -> None:
        os.environ["PATH"] = previous

    def test_validate_does_not_execute_a_path_tool(self) -> None:
        marker = self.ws.parent / f"ran-{self.ws.name}"
        tool = self._plant(f"#!/bin/sh\necho executed > {marker}\n")
        self._path(tool)
        (self.ws / "work").mkdir(exist_ok=True)
        (self.ws / "outputs").mkdir(exist_ok=True)
        (self.ws / "work" / "job.py").write_text("print('ok')\n", encoding="utf-8")
        path = write_contract(
            self.ws,
            "c.json",
            base_contract(isolation={"backend": "sandbox-exec", "network": False}),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["validate", "--workspace", str(self.ws), "--contract", str(path)])
        self.assertEqual(code, 0)
        self.assertFalse(marker.exists(), "validate executed the isolation tool")
        approve(self.ws, path)
        self.assertFalse(marker.exists(), "approve executed the isolation tool before launch")

    def test_replaced_tool_is_refused_and_does_not_report_enforced(self) -> None:
        outside = self.ws.parent / f"escape-{self.ws.name}"
        tool = self._plant("#!/bin/sh\nexit 0\n")
        self._path(tool)
        (self.ws / "work" / "job.py").write_text(
            "import json\nfrom pathlib import Path\n"
            "Path('outputs/out.json').write_text(json.dumps({'status':'ok'})+'\\n')\n",
            encoding="utf-8",
        )
        path = write_contract(
            self.ws,
            "c.json",
            base_contract(isolation={"backend": "sandbox-exec", "network": False}),
        )
        approve(self.ws, path)
        tool.write_text(
            f"#!/bin/sh\necho escaped > {outside}\nexec \"$@\"\n",
            encoding="utf-8",
        )
        with self.assertRaises(PreflightError) as ctx:
            preflight(contract_path=path, workspace=self.ws)
        self.assertIn("does not match the approval", str(ctx.exception))
        with self.assertRaises(PreflightError):
            run_contract(contract_path=path, workspace=self.ws)
        self.assertFalse(outside.exists(), "replaced tool ran and wrote outside the workspace")
        self.assertIsNone(load_certificate(run_state_dir(self.ws, "camp", "run-a")))

    def test_confinement_refuses_a_plan_whose_file_changed(self) -> None:
        tool = self._plant("#!/bin/sh\nexit 0\n")
        self._path(tool)
        plan = effective_plan(IsolationSpec(backend="sandbox-exec", network=False))
        tool.write_text("#!/bin/sh\necho swapped\n", encoding="utf-8")
        with self.assertRaises(PreflightError) as ctx:
            confinement_argv(
                plan,
                [sys.executable, "-c", "print('no')"],
                workspace=self.ws,
                cwd=self.ws,
                profile_path=self.ws / "isolation.sb",
            )
        self.assertIn("changed since approval", str(ctx.exception))
        self.assertFalse((self.ws / "isolation.sb").exists())


def _rm(path: Path) -> None:
    if path.is_dir():
        for child in path.iterdir():
            child.unlink(missing_ok=True)
        path.rmdir()


if __name__ == "__main__":
    unittest.main()
