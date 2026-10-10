"""qafix15 regressions: venv interpreters, .pth paths, hook suffixes, pyvenv text."""

from __future__ import annotations

import importlib.machinery
import json
import os
import py_compile
import shlex
import subprocess
import sys
import sysconfig
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.test_rc15_qafix_docs import (
    VERIFY_INSTALLED,
    _install_and_verify,
    _pin_wheel,
)

_PI_THON = "\N{MATHEMATICAL ITALIC SMALL PI}thon"


def _canary_source(marker: Path) -> str:
    return f"open({str(marker)!r}, 'w').write('ran')\n"


def _is_interpreter_name(name: str) -> bool:
    stem = name[:-4] if name.lower().endswith(".exe") else name
    if stem in {"python", "python3", "pythonw", _PI_THON}:
        return True
    if not stem.startswith("python3."):
        return False
    rest = stem[len("python3.") :]
    if rest.endswith("t") and rest[:-1].replace(".", "").isdigit():
        rest = rest[:-1]
    return bool(rest) and all(ch.isdigit() or ch == "." for ch in rest)


def _write_canary_pyc(dest: Path, marker: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rs-qafix15-pyc-") as raw:
        source = Path(raw) / "mod.py"
        source.write_text(_canary_source(marker), encoding="utf-8")
        py_compile.compile(str(source), cfile=str(dest), doraise=True)


def _write_canary_extension(dest: Path, marker: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    code = (
        "#include <stdio.h>\n"
        "__attribute__((constructor)) static void rs_canary(void) {\n"
        f"    FILE *f = fopen({json.dumps(str(marker))}, \"w\");\n"
        "    if (f) { fputs(\"ran\", f); fclose(f); }\n"
        "}\n"
    )
    result = subprocess.run(
        ["gcc", "-shared", "-fPIC", "-x", "c", "-o", str(dest), "-"],
        input=code,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not dest.is_file():
        dest.write_bytes(b"not a loadable extension\n")


def _stdlib_sitecustomize_text() -> str:
    path = Path(sysconfig.get_path("stdlib")) / "sitecustomize.py"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


class Qafix15VerifierTests(unittest.TestCase):
    def _require_pin(self) -> Path:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        return pin

    def _refuse_without_marker(self, plant, *, needles: tuple[str, ...]) -> None:
        pin = self._require_pin()
        box: dict[str, Path] = {}

        def after_install(hook: object) -> None:
            marker = Path(hook.venv_dir).parent / "SIDE-EFFECT"  # type: ignore[attr-defined]
            box["marker"] = marker
            plant(hook, marker)

        def inspect(result: object) -> None:
            output = result.stdout + result.stderr  # type: ignore[attr-defined]
            self.assertNotEqual(result.returncode, 0, output)  # type: ignore[attr-defined]
            self.assertFalse(box["marker"].exists(), output)
            payload = json.loads(result.stdout.split("---")[0])  # type: ignore[attr-defined]
            self.assertFalse(payload["ok"], payload)
            blob = json.dumps(payload, ensure_ascii=False)
            for needle in needles:
                self.assertIn(needle, blob, payload)

        _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)

    def test_rq1401_python_wrapper_is_refused_with_no_side_effect(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            bindir = Path(hook.venv_dir) / "bin"  # type: ignore[attr-defined]
            entries = [path for path in bindir.iterdir() if _is_interpreter_name(path.name)]
            reals = {path: os.path.realpath(path) for path in entries}
            pi = bindir / _PI_THON
            if pi not in reals:
                reals[pi] = next(iter(reals.values()))
            for path, real in reals.items():
                if path.is_symlink() or path.is_file():
                    path.unlink()
                path.write_text(
                    "#!/bin/sh\n"
                    f"printf ran > {shlex.quote(str(marker))}\n"
                    f"exec {shlex.quote(real)} \"$@\"\n",
                    encoding="utf-8",
                )
                path.chmod(0o755)

        self._refuse_without_marker(plant, needles=("base interpreter", _PI_THON))

    def test_rq1402_pth_directory_and_zip_sitecustomize_have_no_side_effect(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            site = Path(hook.site)  # type: ignore[attr-defined]
            hooks = site / "hooks"
            hooks.mkdir()
            source = _canary_source(marker)
            (hooks / "sitecustomize.py").write_text(source, encoding="utf-8")
            (hooks / "apport_python_hook.py").write_text(source, encoding="utf-8")
            deeper = hooks / "deeper"
            deeper.mkdir()
            (deeper / "sitecustomize.py").write_text(source, encoding="utf-8")
            (hooks / "zz-deeper.pth").write_text("deeper\n", encoding="utf-8")
            (site / "zz-hooks.pth").write_text("hooks\n", encoding="utf-8")
            zpath = site / "evilhooks.zip"
            with zipfile.ZipFile(zpath, "w") as archive:
                archive.writestr("sitecustomize.py", source)
            (site / "zz-zip.pth").write_text("evilhooks.zip\n", encoding="utf-8")

        needles = ("sitecustomize", "evilhooks.zip", "deeper")
        if "apport_python_hook" in _stdlib_sitecustomize_text():
            needles = needles + ("apport_python_hook",)
        self._refuse_without_marker(plant, needles=needles)

    def test_rq1403_extension_and_sourceless_pyc_hooks_have_no_side_effect(self) -> None:
        suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
        tag = sys.implementation.cache_tag or "cpython-00"

        def plant(hook: object, marker: Path) -> None:
            site = Path(hook.site)  # type: ignore[attr-defined]
            _write_canary_extension(site / f"usercustomize{suffix}", marker)
            (site / "usercustomize.pyd").write_bytes(b"not a windows extension\n")
            _write_canary_pyc(site / "sitecustomize.pyc", marker)
            _write_canary_pyc(site / "__pycache__" / f"sitecustomize.{tag}.pyc", marker)
            package = site / "sitecustomize"
            _write_canary_pyc(package / "__init__.pyc", marker)
            _write_canary_extension(package / f"__init__{suffix}", marker)

        self._refuse_without_marker(
            plant,
            needles=(
                f"usercustomize{suffix}",
                "usercustomize.pyd",
                "sitecustomize.pyc",
                f"sitecustomize.{tag}.pyc",
                "__init__.pyc",
                f"__init__{suffix}",
            ),
        )

    def test_rq1404_include_system_site_packages_message_names_pyvenv_cfg(self) -> None:
        def plant(hook: object, marker: Path) -> None:
            cfg = Path(hook.venv_dir) / "pyvenv.cfg"  # type: ignore[attr-defined]
            text = cfg.read_text(encoding="utf-8")
            updated = text.replace(
                "include-system-site-packages = false",
                "include-system-site-packages = true",
            )
            if updated == text:
                raise AssertionError(f"pyvenv.cfg did not contain the false flag: {text}")
            cfg.write_text(updated, encoding="utf-8")
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
            self.assertNotEqual(result.returncode, 0, output)  # type: ignore[attr-defined]
            self.assertFalse(box["marker"].exists(), output)
            payload = json.loads(result.stdout.split("---")[0])  # type: ignore[attr-defined]
            self.assertFalse(payload["ok"], payload)
            message = str(payload.get("message") or "")
            # macOS tempfile is /var, which is /private/var. The verifier
            # prints the resolved path. Compare that path.
            cfg = str(box["cfg"].resolve())
            self.assertIn("include-system-site-packages is turned on", message)
            self.assertIn(cfg, message)
            self.assertIn(f"(file: {cfg})", message)
            self.assertNotIn("file: pyvenv.cfg sets", message)
            self.assertNotIn("file: include-system-site-packages=true", message)

        _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)


if __name__ == "__main__":
    unittest.main()
