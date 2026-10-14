"""qafix21 regressions: .pth lines with whitespace are refused, not reinterpreted."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from tests.test_qafix18 import _canary_source, _stdlib_sitecustomize_text
from tests.test_rc15_qafix_docs import (
    VERIFY_INSTALLED,
    _install_and_verify,
    _pin_wheel,
)


class Qafix21VerifierTests(unittest.TestCase):
    def _require_pin(self) -> Path:
        pin = _pin_wheel()
        if not pin.is_file():
            self.skipTest("pin wheel must be on disk")
        if not VERIFY_INSTALLED.is_file():
            self.skipTest("verify_installed_wheel.py is not packed into this tree")
        return pin

    def _refuse(self, plant, *, needles: tuple[str, ...] = ("cannot read this .pth line", "whitespace")) -> dict:
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

        _install_and_verify(pin, pin, after_install=after_install, inspect=inspect)
        return box

    def _plant_hooks(self, directory: Path, marker: Path) -> None:
        directory.mkdir()
        source = _canary_source(marker)
        (directory / "sitecustomize.py").write_text(source, encoding="utf-8")
        (directory / "apport_python_hook.py").write_text(source, encoding="utf-8")

    def test_rq2001_leading_space_pth_refuses_apport_chain(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            self._plant_hooks(site / " evil", marker)
            (site / "evil").mkdir()
            (site / "zz-space.pth").write_bytes(b" evil\n")

        box = self._refuse(plant)
        if "apport_python_hook" in _stdlib_sitecustomize_text():
            blob = json.dumps(box["payload"], ensure_ascii=False)
            self.assertNotIn("ok\": true", blob)

    def test_rq2001_leading_tab_pth_is_refused(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            self._plant_hooks(site / "\tevil", marker)
            (site / "evil").mkdir()
            (site / "zz-tab.pth").write_bytes(b"\tevil\n")

        self._refuse(plant, needles=("plain ASCII", "cannot read this .pth file"))

    def test_rq2001_trailing_spaces_pth_is_refused(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            self._plant_hooks(site / "hooked", marker)
            (site / "zz-trail.pth").write_bytes(b"hooked   \n")

        self._refuse(plant)

    def test_rq2001_mixed_crlf_pth_is_refused(self) -> None:
        def plant(site: Path, marker: Path) -> None:
            self._plant_hooks(site / " evil", marker)
            (site / "evil").mkdir()
            (site / "zz-crlf.pth").write_bytes(b"# note\r\n evil\r\nbad\x01dir\n")

        self._refuse(plant, needles=("plain ASCII", "cannot read this .pth file"))


if __name__ == "__main__":
    unittest.main()
