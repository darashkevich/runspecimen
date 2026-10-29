"""Real CLI signals against disposable, fixture-approved contracts only."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests.helpers import SRC, approve, base_contract, seed_workspace, write_contract
from runspecimen.lease import Lease
from runspecimen.paths import run_state_dir
from runspecimen.state import load_state


class RunSignalTests(unittest.TestCase):
    def check_signal(self, signum: int) -> None:
        td = seed_workspace(
            "import os,signal,time\n"
            "from pathlib import Path\n"
            "for sig in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT):\n"
            "    signal.signal(sig, signal.SIG_IGN)\n"
            "Path('outputs/contract.pid').write_text(str(os.getpid()))\n"
            "while True:\n"
            "    Path('outputs/heartbeat').write_text(str(time.monotonic()))\n"
            "    time.sleep(.05)\n"
        )
        ws = Path(td.name)
        contract = write_contract(ws, "contract.json", base_contract(caps={
            "wall_timeout_sec": 8, "stdout_max_bytes": 1024, "stderr_max_bytes": 1024,
        }))
        approve(ws, contract)  # Existing synthetic fixture seam; no human gate.
        env = dict(os.environ, PYTHONPATH=str(SRC))
        cli = subprocess.Popen(
            [sys.executable, "-m", "runspecimen", "run", "--workspace", str(ws),
             "--contract", str(contract)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        pid = None
        try:
            end = time.monotonic() + 5
            while not (ws / "outputs/contract.pid").exists():
                self.assertIsNone(cli.poll(), "CLI exited before fixture readiness")
                self.assertLess(time.monotonic(), end, "fixture readiness deadline")
                time.sleep(.01)
            pid = int((ws / "outputs/contract.pid").read_text())
            self.assertTrue(Lease.for_workspace(ws, holder="probe").is_locked_by_other())
            os.kill(cli.pid, signum)
            stdout, stderr = cli.communicate(timeout=5)
            self.assertNotEqual(cli.returncode, 0, (stdout, stderr))
            with self.assertRaises(ProcessLookupError, msg="contract must be gone before CLI returns"):
                os.kill(pid, 0)
            state = load_state(run_state_dir(ws, "camp", "run-a"))
            self.assertEqual(state["phase"], "failed")
            self.assertEqual(state["run_result"], "interrupted")
            self.assertFalse(Lease.for_workspace(ws, holder="probe").is_locked_by_other())
        finally:
            if cli.poll() is None:
                cli.kill()
            cli.communicate(timeout=5)
            # Only the fixture-owned session is ever cleaned here.
            if pid is not None:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            td.cleanup()

    def test_sigterm_stops_contract_and_records_interruption(self) -> None:
        self.check_signal(signal.SIGTERM)

    def test_sighup_stops_contract_and_records_interruption(self) -> None:
        self.check_signal(signal.SIGHUP)

    def test_sigint_stops_contract_and_records_interruption(self) -> None:
        self.check_signal(signal.SIGINT)
