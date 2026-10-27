"""Real parent-loss and denied-cleanup scenarios against fixture-approved contracts.

These tests spawn a real approved contract through the CLI and verify that:
1. SIGKILL of the CLI does not orphan the contract past wall_timeout
2. Death of CLI's entire process group does not orphan the contract
3. EPERM on group kill reports cleanup_pending and retains the lease
4. Wall deadline is enforced even when the CLI process is stopped
"""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.helpers import SRC, approve, base_contract, seed_workspace, write_contract
from runspecimen.lease import Lease
from runspecimen.paths import run_state_dir
from runspecimen.state import load_state


class RunSupervisorTests(unittest.TestCase):
    """Tests for SIGKILL, parent death, and EPERM scenarios."""

    @contextlib.contextmanager
    def fixture(self, *, deny_cleanup: bool = False, wall_sec: int = 8):
        """Create a fixture with an unkillable contract that writes its PID.

        The contract ignores TERM/INT/HUP so it can only be killed by SIGKILL.
        When deny_cleanup=True, the CLI wrapper patches os.killpg to raise EPERM.
        """
        td = seed_workspace(
            "import os, signal, time\n"
            "from pathlib import Path\n"
            "for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):\n"
            "    signal.signal(sig, signal.SIG_IGN)\n"
            "Path('outputs/pid').write_text(str(os.getpid()))\n"
            "while True:\n"
            "    time.sleep(0.02)\n"
        )
        ws = Path(td.name)
        try:
            contract = write_contract(
                ws,
                "contract.json",
                base_contract(
                    caps={
                        "wall_timeout_sec": wall_sec,
                        "stdout_max_bytes": 1024,
                        "stderr_max_bytes": 1024,
                    }
                ),
            )
            approve(ws, contract)

            # Marker file: when it exists, os.killpg raises PermissionError
            deny_marker = ws / "outputs" / "deny_cleanup"
            if deny_cleanup:
                deny_marker.touch()

            # Build CLI command - either direct or with EPERM wrapper
            if deny_cleanup:
                # Write a wrapper that patches os.killpg
                driver = ws / "eperm_driver.py"
                driver.write_text(
                    "import os, sys\n"
                    "from pathlib import Path\n"
                    "from runspecimen.cli import main\n"
                    "real_killpg = os.killpg\n"
                    "marker = Path(sys.argv.pop(1))\n"
                    "def patched_killpg(pgid, sig):\n"
                    "    if marker.exists():\n"
                    "        raise PermissionError('fixture: group kill denied')\n"
                    "    return real_killpg(pgid, sig)\n"
                    "os.killpg = patched_killpg\n"
                    "raise SystemExit(main())\n"
                )
                argv = [sys.executable, str(driver), str(deny_marker)]
            else:
                argv = [sys.executable, "-m", "runspecimen"]

            cli = subprocess.Popen(
                argv + ["run", "--workspace", str(ws), "--contract", str(contract)],
                env=dict(os.environ, PYTHONPATH=str(SRC)),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )

            contract_pid = None
            try:
                deadline = time.monotonic() + 5
                while not (ws / "outputs" / "pid").exists():
                    self.assertIsNone(cli.poll(), "CLI exited before contract started")
                    self.assertLess(time.monotonic(), deadline, "contract startup timeout")
                    time.sleep(0.01)
                contract_pid = int((ws / "outputs" / "pid").read_text())
                yield ws, cli, contract_pid, deny_marker
            finally:
                deny_marker.unlink(missing_ok=True)
                if contract_pid is not None:
                    try:
                        os.killpg(contract_pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                if cli.poll() is None:
                    cli.kill()
                cli.communicate(timeout=5)
        finally:
            td.cleanup()

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def _wait_for_cleanup(self, ws: Path, contract_pid: int, timeout: float = 10.0):
        """Wait for the contract to be killed and lease released."""
        deadline = time.monotonic() + timeout
        lease = Lease.for_workspace(ws, holder="test-probe")

        # Wait for contract death
        while self._pid_alive(contract_pid):
            self.assertTrue(
                lease.is_locked_by_other(),
                "lease must remain held while contract is alive",
            )
            self.assertLess(
                time.monotonic(),
                deadline,
                f"contract (pid={contract_pid}) survived past deadline",
            )
            time.sleep(0.02)

        # Wait for lease release
        while lease.is_locked_by_other():
            self.assertLess(
                time.monotonic(),
                deadline,
                "lease not released after contract death",
            )
            time.sleep(0.02)

        # Verify final state
        state = load_state(run_state_dir(ws, "camp", "run-a"))
        self.assertEqual(state["phase"], "failed")
        self.assertTrue(state.get("cleanup_confirmed", False))

    def test_sigkill_cli_keeps_lease_until_contract_stops(self):
        """SIGKILL of CLI must not orphan the contract; supervisor enforces cleanup."""
        with self.fixture(wall_sec=3) as (ws, cli, contract_pid, _):
            # Kill CLI with SIGKILL - unblockable
            os.kill(cli.pid, signal.SIGKILL)
            cli.wait(timeout=5)

            # The contract should still be killed within wall_timeout
            self._wait_for_cleanup(ws, contract_pid, timeout=8)

            # Verify run result
            state = load_state(run_state_dir(ws, "camp", "run-a"))
            self.assertIn(state["run_result"], ("interrupted", "timeout"))

    def test_entire_cli_group_death_does_not_kill_supervisor(self):
        """Killing CLI's entire group must not orphan the contract."""
        with self.fixture(wall_sec=3) as (ws, cli, contract_pid, _):
            # Kill the entire CLI process group
            os.killpg(cli.pid, signal.SIGKILL)
            cli.wait(timeout=5)

            # Contract should still be killed within wall_timeout
            self._wait_for_cleanup(ws, contract_pid, timeout=8)

    def test_eperm_reports_pending_and_keeps_lease_until_restore(self):
        """EPERM on cleanup must report cleanup_pending and retain lease."""
        with self.fixture(deny_cleanup=True, wall_sec=8) as (ws, cli, contract_pid, deny_marker):
            # Send SIGTERM to CLI - cleanup will fail with EPERM
            os.kill(cli.pid, signal.SIGTERM)
            stdout, stderr = cli.communicate(timeout=10)

            # CLI should exit non-zero
            self.assertNotEqual(cli.returncode, 0, (stdout, stderr))

            # State must be cleanup_pending
            state = load_state(run_state_dir(ws, "camp", "run-a"))
            self.assertEqual(state["phase"], "cleanup_pending")
            self.assertFalse(state.get("cleanup_confirmed", True))

            # Contract must still be alive
            self.assertTrue(self._pid_alive(contract_pid))

            # Lease must still be held
            lease = Lease.for_workspace(ws, holder="test-probe")
            self.assertTrue(lease.is_locked_by_other())

            # Error message should indicate lease retention
            self.assertIn(b"lease retained", stderr.lower())

            # Remove EPERM marker - cleanup should now succeed
            deny_marker.unlink()

            # Wait for deferred cleanup
            self._wait_for_cleanup(ws, contract_pid, timeout=10)

    def test_denied_group_stop_is_not_leader_only_success(self):
        """EPERM on group kill must not fall back to killing only the leader."""
        from runspecimen.run import _stop_process
        from runspecimen.errors import RunError

        class FakeProc:
            pid = 999999999
            returncode = None

            def kill(self):
                raise AssertionError("must not substitute leader kill for denied group stop")

            def wait(self, timeout):
                raise AssertionError("must not wait after denied group stop")

        with patch("runspecimen.run.os.killpg", side_effect=PermissionError("test EPERM")):
            with self.assertRaises(RunError) as ctx:
                _stop_process(FakeProc())
            self.assertIn("unconfirmed", str(ctx.exception).lower())

    def test_wall_deadline_is_enforced_when_cli_is_stopped(self):
        """Wall deadline must be enforced even when CLI process is stopped.

        Timeline budget (why 6s is sufficient):
        - wall_timeout_sec = 2s: supervisor enforces deadline
        - SIGKILL kills contract nearly instantly (~1ms)
        - State update and lease release: ~10ms
        - Total expected: ~2.01s
        - 6s deadline gives 4s margin (200% of expected time)

        The 5s cleanup budget in _stop_process is for worst-case stubborn
        processes; SIGKILL is instant for this simple Python script.
        """
        with self.fixture(wall_sec=2) as (ws, cli, contract_pid, _):
            # SIGSTOP the CLI - it cannot make progress
            os.kill(cli.pid, signal.SIGSTOP)
            try:
                # Contract should still be killed at wall deadline
                deadline = time.monotonic() + 6
                lease = Lease.for_workspace(ws, holder="test-probe")

                # Wait for contract death while asserting lease is held
                while self._pid_alive(contract_pid):
                    self.assertTrue(
                        lease.is_locked_by_other(),
                        "lease must remain held while contract is alive",
                    )
                    self.assertLess(
                        time.monotonic(),
                        deadline,
                        "contract survived SIGSTOP of CLI past wall deadline",
                    )
                    time.sleep(0.02)

                # Product guarantee: state is written before lease is released.
                # Wait for lease release to prove supervisor has finished.
                while lease.is_locked_by_other():
                    self.assertLess(
                        time.monotonic(),
                        deadline,
                        "supervisor did not release lease after contract death",
                    )
                    time.sleep(0.02)

                # Now state must be final and accurate
                state = load_state(run_state_dir(ws, "camp", "run-a"))
                self.assertEqual(state["run_result"], "timeout")
                self.assertTrue(state["cleanup_confirmed"])
            finally:
                os.kill(cli.pid, signal.SIGCONT)
                cli.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
