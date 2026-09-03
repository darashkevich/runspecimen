"""Lease exclusivity tests — workspace-wide execution lease."""

from __future__ import annotations

import multiprocessing
import sys
import unittest
from pathlib import Path

from tests.helpers import SRC, RunSpecimenTestCase, approve, base_contract, write_contract

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.errors import ApprovalError, LeaseError, PreflightError
from runspecimen.lease import Lease, hold_workspace_lease
from runspecimen.preflight import preflight


def _hold_workspace_lease_until_event(workspace: str, ready_evt, release_evt, done_evt) -> None:
    src = str(Path(__file__).resolve().parents[1] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from pathlib import Path as P

    from runspecimen.lease import hold_workspace_lease as _hold

    with _hold(P(workspace), holder="child"):
        ready_evt.set()
        release_evt.wait(timeout=30)
    done_evt.set()


class TestLease(RunSpecimenTestCase):
    def test_concurrent_lease_refusal(self) -> None:
        ctx = multiprocessing.get_context("spawn")
        ready = ctx.Event()
        release = ctx.Event()
        done = ctx.Event()
        proc = ctx.Process(
            target=_hold_workspace_lease_until_event,
            args=(str(self.ws), ready, release, done),
        )
        proc.start()
        self.assertTrue(ready.wait(timeout=10), "child failed to acquire lease")

        other = Lease.for_workspace(self.ws, holder="parent")
        with self.assertRaises(LeaseError):
            other.acquire(blocking=False)
        self.assertTrue(other.is_locked_by_other())

        release.set()
        proc.join(timeout=10)
        self.assertTrue(done.is_set() or done.wait(timeout=5))
        self.assertEqual(proc.exitcode, 0)

        other.acquire(blocking=False)
        other.release()

    def test_cross_process_different_run_ids_share_workspace_lease(self) -> None:
        """Holding the lease for any reason blocks lifecycle on a different run_id."""
        c_a = write_contract(self.ws, "a.json", base_contract(run_id="run-a"))
        c_b = write_contract(
            self.ws,
            "b.json",
            base_contract(run_id="run-b", outputs={"required": ["outputs/b.json"]}),
        )
        # Approve run-a first while lease is free.
        approve(self.ws, c_a)

        ctx = multiprocessing.get_context("spawn")
        ready = ctx.Event()
        release = ctx.Event()
        done = ctx.Event()
        proc = ctx.Process(
            target=_hold_workspace_lease_until_event,
            args=(str(self.ws), ready, release, done),
        )
        proc.start()
        self.assertTrue(ready.wait(timeout=10))

        with self.assertRaises(ApprovalError):
            approve(self.ws, c_b)
        with self.assertRaises(PreflightError):
            preflight(contract_path=c_a, workspace=self.ws)

        release.set()
        proc.join(timeout=10)
        self.assertEqual(proc.exitcode, 0)

    def test_hold_workspace_lease_context(self) -> None:
        with hold_workspace_lease(self.ws, holder="t") as lease:
            self.assertTrue(lease.held)
            assert lease.meta is not None
            self.assertEqual(lease.meta.holder, "t")
        self.assertFalse(lease.held)
        self.assertIsNone(lease.read_meta())

    def test_status_metadata_only_describes_active_holder(self) -> None:
        from runspecimen.status import status_for

        lease = Lease.for_workspace(self.ws, holder="short-lived")
        lease.acquire()
        lease.release()
        doc = status_for(workspace=self.ws, campaign_id="camp", run_id="unused")
        self.assertFalse(doc["workspace_lease_held_by_other"])
        self.assertIsNone(doc["lease_meta"])


if __name__ == "__main__":
    unittest.main()
