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


if __name__ == "__main__":
    unittest.main()
