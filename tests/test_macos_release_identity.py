import importlib.util
from pathlib import Path
import shutil
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mac_identity", ROOT / "scripts/check_macos_release_identity.py")
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)

class MacReleaseIdentityTests(unittest.TestCase):
    def test_repository_identity_is_consistent(self):
        identity.check(ROOT)

    def test_stale_store_paste_sheet_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in identity.FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            metadata = root / "apps/macos/asc-kit/metadata.md"
            metadata.write_text(re.sub(r"\| Build \| [0-9]+ \|", "| Build | 999999 |", metadata.read_text()))
            with self.assertRaisesRegex(ValueError, "metadata.md"):
                identity.check(root)
