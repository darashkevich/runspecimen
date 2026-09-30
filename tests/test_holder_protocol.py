"""Unprivileged tests for snapshot binding and the launch handshake.

These tests do not call Touch ID, do not type an approval phrase, and do
not start the product run path.
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import textwrap
import unittest

from runspecimen.holder_protocol import (
    HolderSim,
    LaunchRequest,
    LeaseHeld,
    NonceSpent,
    PipeEOF,
    ProtocolError,
    bind_execution,
    foreign_wait,
    restat_agrees_with_snapshot,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


class BindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.bound = None

    def tearDown(self) -> None:
        if self.bound is not None:
            self.bound.close()
        self.tmp.cleanup()

    def _file(self, name: str, data: bytes) -> pathlib.Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def _request(self, executable: pathlib.Path, script: pathlib.Path, extra: tuple[str, ...] = ()) -> LaunchRequest:
        return LaunchRequest(
            nonce="n1",
            argv=(str(executable), str(script), str(self.root / "input.txt")),
            executable=str(executable),
            script=str(script),
            inputs=(str(self.root / "input.txt"),),
            dependencies=(str(executable), *extra),
            outputs=("result.txt",),
        )

    def test_exec_reads_snapshot_after_the_original_is_replaced(self) -> None:
        interpreter = self._file("interp", b"#!/bin/sh\n")
        script = self._file("run.sh", f"#!{interpreter}\n".encode())
        source = self._file("input.txt", b"approved\n")
        self.bound = bind_execution(self._request(interpreter, script), self.root / "snap")
        snap = self.bound.snapshot_for(str(source))
        fd_bytes = os.read(snap.fd, 100)
        source.write_bytes(b"replaced\n")
        source.unlink()
        planted = self.root / "elsewhere"
        planted.write_bytes(b"attacker\n")
        source.symlink_to(planted)
        self.assertEqual(fd_bytes, b"approved\n")
        self.assertEqual(pathlib.Path(snap.path).read_bytes(), b"approved\n")
        self.assertNotIn(str(source), self.bound.argv)
        self.assertEqual(pathlib.Path(self.bound.argv[2]).read_bytes(), b"approved\n")
        self.assertFalse(restat_agrees_with_snapshot(source, snap))
        self.assertNotEqual(source.stat().st_ino, snap.inode)
        self.assertEqual(self.bound.cwd, str(self.root / "snap" / "cwd"))
        self.assertTrue(str(self.bound.outputs[0]).endswith("/outputs/result.txt"))
        self.assertIn("dynamic linker", self.bound.residuals[0])

    def test_symlink_input_is_rejected_at_bind(self) -> None:
        interpreter = self._file("interp", b"interp")
        script = self._file("run.sh", f"#!{interpreter}\n".encode())
        target = self._file("real.txt", b"real\n")
        link = self.root / "input.txt"
        link.symlink_to(target)
        with self.assertRaises(ProtocolError):
            bind_execution(self._request(interpreter, script), self.root / "snap")

    def test_live_cwd_and_unbound_interpreter_fail_closed(self) -> None:
        interpreter = self._file("interp", b"interp")
        script = self._file("run.sh", b"#!/usr/bin/env python3\n")
        self._file("input.txt", b"x")
        request = self._request(interpreter, script)
        request = LaunchRequest(**{**request.__dict__, "cwd_mode": "live"})
        with self.assertRaises(ProtocolError) as live:
            bind_execution(request, self.root / "snap")
        self.assertIn("cwd", str(live.exception))
        script.write_bytes(b"#!/usr/bin/env python3\n")
        env_request = self._request(interpreter, script)
        with self.assertRaises(ProtocolError) as env:
            bind_execution(env_request, self.root / "snap2")
        self.assertIn("env shebang", str(env.exception))

    def test_declared_dependency_is_snapshotted_and_sibling_is_not(self) -> None:
        interpreter = self._file("interp", b"interp-bytes")
        script = self._file("run.sh", f"#!{interpreter}\n".encode())
        self._file("input.txt", b"in")
        sibling = self._file("helper.py", b"helper")
        self.bound = bind_execution(self._request(interpreter, script), self.root / "snap")
        originals = {item.original for item in self.bound.snapshots}
        self.assertIn(str(interpreter), originals)
        self.assertNotIn(str(sibling), originals)
        sibling.write_bytes(b"mutated-helper")
        self.assertEqual(pathlib.Path(self.bound.snapshot_for(str(interpreter)).path).read_bytes(), b"interp-bytes")

    def test_snapshot_is_a_distinct_inode(self) -> None:
        interpreter = self._file("interp", b"interp")
        script = self._file("run.sh", f"#!{interpreter}\n".encode())
        source = self._file("input.txt", b"same")
        self.bound = bind_execution(self._request(interpreter, script), self.root / "snap")
        snap = self.bound.snapshot_for(str(source))
        self.assertNotEqual(source.stat().st_ino, snap.inode)
        self.assertEqual(source.stat().st_nlink, 1)


class HandshakeTests(unittest.TestCase):
    def test_every_crash_boundary_launches_once(self) -> None:
        for step in HolderSim.ORDER:
            with self.subTest(step=step):
                sim = HolderSim()
                sim.run_through(step)
                spawned_before = sim.spawned
                commits_before = sim.commits
                image = None
                if sim.durable["pid"]:
                    image = sim.procs[sim.durable["pid"]].image
                sim.crash()
                result = sim.recover()
                self.assertEqual(result["wait"], "echild")
                self.assertEqual(result["spawned"], spawned_before)
                self.assertLessEqual(result["commits"], 1)
                self.assertEqual(result["commits"], commits_before)
                self.assertNotEqual(result["action"], "spawn")
                if step in {"send_go", "recv_ack"}:
                    self.assertEqual(image, "wrapper")
                    self.assertEqual(commits_before, 0)
                    self.assertIn(result["action"], {"kill-waiting-wrapper", "no-live-wrapper"})
                if step == "send_commit":
                    self.assertEqual(image, "payload")
                    self.assertEqual(result["action"], "adopt-payload")
                    self.assertEqual(result["commits"], 1)
                with self.assertRaises(NonceSpent):
                    sim.apply("consume", "n1")

    def test_go_without_durable_ack_does_not_leave_a_payload(self) -> None:
        sim = HolderSim()
        sim.run_through("send_go")
        self.assertEqual(sim.durable["phase"], "armed")
        self.assertEqual(sim.procs[sim.durable["pid"]].image, "wrapper")
        with self.assertRaises(ProtocolError):
            sim.apply("send_commit")

    def test_eof_before_commit_does_not_exec(self) -> None:
        sim = HolderSim()
        sim.run_through("send_go")
        sim.break_pipe()
        with self.assertRaises(PipeEOF):
            sim.apply("recv_ack")
        self.assertEqual(sim.procs[sim.durable["pid"]].image, "wrapper")
        self.assertEqual(sim.commits, 0)
        sim.crash()
        result = sim.recover()
        self.assertEqual(result["commits"], 0)
        self.assertEqual(result["spawned"], 1)

    def test_pid_reuse_is_not_killed_or_relaunched(self) -> None:
        sim = HolderSim()
        sim.run_through("fsync_running")
        sim.reuse_pid()
        sim.crash()
        result = sim.recover()
        self.assertEqual(result["action"], "pid-reuse-not-adopted")
        self.assertEqual(result["kills"], ())
        self.assertTrue(result["lease"])
        self.assertEqual(sim.durable["phase"], "unknown")
        with self.assertRaises(LeaseHeld):
            sim.begin_other("n2")
        self.assertEqual(sim.spawned, 1)

    def test_surviving_descendant_blocks_a_second_nonce(self) -> None:
        sim = HolderSim()
        sim.run_through("fsync_running")
        child = sim.payload_forks()
        sim.mark_dead(sim.durable["pid"])
        sim.crash()
        result = sim.recover()
        self.assertEqual(result["wait"], "echild")
        self.assertEqual(result["action"], "supervise")
        self.assertTrue(result["lease"])
        self.assertTrue(sim.procs[child].alive)
        with self.assertRaises(LeaseHeld):
            sim.begin_other("n2")
        sim.mark_dead(child)
        sim.crash()
        released = sim.recover()
        self.assertEqual(released["wait"], "echild")
        self.assertEqual(released["action"], "terminated-without-status")
        self.assertFalse(released["lease"])
        sim.begin_other("n2")
        self.assertEqual(sim.spawned, 1)
        self.assertNotEqual(sim.durable["nonce"], "n1")

    def test_parent_death_before_spawn_spends_the_nonce(self) -> None:
        sim = HolderSim()
        sim.run_through("write_intent")
        sim.crash()
        result = sim.recover()
        self.assertEqual(result["spawned"], 0)
        self.assertEqual(result["action"], "spent-without-spawn")
        self.assertFalse(result["lease"])
        with self.assertRaises(NonceSpent):
            sim.begin_other("n1")
        sim.begin_other("n2")
        self.assertEqual(sim.spawned, 1)


class ForeignProcessTests(unittest.TestCase):
    def test_waitpid_on_an_orphan_is_not_an_exit_status(self) -> None:
        code = textwrap.dedent(
            """
            import os, sys, time
            pid = os.fork()
            if pid == 0:
                null = os.open("/dev/null", os.O_RDWR)
                os.dup2(null, 0)
                os.dup2(null, 1)
                os.dup2(null, 2)
                time.sleep(60)
                os._exit(0)
            sys.stdout.write(str(pid))
            sys.stdout.flush()
            os._exit(0)
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        child = int(completed.stdout.strip())
        try:
            self.assertEqual(foreign_wait(child), "echild")
        finally:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def test_run_py_does_not_call_the_holder_protocol(self) -> None:
        text = (ROOT / "src" / "runspecimen" / "run.py").read_text(encoding="utf-8")
        self.assertNotIn("holder_protocol", text)
        self.assertNotIn("bind_execution", text)


if __name__ == "__main__":
    unittest.main()
