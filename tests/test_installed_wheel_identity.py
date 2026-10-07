"""RS-05: the installed wheel, not in-tree src/, is what an empty PYTHONPATH loads.

``tests/helpers.py`` prepends the repository ``src`` directory. This module
does not import that helper. It builds the wheel, installs it in a fresh
venv, and checks ``runspecimen.__file__`` plus RECORD hashes there.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_release_check():
    path = ROOT / "scripts" / "release_check.py"
    spec = importlib.util.spec_from_file_location("release_check_wheel_identity", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RELEASE = _load_release_check()


def _empty_pythonpath_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


class InstalledWheelIdentityTests(unittest.TestCase):
    def test_clean_venv_loads_site_packages_matching_wheel_record(self) -> None:
        build_env = os.environ.copy()
        build_env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory(prefix="runspecimen-wheel-id-") as raw:
            temp = Path(raw)
            artifacts = temp / "wheels"
            artifacts.mkdir()
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--wheel-dir",
                    str(artifacts),
                    str(ROOT),
                ],
                cwd=str(temp),
                env=build_env,
                check=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=180,
            )
            wheels = list(artifacts.glob("runspecimen-*.whl"))
            self.assertEqual(len(wheels), 1, wheels)
            wheel = wheels[0]
            venv = temp / "venv"
            # --without-pip keeps this off hosts that lack ensurepip (Debian
            # python3 without python3-venv). The venv still puts its
            # site-packages on sys.path with PYTHONPATH unset.
            subprocess.run(
                [sys.executable, "-m", "venv", "--without-pip", str(venv)],
                cwd=str(temp),
                env=build_env,
                check=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=60,
            )
            python = venv / "bin" / "python"
            sites = list((venv / "lib").glob("python*/site-packages"))
            self.assertEqual(len(sites), 1, sites)
            install_env = _empty_pythonpath_env()
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--target",
                    str(sites[0]),
                    str(wheel),
                ],
                cwd=str(temp),
                env=install_env,
                check=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=120,
            )
            self.assertNotIn("PYTHONPATH", install_env)
            RELEASE.assert_installed_wheel_identity(python, wheel, install_env)


if __name__ == "__main__":
    unittest.main()
