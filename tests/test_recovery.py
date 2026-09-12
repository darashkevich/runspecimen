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
)
from runspecimen.state import load_state, update_state


class TestRecoveryStatus(unittest.TestCase):
    """Tests for checking if a run needs recovery."""

    def test_none_phase_not_recoverable(self):
        state = {"phase": "none"}
        ok, msg = is_recoverable(state)
        self.assertFalse(ok)
        self.assertIn("no run has started", msg)

    def test_approved_phase_not_recoverable(self):
        state = {"phase": "approved"}
        ok, msg = is_recoverable(state)
        self.assertFalse(ok)
        self.assertIn("still in approved phase", msg)

    def test_running_phase_is_recoverable(self):
        state = {"phase": "running"}
        ok, msg = is_recoverable(state)
        self.assertTrue(ok)
        self.assertIn("interrupted", msg)

    def test_completed_phase_not_recoverable(self):
        state = {"phase": "completed"}
        ok, msg = is_recoverable(state)
        self.assertFalse(ok)
        self.assertIn("completed successfully", msg)

    def test_failed_phase_not_recoverable(self):
        state = {"phase": "failed"}
        ok, msg = is_recoverable(state)
        self.assertFalse(ok)
        self.assertIn("already marked as failed", msg)

    def test_postflighted_phase_not_recoverable(self):
        state = {"phase": "postflighted"}
        ok, msg = is_recoverable(state)
        self.assertFalse(ok)
        self.assertIn("already postflighted", msg)

    def test_abandoned_phase_not_recoverable(self):
        state = {"phase": "abandoned"}
        ok, msg = is_recoverable(state)
        self.assertFalse(ok)
        self.assertIn("already abandoned", msg)


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


if __name__ == "__main__":
    unittest.main()
