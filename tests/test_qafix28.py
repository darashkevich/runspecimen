"""Regression tests for qafix28 findings.

QA26-01 P1: Path normalization - refuse unless os.path.normpath(raw) == raw
QA26-02 P2: Plain-English error for pip's #!/bin/sh wrapper
QA26-03 P2: Apply exact-shebang rule to all allowlisted console scripts
QA26-04 P3: Refuse allowlisted symlink whose target doesn't exist
QA26-05 P3: Plain-English error for non-ASCII paths
QA26-06 P3: HUMAN-ACCEPTANCE.md ASCII path rule and pin qafix28
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


class Qa2601PathNormalizationTests(unittest.TestCase):
    """QA26-01: Refuse shebang paths that pathlib normalizes but kernel doesn't."""

    def test_trailing_slash_refused(self) -> None:
        """A shebang path with trailing / is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2601-slash-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/usr/bin/python3/\n# body\n"
            launcher.write_bytes(shebang)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            self.assertIn("not normalized", str(cm.exception).lower())

    def test_double_slash_refused(self) -> None:
        """A shebang path with // is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2601-dslash-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/usr//bin/python3\n# body\n"
            launcher.write_bytes(shebang)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            self.assertIn("not normalized", str(cm.exception).lower())

    def test_dot_slash_refused(self) -> None:
        """A shebang path with /./ is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2601-dotslash-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/usr/./bin/python3\n# body\n"
            launcher.write_bytes(shebang)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            self.assertIn("not normalized", str(cm.exception).lower())

    def test_dot_dot_slash_refused(self) -> None:
        """A shebang path with /../ is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2601-ddslash-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/usr/bin/../bin/python3\n# body\n"
            launcher.write_bytes(shebang)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            self.assertIn("not normalized", str(cm.exception).lower())

    def test_normalized_path_allowed(self) -> None:
        """A normalized shebang path is allowed."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2601-ok-") as raw:
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


class Qa2602ShellWrapperTests(unittest.TestCase):
    """QA26-02: Plain-English error for pip's #!/bin/sh wrapper."""

    def test_bin_sh_refused_with_explanation(self) -> None:
        """A #!/bin/sh shebang is refused with a helpful error message."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2602-sh-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/bin/sh\n'''exec' /usr/bin/python3 \"$0\" \"$@\"\n"
            launcher.write_bytes(shebang)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertIn("shell wrapper", msg)
            self.assertIn("127 bytes", msg)

    def test_usr_bin_sh_refused_with_explanation(self) -> None:
        """A #!/usr/bin/sh shebang is refused with a helpful error message."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2602-usr-sh-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/usr/bin/sh\n'''exec' /usr/bin/python3 \"$0\" \"$@\"\n"
            launcher.write_bytes(shebang)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertIn("shell wrapper", msg)

    def test_bin_bash_refused_with_explanation(self) -> None:
        """A #!/bin/bash shebang is refused with a helpful error message."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2602-bash-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/bin/bash\n'''exec' /usr/bin/python3 \"$0\" \"$@\"\n"
            launcher.write_bytes(shebang)
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertIn("shell wrapper", msg)


class Qa2603ConsoleScriptShebangTests(unittest.TestCase):
    """QA26-03: Apply exact-shebang rule to pip, pip3, etc."""

    def test_pip_with_invalid_shebang_refused(self) -> None:
        """A pip console script with invalid shebang is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2603-pip-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()

            pip = venv_bin / "pip"
            shebang = b"#!/usr//bin/python3\n# pip body\n"
            pip.write_bytes(shebang)
            pip.chmod(pip.stat().st_mode | stat.S_IXUSR)

            findings = module.scan_venv_bin(venv_bin)
            self.assertTrue(
                any("pip" in f.lower() and "invalid shebang" in f.lower() for f in findings),
                f"Expected finding about pip's invalid shebang; got: {findings}"
            )

    def test_pip3_with_invalid_shebang_refused(self) -> None:
        """A pip3 console script with invalid shebang is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2603-pip3-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()

            pip3 = venv_bin / "pip3"
            shebang = b"#!/bin/sh\n# pip3 shell wrapper\n"
            pip3.write_bytes(shebang)
            pip3.chmod(pip3.stat().st_mode | stat.S_IXUSR)

            findings = module.scan_venv_bin(venv_bin)
            self.assertTrue(
                any("pip3" in f.lower() and "invalid shebang" in f.lower() for f in findings),
                f"Expected finding about pip3's invalid shebang; got: {findings}"
            )

    def test_runspecimen_with_invalid_shebang_refused(self) -> None:
        """A runspecimen console script with invalid shebang is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2603-rs-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()

            rs = venv_bin / "runspecimen"
            shebang = b"#!/usr/bin/./python3\n# runspecimen body\n"
            rs.write_bytes(shebang)
            rs.chmod(rs.stat().st_mode | stat.S_IXUSR)

            findings = module.scan_venv_bin(venv_bin)
            self.assertTrue(
                any("runspecimen" in f.lower() and "invalid shebang" in f.lower() for f in findings),
                f"Expected finding about runspecimen's invalid shebang; got: {findings}"
            )


class Qa2604DanglingSymlinkTests(unittest.TestCase):
    """QA26-04: Refuse allowlisted symlink whose target doesn't exist."""

    def test_dangling_python_symlink_refused(self) -> None:
        """An allowlisted symlink to a non-existent target is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2604-dangle-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()

            python_link = venv_bin / "python"
            python_link.symlink_to("/nonexistent/python")

            findings = module.scan_venv_bin(venv_bin)
            self.assertTrue(
                any("missing target" in f.lower() for f in findings),
                f"Expected 'missing target' finding; got: {findings}"
            )

    def test_dangling_python3_symlink_refused(self) -> None:
        """An allowlisted python3 symlink to a non-existent target is refused."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2604-dangle3-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()

            python3_link = venv_bin / "python3"
            python3_link.symlink_to("/nonexistent/python3")

            findings = module.scan_venv_bin(venv_bin)
            self.assertTrue(
                any("missing target" in f.lower() for f in findings),
                f"Expected 'missing target' finding; got: {findings}"
            )

    def test_valid_symlink_allowed(self) -> None:
        """An allowlisted symlink to an existing target is allowed."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qa2604-ok-") as raw:
            root = Path(raw)
            venv_bin = root / "bin"
            venv_bin.mkdir()

            python_link = venv_bin / "python"
            python_link.symlink_to(real)

            findings = module.scan_venv_bin(venv_bin)
            dangling_findings = [f for f in findings if "missing target" in f.lower()]
            self.assertEqual(dangling_findings, [], f"Unexpected dangling findings: {dangling_findings}")


class Qa2605NonAsciiPathTests(unittest.TestCase):
    """QA26-05: Plain-English error for non-ASCII paths."""

    def test_non_ascii_shebang_refused_with_explanation(self) -> None:
        """A shebang with non-ASCII bytes gives a clear portable explanation."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2605-utf8-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = "#!/tmp/venv-café/bin/python\n".encode("utf-8")
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertIn("non-ascii", msg)
            self.assertIn("not portable", msg)

    def test_high_byte_shebang_refused_with_explanation(self) -> None:
        """A shebang with high bytes (>=0x80) gives a portable explanation."""
        if not VERIFY_SCRIPT.is_file():
            self.skipTest("verify_installed_wheel.py not found")
        module = _load_verify_module()

        with tempfile.TemporaryDirectory(prefix="rs-qa2605-high-") as raw:
            root = Path(raw)
            launcher = root / "launcher"
            shebang = b"#!/tmp/venv-\x80/bin/python\n"
            launcher.write_bytes(shebang + b"# body\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

            with self.assertRaises(module.UnsupportedShebangError) as cm:
                module.interpreter_from_launcher(launcher)
            msg = str(cm.exception).lower()
            self.assertIn("non-ascii", msg)


class Qa2606DocConsistencyTests(unittest.TestCase):
    """QA26-06: HUMAN-ACCEPTANCE.md ASCII path rule. Doc pack pin moved to test_qafix29."""

    def test_qafix28_in_historical_list(self) -> None:
        """qafix28 should be in the historical packs list."""
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")

        self.assertIn("qafix28", text, "HUMAN-ACCEPTANCE.md should mention qafix28 in history")

    def test_ascii_path_rule_documented(self) -> None:
        """The ASCII path rule should be documented in HUMAN-ACCEPTANCE.md."""
        if not HUMAN_ACCEPTANCE.is_file():
            self.skipTest("HUMAN-ACCEPTANCE.md not found")
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8").lower()

        self.assertIn("ascii", text, "HUMAN-ACCEPTANCE.md should mention ASCII")
        self.assertTrue(
            "non-ascii" in text or "printable ascii" in text,
            "HUMAN-ACCEPTANCE.md should mention ASCII path requirement"
        )


if __name__ == "__main__":
    unittest.main()
