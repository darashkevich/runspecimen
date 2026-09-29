"""The 0.1.3 rejection was symbol and framework linkage, not the module name."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / "apps" / "macos" / "Scripts" / "verify_mas_runtime.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("mas_runtime_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RejectedRuntimeSymbolTests(unittest.TestCase):
    def test_module_table_name_is_not_the_rejected_symbol(self):
        gate = load_gate()
        table = "o._json._locale._lsprof._lzma._markupbase._md5"
        self.assertEqual(
            [],
            gate.violations("binary:\n /usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n", table),
        )

    def test_rejected_lzma_and_private_framework_symbols_fail(self):
        gate = load_gate()
        self.assertTrue(gate.violations("binary:", "0000000100001f00 T _lzma_code"))
        self.assertTrue(
            gate.violations(
                "binary:\n /System/Library/PrivateFrameworks/TrustEvaluationAgent.framework/TrustEvaluationAgent (x)\n",
                "",
            )
        )
        self.assertTrue(gate.violations("binary:\n /usr/lib/liblzma.5.dylib (x)\n", ""))
