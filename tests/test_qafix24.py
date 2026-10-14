"""Regression tests for qafix24 findings.

QA23-01 P1: CR-injection in shebang (verifier saw only path, probe executed hidden stmt)
QA23-02 P2: CRLF shebang accepted by verifier, rejected by kernel
QA23-03 P2: LF at offset >= 256 accepted by verifier, rejected by kernel
QA23-04 P3: Lock leak test must plant FIFO/directory (covered in test_qafix23.py)
QA23-05 P3: dashboard.py and ABOUT.md wording (doc fix)
QA23-06 P3: HUMAN-ACCEPTANCE.md wording (doc fix)
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
VERIFY_SCRIPT = SCRIPTS_DIR / "verify_installed_wheel.py"

PINNED_CONSOLE_SCRIPT_BODY = b'''\
# -*- coding: utf-8 -*-
import re
import sys
from runspecimen.cli import main
if __name__ == "__main__":
    sys.argv[0] = re.sub(r"(-script\\.pyw|\\.exe)?$", "", sys.argv[0])
    sys.exit(main())
'''


class Qa2301CrInjectionTests(unittest.TestCase):
    """QA23-01: CR-injection in shebang must be refused."""

    def test_cr_before_lf_refused(self) -> None:
        """A shebang with CR before LF must be refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        sys.path.insert(0, str(SCRIPTS_DIR))
        try:
            import verify_installed_wheel as vw
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory(prefix="rs-qa2301-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/usr/bin/python3\rimport os; os.system('id')\n"
            launcher.write_bytes(shebang + PINNED_CONSOLE_SCRIPT_BODY)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(vw.UnsupportedShebangError) as cm:
                vw.interpreter_from_launcher(launcher)
            self.assertIn("carriage return", str(cm.exception).lower())

    def test_hidden_stmt_not_executed_by_probe(self) -> None:
        """Probe must not execute content between CR and LF."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")

        with tempfile.TemporaryDirectory(prefix="rs-qa2301-exec-") as raw:
            root = Path(raw)
            marker = root / "marker.txt"
            launcher = root / "launcher"
            stmt = f"import pathlib; pathlib.Path('{marker}').write_text('executed')"
            shebang = f"#!/usr/bin/python3\r{stmt}\n".encode()
            launcher.write_bytes(shebang + PINNED_CONSOLE_SCRIPT_BODY)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            sys.path.insert(0, str(SCRIPTS_DIR))
            try:
                import verify_installed_wheel as vw
            finally:
                sys.path.pop(0)

            with self.assertRaises(vw.UnsupportedShebangError):
                vw.interpreter_from_launcher(launcher)

            self.assertFalse(marker.exists(), "Hidden statement was executed!")


class Qa2302CrlfShebangTests(unittest.TestCase):
    """QA23-02: CRLF shebang must be refused."""

    def test_crlf_shebang_refused(self) -> None:
        """A shebang ending with CRLF must be refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        sys.path.insert(0, str(SCRIPTS_DIR))
        try:
            import verify_installed_wheel as vw
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory(prefix="rs-qa2302-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/usr/bin/python3\r\n"
            launcher.write_bytes(shebang + PINNED_CONSOLE_SCRIPT_BODY)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(vw.UnsupportedShebangError) as cm:
                vw.interpreter_from_launcher(launcher)
            self.assertIn("carriage return", str(cm.exception).lower())


class Qa2303LongShebangTests(unittest.TestCase):
    """QA23-03: Shebang with LF at offset >= 256 must be refused."""

    def test_lf_at_offset_256_refused(self) -> None:
        """A shebang whose first LF is at offset >= 256 must be refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        sys.path.insert(0, str(SCRIPTS_DIR))
        try:
            import verify_installed_wheel as vw
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory(prefix="rs-qa2303-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            padding = b"./" * 130
            shebang = b"#!" + padding + b"python3\n"
            self.assertGreaterEqual(shebang.find(b"\n"), 256)
            launcher.write_bytes(shebang + PINNED_CONSOLE_SCRIPT_BODY)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(vw.UnsupportedShebangError) as cm:
                vw.interpreter_from_launcher(launcher)
            self.assertIn("256 bytes", str(cm.exception))

    def test_no_lf_refused(self) -> None:
        """A shebang with no LF at all must be refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        sys.path.insert(0, str(SCRIPTS_DIR))
        try:
            import verify_installed_wheel as vw
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory(prefix="rs-qa2303-nolf-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            launcher.write_bytes(b"#!/usr/bin/python3" + PINNED_CONSOLE_SCRIPT_BODY.replace(b"\n", b""))
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(vw.UnsupportedShebangError) as cm:
                vw.interpreter_from_launcher(launcher)
            self.assertIn("256 bytes", str(cm.exception))

    def test_boundary_255_vs_256(self) -> None:
        """Verify the 256-byte boundary: LF at 255 OK, LF at 256 refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        sys.path.insert(0, str(SCRIPTS_DIR))
        try:
            import verify_installed_wheel as vw
        finally:
            sys.path.pop(0)

        with tempfile.TemporaryDirectory(prefix="rs-qa2303-boundary-") as raw:
            root = Path(raw)
            launcher = root / "launcher"

            shebang_255 = b"#!" + (b"x" * 253) + b"\n"
            self.assertEqual(shebang_255.find(b"\n"), 255)
            launcher.write_bytes(shebang_255 + PINNED_CONSOLE_SCRIPT_BODY)

            with self.assertRaises(vw.UnsupportedShebangError) as cm:
                vw.interpreter_from_launcher(launcher)
            self.assertNotIn("256 bytes", str(cm.exception))

            shebang_256 = b"#!" + (b"x" * 254) + b"\n"
            self.assertEqual(shebang_256.find(b"\n"), 256)
            launcher.write_bytes(shebang_256 + PINNED_CONSOLE_SCRIPT_BODY)

            with self.assertRaises(vw.UnsupportedShebangError) as cm:
                vw.interpreter_from_launcher(launcher)
            self.assertIn("256 bytes", str(cm.exception))


class Qa2305DocWordingTests(unittest.TestCase):
    """QA23-05: Dashboard and ABOUT.md use present.py wording."""

    def test_dashboard_has_honest_wording(self) -> None:
        dashboard_path = Path(__file__).resolve().parent.parent / "src" / "runspecimen" / "dashboard.py"
        if not dashboard_path.is_file():
            self.skipTest("dashboard.py not found")
        text = dashboard_path.read_text(encoding="utf-8")
        self.assertNotIn("show up as broken receipts", text)
        self.assertIn("Inconsistent edits to local records can be detected", text)

    def test_about_has_honest_wording(self) -> None:
        about_path = Path(__file__).resolve().parent.parent / "docs" / "ABOUT.md"
        if not about_path.is_file():
            self.skipTest("ABOUT.md not found")
        text = about_path.read_text(encoding="utf-8")
        self.assertNotIn("become broken receipts", text)
        self.assertIn("fabricate consistent evidence", text)


class Qa2306DocOrderTests(unittest.TestCase):
    """QA23-06: HUMAN-ACCEPTANCE.md N3 ordering is accurate."""

    def test_n3_version_described_as_first_launcher_exec(self) -> None:
        ha_path = Path(__file__).resolve().parent.parent / "docs" / "HUMAN-ACCEPTANCE.md"
        if not ha_path.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = ha_path.read_text(encoding="utf-8")
        self.assertNotIn("safe to run any venv code", text)
        self.assertIn("first execution of the installed launcher", text)

    def test_qafix_pin_is_current(self) -> None:
        ha_path = Path(__file__).resolve().parent.parent / "docs" / "HUMAN-ACCEPTANCE.md"
        if not ha_path.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = ha_path.read_text(encoding="utf-8")
        self.assertIn("qafix23", text)
        self.assertNotIn("qafix22 pin", text)


class ProbeBodyOnlyTests(unittest.TestCase):
    """Verify that the probe runs only body bytes, not the shebang line."""

    def test_launcher_body_after_shebang_excludes_shebang(self) -> None:
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        sys.path.insert(0, str(SCRIPTS_DIR))
        try:
            import verify_installed_wheel as vw
        finally:
            sys.path.pop(0)

        shebang = b"#!/usr/bin/python3\n"
        body = b"print('hello')\n"
        data = shebang + body
        result = vw.launcher_body_after_shebang(data)
        self.assertEqual(result, body)

    def test_launcher_body_cr_injection_not_in_body(self) -> None:
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        sys.path.insert(0, str(SCRIPTS_DIR))
        try:
            import verify_installed_wheel as vw
        finally:
            sys.path.pop(0)

        shebang_with_cr = b"#!/usr/bin/python3\rmalicious_code()\n"
        body = b"print('hello')\n"
        data = shebang_with_cr + body
        result = vw.launcher_body_after_shebang(data)
        self.assertEqual(result, body)
        self.assertNotIn(b"malicious", result)


if __name__ == "__main__":
    unittest.main()
