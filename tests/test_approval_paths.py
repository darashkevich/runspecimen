"""Approval, stale binding, provenance, and path-escape tests."""

from __future__ import annotations

import os
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.helpers import (
    SRC,
    RunSpecimenTestCase,
    approve,
    base_contract,
    write_contract,
)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.approve import approve_contract, require_interactive_tty
from runspecimen.contract import (
    MAX_WALL_TIMEOUT_SEC,
    check_contract_paths,
    load_contract,
)
from runspecimen.errors import ApprovalError, ContractError, PathEscapeError, PreflightError
from runspecimen.preflight import preflight
from runspecimen.run import run_contract


class TestApprovalAndPaths(RunSpecimenTestCase):
    def test_tty_required(self) -> None:
        with self.assertRaises(ApprovalError):
            require_interactive_tty(stdin=StringIO("APPROVE\n"), stdout=StringIO())

    def test_stale_approval_expired(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath, now=1_000.0)
        with self.assertRaises(PreflightError) as ctx:
            preflight(contract_path=cpath, workspace=self.ws, now=1_000.0 + 3601)
        self.assertIn("expired", str(ctx.exception).lower())

    def test_stale_approval_source_changed(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        (self.ws / "work" / "job.py").write_text(
            (self.ws / "work" / "job.py").read_text(encoding="utf-8") + "# changed\n",
            encoding="utf-8",
        )
        with self.assertRaises(PreflightError) as ctx:
            preflight(contract_path=cpath, workspace=self.ws)
        self.assertIn("source", str(ctx.exception).lower())

    def test_stale_approval_contract_changed(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        doc = base_contract()
        doc["caps"]["wall_timeout_sec"] = 11
        write_contract(self.ws, "contract.json", doc)
        with self.assertRaises(PreflightError) as ctx:
            preflight(contract_path=cpath, workspace=self.ws)
        msg = str(ctx.exception).lower()
        self.assertTrue("contract" in msg or "provenance" in msg or "hash" in msg)

    def test_path_escape_output(self) -> None:
        doc = base_contract(outputs={"required": ["../outside.txt"]})
        cpath = write_contract(self.ws, "contract.json", doc)
        contract = load_contract(cpath)
        with self.assertRaises(PathEscapeError):
            check_contract_paths(contract, self.ws)

    def test_path_escape_cwd(self) -> None:
        doc = base_contract(cwd="../")
        # cwd ../ from workspace resolves to parent — escape
        cpath = write_contract(self.ws, "contract.json", doc)
        contract = load_contract(cpath)
        with self.assertRaises(PathEscapeError):
            check_contract_paths(contract, self.ws)

    def test_unsafe_caps_refused(self) -> None:
        doc = base_contract(
            caps={
                "wall_timeout_sec": MAX_WALL_TIMEOUT_SEC + 1,
                "stdout_max_bytes": 65536,
                "stderr_max_bytes": 65536,
            }
        )
        cpath = write_contract(self.ws, "contract.json", doc)
        with self.assertRaises(ContractError) as ctx:
            load_contract(cpath)
        self.assertIn("unsafe", str(ctx.exception).lower())

    def test_output_existence_refused(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        (self.ws / "outputs" / "out.json").write_text('{"status":"ok"}\n', encoding="utf-8")
        with self.assertRaises(PreflightError) as ctx:
            preflight(contract_path=cpath, workspace=self.ws)
        self.assertIn("already exists", str(ctx.exception).lower())

    def test_wrong_confirm_phrase(self) -> None:
        from tests.helpers import NullWriter, PhraseReader

        cpath = write_contract(self.ws, "contract.json", base_contract())
        with self.assertRaises(ApprovalError):
            approve_contract(
                contract_path=cpath,
                workspace=self.ws,
                skip_tty_check=True,
                stdin=PhraseReader("nope\n"),
                stdout=NullWriter(),
            )

    def test_runtime_executable_drift_refused(self) -> None:
        (self.ws / "bin").mkdir()
        runner = self.ws / "bin" / "runner"
        runner.write_text("#!/bin/sh\nexec \"$@\"\n", encoding="utf-8")
        runner.chmod(0o755)
        doc = base_contract(argv=["bin/runner", sys.executable, "work/job.py"])
        cpath = write_contract(self.ws, "runtime.json", doc)
        approve(self.ws, cpath)
        runner.write_text("#!/bin/sh\n# changed\nexec \"$@\"\n", encoding="utf-8")
        runner.chmod(0o755)
        with self.assertRaises(PreflightError) as ctx:
            preflight(contract_path=cpath, workspace=self.ws)
        self.assertIn("runtime", str(ctx.exception).lower())

    def test_relative_path_entry_binds_and_launches_same_executable(self) -> None:
        bindir = self.ws / "bin"
        bindir.mkdir()
        runner = bindir / "runner"
        runner.write_text("#!/bin/sh\nexec \"$@\"\n", encoding="utf-8")
        runner.chmod(0o755)
        doc = base_contract(argv=["runner", sys.executable, "work/job.py"])
        cpath = write_contract(self.ws, "relative-path.json", doc)

        with patch.dict(os.environ, {"PATH": "bin"}):
            approval = approve(self.ws, cpath)
            result = run_contract(contract_path=cpath, workspace=self.ws)

        self.assertEqual(
            approval["runtime"]["resolved_executable"], str(runner.resolve())
        )
        self.assertEqual(result["exit_code"], 0)

    def test_unknown_contract_field_refused(self) -> None:
        doc = base_contract()
        doc["watcher"] = {"enabled": True}
        cpath = write_contract(self.ws, "unknown.json", doc)
        with self.assertRaises(ContractError) as ctx:
            load_contract(cpath)
        self.assertIn("unknown field", str(ctx.exception).lower())

    def test_unknown_nested_contract_field_refused(self) -> None:
        doc = base_contract()
        doc["caps"]["worker_count"] = 2
        cpath = write_contract(self.ws, "unknown-nested.json", doc)
        with self.assertRaises(ContractError) as ctx:
            load_contract(cpath)
        self.assertIn("worker_count", str(ctx.exception))

    def test_duplicate_contract_field_refused(self) -> None:
        cpath = self.ws / "duplicate.json"
        cpath.write_text('{"version": 1, "version": 1}\n', encoding="utf-8")
        with self.assertRaises(ContractError) as ctx:
            load_contract(cpath)
        self.assertIn("duplicate", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
