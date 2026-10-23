import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("macos_privacy_gate", ROOT / "apps/macos/Scripts/macos_privacy_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class MacPrivacyGateTests(unittest.TestCase):
    def bundle(self, root, data):
        app = Path(root) / "RunSpecimen.app"
        path = app / "Contents/Resources/PrivacyInfo.xcprivacy"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps(data))
        return app

    def production(self):
        return plistlib.loads((ROOT / "apps/macos/Resources/PrivacyInfo.xcprivacy").read_bytes())

    def test_real_packaged_manifest_matches_release_decision(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(gate.audit(self.bundle(root, self.production())), gate.EXPECTED)

    def test_missing_wrong_extra_and_duplicate_declarations_fail(self):
        entries = [{"NSPrivacyAccessedAPIType": k, "NSPrivacyAccessedAPITypeReasons": v} for k, v in gate.EXPECTED.items()]
        variants = [entries[:-1], entries + [entries[0]], entries + [{"NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryDiskSpace", "NSPrivacyAccessedAPITypeReasons": ["E174.1"]}], entries[:-1] + [{"NSPrivacyAccessedAPIType": entries[-1]["NSPrivacyAccessedAPIType"], "NSPrivacyAccessedAPITypeReasons": ["C617.1"]}]]
        for variant in variants:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):
                    gate.audit(self.bundle(root, {"NSPrivacyAccessedAPITypes": variant}))
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "missing"):
                gate.audit(Path(root))
