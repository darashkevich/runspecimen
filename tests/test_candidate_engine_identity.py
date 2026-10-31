import importlib.util
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "release_check_candidate_engine", ROOT / "scripts" / "release_check.py"
)
release_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_check)

CANDIDATE_DOC_FILES = tuple(
    dict.fromkeys(path for path, _, _ in release_check.CANDIDATE_ENGINE_PINS)
)
VERSION_FILE = "src/runspecimen/__init__.py"


def _copy_identity_tree(destination: Path) -> None:
    for name in (*CANDIDATE_DOC_FILES, VERSION_FILE):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)


class CandidateEngineIdentityTests(unittest.TestCase):
    def test_repository_candidate_docs_match_version(self) -> None:
        release_check.check_candidate_engine_docs(ROOT)
        self.assertEqual(release_check.load_python_version(ROOT), "0.2.0rc16")
        self.assertEqual(
            release_check.plugin_version_for_python("0.2.0rc16"), "0.2.0-rc.16"
        )

    def test_stale_current_candidate_doc_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _copy_identity_tree(root)
            target = root / "docs/RELEASE_IDENTITY.md"
            before = target.read_text(encoding="utf-8")
            after = before.replace(
                "identifies as **`0.2.0rc16`** / **`0.2.0-rc.16`**",
                "identifies as **`0.2.0rc15`** / **`0.2.0-rc.15`**",
            )
            self.assertNotEqual(before, after)
            target.write_text(after, encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "RELEASE_IDENTITY.md"):
                release_check.check_candidate_engine_docs(root)

    def test_version_bump_without_docs_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _copy_identity_tree(root)
            version = root / VERSION_FILE
            version.write_text('__version__ = "0.2.0rc99"\n', encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "does not match"):
                release_check.check_candidate_engine_docs(root)

    def test_historical_status_rc15_row_is_not_a_current_pin(self) -> None:
        status = (ROOT / "apps/macos/asc-kit/STATUS.md").read_text(encoding="utf-8")
        self.assertIn(
            "| Historical integrated candidate | **historical 0.1.5 (13)** |",
            status,
        )
        self.assertIn("engine **0.2.0rc15**", status)
        release_check.check_candidate_engine_docs(ROOT)

    def test_each_current_candidate_pin_rejects_python_drift(self) -> None:
        python_pins = [
            (path, pattern)
            for path, pattern, kinds in release_check.CANDIDATE_ENGINE_PINS
            if kinds == ("python",)
        ]
        for changed, pattern in python_pins:
            with self.subTest(changed=changed, pattern=pattern), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _copy_identity_tree(root)
                target = root / changed
                before = target.read_text(encoding="utf-8")
                match = re.search(pattern, before)
                self.assertIsNotNone(match)
                stale = before[: match.start(1)] + "0.2.0rc15" + before[match.end(1) :]
                self.assertNotEqual(before, stale)
                target.write_text(stale, encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, changed.split("/")[-1]):
                    release_check.check_candidate_engine_docs(root)
