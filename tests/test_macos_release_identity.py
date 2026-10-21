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
            for name in (*identity.FILES, *identity.ACTIVE_DOCS):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            metadata = root / "apps/macos/asc-kit/metadata.md"
            metadata.write_text(re.sub(r"\| Build \| [0-9]+ \|", "| Build | 999999 |", metadata.read_text()))
            with self.assertRaisesRegex(ValueError, "metadata.md"):
                identity.check(root)

    def test_stale_active_overview_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (*identity.FILES, *identity.ACTIVE_DOCS):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            overview = root / "README.md"
            version, build = identity.check(ROOT)
            overview.write_text(overview.read_text().replace(f"local label on this branch is **{version} ({build})**", "local label on this branch is **9.9.9 (999999)**"))
            with self.assertRaisesRegex(ValueError, "README.md"):
                identity.check(root)

    def test_each_release_identity_source_rejects_version_drift(self):
        version, _ = identity.check(ROOT)
        for changed in (*identity.FILES, *identity.ACTIVE_DOCS):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name in (*identity.FILES, *identity.ACTIVE_DOCS):
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / name, target)
                target = root / changed
                before = target.read_text()
                self.assertIn(version, before)
                target.write_text(before.replace(version, "9.9.9"))
                with self.assertRaises(ValueError):
                    identity.check(root)

    def test_stale_integrated_candidate_anywhere_in_status_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (*identity.FILES, *identity.ACTIVE_DOCS):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            status = root / "apps/macos/asc-kit/STATUS.md"
            status.write_text(status.read_text() + "\n| Unpublished integrated candidate | **0.1.5 (13)** | stale |\n")
            with self.assertRaisesRegex(ValueError, "STATUS.md"):
                identity.check(root)

    def test_duplicate_stale_version_and_build_rows_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (*identity.FILES, *identity.ACTIVE_DOCS):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            metadata = root / "apps/macos/asc-kit/metadata.md"
            metadata.write_text(metadata.read_text() + "\n| Short version | 9.9.9 |\n| Build | 999999 |\n")
            with self.assertRaisesRegex(ValueError, "metadata.md"):
                identity.check(root)
