"""Real pipes and fsynced records. These tests do not use HolderSim.

They do not call Touch ID, type an approval phrase, or start ``runspecimen run``.
Mocked identity tests do not signal a pid. A live pre-armed child holds the
lease; allowing another nonce while that child is alive is not a passing case.
"""

from __future__ import annotations

import json
import os
import pathlib
import signal
import sys
import tempfile
import unittest

from runspecimen.holder_protocol import foreign_wait, write_durable_record

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from launch_fault_harness import (
    EXIT_LEASE,
    EXIT_LOST,
    EXIT_SPENT,
    EXIT_STOPPED,
    IdentityError,
    ProcessView,
    liveness,
    linux_identity_from_stat,
    linux_start_token,
    load_spent,
    os_start,
    process_identity,
    reap,
    record_child_identity,
    recover,
    run_fault,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
FAKE_PID = 2_147_483_646
TOKEN = "us:1.000001"
OTHER = "us:1.000002"

# blocked is true while a recorded child is alive or intent is still uncertain.
# after_fork_before_armed stays blocked. A second nonce there is not success.
EXPECTATIONS = (
    ("before_consume", None, False),
    ("after_consume", "consumed", False),
    ("before_intent", "consumed", False),
    ("after_intent", "intent", False),
    ("before_spawn", "intent", False),
    ("after_fork_before_armed", "intent", True),
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

    def _identity(self, root: pathlib.Path, name: str, text: str) -> None:
        folder = root / "identity"
        folder.mkdir(exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")

    def test_reap_does_not_signal_an_unverified_pid(self) -> None:
        samples = {
            "pid-file": ("reap", "12345", "12345"),
            "missing-token": ("identity", "12345.json", '{"pid":12345}'),
            "lstart-only": (
                "identity",
                "12345.json",
                '{"os_start":"Tue Sep 30 01:00:00 2026","pid":12345}',
            ),
            "bool-pid": ("identity", "12345.json", '{"pid":true,"start_token":"us:1.000001"}'),
            "blank-token": ("identity", "12345.json", '{"pid":12345,"start_token":""}'),
            "corrupt": ("identity", "12345.json", "{broken"),
            "token-only": ("identity", "12345.json", '{"start_token":"us:1.000001"}'),
        }
        for name, (folder, filename, text) in samples.items():
            with self.subTest(name=name):
                root = self._root(name)
                target = root / folder
                target.mkdir()
                (target / filename).write_text(text, encoding="utf-8")
                looked: list[int] = []

                def identify(pid: int) -> ProcessView:
                    looked.append(pid)
                    raise AssertionError(f"looked up {pid}")

                killed: list[int] = []
                reap(root, kill=lambda pid, _sig: killed.append(pid), identify=identify)
                self.assertEqual(killed, [])
                self.assertEqual(looked, [])
                decision = recover(root, identify=identify)
                if name == "corrupt":
                    self.assertTrue(decision["lease"])
                    self.assertEqual(decision["action"], "uncertain-child")
                elif name == "pid-file":
                    self.assertFalse(decision["lease"])
                else:
                    self.assertTrue(decision["lease"])
                    self.assertEqual(decision["action"], "uncertain-child")

    def test_reap_does_not_signal_a_conflicting_or_failed_identity(self) -> None:
        root = self._root("conflict")
        self._identity(root, "child.json", json.dumps({"pid": FAKE_PID, "start_token": TOKEN}))
        procs = root / "procs"
        procs.mkdir()
        (procs / "other.json").write_text(
            json.dumps({"pid": FAKE_PID, "start_token": OTHER, "image": "wrapper"}),
            encoding="utf-8",
        )
        killed: list[int] = []
        reap(
            root,
            kill=lambda pid, _sig: killed.append(pid),
            identify=lambda pid: ProcessView("alive", pid, TOKEN),
        )
        self.assertEqual(killed, [])
        self.assertTrue(recover(root, identify=lambda pid: ProcessView("alive", pid, TOKEN))["lease"])

        lookups = {
            "reused": ProcessView("alive", FAKE_PID, OTHER),
            "wrong-pid": ProcessView("alive", FAKE_PID - 1, TOKEN),
            "absent": ProcessView("absent", FAKE_PID, None),
            "empty-token": ProcessView("alive", FAKE_PID, None),
        }
        for name, view in lookups.items():
            with self.subTest(name=name):
                root = self._root(name)
                self._identity(
                    root,
                    "12345.json",
                    json.dumps({"pid": FAKE_PID, "start_token": TOKEN}),
                )
                killed = []
                reap(root, kill=lambda pid, _sig: killed.append(pid), identify=lambda _pid: view)
                self.assertEqual(killed, [])
                self.assertNotIn(12345, killed)

        root = self._root("lookup-error")
        self._identity(root, "child.json", json.dumps({"pid": FAKE_PID, "start_token": TOKEN}))
        killed = []

        def fail(_pid: int) -> ProcessView:
            raise IdentityError("lookup failed")

        reap(root, kill=lambda pid, _sig: killed.append(pid), identify=fail)
        self.assertEqual(killed, [])
        decision = recover(root, identify=fail)
        self.assertTrue(decision["lease"])
        self.assertEqual(decision["action"], "uncertain-child")

    def test_reap_signals_only_after_the_recorded_token_matches(self) -> None:
        root = self._root("match")
        record_child_identity(root, FAKE_PID, identify=lambda pid: ProcessView("alive", pid, TOKEN))
        stored = json.loads(next((root / "identity").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(stored, {"pid": FAKE_PID, "start_token": TOKEN})
        killed: list[tuple[int, int]] = []
        signaled = reap(
            root,
            kill=lambda pid, sig: killed.append((pid, sig)),
            identify=lambda pid: ProcessView("alive", pid, TOKEN),
        )
        self.assertEqual(signaled, [FAKE_PID])
        self.assertEqual(killed, [(FAKE_PID, signal.SIGKILL)])

    def test_changed_identity_is_not_kept_as_authorization(self) -> None:
        root = self._root("changed")
        calls = {"n": 0}

        def identify(pid: int) -> ProcessView:
            calls["n"] += 1
            token = TOKEN if calls["n"] == 1 else OTHER
            return ProcessView("alive", pid, token)

        with self.assertRaises(IdentityError):
            record_child_identity(root, FAKE_PID, identify=identify)
        self.assertFalse(list((root / "identity").glob("*.json")))
        killed: list[int] = []
        reap(root, kill=lambda pid, _sig: killed.append(pid), identify=identify)
        self.assertEqual(killed, [])

    def test_uncertain_intent_without_identity_holds_the_lease(self) -> None:
        root = self._root("uncertain-only")
        write_durable_record(
            root / "durable.json",
            {"phase": "intent", "nonce": "n1", "child": "uncertain"},
        )

        def identify(pid: int) -> ProcessView:
            raise AssertionError(f"looked up {pid}")

        decision = recover(root, identify=identify)
        self.assertTrue(decision["lease"])
        self.assertEqual(decision["action"], "uncertain-child")
        self.assertFalse(decision["success"])
        self.assertEqual(decision["wait"], "echild")
        self.assertFalse(decision["spawn"])
        killed: list[int] = []
        reap(root, kill=lambda pid, _sig: killed.append(pid), identify=identify)
        self.assertEqual(killed, [])
        blocked = run_fault(root, "after_intent", "n2")
        self.assertEqual(blocked.returncode, EXIT_LEASE, blocked.stderr)
        self.assertIn('"child":"uncertain"', (root / "durable.json").read_text(encoding="utf-8"))

    def test_proven_absence_drops_the_lease_without_a_signal(self) -> None:
        root = self._root("proven-absent")
        write_durable_record(
            root / "durable.json",
            {"phase": "intent", "nonce": "n1", "child": "uncertain"},
        )
        self._identity(root, "child.json", json.dumps({"pid": FAKE_PID, "start_token": TOKEN}))
        killed: list[int] = []
        signaled = reap(
            root,
            kill=lambda pid, _sig: killed.append(pid),
            identify=lambda pid: ProcessView("absent", pid, None),
        )
        self.assertEqual(signaled, [])
        self.assertEqual(killed, [])
        decision = recover(root, identify=lambda pid: ProcessView("absent", pid, None))
        self.assertFalse(decision["lease"])
        self.assertFalse(decision["success"])
        self.assertEqual(decision["action"], "terminated-without-status")
        self.assertEqual(decision["wait"], "echild")

    def test_corrupt_spent_history_is_not_a_fresh_launch(self) -> None:
        samples = {
            "broken-json": "{broken",
            "empty": "",
            "array": "[]",
            "null": "null",
            "nonces-string": '{"nonces":"n1"}',
            "nonces-int": '{"nonces":[1]}',
            "nonces-bool": '{"nonces":[true]}',
            "nonces-null": '{"nonces":[null]}',
            "nonces-blank": '{"nonces":[""]}',
            "mixed": '{"nonces":["n1",2]}',
            "missing-nonces": '{"phase":"consumed"}',
        }
        for name, text in samples.items():
            with self.subTest(name=name):
                root = self._root(name)
                (root / "spent.json").write_text(text, encoding="utf-8")
                state = load_spent(root)
                self.assertEqual(state.status, "lost")
                self.assertEqual(state.nonces, set())
                decision = recover(root)
                self.assertEqual(decision["history"], "lost")
                self.assertEqual(decision["action"], "spent-history-lost")
                self.assertTrue(decision["lease"])
                completed = run_fault(root, "after_consume", "n1")
                self.assertEqual(completed.returncode, EXIT_LOST, completed.stderr)
                self.assertEqual((root / "spent.json").read_text(encoding="utf-8"), text)
                self.assertFalse((root / "durable.json").exists())

        root = self._root("symlink")
        (root / "spent.json").symlink_to(root / "missing-target")
        self.assertEqual(load_spent(root).status, "lost")
        root = self._root("directory")
        (root / "spent.json").mkdir()
        self.assertEqual(load_spent(root).status, "lost")

    def test_missing_spent_file_is_new_state(self) -> None:
        root = self._root("spent-new")
        self.assertEqual(load_spent(root).status, "new")
        self.assertEqual(load_spent(root).nonces, set())
        recorded = self._root("spent-empty")
        write_durable_record(recorded / "spent.json", {"nonces": []})
        empty = load_spent(recorded)
        self.assertEqual(empty.status, "recorded")
        self.assertEqual(empty.nonces, set())
        completed = run_fault(root, "after_consume", "n1")
        self.assertEqual(completed.returncode, EXIT_STOPPED, completed.stderr)
        state = load_spent(root)
        self.assertEqual(state.status, "recorded")
        self.assertEqual(state.nonces, {"n1"})
        replay = run_fault(root, "after_intent", "n1")
        self.assertEqual(replay.returncode, EXIT_SPENT, replay.stderr)
        other = run_fault(root, "after_intent", "n2")
        self.assertEqual(other.returncode, EXIT_STOPPED, other.stderr)
        self.assertEqual(load_spent(root).nonces, {"n1", "n2"})

    def test_linux_stat_token_uses_the_starttime_field(self) -> None:
        text = "4321 (weird) name) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 424242 99\n"
        self.assertEqual(linux_start_token(text, 4321), "ticks:424242")
        self.assertEqual(linux_identity_from_stat(text, 4321).state, "alive")
        zombie = text.replace(" S ", " Z ", 1)
        self.assertEqual(linux_identity_from_stat(zombie, 4321).state, "absent")
        dead = text.replace(" S ", " X ", 1)
        self.assertEqual(linux_identity_from_stat(dead, 4321).state, "absent")
        with self.assertRaises(IdentityError):
            linux_start_token(text, 4322)
        with self.assertRaises(IdentityError):
            linux_start_token("nope", 1)

    def test_this_process_identity_is_not_an_lstart_string(self) -> None:
        view = process_identity(os.getpid())
        self.assertEqual(view.state, "alive")
        self.assertEqual(view.pid, os.getpid())
        self.assertIsNotNone(view.start_token)
        assert view.start_token is not None
        self.assertRegex(view.start_token, r"^(us:[1-9][0-9]*\.[0-9]{6}|ticks:[0-9]+)$")
        self.assertNotIn(" ", view.start_token)
        listed = os_start(os.getpid())
        if listed is not None:
            self.assertNotEqual(view.start_token, listed)

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
                    self.assertTrue(decision["lease"])
                    self.assertEqual(decision["action"], "supervise")
                    payload = json.loads(next((root / "identity").glob("*.json")).read_text(encoding="utf-8"))
                    self.assertIsInstance(payload["pid"], int)
                    self.assertRegex(payload["start_token"], r"^(us:|ticks:)")
                    self.assertNotIn("os_start", payload)
                    self.assertTrue(self._alive(payload["pid"]))
                    self.assertFalse((root / "reap").exists())
                    self.assertFalse(list((root / "procs").glob("*.json")))
                    self.assertIn('"child":"uncertain"', record_path.read_text(encoding="utf-8"))
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

    def test_pre_armed_child_holds_the_lease_until_termination_is_proven(self) -> None:
        root = self._root("pre-armed-hold")
        completed = run_fault(root, "after_fork_before_armed", "n1")
        self.assertEqual(completed.returncode, EXIT_STOPPED, completed.stderr)
        decision = recover(root)
        self.assertTrue(decision["lease"])
        self.assertFalse(decision["success"])
        self.assertEqual(decision["action"], "supervise")
        blocked = run_fault(root, "after_intent", "n2")
        self.assertEqual(blocked.returncode, EXIT_LEASE, blocked.stderr)
        signaled = reap(root)
        self.assertTrue(signaled)
        decision = recover(root)
        self.assertFalse(decision["lease"])
        self.assertFalse(decision["success"])
        self.assertEqual(decision["action"], "terminated-without-status")
        self.assertEqual(decision["wait"], "echild")
        replay = run_fault(root, "after_intent", "n1")
        self.assertEqual(replay.returncode, EXIT_SPENT, replay.stderr)
        allowed = run_fault(root, "after_intent", "n2")
        self.assertEqual(allowed.returncode, EXIT_STOPPED, allowed.stderr)

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
