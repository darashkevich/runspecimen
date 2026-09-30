import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("gate", pathlib.Path(__file__).with_name("verify_mas_runtime.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class RejectedRuntimeTests(unittest.TestCase):
    def test_rejects_private_framework(self):
        self.assertTrue(gate.violations("binary:\n /System/Library/PrivateFrameworks/TrustEvaluationAgent.framework/Versions/A/TrustEvaluationAgent (x)", ""))

    def test_rejects_lzma_symbols(self):
        for symbol in ("_lzma_code", "_lzma_alone_decoder", "_lzma_properties_encode", "_lzma_stream_encoder"):
            self.assertTrue(gate.violations("binary:", symbol))

    def test_rejects_host_libraries(self):
        self.assertTrue(gate.violations("binary:\n /opt/homebrew/lib/libssl.dylib (x)", ""))

    def test_accepts_bundled_ssl_and_public_framework(self):
        self.assertEqual([], gate.violations("binary:\n @loader_path/libssl.3.dylib (x)\n /System/Library/Frameworks/Security.framework/Versions/A/Security (x)", "_SecTrustEvaluateWithError"))

    def test_cpython_module_table_name_is_not_a_rejected_symbol(self):
        table = "o._json._locale._lsprof._lzma._markupbase._md5._msi"
        self.assertEqual([], gate.violations("binary:\n /usr/lib/libSystem.B.dylib (x)", table))
        self.assertEqual([], gate.violations("binary:\n /usr/lib/libSystem.B.dylib (x)", "T _PyInit__lzma"))

    def test_defined_lzma_symbol_is_rejected(self):
        self.assertTrue(gate.violations("binary:", "0000000100001f00 T _lzma_code"))
        self.assertTrue(gate.violations("binary:", "                 U _lzma_stream_encoder"))

    def test_every_architecture_slice_is_inspected(self):
        seen = []

        def deps(arch):
            seen.append(("deps", arch))
            return "binary:\n /usr/lib/libSystem.B.dylib (x)\n", None

        def symbols(arch):
            seen.append(("nm", arch))
            if arch == "x86_64":
                return "0000000100001f00 T _lzma_code\n", None
            return "o._json._locale._lsprof._lzma._markupbase\n", None

        errors = gate.inspect_slices(["arm64", "x86_64"], deps, symbols)
        self.assertEqual(seen, [("deps", "arm64"), ("nm", "arm64"), ("deps", "x86_64"), ("nm", "x86_64")])
        self.assertEqual(errors, ["x86_64: rejected API reference: 0000000100001f00 T _lzma_code"])

    def test_slice_tool_failure_is_a_violation(self):
        errors = gate.inspect_slices(
            ["arm64"],
            lambda arch: ("", f"otool failed for {arch}: bad"),
            lambda arch: ("", None),
        )
        self.assertEqual(errors, ["otool failed for arm64: bad"])
        self.assertEqual(gate.inspect_slices([], lambda arch: ("", None), lambda arch: ("", None)), ["no architecture slice inspected"])

    def test_identity_mismatch_fails_a_clean_symbol_scan(self):
        self.assertEqual([], gate.identity_errors({"Python": "abc"}, {"Python": "abc"}))
        self.assertTrue(gate.identity_errors({"Python": "abc"}, {"Python": "def"}))

    def test_resolve_expected_commit_prefers_canonical_and_warns_once(self):
        import io
        from contextlib import redirect_stderr

        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(gate.resolve_expected_commit("a" * 40, None), "a" * 40)
        self.assertEqual(err.getvalue(), "")
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(gate.resolve_expected_commit(None, "b" * 40), "b" * 40)
        self.assertEqual(err.getvalue().count(gate.DEPRECATED_EXPECT_COMMIT), 1)
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(gate.resolve_expected_commit("c" * 40, "c" * 40), "c" * 40)
        self.assertEqual(err.getvalue().count(gate.DEPRECATED_EXPECT_COMMIT), 1)
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            gate.resolve_expected_commit("d" * 40, "e" * 40)


if __name__ == "__main__":
    unittest.main()
