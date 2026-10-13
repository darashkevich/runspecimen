"""qafix31: authenticated install, runtime layout, and authenticated probe.

Rejected fixtures must fail the check and must not execute a canary or write
outside the venv. A clean pip-free environment must still verify. These tests
do not start the suspect interpreter to discover its layout.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_pinned_wheel.py"
VERIFIER = ROOT / "scripts" / "verify_installed_wheel.py"
CANARY_C = textwrap.dedent(
    r"""
    #include <stdio.h>
    __attribute__((constructor)) static void mark(void) {
        FILE *f = fopen(CANARY, "w");
        if (f) { fputs("unverified extension executed", f); fclose(f); }
    }
    void *PyInit_runspecimen(void) { return 0; }
    """
)
DRIVER = textwrap.dedent(
    r"""
    import importlib.util
    import json
    import sys
    from pathlib import Path

    verifier_path, wheel, launcher, marker, mode = sys.argv[1:6]
    spec = importlib.util.spec_from_file_location("verify_qafix31_driver", verifier_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    launcher_path = Path(launcher)
    site_marker = Path(marker)
    venv = launcher_path.parent.parent

    def mutate():
        if mode == "package":
            path = venv / "lib"
            # The versioned directory is whatever the installer created.
            packages = list(path.glob("python*/site-packages/runspecimen/__init__.py"))
            target = packages[0]
            target.write_bytes(
                target.read_bytes()
                + (
                    "\nfrom pathlib import Path as _QaPath\n_QaPath("
                    + repr(str(site_marker))
                    + ").write_text('package executed')\n"
                ).encode()
            )
        elif mode == "launcher":
            data = launcher_path.read_bytes()
            first, rest = data.split(b"\n", 1)
            launcher_path.write_bytes(
                first
                + b"\n"
                + (
                    "from pathlib import Path as _QaPath\n_QaPath("
                    + repr(str(site_marker))
                    + ").write_text('launcher executed')\n"
                ).encode()
                + rest
            )

    if mode in {"package", "launcher"}:
        module.after_authenticated_read = mutate
    report = module.verify_launcher_install(wheel=Path(wheel), launcher=launcher_path)
    print(json.dumps({"ok": report.get("ok"), "message": report.get("message"), "canary": site_marker.exists()}))
    """
)


def _load(path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pin_wheel() -> Path:
    from tests.test_rc15_qafix_docs import _pin_wheel as pin

    wheel = pin()
    if not wheel.is_file():
        raise AssertionError(f"pin wheel missing: {wheel}")
    return wheel


class Qafix31Stages(unittest.TestCase):
    def setUp(self) -> None:
        self.installer = _load(INSTALLER, "install_qafix31")
        self.verifier = _load(VERIFIER, "verify_qafix31")
        base = self.verifier.base_interpreter()
        if base is None:
            self.skipTest("base interpreter was not found; the checker was not started")
        self.base = Path(base)
        self.wheel = _pin_wheel()
        self.digest = hashlib.sha256(self.wheel.read_bytes()).hexdigest()

    def _fresh(self) -> tuple[Path, Path]:
        raw = Path(tempfile.mkdtemp(prefix="rs-qafix31-"))
        self.addCleanup(shutil.rmtree, raw, True)
        venv = raw / "v"
        created = subprocess.run(
            [str(self.base), "-I", "-S", "-m", "venv", "--without-pip", str(venv)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        self.installer.install_pinned_wheel(self.wheel, venv, self.digest)
        return raw, venv

    def _verify(self, venv: Path, marker: Path, mode: str = "clean") -> dict:
        driver = venv.parent / "driver.py"
        driver.write_text(DRIVER, encoding="utf-8")
        env = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONPYCACHEPREFIX"):
            env.pop(key, None)
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [
                str(self.base),
                "-I",
                "-S",
                str(driver),
                str(VERIFIER),
                str(self.wheel),
                str(venv / "bin" / "runspecimen"),
                str(marker),
                mode,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_clean_pip_free_environment_verifies(self) -> None:
        raw, venv = self._fresh()
        marker = raw / "canary.txt"
        report = self._verify(venv, marker)
        self.assertTrue(report["ok"], report["message"])
        self.assertFalse(marker.exists())
        if str(venv).startswith("/var/"):
            alias = Path("/private") / venv.relative_to("/")
            self.assertTrue(os.path.samefile(venv, alias))

    def test_unmanifested_extension_is_refused_and_not_executed(self) -> None:
        compiler = shutil.which("clang") or shutil.which("cc")
        if compiler is None:
            self.fail("no C compiler; the native-extension regression was not run")
        raw, venv = self._fresh()
        marker = raw / "canary.txt"
        site = self.installer.venv_purelib(venv)
        source = raw / "canary.c"
        source.write_text(CANARY_C, encoding="utf-8")
        output = site / "runspecimen" / "__init__.so"
        command = [compiler, "-DCANARY=" + json.dumps(str(marker)), str(source), "-o", str(output)]
        if sys.platform == "darwin":
            command[1:1] = ["-bundle", "-undefined", "dynamic_lookup"]
        else:
            command[1:1] = ["-shared", "-fPIC"]
        built = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        report = self._verify(venv, marker)
        self.assertFalse(report["ok"], report["message"])
        self.assertIn("extra_files", report["message"])
        self.assertFalse(marker.exists())
        self.assertFalse(list(raw.rglob("canary.txt")))

    def test_sibling_native_extension_is_refused_and_not_executed(self) -> None:
        raw, venv = self._fresh()
        marker = raw / "canary.txt"
        site = self.installer.venv_purelib(venv)
        (site / "runspecimen.so").write_bytes(b"not a loadable extension")
        report = self._verify(venv, marker)
        self.assertFalse(report["ok"], report["message"])
        self.assertIn("extra_files", report["message"])
        self.assertFalse(marker.exists())

    def test_forged_home_is_refused_without_starting_it(self) -> None:
        raw, venv = self._fresh()
        marker = raw / "canary.txt"
        import sysconfig

        fake = venv / "fakebase"
        (fake / "bin").mkdir(parents=True)
        (fake / "bin" / "python3").symlink_to(self.base)
        major, minor = sys.version_info[:2]
        lib = fake / "lib" / f"python{major}.{minor}"
        lib.mkdir(parents=True)
        stdlib = Path(sysconfig.get_path("stdlib"))
        (lib / "os.py").symlink_to(stdlib / "os.py")
        (lib / "encodings").symlink_to(stdlib / "encodings", target_is_directory=True)
        (lib / "sitecustomize.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('fake home startup')\n",
            encoding="utf-8",
        )
        cfg = venv / "pyvenv.cfg"
        lines = []
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.startswith("home = "):
                lines.append(f"home = {fake / 'bin'}")
            else:
                lines.append(line)
        cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = self._verify(venv, marker)
        self.assertFalse(report["ok"], report["message"])
        self.assertIn("standard library", report["message"])
        self.assertFalse(marker.exists())

    def test_package_mutation_between_read_and_probe_is_not_executed(self) -> None:
        raw, venv = self._fresh()
        marker = raw / "canary.txt"
        report = self._verify(venv, marker, mode="package")
        self.assertFalse(report["ok"], report["message"])
        self.assertIn("probe not started", report["message"])
        self.assertFalse(marker.exists())

    def test_launcher_mutation_between_read_and_probe_is_not_executed(self) -> None:
        raw, venv = self._fresh()
        marker = raw / "canary.txt"
        report = self._verify(venv, marker, mode="launcher")
        self.assertFalse(report["ok"], report["message"])
        self.assertIn("probe was not started", report["message"])
        self.assertFalse(marker.exists())

    def test_copied_interpreter_with_relative_loader_deps_is_refused(self) -> None:
        raw, venv = self._fresh()
        marker = raw / "canary.txt"
        deps = self.verifier._loader_relative_deps(self.base)
        py = venv / "bin" / "python"
        py.unlink()
        shutil.copy2(self.base, py)
        py.chmod(py.stat().st_mode | stat.S_IXUSR)
        report = self._verify(venv, marker)
        if deps:
            self.assertFalse(report["ok"], report["message"])
            self.assertIn("copied interpreter", report["message"])
        else:
            # This interpreter's loader closure does not move with a copy.
            # That is a different layout from the standalone Python defect.
            self.assertNotIn("unverified extension executed", report["message"])
        self.assertFalse(marker.exists())

    def test_installer_refuses_a_replaced_lib_directory_and_writes_nothing_outside(self) -> None:
        raw = Path(tempfile.mkdtemp(prefix="rs-qafix31-install-"))
        self.addCleanup(shutil.rmtree, raw, True)
        venv = raw / "v"
        outside = raw / "outside"
        outside.mkdir()
        created = subprocess.run(
            [str(self.base), "-I", "-S", "-m", "venv", "--without-pip", str(venv)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        original = self.installer._write_members

        def swap(target, parts, members):
            lib = target / "lib"
            lib.rename(target / "lib-original")
            lib.symlink_to(outside, target_is_directory=True)
            original(target, parts, members)

        self.installer._write_members = swap
        try:
            with self.assertRaises(self.installer.InstallRefusal) as caught:
                self.installer.install_pinned_wheel(self.wheel, venv, self.digest)
        finally:
            self.installer._write_members = original
        self.assertIn("follow", str(caught.exception).lower())
        files = [path for path in outside.rglob("*") if path.is_file()]
        self.assertEqual(files, [])
