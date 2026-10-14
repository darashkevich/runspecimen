"""qafix22 regressions: .pth bytes are an ASCII allowlist, and FIFOs are not opened."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.test_qafix18 import _canary_source
from tests.test_rc15_qafix_docs import (
    VERIFY_INSTALLED,
    _install_and_verify,
    _load_verify_module,
    _pin_wheel,
)


class Qafix22VerifierTests(unittest.TestCase):
    def _require_pin(self) -> Path:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        return pin

    def _refuse(self, plant, *, needles: tuple[str, ...]) -> dict:
        pin = self._require_pin()
        box: dict[str, Path] = {}

        def after_install(hook: object) -> None:
            marker = Path(hook.venv_dir).parent / "SIDE-EFFECT"  # type: ignore[attr-defined]
            box["marker"] = marker
            plant(Path(hook.site), marker)  # type: ignore[attr-defined]

        def inspect(result: object) -> None:
            output = result.stdout + result.stderr  # type: ignore[attr-defined]
            self.assertNotIn("Traceback", output)
            self.assertNotIn("the installed-wheel check stopped", output)
            self.assertNotEqual(result.returncode, 0, output)  # type: ignore[attr-defined]
            self.assertFalse(box["marker"].exists(), output)
            payload = json.loads(result.stdout.split("---")[0])  # type: ignore[attr-defined]
            self.assertFalse(payload["ok"], payload)
            message = str(payload.get("message") or "")
            for needle in needles:
                self.assertIn(needle, message, payload)
            box["payload"] = payload

        _install_and_verify(
            pin,
            pin,
            after_install=after_install,
            inspect=inspect,
            verify_timeout=30,
        )
        return box

    def _plant_hooks(self, directory: Path, marker: Path) -> None:
        directory.mkdir()
        source = _canary_source(marker)
        (directory / "sitecustomize.py").write_text(source, encoding="utf-8")
        (directory / "apport_python_hook.py").write_text(source, encoding="utf-8")

    def _import_canary(self, marker: Path) -> bytes:
        return (
            "import pathlib; pathlib.Path("
            + repr(str(marker))
            + ").write_text('ran')\n"
        ).encode("ascii")

    def test_rq2101_bom_import_is_refused(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            (site / "zz-bom-import.pth").write_bytes(b"\xef\xbb\xbf" + self._import_canary(marker))

        self._refuse(plant, needles=("plain ASCII", "cannot read this .pth file"))

    def test_rq2101_bom_directory_is_refused(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            self._plant_hooks(site / "hooked", marker)
            (site / "zz-bom-dir.pth").write_bytes(b"\xef\xbb\xbfhooked\n")

        self._refuse(plant, needles=("plain ASCII", "cannot read this .pth file"))

    def test_rq2102_line_separators_are_refused(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            self._plant_hooks(site / "prefix", marker)
            separators = {
                "u2028": "\u2028".encode("utf-8"),
                "u2029": "\u2029".encode("utf-8"),
                "u0085": "\u0085".encode("utf-8"),
                "fs": b"\x1c",
                "vt": b"\v",
                "ff": b"\f",
            }
            import_line = self._import_canary(marker).rstrip(b"\n")
            for name, separator in separators.items():
                (site / f"zz-{name}.pth").write_bytes(b"prefix" + separator + import_line + b"\n")

        self._refuse(plant, needles=("plain ASCII", "cannot read this .pth file"))

    def test_rq2102_lone_cr_is_refused(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            self._plant_hooks(site / "hooked", marker)
            (site / "zz-cr-dir.pth").write_bytes(b"hooked\r")
            (site / "zz-cr-import.pth").write_bytes(self._import_canary(marker).replace(b"\n", b"\r"))

        self._refuse(plant, needles=("plain ASCII", "cannot read this .pth file"))

    def test_rq2102_non_ascii_directory_name_is_refused(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            self._plant_hooks(site / "caf\u00e9", marker)
            self._plant_hooks(site / "caf", marker)
            (site / "zz-utf8.pth").write_bytes("caf\u00e9\n".encode("utf-8"))

        self._refuse(plant, needles=("plain ASCII", "cannot read this .pth file"))

    def test_rq2103_fifo_pth_is_refused(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            (site / "sitecustomize.py").write_text(_canary_source(marker), encoding="utf-8")
            os.mkfifo(site / "zz-fifo.pth")

        self._refuse(
            plant,
            needles=("not a regular file", "cannot read this .pth file"),
        )

    def test_rq2103_fifo_path_entry_is_refused(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            (site / "sitecustomize.py").write_text(_canary_source(marker), encoding="utf-8")
            os.mkfifo(site / "zzfifo")
            (site / "zz-name.pth").write_bytes(b"zzfifo\n")

        self._refuse(plant, needles=("not a regular file",))

    def test_common_pth_bodies_follow_the_ascii_policy(self) -> None:
        module = _load_verify_module()
        with tempfile.TemporaryDirectory(prefix="rs-qafix22-pth-") as raw:
            site = Path(raw)
            (site / "distutils-precedence.pth").write_text(
                "import _distutils_hack\n",
                encoding="ascii",
            )
            (site / "_virtualenv.pth").write_text("import _virtualenv\n", encoding="ascii")
            (site / "__editable___foo.pth").write_text(
                "import __editable___foo_finder; __editable___foo_finder.install()\n",
                encoding="ascii",
            )
            (site / "pywin32.pth").write_text(
                "# pywin32\nwin32\nimport pywin32_bootstrap\n",
                encoding="ascii",
            )
            (site / "matplotlib.pth").write_text(
                "import matplotlib\n",
                encoding="ascii",
            )
            findings = module.scan_pth_files(site)
        reasons = " ".join(str(item.get("reason") or "") for item in findings)
        self.assertIn("distutils-precedence", reasons)
        self.assertIn("executable import", reasons)
        self.assertNotIn("plain ASCII", reasons)
        self.assertGreaterEqual(len(findings), 4, findings)

    def test_pyvenv_allows_non_ascii_only_in_path_values(self) -> None:
        module = _load_verify_module()
        with tempfile.TemporaryDirectory(prefix="rs-qafix22-cfg-") as raw:
            root = Path(raw)
            home = root / "caf\u00e9"
            cfg = root / "pyvenv.cfg"
            cfg.write_bytes(
                (
                    "home = "
                    + str(home)
                    + "\ninclude-system-site-packages = false\nversion = 3.11.17\n"
                    "executable = "
                    + str(home / "python")
                    + "\ncommand = "
                    + str(home / "python")
                    + " -m venv\n"
                ).encode("utf-8")
            )
            parsed, problem = module._parse_pyvenv_cfg(cfg)
            self.assertIsNone(problem, problem)
            self.assertIn("caf\u00e9", parsed["home"])

            cfg.write_bytes("home = /tmp/base\nversion = 3.11\u00e9\n".encode("utf-8"))
            _parsed, problem = module._parse_pyvenv_cfg(cfg)
            self.assertIsNotNone(problem)
            self.assertIn("plain ASCII", problem or "")

            cfg.write_bytes("home = /tmp/base\u2028/bin\n".encode("utf-8"))
            _parsed, problem = module._parse_pyvenv_cfg(cfg)
            self.assertIsNotNone(problem)
            self.assertIn("plain ASCII", problem or "")

            cfg.write_bytes(b"\xef\xbb\xbfhome = /tmp/base\n")
            _parsed, problem = module._parse_pyvenv_cfg(cfg)
            self.assertIsNotNone(problem)
            self.assertIn("plain ASCII", problem or "")

            os.mkfifo(root / "fifo.cfg")
            _parsed, problem = module._parse_pyvenv_cfg(root / "fifo.cfg")
            self.assertIsNotNone(problem)
            self.assertIn("not a regular file", problem or "")


if __name__ == "__main__":
    unittest.main()
