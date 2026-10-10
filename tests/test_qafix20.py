"""qafix20 regressions: venv-started checker, unreadable .pth paths, sheet BASE_PY."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.test_qafix18 import _canary_source
from tests.test_rc15_qafix_docs import (
    HUMAN_ACCEPTANCE,
    VERIFY_INSTALLED,
    _helper_functions,
    _install_and_verify,
    _load_verify_module,
    _pin_wheel,
    _require_zsh,
    _sanitized_env,
    _site_packages,
    _uninstall_setuptools,
    _venv_python,
)


def _shells() -> list[str]:
    shells = ["bash"]
    if shutil.which("zsh"):
        shells.append(_require_zsh())
    return shells


class Qafix20VerifierTests(unittest.TestCase):
    def _require_pin(self) -> Path:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        return pin

    def _payload(self, result: subprocess.CompletedProcess[str]) -> dict:
        output = result.stdout + result.stderr
        self.assertNotIn("Traceback", output)
        self.assertNotIn("the installed-wheel check stopped", output)
        self.assertNotEqual(result.returncode, 0, output)
        payload = json.loads(result.stdout.split("---")[0])
        self.assertFalse(payload["ok"], payload)
        return payload

    def test_rq1901_venv_python_with_i_s_is_refused_and_canary_absent(self) -> None:
        pin = self._require_pin()
        with tempfile.TemporaryDirectory(prefix="rs-qafix20-venvpy-") as raw:
            root = Path(raw)
            marker = root / "SIDE-EFFECT"
            venv_dir = root / "venv"
            created = subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            py = _venv_python(venv_dir)
            env = _sanitized_env()
            site = _site_packages(py, env)
            (site / "sitecustomize.py").write_text(_canary_source(marker), encoding="utf-8")
            (site / "zz-canary.pth").write_text(
                "import pathlib\n"
                f"pathlib.Path({str(marker)!r}).write_text('ran-pth')\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(py),
                    "-I",
                    "-S",
                    str(VERIFY_INSTALLED),
                    "--wheel",
                    str(pin.resolve()),
                    "--launcher",
                    str(py),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            payload = self._payload(result)
            message = str(payload.get("message") or "")
            self.assertIn("virtual environment", message)
            self.assertIn("-I -S", message)
            self.assertFalse(marker.exists(), result.stdout + result.stderr)
            started = _load_verify_module().base_interpreter_in_use()
            self.assertEqual(started, Path(os.path.realpath(sys.executable)))

    def test_rq1901_sheet_basepy_uses_i_s_so_venv_on_path_does_not_run_hooks(self) -> None:
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")
        self.assertIn('basepy() { env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP -u PYTHONPYCACHEPREFIX PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 "$BASE_PY" -I -S "$@"; }', text)
        self.assertIn(
            'basepy -I -S "$PWD/scripts/verify_installed_wheel.py"',
            text,
        )
        helpers = _helper_functions(text)
        with tempfile.TemporaryDirectory(prefix="rs-qafix20-path-") as raw:
            root = Path(raw)
            marker = root / "SIDE-EFFECT"
            venv_dir = root / "venv"
            created = subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            py = _venv_python(venv_dir)
            env = _sanitized_env()
            site = _site_packages(py, env)
            (site / "sitecustomize.py").write_text(_canary_source(marker), encoding="utf-8")
            (site / "zz-canary.pth").write_text(
                "import pathlib\n"
                f"pathlib.Path({str(marker)!r}).write_text('ran-pth')\n",
                encoding="utf-8",
            )
            script = f"{helpers}\nprintf '%s\\n' \"$BASE_PY\"\n"
            run_env = os.environ.copy()
            run_env["PATH"] = str(py.parent) + os.pathsep + run_env.get("PATH", "")
            run_env.pop("PYTHONPATH", None)
            run_env.pop("PYTHONHOME", None)
            run_env.pop("PYTHONSTARTUP", None)
            for shell in _shells():
                with self.subTest(shell=shell):
                    if marker.exists():
                        marker.unlink()
                    result = subprocess.run(
                        [shell, "-c", script],
                        check=False,
                        capture_output=True,
                        text=True,
                        env=run_env,
                    )
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 0, output)
                    reported = result.stdout.strip().splitlines()[-1]
                    self.assertEqual(reported, os.path.realpath(sys.executable), output)
                    self.assertFalse(str(venv_dir) in reported, output)
                    self.assertFalse(marker.exists(), output)

    def test_rq1902_unreadable_zip_on_pth_is_refused(self) -> None:
        pin = self._require_pin()
        box: dict[str, Path] = {}

        def after_install(hook: object) -> None:
            marker = Path(hook.venv_dir).parent / "SIDE-EFFECT"  # type: ignore[attr-defined]
            box["marker"] = marker
            zpath = Path(hook.venv_dir).parent / "secret.zip"  # type: ignore[attr-defined]
            with zipfile.ZipFile(zpath, "w") as archive:
                archive.writestr("sitecustomize.py", _canary_source(marker))
            os.chmod(zpath, 0)
            box["zip"] = zpath
            site = Path(hook.site)  # type: ignore[attr-defined]
            (site / "zz-secret.pth").write_text(str(zpath) + "\n", encoding="utf-8")

        def inspect(result: object) -> None:
            os.chmod(box["zip"], 0o644)
            self.assertTrue(zipfile.is_zipfile(box["zip"]))
            with zipfile.ZipFile(box["zip"]) as archive:
                self.assertIn("sitecustomize.py", archive.namelist())
            payload = self._payload(result)  # type: ignore[arg-type]
            blob = json.dumps(payload, ensure_ascii=False)
            self.assertIn("cannot read", blob, payload)
            self.assertFalse(box["marker"].exists(), blob)

        try:
            _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)
        finally:
            zpath = box.get("zip")
            if zpath is not None and zpath.exists():
                os.chmod(zpath, 0o644)

    def test_rq1902_unreadable_directory_and_non_zip_file_are_refused(self) -> None:
        pin = self._require_pin()
        box: dict[str, Path] = {}

        def after_install(hook: object) -> None:
            marker = Path(hook.venv_dir).parent / "SIDE-EFFECT"  # type: ignore[attr-defined]
            box["marker"] = marker
            parent = Path(hook.venv_dir).parent  # type: ignore[attr-defined]
            locked = parent / "locked-dir"
            locked.mkdir()
            (locked / "sitecustomize.py").write_text(_canary_source(marker), encoding="utf-8")
            os.chmod(locked, 0)
            box["locked"] = locked
            plain = parent / "not-a-zip.py"
            plain.write_text(_canary_source(marker), encoding="utf-8")
            fifo = parent / "hook.fifo"
            os.mkfifo(fifo)
            site = Path(hook.site)  # type: ignore[attr-defined]
            (site / "zz-bad.pth").write_text(
                f"{locked}\n{plain}\n{fifo}\n",
                encoding="utf-8",
            )

        def inspect(result: object) -> None:
            os.chmod(box["locked"], 0o755)
            payload = self._payload(result)  # type: ignore[arg-type]
            blob = json.dumps(payload, ensure_ascii=False)
            self.assertIn("cannot read", blob, payload)
            self.assertIn("not a directory or a readable zip", blob, payload)
            self.assertIn("not a regular file or a directory", blob, payload)
            self.assertFalse(box["marker"].exists(), blob)

        try:
            _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)
        finally:
            locked = box.get("locked")
            if locked is not None and locked.exists():
                os.chmod(locked, 0o755)

    def test_rq1903_duplicate_pyvenv_home_executable_is_refused(self) -> None:
        pin = self._require_pin()
        box: dict[str, Path] = {}

        def after_install(hook: object) -> None:
            marker = Path(hook.venv_dir).parent / "SIDE-EFFECT"  # type: ignore[attr-defined]
            box["marker"] = marker
            cfg = Path(hook.venv_dir) / "pyvenv.cfg"  # type: ignore[attr-defined]
            text = cfg.read_text(encoding="utf-8")
            cfg.write_text(
                text
                + "home = /tmp/not-real\n"
                + "executable = /tmp/not-real/python\n",
                encoding="utf-8",
            )
            box["cfg"] = cfg
            started = subprocess.run(
                [str(hook.py), "-c", "print(123)"],  # type: ignore[attr-defined]
                check=False,
                capture_output=True,
                text=True,
                env=hook.env,  # type: ignore[attr-defined]
            )
            box["started"] = started  # type: ignore[assignment]
            site = Path(hook.site)  # type: ignore[attr-defined]
            (site / "sitecustomize.py").write_text(_canary_source(marker), encoding="utf-8")

        def inspect(result: object) -> None:
            started = box["started"]
            self.assertEqual(started.returncode, 0, started.stderr)  # type: ignore[attr-defined]
            self.assertIn("123", started.stdout)  # type: ignore[attr-defined]
            payload = self._payload(result)  # type: ignore[arg-type]
            message = str(payload.get("message") or "")
            self.assertIn("pyvenv.cfg repeats home or executable", message)
            self.assertIn("repeated setting", message)
            self.assertIn(str(box["cfg"]), message)
            self.assertNotIn("does not name the Python", message)
            self.assertFalse(box["marker"].exists(), message)

        _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)

    def test_rq1904_pth_symlink_loop_is_a_json_refusal(self) -> None:
        pin = self._require_pin()
        box: dict[str, Path] = {}

        def after_install(hook: object) -> None:
            marker = Path(hook.venv_dir).parent / "SIDE-EFFECT"  # type: ignore[attr-defined]
            box["marker"] = marker
            site = Path(hook.site)  # type: ignore[attr-defined]
            loop = site / "loop"
            loop.symlink_to("loop")
            (site / "zz-loop.pth").write_text("loop\n", encoding="utf-8")
            (site / "sitecustomize.py").write_text(_canary_source(marker), encoding="utf-8")

        def inspect(result: object) -> None:
            payload = self._payload(result)  # type: ignore[arg-type]
            message = str(payload.get("message") or "")
            self.assertIn("symlink loop", message)
            self.assertNotIn("Symlink loop from", message)
            self.assertFalse(box["marker"].exists(), message)

        _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)

    def test_rq1905_sheet_does_not_run_a_python3_function_alias_or_relative_shim(self) -> None:
        helpers = _helper_functions(HUMAN_ACCEPTANCE.read_text(encoding="utf-8"))
        cases = {
            "function": "python3() { printf ran > \"$MARKER\"; }\n",
            "alias": "alias python3='printf ran > \"$MARKER\"'\n",
            "relative": "",
        }
        for shell in _shells():
            for kind, prelude in cases.items():
                with self.subTest(shell=shell, kind=kind):
                    with tempfile.TemporaryDirectory(prefix="rs-qafix20-shim-") as raw:
                        root = Path(raw)
                        marker = root / "SIDE-EFFECT"
                        extra = ""
                        run_env = os.environ.copy()
                        if kind == "alias" and Path(shell).name == "bash":
                            extra = "shopt -s expand_aliases\n"
                        if kind == "relative":
                            bindir = root / "relbin"
                            bindir.mkdir()
                            shim = bindir / "python3"
                            shim.write_text(
                                "#!/bin/sh\n"
                                f"printf ran > {shlex.quote(str(marker))}\n",
                                encoding="utf-8",
                            )
                            shim.chmod(0o755)
                            run_env["PATH"] = "relbin" + os.pathsep + run_env.get("PATH", "")
                        script = (
                            f"MARKER={shlex.quote(str(marker))}\n"
                            f"{extra}{prelude}{helpers}\n"
                            "printf '%s\\n' \"$BASE_PY\"\n"
                        )
                        result = subprocess.run(
                            [shell, "-c", script],
                            check=False,
                            capture_output=True,
                            text=True,
                            env=run_env,
                            cwd=str(root),
                        )
                        output = result.stdout + result.stderr
                        self.assertNotEqual(result.returncode, 0, output)
                        self.assertIn("absolute path to a real program", output)
                        self.assertFalse(marker.exists(), output)
                        self.assertNotIn("ran", result.stdout)


if __name__ == "__main__":
    unittest.main()
