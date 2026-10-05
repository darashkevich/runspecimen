"""Negative fixtures for the iOS Release nm gate.

These tests do not build or install RunSpecimenObserve. They do not prove a
device Release artifact. Unprivileged tests do not prove installed protection.
"""

from __future__ import annotations

import importlib.util
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

_GATE = Path(__file__).resolve().parents[1] / "apps" / "ios" / "Scripts" / "nm_symbol_gate.py"
_spec = importlib.util.spec_from_file_location("nm_symbol_gate", _GATE)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SymbolGateError = _mod.SymbolGateError
assert_forbidden_absent = _mod.assert_forbidden_absent
nm_defined_symbols = _mod.nm_defined_symbols
scan_path = _mod.scan_path


class NmSymbolGateNegativeTests(unittest.TestCase):
    def test_forbidden_symbol_is_fatal(self) -> None:
        with self.assertRaises(SymbolGateError) as ctx:
            assert_forbidden_absent(
                "t _beforeFinalSignatureDecision\n",
                label="fixture",
            )
        self.assertIn("beforeFinalSignatureDecision", str(ctx.exception))

    def test_missing_object_is_fatal(self) -> None:
        with self.assertRaises(SymbolGateError) as ctx:
            nm_defined_symbols(Path("/tmp/rs-nm-missing-object-does-not-exist"))
        self.assertIn("missing scan target", str(ctx.exception))

    def test_non_mach_o_is_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "not-macho.txt"
            path.write_text("this is not a mach-o\n", encoding="utf-8")
            with self.assertRaises(SymbolGateError) as ctx:
                scan_path(path)
            self.assertIn("nm failed", str(ctx.exception))

    def test_unreadable_object_is_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "hidden.o"
            path.write_bytes(b"\xcf\xfa\xed\xfe")
            path.chmod(0)
            try:
                with self.assertRaises(SymbolGateError):
                    nm_defined_symbols(path)
            finally:
                path.chmod(0o644)

    def test_clean_mach_o_object_passes_and_is_cached(self) -> None:
        compiler = "cc"
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "clean.c"
            obj = Path(td) / "clean.o"
            src.write_text("int clean_symbol(void){return 1;}\n", encoding="utf-8")
            built = subprocess.run(
                [compiler, "-c", str(src), "-o", str(obj)],
                check=False,
                capture_output=True,
                text=True,
            )
            if built.returncode != 0:
                self.skipTest("cc unavailable")
            calls = {"n": 0}
            real = _mod.subprocess.run

            def _counting(*args, **kwargs):
                calls["n"] += 1
                return real(*args, **kwargs)

            _mod.subprocess.run = _counting
            try:
                first = scan_path(obj)
                second = nm_defined_symbols(obj)
            finally:
                _mod.subprocess.run = real
            self.assertEqual(calls["n"], 1)
            self.assertEqual(first, second)
            self.assertNotIn("beforeConsumptionDecision", first)
            self.assertTrue(obj.stat().st_mode & stat.S_IFREG)
