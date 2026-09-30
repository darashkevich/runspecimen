"""Unprivileged tests for snapshot binding and the launch handshake.

These tests do not call Touch ID, do not type an approval phrase, and do
not start the product run path.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

import runspecimen.holder_protocol as holder_protocol
from runspecimen.holder_protocol import (
    HolderSim,
    LaunchRequest,
    LeaseHeld,
    NonceSpent,
    PipeEOF,
    ProtocolError,
    assess_durable,
    bind_execution,
    foreign_wait,
    read_durable_record,
    restat_agrees_with_snapshot,
    write_durable_record,
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

    def _fingerprints(self, *paths: pathlib.Path) -> dict[str, str]:
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

    def _request(self, executable: pathlib.Path, script: pathlib.Path, extra: tuple[str, ...] = ()) -> LaunchRequest:
        extra_paths = tuple(pathlib.Path(item) for item in extra)
        source = self.root / "input.txt"
        return LaunchRequest(
            nonce="n1",
            argv=(str(executable), str(script), str(source)),
            executable=str(executable),
            script=str(script),
            inputs=(str(source),),
            dependencies=(str(executable), *extra),
            outputs=("result.txt",),
            fingerprints=self._fingerprints(executable, script, source, *extra_paths),
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

    def test_precreated_wrong_bytes_are_rejected_via_the_opened_fd(self) -> None:
        interpreter = self._file("interp", b"interp")
        script = self._file("run.sh", f"#!{interpreter}\n".encode())
        source = self._file("input.txt", b"expected-bytes")
        digest = hashlib.sha256(b"expected-bytes").hexdigest()
        planted = self.root / "snap" / "files" / digest
        planted.parent.mkdir(parents=True)
        planted.write_bytes(b"wrong-bytes")
        with self.assertRaises(ProtocolError) as caught:
            bind_execution(self._request(interpreter, script), self.root / "snap")
        self.assertIn("reused snapshot", str(caught.exception))
        self.assertEqual(planted.read_bytes(), b"wrong-bytes")

    def test_precreated_symlink_and_directory_are_rejected(self) -> None:
        interpreter = self._file("interp", b"interp")
        script = self._file("run.sh", f"#!{interpreter}\n".encode())
        source = self._file("input.txt", b"expected-bytes")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        for kind in ("link", "dir"):
            with self.subTest(kind=kind):
                root = self.root / kind
                planted = root / "files" / digest
                planted.parent.mkdir(parents=True)
                if kind == "link":
                    planted.symlink_to(source)
                else:
                    planted.mkdir()
                with self.assertRaises(ProtocolError):
                    bind_execution(self._request(interpreter, script), root)

    def test_matching_precreated_file_is_what_the_fd_reads(self) -> None:
        interpreter = self._file("interp", b"interp")
        script = self._file("run.sh", f"#!{interpreter}\n".encode())
        source = self._file("input.txt", b"expected-bytes")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        planted = self.root / "snap" / "files" / digest
        planted.parent.mkdir(parents=True)
        planted.write_bytes(source.read_bytes())
        inode = planted.stat().st_ino
        self.bound = bind_execution(self._request(interpreter, script), self.root / "snap")
        snap = self.bound.snapshot_for(str(source))
        os.lseek(snap.fd, 0, os.SEEK_SET)
        self.assertEqual(os.read(snap.fd, 100), b"expected-bytes")
        self.assertEqual(snap.digest, digest)
        self.assertEqual(snap.inode, inode)
        self.assertEqual(stat.S_IMODE(pathlib.Path(snap.path).stat().st_mode) & 0o111, 0)

    def test_missing_or_invalid_fingerprint_fails_closed(self) -> None:
        interpreter = self._file("interp", b"interp")
        script = self._file("run.sh", f"#!{interpreter}\n".encode())
        self._file("input.txt", b"expected-bytes")
        request = self._request(interpreter, script)
        missing = LaunchRequest(**{**request.__dict__, "fingerprints": {}})
        with self.assertRaises(ProtocolError) as absent:
            bind_execution(missing, self.root / "snap-missing")
        self.assertIn("fingerprints", str(absent.exception))
        partial = dict(request.fingerprints)
        partial.pop(str(self.root / "input.txt"))
        with self.assertRaises(ProtocolError):
            bind_execution(
                LaunchRequest(**{**request.__dict__, "fingerprints": partial}),
                self.root / "snap-partial",
            )
        malformed = dict(request.fingerprints)
        malformed[str(interpreter)] = "abcd"
        with self.assertRaises(ProtocolError) as bad:
            bind_execution(
                LaunchRequest(**{**request.__dict__, "fingerprints": malformed}),
                self.root / "snap-bad",
            )
        self.assertIn("sha256", str(bad.exception))
        wrong = dict(request.fingerprints)
        wrong[request.executable] = hashlib.sha256(b"other").hexdigest()
        with self.assertRaises(ProtocolError) as mismatch:
            bind_execution(
                LaunchRequest(**{**request.__dict__, "fingerprints": wrong}),
                self.root / "snap-wrong",
            )
        self.assertIn("do not match", str(mismatch.exception))

    def test_short_writes_still_match_and_cleanup_failure_is_reported(self) -> None:
        interpreter = self._file("interp", b"interp")
        script = self._file("run.sh", f"#!{interpreter}\n".encode())
        self._file("input.txt", b"expected-bytes")
        request = self._request(interpreter, script)
        real_write = holder_protocol.os.write

        def one_byte(fd: int, data: bytes | memoryview) -> int:
            view = memoryview(data)
            if not view:
                return 0
            return real_write(fd, view[:1])

        with mock.patch.object(holder_protocol.os, "write", one_byte):
            self.bound = bind_execution(request, self.root / "snap-short")
        for item in self.bound.snapshots:
            os.lseek(item.fd, 0, os.SEEK_SET)
            self.assertEqual(hashlib.sha256(os.read(item.fd, 1_000_000)).hexdigest(), item.digest)

        def fail_write(fd: int, data: bytes | memoryview) -> int:
            return 0

        def fail_unlink(path: str | pathlib.Path) -> None:
            raise OSError("busy")

        with mock.patch.object(holder_protocol.os, "write", fail_write), mock.patch.object(
            holder_protocol.os, "unlink", fail_unlink
        ):
            with self.assertRaises(ProtocolError) as caught:
                bind_execution(request, self.root / "snap-cleanup")
        self.assertIn("cleanup failed", str(caught.exception))

    def test_returned_command_runs_and_shebang_names_the_snapshot_interpreter(self) -> None:
        shell = pathlib.Path("/bin/sh")
        script = self._file(
            "run.sh",
            f"#!{shell}\nIFS= read -r line < \"$1\"\nprintf '%s' \"$line\"\n".encode(),
        )
        source = self._file("input.txt", b"approved\n")
        self.bound = bind_execution(
            LaunchRequest(
                nonce="n1",
                argv=(str(script), str(source)),
                executable=str(script),
                script=str(script),
                inputs=(str(source),),
                dependencies=(str(shell),),
                fingerprints=self._fingerprints(script, source, shell),
            ),
            self.root / "snap",
        )
        argv0 = pathlib.Path(self.bound.argv[0])
        self.assertTrue(argv0.stat().st_mode & stat.S_IXUSR)
        interpreter = self.bound.snapshot_for(str(shell))
        self.assertTrue(pathlib.Path(interpreter.path).stat().st_mode & stat.S_IXUSR)
        script_snap = self.bound.snapshot_for(str(script))
        os.lseek(script_snap.fd, 0, os.SEEK_SET)
        fd_bytes = os.read(script_snap.fd, 1_000_000)
        self.assertEqual(hashlib.sha256(fd_bytes).hexdigest(), script_snap.digest)
        self.assertEqual(script_snap.source_digest, hashlib.sha256(script.read_bytes()).hexdigest())
        self.assertNotEqual(script_snap.digest, script_snap.source_digest)
        self.assertEqual(fd_bytes.splitlines()[0], f"#!{interpreter.path}".encode())
        self.assertIn(b"printf '%s' \"$line\"", fd_bytes)
        completed = subprocess.run(
            self.bound.argv,
            cwd=self.bound.cwd,
            check=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(completed.stdout, b"approved")


class HandshakeTests(unittest.TestCase):
    """HolderSim only. These crashes do not fsync a file and do not reap a real child."""
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

    def test_simulator_does_not_persist_and_partial_state_does_not_spawn(self) -> None:
        self.assertFalse(HolderSim.persists)
        for record in (
            {"phase": "armed", "nonce": "n1"},
            {"phase": "running", "nonce": "n1", "pid": 9},
            {"phase": "acked", "pid": 9, "start": 3},
            {"nonce": "n1"},
        ):
            with self.subTest(record=record):
                sim = HolderSim()
                sim.crash()
                sim.durable = dict(record)
                result = sim.recover()
                self.assertEqual(result["wait"], "echild")
                self.assertEqual(result["action"], "partial-record")
                self.assertEqual(result["spawned"], 0)
                self.assertTrue(result["lease"])
                self.assertEqual(sim.durable["phase"], "unknown")
                with self.assertRaises(LeaseHeld):
                    sim.begin_other("n2")


class DurableFileTests(unittest.TestCase):
    """Real files. A pass here is not a HolderSim crash result."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_fsynced_record_and_partial_files_do_not_launch(self) -> None:
        path = self.root / "launch.json"
        record = {"nonce": "n1", "phase": "armed", "pid": 4, "start": 2}
        write_durable_record(path, record)
        self.assertEqual(read_durable_record(path), record)
        decision = assess_durable(read_durable_record(path))
        self.assertFalse(decision["spawn"])
        self.assertEqual(decision["wait"], "echild")
        self.assertEqual(decision["action"], "not-parent-do-not-commit")
        self.assertTrue(decision["lease"])

        missing = assess_durable(read_durable_record(self.root / "absent.json"))
        self.assertEqual(missing["action"], "missing-record")
        self.assertFalse(missing["spawn"])
        self.assertFalse(missing["lease"])
        self.assertEqual(missing["wait"], "echild")

        for payload in (b"", b'{"phase":'):
            partial = self.root / "partial.json"
            partial.write_bytes(payload)
            with self.assertRaises(ProtocolError) as caught:
                read_durable_record(partial)
            self.assertIn("partial", str(caught.exception))

        held = assess_durable({"phase": "running", "nonce": "n1", "pid": 1})
        self.assertEqual(held["action"], "partial-record")
        self.assertTrue(held["lease"])
        self.assertFalse(held["spawn"])
        self.assertEqual(held["wait"], "echild")
        spent = assess_durable({"phase": "intent", "nonce": "n1"})
        self.assertEqual(spent["action"], "spent-without-spawn")
        self.assertFalse(spent["spawn"])
        self.assertFalse(spent["lease"])

        link = self.root / "link.json"
        link.symlink_to(path)
        with self.assertRaises(ProtocolError):
            read_durable_record(link)

    def test_durable_cleanup_failure_is_reported(self) -> None:
        def fail_write(fd: int, data: bytes | memoryview) -> int:
            return 0

        def fail_unlink(path: str | pathlib.Path) -> None:
            raise OSError("busy")

        with mock.patch.object(holder_protocol.os, "write", fail_write), mock.patch.object(
            holder_protocol.os, "unlink", fail_unlink
        ):
            with self.assertRaises(ProtocolError) as caught:
                write_durable_record(self.root / "launch.json", {"phase": "intent", "nonce": "n1"})
        self.assertIn("cleanup failed", str(caught.exception))


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
