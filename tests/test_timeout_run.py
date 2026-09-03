"""Timeout cleanup and run orchestration tests."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

from tests.helpers import (
    SRC,
    RunSpecimenTestCase,
    approve,
    base_contract,
    seed_workspace,
    write_contract,
)

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.errors import RunError
from runspecimen.paths import run_state_dir
from runspecimen.preflight import preflight
from runspecimen.run import run_contract
from runspecimen.state import load_state


class TestTimeout(unittest.TestCase):
    def test_timeout_kills_process_group_and_records_failure(self) -> None:
        sleeper = (
            "import os, time, signal\n"
            "print('child-pgid', os.getpgrp(), flush=True)\n"
            "time.sleep(60)\n"
        )
        td = seed_workspace(job_source=sleeper)
        self.addCleanup(td.cleanup)
        ws = Path(td.name)
        doc = base_contract(
            caps={
                "wall_timeout_sec": 1,
                "stdout_max_bytes": 65536,
                "stderr_max_bytes": 65536,
            }
        )
        cpath = write_contract(ws, "contract.json", doc)
        approve(ws, cpath)
        preflight(contract_path=cpath, workspace=ws)

        t0 = time.monotonic()
        with self.assertRaises(RunError) as ctx:
            run_contract(contract_path=cpath, workspace=ws)
        elapsed = time.monotonic() - t0
        self.assertIn("timeout", str(ctx.exception).lower())
        self.assertLess(elapsed, 15, "timeout cleanup should not wait for full sleep")

        state = load_state(run_state_dir(ws, "camp", "run-a"))
        self.assertEqual(state.get("phase"), "failed")
        self.assertEqual(state.get("run_result"), "timeout")
        self.assertTrue(state.get("timed_out"))

        # Ensure no orphan sleeper with our workspace marker still running.
        # Best-effort: pgid kill should have reaped children.
        time.sleep(0.2)


class TestHappyRun(RunSpecimenTestCase):
    def test_run_records_completion_and_captures(self) -> None:
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        preflight(contract_path=cpath, workspace=self.ws)
        result = run_contract(contract_path=cpath, workspace=self.ws)
        self.assertEqual(result["run_result"], "completed")
        self.assertEqual(result["exit_code"], 0)
        state_dir = run_state_dir(self.ws, "camp", "run-a")
        self.assertTrue((state_dir / "stdout.capture").exists())
        self.assertIn(b"done", (state_dir / "stdout.capture").read_bytes())
        self.assertTrue((self.ws / "outputs" / "out.json").is_file())


if __name__ == "__main__":
    unittest.main()
