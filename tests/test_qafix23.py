"""qafix23 regressions: shebang args, interpreter names, lock leak, hint wording."""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFY_INSTALLED = ROOT / "scripts" / "verify_installed_wheel.py"
HUMAN_ACCEPTANCE = ROOT / "docs" / "HUMAN-ACCEPTANCE.md"
PRESENT_PY = ROOT / "src" / "runspecimen" / "present.py"


def _load_verify_module():
    """Load verify_installed_wheel.py as a module for unit testing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("verify_installed_wheel", VERIFY_INSTALLED)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load verify_installed_wheel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Qa2201ShebangArgsTests(unittest.TestCase):
    """QA22-01: Refuse shebang with interpreter args."""

    def test_shebang_with_args_is_refused(self) -> None:
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()
        with tempfile.TemporaryDirectory(prefix="rs-qa2201-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            python = venv_bin / "python"
            python.write_text("#!/usr/bin/env python3\npass\n", encoding="utf-8")
            launcher = venv_bin / "runspecimen"
            launcher.write_bytes(
                f"#!{python} -O\n# -*- coding: utf-8 -*-\nprint('canary')\n".encode("utf-8")
            )
            launcher.chmod(0o755)
            with self.assertRaises(module.UnsupportedShebangError) as ctx:
                module.interpreter_from_launcher(launcher)
            self.assertIn("extra interpreter args", str(ctx.exception))

    def test_shebang_without_args_is_accepted(self) -> None:
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()
        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2201-clean-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            python = venv_bin / "python"
            python.symlink_to(real)
            launcher = venv_bin / "runspecimen"
            launcher.write_bytes(f"#!{python}\n# body\n".encode("utf-8"))
            launcher.chmod(0o755)
            result = module.interpreter_from_launcher(launcher)
            self.assertEqual(result, python)


class Qa2202InterpreterNameTests(unittest.TestCase):
    """QA22-02: Refuse unchecked interpreter names."""

    def test_python2_is_refused_in_shebang(self) -> None:
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()
        self.assertFalse(module._is_identity_checked_interpreter_name("python2"))
        self.assertFalse(module._is_identity_checked_interpreter_name("python2.7"))

    def test_python3_versions_are_accepted(self) -> None:
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()
        self.assertTrue(module._is_identity_checked_interpreter_name("python"))
        self.assertTrue(module._is_identity_checked_interpreter_name("python3"))
        self.assertTrue(module._is_identity_checked_interpreter_name("python3.11"))
        self.assertTrue(module._is_identity_checked_interpreter_name("python3.12t"))
        self.assertTrue(module._is_identity_checked_interpreter_name("pythonw"))
        self.assertTrue(module._is_identity_checked_interpreter_name("\N{MATHEMATICAL ITALIC SMALL PI}thon"))

    def test_python2_is_refused_in_bin_allowlist(self) -> None:
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()
        self.assertFalse(module.is_allowed_venv_bin_name("python2"))
        self.assertFalse(module.is_allowed_venv_bin_name("python2.7"))

    def test_python3_is_accepted_in_bin_allowlist(self) -> None:
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()
        self.assertTrue(module.is_allowed_venv_bin_name("python"))
        self.assertTrue(module.is_allowed_venv_bin_name("python3"))
        self.assertTrue(module.is_allowed_venv_bin_name("python3.11"))
        self.assertTrue(module.is_allowed_venv_bin_name("python3.12t"))

    def test_venv_interpreter_entry_consistent_with_identity_check(self) -> None:
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()
        for name in ("python", "python3", "python3.11", "python3.12t", "pythonw"):
            self.assertEqual(
                module._is_venv_interpreter_entry(name),
                module._is_identity_checked_interpreter_name(name),
                f"inconsistent policy for {name}",
            )
        for name in ("python2", "python2.7"):
            self.assertFalse(module._is_venv_interpreter_entry(name), name)
            self.assertFalse(module._is_identity_checked_interpreter_name(name), name)


class Qa2203DocOrderTests(unittest.TestCase):
    """QA22-03: HUMAN-ACCEPTANCE.md runs verify before venv code."""

    def test_n3_verify_before_version(self) -> None:
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")
        n3_match = re.search(r"## N3.*?(?=## N4|\Z)", text, re.DOTALL)
        self.assertIsNotNone(n3_match, "N3 section not found")
        n3_text = n3_match.group(0)
        verify_pos = n3_text.find("rs_ok N3-verify")
        version_pos = n3_text.find("rs_ok N3-version")
        self.assertGreater(verify_pos, 0, "N3-verify not found")
        self.assertGreater(version_pos, 0, "N3-version not found")
        self.assertLess(verify_pos, version_pos, "verify must come before version in N3")

    def test_record_section_mentions_base_interpreter_probe(self) -> None:
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")
        self.assertIn("base-interpreter probe", text)
        self.assertIn("startup disabled", text)
        self.assertNotIn("real launcher doctor process", text.lower())


class Qa2204LockLeakTests(unittest.TestCase):
    """QA22-04: Event-log lock released on refusal.
    
    The test plants a FIFO (or directory on systems without mkfifo) at the
    events.jsonl path. A symlink is refused in _prepare_log_parent before the
    lock is taken, so it does not exercise the lock leak. A FIFO or directory
    takes the lock and then fails in _ensure_file_unlocked, which is where the
    leak would occur.
    """

    def test_lock_released_on_ensure_file_failure(self) -> None:
        from runspecimen.events import EventLog
        from runspecimen.errors import PathEscapeError

        with tempfile.TemporaryDirectory(prefix="rs-qa2204-") as raw:
            root = Path(raw)
            state_dir = root / ".runspecimen" / "runs" / "c" / "r"
            state_dir.mkdir(parents=True)
            log = EventLog.for_state_dir(state_dir)
            events_path = state_dir / "events.jsonl"
            try:
                os.mkfifo(str(events_path))
            except (OSError, AttributeError):
                events_path.mkdir()
            fd_count_before = len(os.listdir(f"/proc/{os.getpid()}/fd")) if Path("/proc/self/fd").exists() else -1
            with self.assertRaises((OSError, PathEscapeError)):
                log.append("test", {"key": "value"})
            lock_path = state_dir / "events.append.lock"
            if lock_path.exists():
                fd = os.open(str(lock_path), os.O_RDWR)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except BlockingIOError:
                    self.fail("Lock is still held after refusal - fd leak detected")
                finally:
                    os.close(fd)
            if fd_count_before >= 0:
                fd_count_after = len(os.listdir(f"/proc/{os.getpid()}/fd"))
                self.assertEqual(fd_count_before, fd_count_after, "fd count changed - possible leak")

    def test_append_then_retry_works_after_refusal(self) -> None:
        from runspecimen.events import EventLog
        from runspecimen.errors import PathEscapeError

        with tempfile.TemporaryDirectory(prefix="rs-qa2204-retry-") as raw:
            root = Path(raw)
            state_dir = root / ".runspecimen" / "runs" / "c" / "r"
            state_dir.mkdir(parents=True)
            log = EventLog.for_state_dir(state_dir)
            events_path = state_dir / "events.jsonl"
            try:
                os.mkfifo(str(events_path))
            except (OSError, AttributeError):
                events_path.mkdir()
            with self.assertRaises((OSError, PathEscapeError)):
                log.append("test1", {"key": "value"})
            if events_path.is_dir():
                events_path.rmdir()
            else:
                events_path.unlink()
            record = log.append("test2", {"key": "value"})
            self.assertEqual(record.seq, 1)
            self.assertEqual(record.type, "test2")


class Qa2205HintWordingTests(unittest.TestCase):
    """QA22-05: present.py hint wording is honest about limitations."""

    def test_interactive_tty_hint_is_honest(self) -> None:
        if not PRESENT_PY.is_file():
            self.skipTest("present.py not found")
        text = PRESENT_PY.read_text(encoding="utf-8")
        self.assertNotIn("show up as broken receipts", text)
        self.assertIn("Inconsistent edits to local records can be detected", text)
        self.assertIn("fabricate consistent evidence", text)
        self.assertIn("signing with an inaccessible key", text)

    def test_hint_consistent_with_cli_about_summary(self) -> None:
        from runspecimen.cli import _ABOUT_SUMMARY
        from runspecimen.present import _ERROR_HINTS

        hint_text = ""
        for name, text in _ERROR_HINTS:
            if name == "interactive TTY":
                hint_text = text
                break
        self.assertIn("signing with", hint_text.lower())
        self.assertIn("signing with", _ABOUT_SUMMARY.lower())
        self.assertIn("fabricate", hint_text)
        self.assertIn("fake approval", _ABOUT_SUMMARY)


if __name__ == "__main__":
    unittest.main()
