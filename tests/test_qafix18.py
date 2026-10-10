"""qafix18 regressions: scan limits, sheet basepy, pyvenv identity, NUL .pth."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path

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
    _venv_launcher,
)


def _canary_source(marker: Path) -> str:
    return f"open({str(marker)!r}, 'w').write('ran')\n"


def _stdlib_sitecustomize_text() -> str:
    path = Path(sysconfig.get_path("stdlib")) / "sitecustomize.py"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


class Qafix18VerifierTests(unittest.TestCase):
    def _require_pin(self) -> Path:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        return pin

    def _refuse_without_marker(self, plant, *, needles: tuple[str, ...]) -> dict:
        pin = self._require_pin()
        box: dict[str, Path] = {}

        def after_install(hook: object) -> None:
            marker = Path(hook.venv_dir).parent / "SIDE-EFFECT"  # type: ignore[attr-defined]
            box["marker"] = marker
            plant(hook, marker)

        def inspect(result: object) -> None:
            output = result.stdout + result.stderr  # type: ignore[attr-defined]
            self.assertNotIn("Traceback", output)
            self.assertNotEqual(result.returncode, 0, output)  # type: ignore[attr-defined]
            self.assertFalse(box["marker"].exists(), output)
            payload = json.loads(result.stdout.split("---")[0])  # type: ignore[attr-defined]
            self.assertFalse(payload["ok"], payload)
            box["payload"] = payload
            blob = json.dumps(payload, ensure_ascii=False)
            for needle in needles:
                self.assertIn(needle, blob, payload)

        _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)
        return box

    def test_rq1701_eighty_pth_dirs_are_scanned_with_no_side_effect(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            site = Path(hook.site)  # type: ignore[attr-defined]
            lines: list[str] = []
            for index in range(80):
                directory = site / f"d{index:03d}"
                directory.mkdir()
                lines.append(f"d{index:03d}")
            last = site / "d079"
            source = _canary_source(marker)
            (last / "sitecustomize.py").write_text(source, encoding="utf-8")
            (last / "apport_python_hook.py").write_text(source, encoding="utf-8")
            (site / "zz-eighty.pth").write_text("\n".join(lines) + "\n", encoding="utf-8")
            hook.hook_path = last / "sitecustomize.py"  # type: ignore[attr-defined]

        needles = ("d079/sitecustomize.py", "d079")
        if "apport_python_hook" in _stdlib_sitecustomize_text():
            needles = needles + ("apport_python_hook",)
        box = self._refuse_without_marker(plant, needles=needles)
        blob = json.dumps(box["payload"], ensure_ascii=False)
        self.assertNotIn("too many directories", blob)

    def test_rq1701_scan_limit_refuses_instead_of_dropping_paths(self) -> None:
        mod = _load_verify_module()
        mod.SITE_PATH_LIMIT = 2
        with tempfile.TemporaryDirectory(prefix="rs-qafix18-limit-") as raw:
            root = Path(raw)
            site = root / "site"
            site.mkdir()
            extras = []
            for index in range(3):
                directory = root / f"extra{index}"
                directory.mkdir()
                extras.append(directory)
            (extras[2] / "sitecustomize.py").write_text("print('ran')\n", encoding="utf-8")
            (site / "zz.pth").write_text(
                "\n".join(str(path) for path in extras) + "\n",
                encoding="utf-8",
            )
            chosen, findings = mod.expand_site_paths([site])
        self.assertTrue(any("too many directories" in item for item in findings), findings)
        self.assertEqual(len(chosen), 2, [str(path) for path in chosen])
        self.assertNotIn(extras[2], chosen)

    def test_rq1701_missing_paths_do_not_consume_the_scan_limit(self) -> None:
        mod = _load_verify_module()
        mod.SITE_PATH_LIMIT = 2
        with tempfile.TemporaryDirectory(prefix="rs-qafix18-missing-") as raw:
            root = Path(raw)
            site = root / "site"
            site.mkdir()
            hook = root / "d079"
            hook.mkdir()
            (hook / "sitecustomize.py").write_text("print('ran')\n", encoding="utf-8")
            (site / "zz.pth").write_text(str(hook) + "\n", encoding="utf-8")
            missing = [root / f"missing{index}" for index in range(10)]
            chosen, findings = mod.expand_site_paths(missing + [site])
        self.assertEqual(findings, [], findings)
        self.assertEqual({path.name for path in chosen}, {"site", "d079"})

    def test_rq1701_too_many_interpreter_links_is_a_refusal(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            bindir = Path(hook.venv_dir) / "bin"  # type: ignore[attr-defined]
            wrapper = bindir / "not-an-interpreter"
            wrapper.write_text(
                "#!/bin/sh\n"
                f"printf ran > {shlex.quote(str(marker))}\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
            current = wrapper
            for index in range(41):
                nxt = bindir / f"link{index}"
                nxt.symlink_to(current.name if current.parent == bindir else current)
                current = nxt
            python = bindir / "python"
            python.unlink()
            python.symlink_to(current.name)

        self._refuse_without_marker(
            plant,
            needles=("followed too many links",),
        )

    def test_rq1702_sheet_basepy_does_not_execute_venv_python(self) -> None:
        text = HUMAN_ACCEPTANCE.read_text(encoding="utf-8")
        self.assertLess(
            text.index('_RS_PY3="$(command -v python3)"'),
            text.index('python3 -m venv "$VENV"'),
        )
        self.assertLess(
            text.index('"$BASE_PY" -I -S "$@"'),
            text.index('python3 -m venv "$VENV"'),
        )
        basepy_line = next(line for line in text.splitlines() if line.startswith("basepy()"))
        self.assertIn('"$BASE_PY"', basepy_line)
        self.assertIn("-I -S", basepy_line)
        self.assertNotIn("$PY", basepy_line)
        self.assertNotIn("readlink", basepy_line)
        self.assertNotIn("while [ -L", text)
        n3 = next(line for line in text.splitlines() if "verify_installed_wheel.py" in line)
        self.assertIn("basepy -I -S", n3)
        helpers = _helper_functions(text)
        real = sys.executable

        def run_plant(shell: str, plant) -> None:
            with tempfile.TemporaryDirectory(prefix="rs-qafix18-basepy-") as raw:
                root = Path(raw)
                marker = root / "SIDE-EFFECT"
                bindir = root / "bin"
                bindir.mkdir()
                py = bindir / "python"
                plant(py, marker, real)
                script = (
                    f"export BASE_PY={shlex.quote(real)}\n"
                    f"export PY={shlex.quote(str(py))}\n"
                    f"{helpers}\n"
                    "basepy -c 'print(123)'\n"
                )
                result = subprocess.run(
                    [shell, "-c", script],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertIn("123", result.stdout)
                self.assertFalse(marker.exists(), output)

        def as_wrapper(path: Path, marker: Path, _real: str) -> None:
            path.write_text(
                "#!/bin/sh\n"
                f"printf ran > {shlex.quote(str(marker))}\n"
                f"exec {shlex.quote(_real)} \"$@\"\n",
                encoding="utf-8",
            )
            path.chmod(0o755)

        def as_symlink(path: Path, marker: Path, _real: str) -> None:
            wrapper = path.parent / "wrapper"
            as_wrapper(wrapper, marker, _real)
            path.symlink_to(wrapper)

        def as_byte_copy(path: Path, marker: Path, _real: str) -> None:
            wrapper = path.parent / "wrapper"
            as_wrapper(wrapper, marker, _real)
            path.write_bytes(wrapper.read_bytes())
            path.chmod(0o755)

        shells = ["bash"]
        if shutil.which("zsh"):
            shells.append(_require_zsh())
        for shell in shells:
            for plant in (as_wrapper, as_symlink, as_byte_copy):
                with self.subTest(shell=shell, plant=plant.__name__):
                    run_plant(shell, plant)

    def test_rq1703_symlinked_interpreter_home_is_accepted(self) -> None:
        pin = self._require_pin()
        real = Path(os.path.realpath(sys.executable))
        with tempfile.TemporaryDirectory(prefix="rs-qafix18-home-") as raw:
            root = Path(raw)
            linkdir = root / "pybin"
            linkdir.mkdir()
            link = linkdir / "python3"
            link.symlink_to(real)
            venv_dir = root / "venv"
            created = subprocess.run(
                [str(link), "-m", "venv", str(venv_dir)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            cfg_path = venv_dir / "pyvenv.cfg"
            # Debian records home as the symlink directory and executable as
            # the real binary. macOS framework Python records home as the real
            # framework bin even when creation went through the symlink. Write
            # the Debian shape so the check is the same on every host.
            lines = []
            saw_home = False
            for raw in cfg_path.read_text(encoding="utf-8").splitlines():
                key = raw.split("=", 1)[0].strip().lower() if "=" in raw else ""
                if key == "home":
                    lines.append(f"home = {linkdir}")
                    saw_home = True
                else:
                    lines.append(raw)
            if not saw_home:
                raise AssertionError(cfg_path.read_text(encoding="utf-8"))
            cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            env = _sanitized_env()
            py = venv_dir / "bin" / "python"
            _uninstall_setuptools(py, env)
            install = subprocess.run(
                [
                    str(py),
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--no-compile",
                    "--force-reinstall",
                    str(pin.resolve()),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(install.returncode, 0, install.stderr)
            launcher = _venv_launcher(venv_dir)
            result = subprocess.run(
                [
                    str(real),
                    "-I",
                    str(VERIFY_INSTALLED),
                    "--wheel",
                    str(pin.resolve()),
                    "--launcher",
                    str(launcher),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            output = result.stdout + result.stderr
            self.assertNotIn("Traceback", output)
            payload = json.loads(result.stdout.split("---")[0])
            self.assertTrue(payload["ok"], payload)
            self.assertEqual(result.returncode, 0, output)

    def test_rq1704_nul_pth_is_a_json_refusal(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            site = Path(hook.site)  # type: ignore[attr-defined]
            (site / "aa-nul.pth").write_bytes("hooks\n".encode("utf-16"))
            (site / "zz-bad.pth").write_bytes(b"\xff\xfehooks\n")
            (site / "sitecustomize.py").write_text(_canary_source(marker), encoding="utf-8")

        box = self._refuse_without_marker(
            plant,
            needles=("null byte", "not UTF-8"),
        )
        message = str(box["payload"].get("message") or "")
        self.assertIn("cannot read this .pth file", message)

    def test_rq1705_home_mismatch_names_pyvenv_cfg(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            cfg = Path(hook.venv_dir) / "pyvenv.cfg"  # type: ignore[attr-defined]
            lines = []
            for raw in cfg.read_text(encoding="utf-8").splitlines():
                if raw.strip().lower().startswith("home ") or raw.strip().lower().startswith("home="):
                    lines.append("home = /tmp/not-the-base-interpreter")
                elif raw.strip().lower().startswith("executable"):
                    lines.append("executable = /tmp/not-the-base-interpreter/python3")
                else:
                    lines.append(raw)
            cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
            site = Path(hook.site)  # type: ignore[attr-defined]
            (site / "sitecustomize.py").write_text(_canary_source(marker), encoding="utf-8")
            hook.cfg = cfg  # type: ignore[attr-defined]

        pin = self._require_pin()
        box: dict[str, Path] = {}

        def after_install(hook: object) -> None:
            marker = Path(hook.venv_dir).parent / "SIDE-EFFECT"  # type: ignore[attr-defined]
            box["marker"] = marker
            plant(hook, marker)
            box["cfg"] = Path(hook.venv_dir) / "pyvenv.cfg"  # type: ignore[attr-defined]

        def inspect(result: object) -> None:
            output = result.stdout + result.stderr  # type: ignore[attr-defined]
            self.assertNotIn("Traceback", output)
            self.assertNotEqual(result.returncode, 0, output)  # type: ignore[attr-defined]
            self.assertFalse(box["marker"].exists(), output)
            payload = json.loads(result.stdout.split("---")[0])  # type: ignore[attr-defined]
            self.assertFalse(payload["ok"], payload)
            message = str(payload.get("message") or "")
            cfg = str(box["cfg"].resolve())
            self.assertIn(
                "pyvenv.cfg does not name the Python that is running this check",
                message,
            )
            self.assertIn(cfg, message)
            self.assertNotIn("extra startup code", message)
            self.assertNotIn("file: pyvenv.cfg does not", message)
            self.assertNotIn("file: pyvenv.cfg home", message)

        _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)


if __name__ == "__main__":
    unittest.main()
