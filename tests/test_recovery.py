"""Tests for crash recovery functionality."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from runspecimen.errors import ApprovalError, RecoveryError
from runspecimen.events import EventLog
from runspecimen.recovery import (
    ABANDON_PHRASE,
    abandon_run,
    check_recovery_status,
    is_recoverable,
    is_recoverable_phase,
)
from runspecimen.state import load_state, update_state


class TestRecoveryPhaseStatus(unittest.TestCase):
    """Tests for checking if a run's phase indicates it might need recovery."""

    def test_none_phase_not_recoverable(self):
        state = {"phase": "none"}
        ok, msg = is_recoverable_phase(state)
        self.assertFalse(ok)
        self.assertIn("no run has started", msg)

    def test_approved_phase_not_recoverable(self):
        state = {"phase": "approved"}
        ok, msg = is_recoverable_phase(state)
        self.assertFalse(ok)
        self.assertIn("still in approved phase", msg)

    def test_running_phase_could_need_recovery(self):
        state = {"phase": "running"}
        ok, msg = is_recoverable_phase(state)
        self.assertTrue(ok)
        self.assertIn("running", msg.lower())

    def test_completed_phase_not_recoverable(self):
        state = {"phase": "completed"}
        ok, msg = is_recoverable_phase(state)
        self.assertFalse(ok)
        self.assertIn("completed successfully", msg)

    def test_failed_phase_not_recoverable(self):
        state = {"phase": "failed"}
        ok, msg = is_recoverable_phase(state)
        self.assertFalse(ok)
        self.assertIn("already marked as failed", msg)

    def test_postflighted_phase_not_recoverable(self):
        state = {"phase": "postflighted"}
        ok, msg = is_recoverable_phase(state)
        self.assertFalse(ok)
        self.assertIn("already postflighted", msg)

    def test_abandoned_phase_not_recoverable(self):
        state = {"phase": "abandoned"}
        ok, msg = is_recoverable_phase(state)
        self.assertFalse(ok)
        self.assertIn("already abandoned", msg)


class TestRecoveryWithLease(unittest.TestCase):
    """Tests for recovery status considering active leases."""

    def test_running_without_lease_is_recoverable(self):
        """A running state with no active lease needs recovery."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state = {"phase": "running"}
            ok, msg = is_recoverable(state, workspace=workspace)
            self.assertTrue(ok)
            self.assertIn("no active lease", msg)

    def test_running_with_active_lease_not_recoverable(self):
        """A running state with an active lease is still executing."""
        from runspecimen.lease import hold_workspace_lease
        from tests.helpers import SRC
        import subprocess
        import sys
        import os

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state = {"phase": "running"}

            # Create a ready signal file for deterministic synchronization
            ready_signal = workspace / "ready.signal"

            # Create a script file to hold the lease
            script = workspace / "hold_lease.py"
            script.write_text(f'''
import sys
sys.path.insert(0, {str(SRC)!r})
from runspecimen.lease import hold_workspace_lease
import signal
from pathlib import Path

def handler(signum, frame):
    sys.exit(0)

signal.signal(signal.SIGTERM, handler)

with hold_workspace_lease({str(workspace)!r}, holder="test-runner"):
    # Signal that lease is acquired
    Path({str(ready_signal)!r}).write_text("ready")
    # Wait for termination
    signal.pause()
''')

            # Start a process that holds the lease
            proc = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(workspace),
            )

            try:
                # Wait for ready signal (deterministic sync)
                for _ in range(100):  # 10 second timeout
                    if ready_signal.exists():
                        break
                    import time
                    time.sleep(0.1)
                else:
                    self.fail("Subprocess did not acquire lease in time")

                # Now check - should not be recoverable
                ok, msg = is_recoverable(state, workspace=workspace)
                self.assertFalse(ok)
                self.assertIn("lease held", msg.lower())
            finally:
                proc.terminate()
                proc.wait()

    def test_stale_running_no_lease_needs_recovery(self):
        """A running state with no lease indicates a crash needing recovery."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state_dir = workspace / ".runspecimen" / "runs" / "test" / "run-001"
            state_dir.mkdir(parents=True)

            # Phase is running but no lease is held (simulates crash)
            update_state(
                state_dir,
                phase="running",
                run_started_at="2024-01-01T00:00:00Z",
            )

            # Should need recovery
            result = check_recovery_status(
                workspace=workspace,
                campaign_id="test",
                run_id="run-001",
            )

            self.assertTrue(result["needs_recovery"])
            self.assertFalse(result["workspace_lease_held"])

    def test_concurrent_abandon_refused_when_lease_held(self):
        """Abandon must fail if workspace lease is held by another process."""
        from runspecimen.lease import hold_workspace_lease
        from tests.helpers import SRC
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state_dir = workspace / ".runspecimen" / "runs" / "test" / "run-001"
            state_dir.mkdir(parents=True)

            update_state(
                state_dir,
                phase="running",
                run_started_at="2024-01-01T00:00:00Z",
            )

            ready_signal = workspace / "ready.signal"
            script = workspace / "hold_lease.py"
            script.write_text(f'''
import sys
sys.path.insert(0, {str(SRC)!r})
from runspecimen.lease import hold_workspace_lease
import signal
from pathlib import Path

def handler(signum, frame):
    sys.exit(0)

signal.signal(signal.SIGTERM, handler)

with hold_workspace_lease({str(workspace)!r}, holder="blocking-runner"):
    Path({str(ready_signal)!r}).write_text("ready")
    signal.pause()
''')

            proc = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(workspace),
            )

            try:
                for _ in range(100):
                    if ready_signal.exists():
                        break
                    import time
                    time.sleep(0.1)
                else:
                    self.fail("Subprocess did not acquire lease in time")

                # Attempt abandon should fail because lease is held
                with self.assertRaises(RecoveryError) as ctx:
                    abandon_run(
                        workspace=workspace,
                        campaign_id="test",
                        run_id="run-001",
                        stdin=io.StringIO(ABANDON_PHRASE + "\n"),
                        stdout=io.StringIO(),
                        skip_tty_check=True,
                    )
                self.assertIn("lease", str(ctx.exception).lower())
            finally:
                proc.terminate()
                proc.wait()

    def test_abandon_event_state_consistency(self):
        """After abandon, event log and state must be consistent."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state_dir = workspace / ".runspecimen" / "runs" / "test" / "run-001"
            state_dir.mkdir(parents=True)

            # Initialize event log
            log = EventLog.for_state_dir(state_dir)
            log.ensure()

            update_state(
                state_dir,
                phase="running",
                run_started_at="2024-01-01T00:00:00Z",
                campaign_id="test",
                run_id="run-001",
            )

            abandon_run(
                workspace=workspace,
                campaign_id="test",
                run_id="run-001",
                stdin=io.StringIO(ABANDON_PHRASE + "\n"),
                stdout=io.StringIO(),
                skip_tty_check=True,
            )

            # Check state consistency
            state = load_state(state_dir)
            self.assertEqual(state["phase"], "abandoned")
            self.assertEqual(state["run_result"], "abandoned")
            self.assertEqual(state["recovery_decision"], "abandon")

            # Check event log consistency
            events = log.read_all()
            abandon_events = [e for e in events if e.type == "recovery_abandon"]
            self.assertEqual(len(abandon_events), 1)
            self.assertEqual(abandon_events[0].body["decision"], "abandon")

    def test_check_recovery_status_includes_lease_info(self):
        """check_recovery_status should include lease information."""
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state_dir = workspace / ".runspecimen" / "runs" / "test" / "run-001"
            state_dir.mkdir(parents=True)

            update_state(
                state_dir,
                phase="running",
                run_started_at="2024-01-01T00:00:00Z",
            )

            result = check_recovery_status(
                workspace=workspace,
                campaign_id="test",
                run_id="run-001",
            )

            # Should include lease info
            self.assertIn("workspace_lease_held", result)
            self.assertIn("lease_holder", result)
            # No lease held, so should need recovery
            self.assertTrue(result["needs_recovery"])
            self.assertFalse(result["workspace_lease_held"])


class TestAbandonRun(unittest.TestCase):
    """Tests for abandoning a crashed run."""

    def test_abandon_requires_tty_by_default(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            # TTY check happens via require_interactive_tty in approve module
            # It raises ApprovalError when stdin/stdout are not TTYs
            with self.assertRaises(ApprovalError) as ctx:
                abandon_run(
                    workspace=workspace,
                    campaign_id="test-campaign",
                    run_id="run-001",
                    stdin=io.StringIO(""),
                    stdout=io.StringIO(),
                )
            self.assertIn("TTY", str(ctx.exception))

    def test_abandon_refuses_non_recoverable_state(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state_dir = workspace / ".runspecimen" / "runs" / "test" / "run-001"
            state_dir.mkdir(parents=True)

            # Set phase to "none" (not recoverable)
            update_state(state_dir, phase="none")

            stdin = io.StringIO(ABANDON_PHRASE + "\n")
            stdout = io.StringIO()

            with self.assertRaises(RecoveryError) as ctx:
                abandon_run(
                    workspace=workspace,
                    campaign_id="test",
                    run_id="run-001",
                    stdin=stdin,
                    stdout=stdout,
                    skip_tty_check=True,
                )
            self.assertIn("not in a recoverable state", str(ctx.exception))

    def test_abandon_wrong_phrase_aborts(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state_dir = workspace / ".runspecimen" / "runs" / "test" / "run-001"
            state_dir.mkdir(parents=True)

            # Set phase to "running" (recoverable)
            update_state(state_dir, phase="running", run_started_at="2024-01-01T00:00:00Z")

            stdin = io.StringIO("wrong-phrase\n")
            stdout = io.StringIO()

            with self.assertRaises(RecoveryError) as ctx:
                abandon_run(
                    workspace=workspace,
                    campaign_id="test",
                    run_id="run-001",
                    stdin=stdin,
                    stdout=stdout,
                    skip_tty_check=True,
                )
            self.assertIn("confirmation phrase mismatch", str(ctx.exception))

    def test_abandon_marks_run_as_abandoned(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state_dir = workspace / ".runspecimen" / "runs" / "test" / "run-001"
            state_dir.mkdir(parents=True)

            # Set phase to "running" (recoverable)
            update_state(
                state_dir,
                phase="running",
                run_started_at="2024-01-01T00:00:00Z",
                campaign_id="test",
                run_id="run-001",
            )

            stdin = io.StringIO(ABANDON_PHRASE + "\n")
            stdout = io.StringIO()

            result = abandon_run(
                workspace=workspace,
                campaign_id="test",
                run_id="run-001",
                stdin=stdin,
                stdout=stdout,
                skip_tty_check=True,
                reason="test abandonment",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["action"], "abandon")

            # Verify state was updated
            state = load_state(state_dir)
            self.assertEqual(state["phase"], "abandoned")
            self.assertEqual(state["run_result"], "abandoned")
            self.assertEqual(state["recovery_decision"], "abandon")

    def test_abandon_records_event(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state_dir = workspace / ".runspecimen" / "runs" / "test" / "run-001"
            state_dir.mkdir(parents=True)

            # Initialize event log
            log = EventLog.for_state_dir(state_dir)
            log.ensure()

            # Set phase to "running" (recoverable)
            update_state(
                state_dir,
                phase="running",
                run_started_at="2024-01-01T00:00:00Z",
                campaign_id="test",
                run_id="run-001",
            )

            stdin = io.StringIO(ABANDON_PHRASE + "\n")
            stdout = io.StringIO()

            abandon_run(
                workspace=workspace,
                campaign_id="test",
                run_id="run-001",
                stdin=stdin,
                stdout=stdout,
                skip_tty_check=True,
            )

            # Verify event was recorded
            events = log.read_all()
            self.assertTrue(len(events) > 0)
            last_event = events[-1]
            self.assertEqual(last_event.type, "recovery_abandon")
            self.assertEqual(last_event.body["decision"], "abandon")


class TestCheckRecoveryStatus(unittest.TestCase):
    """Tests for the recovery status check."""

    def test_check_recovery_status_returns_details(self):
        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            state_dir = workspace / ".runspecimen" / "runs" / "test" / "run-001"
            state_dir.mkdir(parents=True)

            update_state(
                state_dir,
                phase="running",
                run_started_at="2024-01-01T00:00:00Z",
            )

            result = check_recovery_status(
                workspace=workspace,
                campaign_id="test",
                run_id="run-001",
            )

            self.assertEqual(result["campaign_id"], "test")
            self.assertEqual(result["run_id"], "run-001")
            self.assertEqual(result["phase"], "running")
            self.assertTrue(result["needs_recovery"])


class TestAbandonedRunIsPermanentlyTerminal(unittest.TestCase):
    """Tests proving abandoned run IDs are permanently terminal."""

    def test_abandoned_run_cannot_be_reapproved(self):
        """Abandoned runs must refuse re-approval."""
        from runspecimen.approve import approve_contract
        from runspecimen.errors import ApprovalError
        from tests.helpers import base_contract, write_contract, PhraseReader, NullWriter

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()
            (workspace / "outputs").mkdir()
            (workspace / "work" / "job.py").write_text(
                "print('ok')\n", encoding="utf-8"
            )

            doc = base_contract()
            contract_path = write_contract(workspace, "contract.json", doc)

            # Set up abandoned state
            state_dir = workspace / ".runspecimen" / "runs" / doc["campaign_id"] / doc["run_id"]
            state_dir.mkdir(parents=True)
            update_state(
                state_dir,
                phase="abandoned",
                run_result="abandoned",
                campaign_id=doc["campaign_id"],
                run_id=doc["run_id"],
            )

            # Attempt re-approval should fail
            with self.assertRaises(ApprovalError) as ctx:
                approve_contract(
                    contract_path=contract_path,
                    workspace=workspace,
                    skip_tty_check=True,
                    stdin=PhraseReader("APPROVE\n"),
                    stdout=NullWriter(),
                )
            self.assertIn("abandoned", str(ctx.exception).lower())

    def test_abandoned_run_cannot_be_preflighted(self):
        """Abandoned runs must refuse preflight."""
        from runspecimen.preflight import preflight
        from runspecimen.errors import PreflightError
        from runspecimen.approve import approve_contract
        from tests.helpers import base_contract, write_contract, PhraseReader, NullWriter

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()
            (workspace / "outputs").mkdir()
            (workspace / "work" / "job.py").write_text(
                "print('ok')\n", encoding="utf-8"
            )

            doc = base_contract()
            contract_path = write_contract(workspace, "contract.json", doc)

            # Set up abandoned state with approval (simulating a crash after approval)
            state_dir = workspace / ".runspecimen" / "runs" / doc["campaign_id"] / doc["run_id"]
            state_dir.mkdir(parents=True)

            # Write an approval document
            import time
            from runspecimen.atomic import atomic_write_json
            from runspecimen.hashutil import hash_source
            from runspecimen.contract import load_contract
            from runspecimen.runtime import runtime_provenance

            contract = load_contract(contract_path)
            source_hash, _ = hash_source(
                workspace, list(contract.source.roots), list(contract.source.excludes)
            )
            runtime = runtime_provenance(contract, workspace)
            ts = time.time()

            approval_doc = {
                "approved_at_unix": ts,
                "expires_at_unix": ts + 3600,
                "campaign_id": doc["campaign_id"],
                "run_id": doc["run_id"],
                "contract_hash": contract.contract_hash,
                "source_hash": source_hash,
                "runtime": runtime,
            }
            atomic_write_json(state_dir / "approval.json", approval_doc)

            # Set phase to abandoned
            update_state(
                state_dir,
                phase="abandoned",
                run_result="abandoned",
                campaign_id=doc["campaign_id"],
                run_id=doc["run_id"],
            )

            # Attempt preflight should fail
            with self.assertRaises(PreflightError) as ctx:
                preflight(contract_path=contract_path, workspace=workspace)
            self.assertIn("abandoned", str(ctx.exception).lower())

    def test_abandoned_run_cannot_be_executed(self):
        """Abandoned runs must refuse execution."""
        from runspecimen.run import run_contract
        from runspecimen.errors import PreflightError
        from tests.helpers import base_contract, write_contract

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)
            (workspace / "work").mkdir()
            (workspace / "outputs").mkdir()
            (workspace / "work" / "job.py").write_text(
                "print('ok')\n", encoding="utf-8"
            )

            doc = base_contract()
            contract_path = write_contract(workspace, "contract.json", doc)

            # Set up abandoned state
            state_dir = workspace / ".runspecimen" / "runs" / doc["campaign_id"] / doc["run_id"]
            state_dir.mkdir(parents=True)
            update_state(
                state_dir,
                phase="abandoned",
                run_result="abandoned",
                campaign_id=doc["campaign_id"],
                run_id=doc["run_id"],
            )

            # Attempt run should fail
            with self.assertRaises(PreflightError) as ctx:
                run_contract(contract_path=contract_path, workspace=workspace)
            self.assertIn("abandoned", str(ctx.exception).lower())

    def test_abandoned_predecessor_rejected_with_refuse_if_failed(self):
        """Predecessor with refuse_if_failed=true must reject abandoned predecessor."""
        from runspecimen.preflight import check_predecessor
        from runspecimen.contract import Contract, PredecessorSpec
        from runspecimen.errors import PreflightError

        with tempfile.TemporaryDirectory() as ws:
            workspace = Path(ws)

            # Set up predecessor in abandoned state
            pred_dir = workspace / ".runspecimen" / "runs" / "camp" / "run-pred"
            pred_dir.mkdir(parents=True)
            update_state(
                pred_dir,
                phase="abandoned",
                run_result="abandoned",
                campaign_id="camp",
                run_id="run-pred",
            )

            # Create a mock contract with predecessor spec
            # refuse_if_failed=True, require_postflight=False
            class MockContract:
                predecessor = PredecessorSpec(
                    campaign_id="camp",
                    run_id="run-pred",
                    require_postflight=False,
                    refuse_if_failed=True,
                )

            # This should fail because predecessor is abandoned
            with self.assertRaises(PreflightError) as ctx:
                check_predecessor(workspace, MockContract())
            self.assertIn("abandoned", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
