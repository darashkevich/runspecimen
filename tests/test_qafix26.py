"""Regression tests for qafix26 findings.

QA24-01 P1: Symlink to directory in venv bin was skipped (verify ok while kernel runs attacker code)
QA24-02 P1: PEP 263 coding cookie in shebang path (verify ok then kernel runs wrong encoding)
QA24-03 P2: Unicode whitespace in shebang stripped by verifier but kept by kernel (verify ok, kernel ENOENT)
QA24-04 P3: HUMAN-ACCEPTANCE.md pack pin mismatch (doc fix)
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


class Qa2401SymlinkToDirectoryTests(unittest.TestCase):
    """QA24-01: Symlink to a directory in venv bin must be refused."""

    def test_symlink_to_directory_refused(self) -> None:
        """An allowlisted symlink pointing at a directory is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2401-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            
            package_dir = root / "package"
            package_dir.mkdir()
            (package_dir / "__init__.py").write_text("print('attacker')\n")
            
            target_symlink = venv_bin / "runspecimen"
            target_symlink.symlink_to(package_dir)
            
            findings = module.scan_venv_bin(venv_bin)
            self.assertTrue(
                any("points at a directory" in f for f in findings),
                f"Expected 'points at a directory' finding; got: {findings}"
            )

    def test_symlink_to_regular_file_allowed(self) -> None:
        """An allowlisted symlink pointing at a regular file is allowed."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2401-ok-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            
            python_link = venv_bin / "python"
            python_link.symlink_to(real)
            python3_link = venv_bin / "python3"
            python3_link.symlink_to(real)
            
            findings = module.scan_venv_bin(venv_bin)
            directory_findings = [f for f in findings if "directory" in f.lower()]
            self.assertEqual(directory_findings, [], f"Unexpected directory findings: {directory_findings}")

    def test_nested_symlink_to_directory_refused(self) -> None:
        """A symlink chain that ends in a directory is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2401-nest-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            
            package_dir = root / "package"
            package_dir.mkdir()
            
            intermediate = root / "intermediate"
            intermediate.symlink_to(package_dir)
            
            target_symlink = venv_bin / "runspecimen"
            target_symlink.symlink_to(intermediate)
            
            findings = module.scan_venv_bin(venv_bin)
            self.assertTrue(
                any("points at a directory" in f for f in findings),
                f"Expected 'points at a directory' finding; got: {findings}"
            )


class Qa2402CodingCookieTests(unittest.TestCase):
    """QA24-02: PEP 263 coding cookie in shebang path must be refused."""

    def test_coding_equals_refused(self) -> None:
        """A shebang with 'coding=' in the path is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2402-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/tmp/coding=cp037/python3\n# body\n"
            launcher.write_bytes(shebang)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            self.assertIn("coding cookie", str(cm.exception).lower())

    def test_coding_colon_refused(self) -> None:
        """A shebang with 'coding:' in the path is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2402-colon-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/tmp/coding:utf-8/python3\n# body\n"
            launcher.write_bytes(shebang)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            self.assertIn("coding cookie", str(cm.exception).lower())

    def test_encoding_variants_refused(self) -> None:
        """Various encoding names in shebang paths are refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        variants = [
            b"#!/tmp/coding=rot_13/python3\n",
            b"#!/tmp/coding=utf_16/python3\n",
            b"#!/tmp/coding=unicode_escape/python3\n",
            b"#!/tmp/xycoding=cp037/python3\n",
        ]

        for shebang in variants:
            with tempfile.TemporaryDirectory(prefix="rs-qa2402-var-") as raw:
                root = Path(raw)
                launcher = root / "launcher"
                launcher.write_bytes(shebang + b"# body\n")
                launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

                with self.assertRaises(module.UnsupportedShebangError, msg=f"should refuse {shebang!r}"):
                    module.interpreter_from_launcher(launcher)

    def test_normal_path_allowed(self) -> None:
        """A normal shebang path without 'coding' is allowed."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2402-ok-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            python_link = venv_bin / "python"
            python_link.symlink_to(real)
            
            launcher = venv_bin / "runspecimen"
            shebang = f"#!{python_link}\n".encode()
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            result = module.interpreter_from_launcher(launcher)
            self.assertEqual(result, python_link)

    def test_non_printable_ascii_refused(self) -> None:
        """Non-printable-ASCII bytes in shebang path are refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2402-npa-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/tmp/bin\x7fpython\n"
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            # QA28-03: 0x7F (DEL) gets "control character" error; high bytes get "non-ascii".
            msg = str(cm.exception).lower()
            self.assertTrue(
                "non-printable-ascii" in msg or "non-ascii" in msg or "control character" in msg,
                f"Expected control character, non-ASCII, or non-printable-ASCII error: {cm.exception}"
            )


class Qa2403UnicodeWhitespaceTests(unittest.TestCase):
    """QA24-03: Unicode whitespace in shebang must be refused (not stripped)."""

    def test_form_feed_trailing_refused(self) -> None:
        """A shebang with trailing form feed (\\x0c) before LF is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2403-ff-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            python_link = venv_bin / "python"
            python_link.symlink_to(real)
            
            launcher = venv_bin / "runspecimen"
            shebang = f"#!{python_link}\x0c\n".encode()
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertTrue(
                "non-printable-ascii" in msg or "control character" in msg,
                f"Expected control character or non-printable-ASCII error: {cm.exception}"
            )

    def test_vertical_tab_trailing_refused(self) -> None:
        """A shebang with trailing vertical tab (\\x0b) before LF is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2403-vt-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            python_link = venv_bin / "python"
            python_link.symlink_to(real)
            
            launcher = venv_bin / "runspecimen"
            shebang = f"#!{python_link}\x0b\n".encode()
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertTrue(
                "non-printable-ascii" in msg or "control character" in msg,
                f"Expected control character or non-printable-ASCII error: {cm.exception}"
            )

    def test_nbsp_trailing_refused(self) -> None:
        """A shebang with trailing NBSP (U+00A0) before LF is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2403-nbsp-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            python_link = venv_bin / "python"
            python_link.symlink_to(real)
            
            launcher = venv_bin / "runspecimen"
            path_with_nbsp = f"{python_link}\u00a0"
            shebang = f"#!{path_with_nbsp}\n".encode("utf-8")
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            # QA26-05: High bytes (>=0x80) now get "non-ascii" error.
            msg = str(cm.exception).lower()
            self.assertTrue(
                "non-printable-ascii" in msg or "non-ascii" in msg,
                f"Expected non-ASCII or non-printable-ASCII error: {cm.exception}"
            )

    def test_line_separator_refused(self) -> None:
        """A shebang with U+2028 LINE SEPARATOR before LF is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2403-ls-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            python_link = venv_bin / "python"
            python_link.symlink_to(real)
            
            launcher = venv_bin / "runspecimen"
            path_with_ls = f"{python_link}\u2028"
            shebang = f"#!{path_with_ls}\n".encode("utf-8")
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            # QA26-05: High bytes (>=0x80) now get "non-ascii" error.
            msg = str(cm.exception).lower()
            self.assertTrue(
                "non-printable-ascii" in msg or "non-ascii" in msg,
                f"Expected non-ASCII or non-printable-ASCII error: {cm.exception}"
            )

    def test_space_in_shebang_refused(self) -> None:
        """Spaces in shebang (padding or arguments) are refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2403-space-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            python_link = venv_bin / "python"
            python_link.symlink_to(real)
            
            launcher = venv_bin / "runspecimen"
            shebang = f"#! {python_link}\n".encode()
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            self.assertIn("whitespace", str(cm.exception).lower())

    def test_clean_shebang_allowed(self) -> None:
        """A clean shebang with no spaces, tabs, or special chars is allowed."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2403-ok-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()
            python_link = venv_bin / "python"
            python_link.symlink_to(real)
            
            launcher = venv_bin / "runspecimen"
            shebang = f"#!{python_link}\n".encode()
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            result = module.interpreter_from_launcher(launcher)
            self.assertEqual(result, python_link)


class Qa2404DocConsistencyTests(unittest.TestCase):
    """QA24-04: HUMAN-ACCEPTANCE.md pack references. Current pack pin in test_qafix29."""

    def test_qafix26_in_historical_list(self) -> None:
        """qafix26 should be in the historical packs list."""
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")

        self.assertIn("qafix26", text, "HUMAN-ACCEPTANCE.md should mention qafix26 in history")


if __name__ == "__main__":
    unittest.main()
