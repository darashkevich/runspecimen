"""Regression tests for qafix29 findings.

QA28-01 P3: pip*/runspecimen* symlinks shebang check, pip body verification
QA28-02 P3: Plain-English shell wrapper, unclosed backtick fix
QA28-03 P3: non-ASCII sentence only for bytes >= 0x80; control/DEL get own message
QA28-04 P3: state activate scripts are outside verified CLI
QA28-05 P3: basepy for pre-verification, sitecustomize test
QA28-06 P3: refuse leading '//' (POSIX implementation-defined)
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
VERIFY_SCRIPT = SCRIPTS_DIR / "verify_installed_wheel.py"
HUMAN_ACCEPTANCE = Path(__file__).resolve().parent.parent / "docs" / "HUMAN-ACCEPTANCE.md"


def _load_verify_module():
    """Load verify_installed_wheel.py as a module for unit testing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("verify_installed_wheel", VERIFY_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load verify_installed_wheel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Qa2801SymlinkShebangAndPipBodyTests(unittest.TestCase):
    """QA28-01: pip*/runspecimen* symlinks get shebang checks, pip body verification."""

    def test_pip_symlink_shebang_checked(self) -> None:
        """A pip symlink pointing at a file with invalid shebang is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2801-pipsym-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()

            real_pip = root / "real_pip"
            shebang = b"#!/usr//bin/python3\n# pip body\n"
            real_pip.write_bytes(shebang)
            real_pip.chmod(real_pip.stat().st_mode | stat.S_IXUSR)

            pip_link = venv_bin / "pip"
            pip_link.symlink_to(real_pip)

            findings = module.scan_venv_bin(venv_bin)
            self.assertTrue(
                any("pip" in f.lower() and "invalid shebang" in f.lower() for f in findings),
                f"Expected finding about pip symlink's invalid shebang; got: {findings}"
            )

    def test_runspecimen_symlink_shebang_checked(self) -> None:
        """A runspecimen symlink pointing at a file with invalid shebang is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2801-rssym-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()

            real_rs = root / "real_runspecimen"
            shebang = b"#!/bin/sh\n# shell wrapper\n"
            real_rs.write_bytes(shebang)
            real_rs.chmod(real_rs.stat().st_mode | stat.S_IXUSR)

            rs_link = venv_bin / "runspecimen"
            rs_link.symlink_to(real_rs)

            findings = module.scan_venv_bin(venv_bin)
            self.assertTrue(
                any("runspecimen" in f.lower() and "invalid shebang" in f.lower() for f in findings),
                f"Expected finding about runspecimen symlink's invalid shebang; got: {findings}"
            )

    def test_pip_unknown_body_refused(self) -> None:
        """A pip launcher with unrecognized body is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2801-pipbody-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()

            python_link = venv_bin / "python"
            python_link.symlink_to(real)

            pip = venv_bin / "pip"
            shebang = f"#!{python_link}\n".encode()
            unknown_body = b"# malicious pip replacement\nimport subprocess\nsubprocess.call(['rm', '-rf', '/'])\n"
            pip.write_bytes(shebang + unknown_body)
            pip.chmod(pip.stat().st_mode | stat.S_IXUSR)

            findings = module.scan_venv_bin(venv_bin)
            self.assertTrue(
                any("pip" in f.lower() and "unrecognized body" in f.lower() for f in findings),
                f"Expected finding about pip's unrecognized body; got: {findings}"
            )

    def test_pip_known_distlib_body_allowed(self) -> None:
        """A pip launcher with distlib body is allowed."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2801-okpip-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()

            python_link = venv_bin / "python"
            python_link.symlink_to(real)

            pip = venv_bin / "pip"
            shebang = f"#!{python_link}\n".encode()
            pip.write_bytes(shebang + module.PIP_DISTLIB_BODY)
            pip.chmod(pip.stat().st_mode | stat.S_IXUSR)

            findings = module.scan_venv_bin(venv_bin)
            body_findings = [f for f in findings if "unrecognized body" in f.lower()]
            self.assertEqual(body_findings, [], f"Unexpected body findings: {body_findings}")


class Qa2803ControlVsNonAsciiTests(unittest.TestCase):
    """QA28-03: non-ASCII sentence only for bytes >= 0x80; control/DEL get own message."""

    def test_non_ascii_high_byte_message(self) -> None:
        """Bytes >= 0x80 get non-ASCII error with portability explanation."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2803-high-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/tmp/venv-\x80/bin/python\n"
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertIn("non-ascii", msg)
            self.assertIn("not portable", msg)

    def test_control_character_message(self) -> None:
        """Control characters (0x00-0x1F) get control character error."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2803-ctrl-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/tmp/venv-\x01/bin/python\n"
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertIn("control character", msg)
            self.assertNotIn("non-ascii", msg)

    def test_del_character_message(self) -> None:
        """DEL (0x7F) gets control character error."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2803-del-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/tmp/venv-\x7f/bin/python\n"
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertIn("control character", msg)
            self.assertNotIn("non-ascii", msg)


class Qa2806LeadingDoubleSlashTests(unittest.TestCase):
    """QA28-06: Refuse leading '//' (POSIX implementation-defined)."""

    def test_leading_double_slash_refused(self) -> None:
        """A shebang path starting with // is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2806-dslash-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"//usr/bin/python3\n"
            launcher.write_bytes(b"#!" + shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertIn("//", msg)
            self.assertIn("implementation-defined", msg)

    def test_triple_slash_normalized(self) -> None:
        """A shebang path starting with /// is normalized (not impl-defined)."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2806-tslash-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!///usr/bin/python3\n"
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertIn("not normalized", msg)
            self.assertNotIn("implementation-defined", msg)


class Qa2804ActivateScriptsDocTests(unittest.TestCase):
    """QA28-04: HUMAN-ACCEPTANCE.md states activate scripts are outside verified CLI."""

    def test_activate_statement_present(self) -> None:
        """HUMAN-ACCEPTANCE.md mentions activate scripts are not verified."""
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8").lower()

        self.assertIn("activate", text, "HUMAN-ACCEPTANCE.md should mention activate")
        self.assertTrue(
            "outside the verified cli" in text or "never sources them" in text,
            "HUMAN-ACCEPTANCE.md should state activate scripts are not verified"
        )


class Qa2805BasepyPreVerificationTests(unittest.TestCase):
    """QA28-05: N2 hash uses basepy, not py."""

    def test_n2_hash_uses_basepy(self) -> None:
        """The N2-hash step should use basepy, not py."""
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")

        in_n2_section = False
        found_basepy_hash = False
        for line in text.split("\n"):
            if "## N2" in line:
                in_n2_section = True
            elif line.startswith("## N") and in_n2_section:
                break
            elif in_n2_section and "rs_ok N2-hash" in line:
                pass
            elif in_n2_section and "import hashlib" in line:
                if line.strip().startswith("basepy -c"):
                    found_basepy_hash = True
                elif line.strip().startswith("py -c"):
                    self.fail("N2-hash should use basepy, not py")

        self.assertTrue(found_basepy_hash, "N2-hash should use basepy -c for the hash check")

    def test_n2_install_uses_isolated_mode(self) -> None:
        """The N2-install step should use isolated mode (-I)."""
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")

        in_n2_section = False
        found = False
        for line in text.split("\n"):
            if "## N2" in line:
                in_n2_section = True
            elif line.startswith("## N") and in_n2_section:
                break
            elif in_n2_section and "install_pinned_wheel.py" in line:
                found = True
                self.assertIn("basepy", line)
                self.assertNotIn("pip install", line)
        self.assertTrue(found, "N2-install should call install_pinned_wheel.py via basepy")


class Qa2902DocConsistencyTests(unittest.TestCase):
    """The sheet names the current pack, and keeps qafix29 as history."""

    def test_pack_references_qafix29(self) -> None:
        """qafix29 stays in the history list. Identity lines name qafix32."""
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")

        self.assertIn("qafix29", text, "HUMAN-ACCEPTANCE.md should keep qafix29 in history")

        identity_lines = []
        for line in text.split("\n"):
            if "Candidate pack:" in line or line.startswith("- Pack: `artifacts/"):
                identity_lines.append(line)

        self.assertTrue(identity_lines)
        for line in identity_lines:
            self.assertIn("qafix32", line, f"Identity line should reference qafix32: {line}")

    def test_export_pack_matches_identity(self) -> None:
        """The export PACK= line should match the identity pack."""
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")

        export_line = None
        for line in text.split("\n"):
            if line.strip().startswith('export PACK="$PWD/artifacts/'):
                export_line = line
                break

        if export_line is None:
            self.skipTest("export PACK line not found")

        self.assertIn("qafix32", export_line, f"export PACK should use qafix32: {export_line}")

    def test_backtick_closed_at_line_75(self) -> None:
        """The backtick for /./' at line 75 should be properly closed."""
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")

        self.assertIn("`/./'`", text, "The /./' pattern should be properly backtick-quoted")


if __name__ == "__main__":
    unittest.main()
