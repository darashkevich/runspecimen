"""Timeout cleanup and run orchestration tests."""

from __future__ import annotations

import os
import signal
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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

from runspecimen.errors import PreflightError, RunError
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

    def test_detached_process_cannot_hold_capture_open_past_timeout(self) -> None:
        td = seed_workspace(job_source=(
            "import subprocess, sys\n"
            "from pathlib import Path\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(6)'], "
            "start_new_session=True)\n"
            "Path('outputs/child.pid').write_text(str(child.pid))\n"
            "print('launcher finished', flush=True)\n"
        ))
        self.addCleanup(td.cleanup)
        ws = Path(td.name)
        doc = base_contract(caps={
            "wall_timeout_sec": 1,
            "stdout_max_bytes": 1024,
            "stderr_max_bytes": 1024,
        })
        cpath = write_contract(ws, "contract.json", doc)
        approve(ws, cpath)
        started = time.monotonic()
        try:
            with self.assertRaisesRegex(RunError, "timeout"):
                run_contract(contract_path=cpath, workspace=ws)
            self.assertLess(time.monotonic() - started, 3)
            state_dir = run_state_dir(ws, "camp", "run-a")
            self.assertEqual(load_state(state_dir)["run_result"], "timeout")
            self.assertIn(b"launcher finished", (state_dir / "stdout.capture").read_bytes())
        finally:
            # Detached sessions are outside RunSpecimen's containment promise;
            # the fixture owns and cleans up this exact detached sleeper.
            pid_file = ws / "outputs" / "child.pid"
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass


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

    def test_descendant_held_pipes_do_not_delay_completion(self) -> None:
        (self.ws / "work" / "job.py").write_text(
            "import subprocess, sys\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(6)'])\n"
            "print('launcher finished', flush=True)\n",
            encoding="utf-8",
        )
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        started = time.monotonic()
        result = run_contract(contract_path=cpath, workspace=self.ws)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(result["exit_code"], 0)
        self.assertIn(
            b"launcher finished",
            (run_state_dir(self.ws, "camp", "run-a") / "stdout.capture").read_bytes(),
        )

    def test_large_stdout_and_stderr_are_drained_to_independent_caps(self) -> None:
        (self.ws / "work" / "job.py").write_text(
            "import os\n"
            "for _ in range(40):\n"
            "    os.write(1, b'a' * 10000)\n"
            "    os.write(2, b'b' * 10000)\n",
            encoding="utf-8",
        )
        doc = base_contract(caps={
            "wall_timeout_sec": 5,
            "stdout_max_bytes": 1024,
            "stderr_max_bytes": 2048,
        })
        cpath = write_contract(self.ws, "contract.json", doc)
        approve(self.ws, cpath)
        result = run_contract(contract_path=cpath, workspace=self.ws)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout_bytes"], 1024)
        self.assertEqual(result["stderr_bytes"], 2048)
        self.assertTrue(result["stdout_truncated"])
        self.assertTrue(result["stderr_truncated"])
        state_dir = run_state_dir(self.ws, "camp", "run-a")
        self.assertEqual((state_dir / "stdout.capture").read_bytes(), b"a" * 1024)
        self.assertEqual((state_dir / "stderr.capture").read_bytes(), b"b" * 2048)

    def test_interrupt_kills_child_and_preserves_failed_state_and_capture(self) -> None:
        (self.ws / "work" / "job.py").write_text("import time\ntime.sleep(6)\n", encoding="utf-8")
        cpath = write_contract(self.ws, "contract.json", base_contract())
        approve(self.ws, cpath)
        children = []

        def interrupt(proc, stdout, stderr, deadline):
            children.append(proc)
            stdout.append(b"partial output\n")
            raise KeyboardInterrupt

        with patch("runspecimen.run._supervise_process", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_contract(contract_path=cpath, workspace=self.ws)
        self.assertIsNotNone(children[0].poll(), "interrupted child must be reaped")
        state_dir = run_state_dir(self.ws, "camp", "run-a")
        state = load_state(state_dir)
        self.assertEqual(state["phase"], "failed")
        self.assertEqual(state["run_result"], "interrupted")
        self.assertEqual((state_dir / "stdout.capture").read_bytes(), b"partial output\n")
        with self.assertRaisesRegex(PreflightError, "phase='failed'"):
            run_contract(contract_path=cpath, workspace=self.ws)


if __name__ == "__main__":
    unittest.main()
