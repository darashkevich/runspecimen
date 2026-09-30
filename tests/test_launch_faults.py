"""Real pipes and fsynced records. These tests do not use HolderSim.

They do not call Touch ID, type an approval phrase, or start ``runspecimen run``.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

from runspecimen.holder_protocol import foreign_wait

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from launch_fault_harness import (
    EXIT_LEASE,
    EXIT_SPENT,
    EXIT_STOPPED,
    liveness,
    reap,
    recover,
    run_fault,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]

# n2_blocked is true while a recorded process is still alive.
EXPECTATIONS = (
    ("before_consume", None, False),
    ("after_consume", "consumed", False),
    ("before_intent", "consumed", False),
    ("after_intent", "intent", False),
    ("before_spawn", "intent", False),
    ("after_fork_before_armed", "intent", False),
    ("after_armed_before_release", "armed", True),
    ("after_armed", "armed", True),
    ("before_go", "armed", True),
    ("after_go", "armed", True),
    ("after_ack", "armed", True),
    ("before_acked_fsync", "armed", True),
    ("after_acked", "acked", True),
    ("before_commit", "acked", True),
    ("after_commit", "acked", True),
    ("before_running_fsync", "acked", True),
    ("after_running", "running", True),
    ("wrapper_eof", "armed", True),
    ("descendant", "running", True),
)


class LaunchFaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.roots: list[pathlib.Path] = []

    def tearDown(self) -> None:
        for root in self.roots:
            reap(root)
        self.tmp.cleanup()

    def _root(self, name: str) -> pathlib.Path:
        root = pathlib.Path(self.tmp.name) / name
        root.mkdir()
        self.roots.append(root)
        return root

    def _alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def test_each_persistence_and_handshake_boundary(self) -> None:
        for fault, phase, blocked in EXPECTATIONS:
            with self.subTest(fault=fault):
                root = self._root(fault)
                completed = run_fault(root, fault, "n1")
                self.assertEqual(completed.returncode, EXIT_STOPPED, completed.stderr)
                decision = recover(root)
                self.assertFalse(decision["success"])
                self.assertFalse(decision["spawn"])
                self.assertEqual(decision["wait"], "echild")
                record_path = root / "durable.json"
                if phase is None:
                    self.assertFalse(record_path.exists())
                else:
                    text = record_path.read_text(encoding="utf-8")
                    self.assertIn(f'"phase":"{phase}"', text)
                if fault == "after_fork_before_armed":
                    reap_ids = [int(path.name) for path in (root / "reap").glob("*")]
                    self.assertTrue(reap_ids)
                    self.assertTrue(self._alive(reap_ids[0]))
                    self.assertFalse(decision["lease"])
                    self.assertFalse(list((root / "procs").glob("*.json")))
                if fault == "wrapper_eof":
                    self.assertIn('"handshake":"eof"', record_path.read_text(encoding="utf-8"))
                    images = [path.read_text(encoding="utf-8") for path in (root / "procs").glob("*.json")]
                    self.assertTrue(any('"image":"wrapper"' in image for image in images))
                    self.assertFalse(any('"image":"payload"' in image for image in images))
                if fault == "descendant":
                    images = [path.read_text(encoding="utf-8") for path in (root / "procs").glob("*.json")]
                    self.assertTrue(any('"image":"descendant"' in image for image in images))
                if fault == "after_armed":
                    pid = int(record_path.read_text(encoding="utf-8").split('"pid":')[1].split(",")[0])
                    self.assertEqual(foreign_wait(pid), "echild")
                    self.assertTrue(self._alive(pid))
                second = run_fault(root, "after_intent", "n2")
                if blocked:
                    self.assertEqual(second.returncode, EXIT_LEASE, second.stderr)
                    self.assertIn(f'"phase":"{phase}"', record_path.read_text(encoding="utf-8"))
                else:
                    self.assertEqual(second.returncode, EXIT_STOPPED, second.stderr)
                    if phase in {"consumed", "intent"}:
                        replay = run_fault(root, "after_intent", "n1")
                        self.assertEqual(replay.returncode, EXIT_SPENT, replay.stderr)

    def test_killing_the_wrapper_drops_the_lease_without_success(self) -> None:
        root = self._root("clear-wrapper")
        completed = run_fault(root, "after_armed", "n1")
        self.assertEqual(completed.returncode, EXIT_STOPPED, completed.stderr)
        self.assertTrue(recover(root)["lease"])
        blocked = run_fault(root, "after_intent", "n2")
        self.assertEqual(blocked.returncode, EXIT_LEASE)
        reap(root)
        decision = recover(root)
        self.assertFalse(decision["lease"])
        self.assertFalse(decision["success"])
        self.assertFalse(decision["spawn"])
        self.assertEqual(decision["action"], "terminated-without-status")
        self.assertEqual(decision["wait"], "echild")
        replay = run_fault(root, "after_intent", "n1")
        self.assertEqual(replay.returncode, EXIT_SPENT)
        allowed = run_fault(root, "after_intent", "n2")
        self.assertEqual(allowed.returncode, EXIT_STOPPED, allowed.stderr)

    def test_descendant_blocks_a_second_nonce_until_it_is_gone(self) -> None:
        root = self._root("descendant-clear")
        completed = run_fault(root, "descendant", "n1")
        self.assertEqual(completed.returncode, EXIT_STOPPED, completed.stderr)
        self.assertTrue(recover(root)["lease"])
        blocked = run_fault(root, "after_intent", "n2")
        self.assertEqual(blocked.returncode, EXIT_LEASE)
        reap(root)
        decision = recover(root)
        self.assertFalse(decision["success"])
        self.assertFalse(decision["lease"])
        self.assertEqual(decision["wait"], "echild")
        allowed = run_fault(root, "after_intent", "n2")
        self.assertEqual(allowed.returncode, EXIT_STOPPED, allowed.stderr)

    def test_pid_reuse_comparison_is_not_adoption(self) -> None:
        self.assertEqual(liveness("Tue Sep 30 01:00:00 2026", "Tue Sep 30 01:00:00 2026"), "alive")
        self.assertEqual(liveness("Tue Sep 30 01:00:00 2026", "Tue Sep 30 01:00:01 2026"), "pid-reuse-not-adopted")
        self.assertEqual(liveness("Tue Sep 30 01:00:00 2026", None), "dead")

    def test_harness_is_not_the_simulator_or_the_run_path(self) -> None:
        harness = (ROOT / "tests" / "launch_fault_harness.py").read_text(encoding="utf-8")
        self.assertNotIn("HolderSim", harness)
        run_py = (ROOT / "src" / "runspecimen" / "run.py").read_text(encoding="utf-8")
        self.assertNotIn("launch_fault_harness", run_py)
        self.assertNotIn("holder_protocol", run_py)


if __name__ == "__main__":
    unittest.main()
