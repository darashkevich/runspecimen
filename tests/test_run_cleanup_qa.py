"""Real-process coverage for PR80 independent-QA findings.

These tests drive the CLI (or the membership helpers) against disposable
fixture-approved contracts. They must fail on 3a3c5fe and pass after the
cleanup/supervisor fixes.
"""

from __future__ import annotations

import errno
import json
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


BG_JOB = (
    "import os\n"
    "from pathlib import Path\n"
    "os.system('sleep 30 >/dev/null 2>&1 & echo $! > outputs/bg.pid')\n"
    "Path('outputs/out.json').write_text('{\"status\": \"ok\", \"n\": 1}\\n')\n"
    "print('done')\n"
)

LONG_JOB = (
    "import os, signal, time\n"
    "from pathlib import Path\n"
    "for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):\n"
    "    signal.signal(sig, signal.SIG_IGN)\n"
    "Path('outputs/pid').write_text(str(os.getpid()))\n"
    "while True:\n"
    "    time.sleep(0.02)\n"
)

FAST_JOB = (
    "from pathlib import Path\n"
    "Path('outputs/out.json').write_text('{\"status\": \"ok\", \"n\": 1}\\n')\n"
    "print('done')\n"
)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _kill_group(pid: int) -> None:
    if pid <= 0:
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _eperm_driver(ws: Path, marker: Path) -> list[str]:
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
    return [sys.executable, str(driver), str(marker)]


def _late_term_driver(ws: Path) -> list[str]:
    """Widen the post-result window so a late SIGTERM is delivered before JSON."""
    driver = ws / "late_term_driver.py"
    driver.write_text(
        "import time\n"
        "from runspecimen import cli\n"
        "real_emit = cli._emit\n"
        "def slow_emit(*args, **kwargs):\n"
        "    time.sleep(0.3)\n"
        "    return real_emit(*args, **kwargs)\n"
        "cli._emit = slow_emit\n"
        "raise SystemExit(cli.main())\n"
    )
    return [sys.executable, str(driver)]


class RunCleanupQATests(unittest.TestCase):
    def _approve_contract(self, ws: Path, job: str, *, wall_sec: int) -> Path:
        (ws / "work" / "job.py").write_text(job)
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
        return contract

    def _start_cli(
        self,
        ws: Path,
        contract: Path,
        *,
        extra_argv: list[str] | None = None,
    ) -> subprocess.Popen:
        argv = extra_argv or [sys.executable, "-m", "runspecimen"]
        return subprocess.Popen(
            argv + ["run", "--workspace", str(ws), "--contract", str(contract)],
            env=dict(os.environ, PYTHONPATH=str(SRC)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

    def _wait_file(self, path: Path, cli: subprocess.Popen, timeout: float = 5.0) -> str:
        deadline = time.monotonic() + timeout
        while not path.exists():
            self.assertIsNone(cli.poll(), f"CLI exited before {path.name}")
            self.assertLess(time.monotonic(), deadline, f"{path.name} startup timeout")
            time.sleep(0.01)
        return path.read_text().strip()

    def test_redirected_background_member_is_stopped_on_normal_exit(self):
        """P1-01: sh -c 'sleep >/dev/null 2>&1 &' must not survive completed."""
        td = seed_workspace(BG_JOB)
        ws = Path(td.name)
        cli = None
        bg_pid = 0
        try:
            contract = self._approve_contract(ws, BG_JOB, wall_sec=8)
            cli = self._start_cli(ws, contract)
            bg_pid = int(self._wait_file(ws / "outputs" / "bg.pid", cli))
            stdout, stderr = cli.communicate(timeout=8)
            self.assertEqual(cli.returncode, 0, (stdout, stderr))
            state = load_state(run_state_dir(ws, "camp", "run-a"))
            self.assertEqual(state["phase"], "completed")
            self.assertEqual(state["run_result"], "completed")
            self.assertTrue(state.get("cleanup_confirmed"))
            self.assertFalse(
                Lease.for_workspace(ws, holder="probe").is_locked_by_other()
            )
            self.assertFalse(
                _pid_alive(bg_pid),
                "background process-group member survived a completed run",
            )
            self.assertEqual(state.get("cleanup_scope"), "process_group")
        finally:
            if cli is not None and cli.poll() is None:
                cli.kill()
                cli.communicate(timeout=5)
            _kill_group(bg_pid)
            td.cleanup()

    def test_eperm_on_completed_leader_reports_pending_and_keeps_lease(self):
        """P3-06 / P1-01 EPERM: leader already gone, group kill denied."""
        td = seed_workspace(BG_JOB)
        ws = Path(td.name)
        cli = None
        bg_pid = 0
        deny = ws / "outputs" / "deny_cleanup"
        try:
            contract = self._approve_contract(ws, BG_JOB, wall_sec=8)
            deny.touch()
            cli = self._start_cli(ws, contract, extra_argv=_eperm_driver(ws, deny))
            bg_pid = int(self._wait_file(ws / "outputs" / "bg.pid", cli))
            stdout, stderr = cli.communicate(timeout=8)
            self.assertNotEqual(cli.returncode, 0, (stdout, stderr))
            state = load_state(run_state_dir(ws, "camp", "run-a"))
            self.assertEqual(state["phase"], "cleanup_pending")
            self.assertFalse(state.get("cleanup_confirmed", True))
            self.assertTrue(_pid_alive(bg_pid), "denied cleanup must leave the member")
            lease = Lease.for_workspace(ws, holder="probe")
            self.assertTrue(lease.is_locked_by_other(), "lease must stay held")
            self.assertIn(b"lease retained", stderr.lower())

            deny.unlink()
            deadline = time.monotonic() + 8
            while _pid_alive(bg_pid) or lease.is_locked_by_other():
                self.assertLess(
                    time.monotonic(),
                    deadline,
                    "deferred cleanup did not finish after EPERM was cleared",
                )
                time.sleep(0.02)
            state = load_state(run_state_dir(ws, "camp", "run-a"))
            self.assertTrue(state.get("cleanup_confirmed"))
            self.assertIn(state["phase"], ("failed", "completed"))
        finally:
            deny.unlink(missing_ok=True)
            if cli is not None and cli.poll() is None:
                cli.kill()
                cli.communicate(timeout=5)
            _kill_group(bg_pid)
            td.cleanup()

    def test_supervisor_only_kill_does_not_orphan_or_free_lease_while_alive(self):
        """P2-01: SIGKILL of the supervisor alone must not orphan the contract."""
        td = seed_workspace(LONG_JOB)
        ws = Path(td.name)
        cli = None
        contract_pid = 0
        try:
            contract = self._approve_contract(ws, LONG_JOB, wall_sec=4)
            cli = self._start_cli(ws, contract)
            contract_pid = int(self._wait_file(ws / "outputs" / "pid", cli))
            lease = Lease.for_workspace(ws, holder="probe")
            meta = lease.read_meta()
            self.assertIsNotNone(meta)
            supervisor_pid = int(meta.pid)
            self.assertTrue(_pid_alive(supervisor_pid))
            self.assertNotEqual(supervisor_pid, cli.pid)
            self.assertNotEqual(supervisor_pid, contract_pid)

            os.kill(supervisor_pid, signal.SIGKILL)
            deadline = time.monotonic() + 6
            while _pid_alive(contract_pid):
                self.assertTrue(
                    lease.is_locked_by_other(),
                    "lease must remain held while the contract is alive",
                )
                self.assertLess(
                    time.monotonic(),
                    deadline,
                    "contract survived supervisor death past the wall budget",
                )
                time.sleep(0.02)
            while lease.is_locked_by_other():
                self.assertLess(
                    time.monotonic(),
                    deadline,
                    "lease stuck after supervisor and contract died",
                )
                time.sleep(0.02)
            if cli.poll() is None:
                cli.communicate(timeout=5)
            else:
                cli.communicate(timeout=1)
        finally:
            if cli is not None and cli.poll() is None:
                cli.kill()
                cli.communicate(timeout=5)
            _kill_group(contract_pid)
            td.cleanup()

    def test_eperm_plus_unwritable_state_retains_lease_while_contract_alive(self):
        """P2-02: capture/state write failure must not drop cleanup_pending."""
        td = seed_workspace(LONG_JOB)
        ws = Path(td.name)
        cli = None
        contract_pid = 0
        state_dir = None
        deny = ws / "outputs" / "deny_cleanup"
        try:
            contract = self._approve_contract(ws, LONG_JOB, wall_sec=8)
            deny.touch()
            cli = self._start_cli(ws, contract, extra_argv=_eperm_driver(ws, deny))
            contract_pid = int(self._wait_file(ws / "outputs" / "pid", cli))
            state_dir = run_state_dir(ws, "camp", "run-a")
            os.chmod(state_dir, 0o555)
            os.kill(cli.pid, signal.SIGTERM)
            stdout, stderr = cli.communicate(timeout=8)
            self.assertNotEqual(cli.returncode, 0, (stdout, stderr))
            self.assertTrue(_pid_alive(contract_pid), "contract must still be alive")
            self.assertTrue(
                Lease.for_workspace(ws, holder="probe").is_locked_by_other(),
                "lease was released while cleanup was unconfirmed",
            )
            self.assertNotIn(
                b".stdout.capture.",
                stderr,
                "capture-write failure must not replace the retain path",
            )
        finally:
            if state_dir is not None and state_dir.exists():
                os.chmod(state_dir, 0o755)
            deny.unlink(missing_ok=True)
            if cli is not None and cli.poll() is None:
                cli.kill()
                cli.communicate(timeout=5)
            _kill_group(contract_pid)
            td.cleanup()

    def test_leader_exit_probe_does_not_call_waitid_off_linux(self):
        """macOS waitid(WNOHANG|WNOWAIT) can block; do not call it there."""
        from runspecimen.run import _leader_exited_unreaped

        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 2
            with patch("runspecimen.run.sys.platform", "darwin"), patch(
                "runspecimen.run.os.waitid",
                side_effect=AssertionError("waitid must not run off linux"),
            ):
                while not _leader_exited_unreaped(proc):
                    self.assertLess(
                        time.monotonic(),
                        deadline,
                        "darwin exit probe did not see the unreaped leader",
                    )
                    time.sleep(0.01)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=2)

    def test_leftover_member_is_killed_when_killpg_returns_esrch(self):
        """macOS: killpg can be ESRCH after the leader exits; members must still die."""
        from runspecimen.run import _stop_process

        td = seed_workspace()
        pid_dir = Path(td.name)
        leader = None
        member_pid = 0
        try:
            leader = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import os, subprocess, sys, time\n"
                    "from pathlib import Path\n"
                    "Path(sys.argv[1]).write_text(str(os.getpid()))\n"
                    "child = subprocess.Popen("
                    "[sys.executable, '-c', 'import time; time.sleep(30)']"
                    ")\n"
                    "Path(sys.argv[2]).write_text(str(child.pid))\n"
                    "time.sleep(30)\n",
                    str(pid_dir / "leader.pid"),
                    str(pid_dir / "member.pid"),
                ],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 5
            while not (pid_dir / "member.pid").exists():
                self.assertIsNone(leader.poll(), "leader exited before spawning member")
                self.assertLess(time.monotonic(), deadline, "member pid not written")
                time.sleep(0.01)
            member_pid = int((pid_dir / "member.pid").read_text())
            os.kill(leader.pid, signal.SIGKILL)
            leader.wait(timeout=2)
            self.assertTrue(_pid_alive(member_pid), "member must survive leader reap")

            class _Reaped:
                pid = leader.pid
                returncode = -9

                def wait(self, timeout=None):
                    return self.returncode

            with patch(
                "runspecimen.run.os.killpg",
                side_effect=ProcessLookupError("ESRCH"),
            ):
                _stop_process(_Reaped())
            self.assertFalse(
                _pid_alive(member_pid),
                "member must be killed by pid when killpg is ESRCH",
            )
        finally:
            if leader is not None and leader.poll() is None:
                leader.kill()
                leader.wait(timeout=2)
            _kill_group(member_pid)
            td.cleanup()

    def test_failed_ps_probe_is_not_treated_as_no_members(self):
        """P2-03: a failing membership probe must not confirm an empty group."""
        from runspecimen.run import (
            _GroupMembershipUnknown,
            _live_group_members,
            _stop_process,
        )
        from runspecimen.errors import RunError

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            with patch("runspecimen.run._proc_available", return_value=False), patch(
                "runspecimen.run._PS_ARGV", ["/bin/false"]
            ), patch("runspecimen.run.sys.platform", "linux"):
                with self.assertRaises(_GroupMembershipUnknown):
                    _live_group_members(proc.pid, 1.0)
                self.assertTrue(_pid_alive(proc.pid))
                with patch("runspecimen.run.os.killpg"):
                    with self.assertRaises(RunError) as ctx:
                        _stop_process(proc)
                    self.assertIn("unconfirmed", str(ctx.exception).lower())
                self.assertTrue(
                    _pid_alive(proc.pid),
                    "fail-closed probe must not confirm death",
                )
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)

    def test_darwin_empty_group_confirms_when_ps_fails(self):
        """macOS must not enter unbounded retain when libproc sees no live members."""
        from runspecimen.run import _stop_process

        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            proc.wait(timeout=2)

            class _Reaped:
                pid = proc.pid
                returncode = 0

                def wait(self, timeout=None):
                    return self.returncode

            with patch("runspecimen.run.sys.platform", "darwin"), patch(
                "runspecimen.run._proc_available", return_value=False
            ), patch("runspecimen.run._PS_ARGV", ["/bin/false"]), patch(
                "runspecimen.run._darwin_group_members",
                return_value=[],
                create=True,
            ), patch(
                "runspecimen.run.os.killpg",
                side_effect=ProcessLookupError("ESRCH"),
            ):
                try:
                    _stop_process(_Reaped())
                except Exception as exc:
                    self.fail(
                        "empty Darwin group must confirm without retain, "
                        f"got {type(exc).__name__}: {exc}"
                    )
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2)

    def test_darwin_lists_leftover_member_when_ps_fails(self):
        """macOS libproc must still find leftover members if /bin/ps fails."""
        from runspecimen.run import _stop_process

        td = seed_workspace()
        pid_dir = Path(td.name)
        leader = None
        member_pid = 0
        try:
            leader = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import os, subprocess, sys, time\n"
                    "from pathlib import Path\n"
                    "Path(sys.argv[1]).write_text(str(os.getpid()))\n"
                    "child = subprocess.Popen("
                    "[sys.executable, '-c', 'import time; time.sleep(30)']"
                    ")\n"
                    "Path(sys.argv[2]).write_text(str(child.pid))\n"
                    "time.sleep(30)\n",
                    str(pid_dir / "leader.pid"),
                    str(pid_dir / "member.pid"),
                ],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 5
            while not (pid_dir / "member.pid").exists():
                self.assertIsNone(leader.poll(), "leader exited before spawning member")
                self.assertLess(time.monotonic(), deadline, "member pid not written")
                time.sleep(0.01)
            member_pid = int((pid_dir / "member.pid").read_text())
            os.kill(leader.pid, signal.SIGKILL)
            leader.wait(timeout=2)
            self.assertTrue(_pid_alive(member_pid), "member must survive leader reap")

            class _Reaped:
                pid = leader.pid
                returncode = -9

                def wait(self, timeout=None):
                    return self.returncode

            with patch("runspecimen.run.sys.platform", "darwin"), patch(
                "runspecimen.run._proc_available", return_value=False
            ), patch("runspecimen.run._PS_ARGV", ["/bin/false"]), patch(
                "runspecimen.run._darwin_group_members",
                side_effect=lambda pgid: [member_pid] if _pid_alive(member_pid) else [],
                create=True,
            ), patch(
                "runspecimen.run.os.killpg",
                side_effect=ProcessLookupError("ESRCH"),
            ):
                _stop_process(_Reaped())
            self.assertFalse(
                _pid_alive(member_pid),
                "Darwin membership must still kill leftovers when ps fails",
            )
        finally:
            if leader is not None and leader.poll() is None:
                leader.kill()
                leader.wait(timeout=2)
            _kill_group(member_pid)
            td.cleanup()

    def test_retain_records_pending_before_notifying_cli(self):
        """CLI must not learn cleanup_pending before that phase is on disk."""
        from runspecimen import run as run_mod
        from runspecimen.errors import RunError

        order: list[str] = []

        def fake_update(_state_dir, **fields):
            order.append(str(fields.get("phase") or "update"))

        def fake_notify(_message: str) -> None:
            order.append("notify")

        class _Proc:
            pid = 1
            returncode = -9

        exc = run_mod._CleanupUnconfirmed(_Proc(), "denied")
        td = seed_workspace()
        try:
            with patch.object(run_mod, "_cleanup_notification", fake_notify), patch.object(
                run_mod, "update_state", fake_update
            ), patch.object(run_mod, "_stop_process"), patch.object(
                run_mod.EventLog, "for_state_dir", side_effect=OSError("no log")
            ):
                with self.assertRaises(RunError):
                    run_mod._retain_cleanup(exc, Path(td.name))
            self.assertIn("cleanup_pending", order)
            self.assertIn("notify", order)
            self.assertLess(
                order.index("cleanup_pending"),
                order.index("notify"),
                f"persist must precede notify: {order}",
            )
        finally:
            td.cleanup()

    def test_interrupt_after_leader_exit_stops_background_member(self):
        """P1-01: SIGTERM after the leader has exited still stops the group."""
        td = seed_workspace(BG_JOB)
        ws = Path(td.name)
        cli = None
        bg_pid = 0
        try:
            contract = self._approve_contract(ws, BG_JOB, wall_sec=8)
            cli = self._start_cli(ws, contract)
            bg_pid = int(self._wait_file(ws / "outputs" / "bg.pid", cli))
            os.kill(cli.pid, signal.SIGTERM)
            stdout, stderr = cli.communicate(timeout=8)
            self.assertFalse(
                _pid_alive(bg_pid),
                f"background member survived interrupt after leader exit: {stdout!r} {stderr!r}",
            )
        finally:
            if cli is not None and cli.poll() is None:
                cli.kill()
                cli.communicate(timeout=5)
            _kill_group(bg_pid)
            td.cleanup()

    def test_late_sigterm_after_completed_still_emits_json(self):
        """P3-02: a late SIGTERM must not replace completed JSON with rc -15."""
        td = seed_workspace(FAST_JOB)
        ws = Path(td.name)
        cli = None
        try:
            contract = self._approve_contract(ws, FAST_JOB, wall_sec=8)
            cli = self._start_cli(ws, contract, extra_argv=_late_term_driver(ws))
            state_dir = run_state_dir(ws, "camp", "run-a")
            deadline = time.monotonic() + 5
            while load_state(state_dir).get("phase") != "completed":
                self.assertIsNone(cli.poll(), "CLI exited before completed was recorded")
                self.assertLess(time.monotonic(), deadline, "completed state not written")
                time.sleep(0.01)
            if cli.poll() is None:
                os.kill(cli.pid, signal.SIGTERM)
            stdout, stderr = cli.communicate(timeout=5)
            self.assertEqual(cli.returncode, 0, (stdout, stderr))
            payload = json.loads(stdout.decode())
            self.assertEqual(payload.get("run_result"), "completed")
        finally:
            if cli is not None and cli.poll() is None:
                cli.kill()
                cli.communicate(timeout=5)
            td.cleanup()

    def test_eperm_on_zombie_only_group_proceeds_to_reap(self):
        """Zombie-only EPERM is not a live deny; verified-empty may reap.

        Darwin: killpg on an unreaped zombie-only group returns EPERM, not
        ESRCH (XNU skips SZOMB, POSIX EPERM). Linux killpg on that group is
        ESRCH, so PermissionError is injected. Membership is the real Linux
        /proc probe, which already excludes zombies. Simulated: the EPERM.
        """
        from runspecimen.run import (
            _kill_process_group,
            _leader_exited_unreaped,
            _stop_process,
        )

        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 2
            while not _leader_exited_unreaped(proc):
                self.assertLess(
                    time.monotonic(),
                    deadline,
                    "leader did not become an unreaped zombie",
                )
                time.sleep(0.01)
            self.assertIsNone(proc.returncode, "leader must stay unreaped until stop")

            eperm = PermissionError(errno.EPERM, "Operation not permitted")
            with patch("runspecimen.run.os.killpg", side_effect=eperm):
                try:
                    _kill_process_group(proc)
                except Exception as exc:
                    self.fail(
                        "zombie-only EPERM must not stay unconfirmed on "
                        f"_kill_process_group: {type(exc).__name__}: {exc}"
                    )
                try:
                    _stop_process(proc)
                except Exception as exc:
                    self.fail(
                        "zombie-only EPERM must not stay unconfirmed on "
                        f"_stop_process: {type(exc).__name__}: {exc}"
                    )
            self.assertIsNotNone(proc.returncode, "verified-empty EPERM must reap")
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=2)

    def test_eperm_with_live_members_stays_unconfirmed(self):
        """EPERM plus a live descendant must retain, not reap or ignore.

        Simulated: PermissionError from killpg. Membership is a real leftover
        member still in the leader's group after the leader was reaped.
        """
        from runspecimen.run import _CleanupUnconfirmed, _kill_process_group, _stop_process

        td = seed_workspace()
        pid_dir = Path(td.name)
        leader = None
        member_pid = 0
        try:
            leader = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import os, subprocess, sys, time\n"
                    "from pathlib import Path\n"
                    "Path(sys.argv[1]).write_text(str(os.getpid()))\n"
                    "child = subprocess.Popen("
                    "[sys.executable, '-c', 'import time; time.sleep(30)']"
                    ")\n"
                    "Path(sys.argv[2]).write_text(str(child.pid))\n"
                    "time.sleep(30)\n",
                    str(pid_dir / "leader.pid"),
                    str(pid_dir / "member.pid"),
                ],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 5
            while not (pid_dir / "member.pid").exists():
                self.assertIsNone(leader.poll(), "leader exited before spawning member")
                self.assertLess(time.monotonic(), deadline, "member pid not written")
                time.sleep(0.01)
            member_pid = int((pid_dir / "member.pid").read_text())
            os.kill(leader.pid, signal.SIGKILL)
            leader.wait(timeout=2)
            self.assertTrue(_pid_alive(member_pid), "member must survive leader reap")

            class _Reaped:
                pid = leader.pid
                returncode = -9

                def kill(self):
                    raise AssertionError(
                        "must not substitute leader kill for denied group stop"
                    )

                def wait(self, timeout=None):
                    raise AssertionError("must not reap while live members remain")

            eperm = PermissionError(errno.EPERM, "Operation not permitted")
            with patch("runspecimen.run.os.killpg", side_effect=eperm):
                with self.assertRaises(_CleanupUnconfirmed) as ctx:
                    _kill_process_group(_Reaped())
                self.assertIn("unconfirmed", str(ctx.exception).lower())
                with self.assertRaises(_CleanupUnconfirmed) as ctx:
                    _stop_process(_Reaped())
                self.assertIn("unconfirmed", str(ctx.exception).lower())
            self.assertTrue(
                _pid_alive(member_pid),
                "EPERM with live members must not confirm or kill leftovers",
            )
        finally:
            if leader is not None and leader.poll() is None:
                leader.kill()
                leader.wait(timeout=2)
            _kill_group(member_pid)
            td.cleanup()

    def test_eperm_with_unknown_membership_stays_unconfirmed(self):
        """EPERM plus an unknown probe must retain; do not reap on guess.

        Simulated: PermissionError from killpg, and ``/bin/false`` as ps with
        /proc disabled so membership cannot be proven empty. The payload is a
        real live process. Darwin libproc is not invoked (platform=linux).
        """
        from runspecimen.run import _CleanupUnconfirmed, _kill_process_group, _stop_process

        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            eperm = PermissionError(errno.EPERM, "Operation not permitted")

            class _Guarded:
                pid = proc.pid
                returncode = None

                def kill(self):
                    raise AssertionError(
                        "must not substitute leader kill when membership is unknown"
                    )

                def wait(self, timeout=None):
                    raise AssertionError("must not reap when membership is unknown")

            with patch("runspecimen.run._proc_available", return_value=False), patch(
                "runspecimen.run._PS_ARGV", ["/bin/false"]
            ), patch("runspecimen.run.sys.platform", "linux"), patch(
                "runspecimen.run.os.killpg",
                side_effect=eperm,
            ):
                with self.assertRaises(_CleanupUnconfirmed) as ctx:
                    _kill_process_group(_Guarded())
                self.assertIn("unconfirmed", str(ctx.exception).lower())
                with self.assertRaises(_CleanupUnconfirmed) as ctx:
                    _stop_process(_Guarded())
                self.assertIn("unconfirmed", str(ctx.exception).lower())
            self.assertTrue(_pid_alive(proc.pid))
            self.assertIsNone(proc.returncode)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)

    def test_unwritable_state_after_stop_names_persist_failure(self):
        """P3-03: after a confirmed stop, the error must name state persistence."""
        td = seed_workspace(LONG_JOB)
        ws = Path(td.name)
        cli = None
        contract_pid = 0
        state_dir = None
        try:
            contract = self._approve_contract(ws, LONG_JOB, wall_sec=8)
            cli = self._start_cli(ws, contract)
            contract_pid = int(self._wait_file(ws / "outputs" / "pid", cli))
            state_dir = run_state_dir(ws, "camp", "run-a")
            os.chmod(state_dir, 0o555)
            os.kill(cli.pid, signal.SIGTERM)
            stdout, stderr = cli.communicate(timeout=8)
            self.assertNotEqual(cli.returncode, 0, (stdout, stderr))
            self.assertFalse(_pid_alive(contract_pid), "contract must be stopped")
            self.assertFalse(
                Lease.for_workspace(ws, holder="probe").is_locked_by_other()
            )
            err = stderr.lower()
            self.assertIn(b"state", err)
            self.assertNotIn(b".stdout.capture.", stderr)
        finally:
            if state_dir is not None and state_dir.exists():
                os.chmod(state_dir, 0o755)
            if cli is not None and cli.poll() is None:
                cli.kill()
                cli.communicate(timeout=5)
            _kill_group(contract_pid)
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
