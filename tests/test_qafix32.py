"""qafix32: home search, nested package aliases, and hardlink loader layout.

These fixtures are planted before verification. A refusal must happen before
the installed launcher runs, and a planted marker must stay absent. The
suspect interpreter is not started to discover its layout.
"""

from __future__ import annotations

import os
import sys
import sysconfig
from pathlib import Path

import unittest


def _stages():
    # Import inside the call so discovery does not collect that class twice.
    from tests.test_qafix31 import Qafix31Stages

    return Qafix31Stages


def _rewrite_home(venv: Path, home: Path) -> None:
    cfg = venv / "pyvenv.cfg"
    lines = []
    for line in cfg.read_text(encoding="utf-8").splitlines():
        if line.startswith("home = "):
            lines.append(f"home = {home}")
        else:
            lines.append(line)
    cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _alias_stdlib(lib: Path, stdlib: Path, *, skip_os_py: bool) -> None:
    lib.mkdir(parents=True, exist_ok=True)
    for entry in stdlib.iterdir():
        if skip_os_py and entry.name == "os.py":
            continue
        dest = lib / entry.name
        if dest.exists() or dest.is_symlink():
            continue
        dest.symlink_to(entry, target_is_directory=entry.is_dir())


class Qafix32LayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        _stages().setUp(self)

    def _fresh(self):
        return _stages()._fresh(self)

    def _verify(self, venv, marker):
        return _stages()._verify(self, venv, marker)

    def _plant_startup(self, lib: Path, marker: Path) -> None:
        lib.mkdir(parents=True, exist_ok=True)
        (lib / "sitecustomize.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('fake home startup')\n",
            encoding="utf-8",
        )

    def test_parent_directory_home_is_refused_before_startup(self) -> None:
        raw, venv = self._fresh()
        marker = venv / "canary.txt"
        fake = venv / "fakebase"
        home = fake / "nested" / "bin"
        home.mkdir(parents=True)
        (home / "python3").symlink_to(self.base)
        major, minor = sys.version_info[:2]
        lib = fake / "lib" / f"python{major}.{minor}"
        _alias_stdlib(lib, Path(sysconfig.get_path("stdlib")), skip_os_py=False)
        self._plant_startup(lib, marker)
        _rewrite_home(venv, home)
        report = self._verify(venv, marker)
        self.assertFalse(report["ok"], report["message"])
        self.assertIn("standard library", report["message"])
        self.assertFalse(marker.exists())

    def test_pyc_only_home_landmark_is_refused_before_startup(self) -> None:
        raw, venv = self._fresh()
        marker = venv / "canary.txt"
        fake = venv / "fakebase"
        home = fake / "bin"
        home.mkdir(parents=True)
        (home / "python3").symlink_to(self.base)
        major, minor = sys.version_info[:2]
        lib = fake / "lib" / f"python{major}.{minor}"
        stdlib = Path(sysconfig.get_path("stdlib"))
        _alias_stdlib(lib, stdlib, skip_os_py=True)
        import py_compile

        py_compile.compile(str(stdlib / "os.py"), cfile=str(lib / "os.pyc"), doraise=True)
        self._plant_startup(lib, marker)
        _rewrite_home(venv, home)
        report = self._verify(venv, marker)
        self.assertFalse(report["ok"], report["message"])
        self.assertIn("standard library", report["message"])
        self.assertFalse(marker.exists())

    def test_nested_package_directory_alias_is_refused_before_launch(self) -> None:
        raw, venv = self._fresh()
        marker = raw / "canary.txt"
        site = self.installer.venv_purelib(venv)
        (site / "runspecimen" / "cli").symlink_to(".", target_is_directory=True)
        report = self._verify(venv, marker)
        self.assertFalse(report["ok"], report["message"])
        self.assertIn("extra_files", report["message"])
        self.assertFalse(marker.exists())

    def test_whole_package_directory_alias_with_the_same_bytes_verifies(self) -> None:
        raw, venv = self._fresh()
        marker = raw / "canary.txt"
        site = self.installer.venv_purelib(venv)
        package = site / "runspecimen"
        moved = venv / "moved-package"
        package.rename(moved)
        package.symlink_to(moved, target_is_directory=True)
        report = self._verify(venv, marker)
        self.assertTrue(report["ok"], report["message"])
        self.assertFalse(marker.exists())

    def test_framework_hardlink_is_not_the_trusted_executable_location(self) -> None:
        raw, venv = self._fresh()
        marker = raw / "canary.txt"
        deps = self.verifier._loader_relative_deps(self.base)
        target = Path(os.path.realpath(self.base))
        py = venv / "bin" / "python"
        py.unlink()
        try:
            os.link(target, py)
        except OSError as exc:
            self.fail(f"could not hardlink the framework interpreter: {exc}")
        report = self._verify(venv, marker)
        if deps:
            self.assertFalse(report["ok"], report["message"])
            self.assertIn("hard link", report["message"])
        else:
            # Absolute loader dependencies do not move with the hardlink path.
            # This host is not the framework layout the report reproduced.
            self.assertNotIn("loader canary", report["message"])
        self.assertFalse(marker.exists())
