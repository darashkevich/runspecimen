"""NEW-01: packaged unittest suites must import from the sandbox copy.

A start_dir named ``tests`` with ``tests/__init__.py`` used to be imported from
the live workspace because the runner put that workspace ahead of the temp
sandbox on ``sys.path``. Discovery then reported zero tests and
``module incorrectly imported``. These cases fail on that order and pass when
the sandbox wins for the suite package while application imports still resolve
to the live tree.
"""

from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path

from tests.helpers import RunSpecimenTestCase

from runspecimen.requirements import (
    OUTCOME_PASSED,
    CheckRef,
    Requirement,
    UnittestProvider,
)


def _requirement() -> Requirement:
    return Requirement(
        id="r",
        description="d",
        check=CheckRef(provider="unittest", id="u", config={}),
        inputs=(),
        source_scope=(),
        required_evidence=(),
        expected={},
        rationale=None,
        manual_unverifiable=False,
    )


def _tree_state(root: Path) -> tuple[tuple[str, ...], dict[str, str]]:
    """List every relative path under *root* and hash every regular file."""
    names: list[str] = []
    hashes: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames.sort()
        rel_dir = Path(dirpath).relative_to(root)
        for dirname in dirnames:
            rel = dirname if str(rel_dir) == "." else str(rel_dir / dirname)
            names.append(rel + "/")
        for filename in filenames:
            rel = filename if str(rel_dir) == "." else str(rel_dir / filename)
            names.append(rel)
            path = Path(dirpath) / filename
            hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return tuple(sorted(names)), hashes


def _passed_count(raw: dict) -> int:
    return sum(1 for t in raw.get("tests") or [] if t.get("outcome") == "passed")


class New01PackagedUnittestSuiteTests(RunSpecimenTestCase):
    def test_new01_packaged_suite_discovers_and_passes(self) -> None:
        tests = self.ws / "tests"
        tests.mkdir()
        (tests / "__init__.py").write_text("", encoding="utf-8")
        (tests / "test_ok.py").write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        raw = UnittestProvider().run(
            workspace=self.ws,
            check_id="u",
            config={"start_dir": "tests", "pattern": "test_*.py"},
            requirement=_requirement(),
        )
        self.assertEqual(raw["outcome"], OUTCOME_PASSED, raw)
        self.assertEqual(raw.get("tests_run"), 1, raw)
        self.assertEqual(len(raw.get("tests") or []), 1, raw)
        self.assertEqual(_passed_count(raw), 1, raw)

    def test_new01_nested_package_imports_helpers(self) -> None:
        tests = self.ws / "tests"
        unit = tests / "unit"
        unit.mkdir(parents=True)
        (tests / "__init__.py").write_text("", encoding="utf-8")
        (tests / "helpers.py").write_text("X = 7\n", encoding="utf-8")
        (unit / "__init__.py").write_text("", encoding="utf-8")
        (unit / "test_nested.py").write_text(
            "import unittest\n"
            "from tests.helpers import X\n"
            "class T(unittest.TestCase):\n"
            "    def test_nested(self):\n"
            "        self.assertEqual(X, 7)\n",
            encoding="utf-8",
        )
        raw = UnittestProvider().run(
            workspace=self.ws,
            check_id="u",
            config={"start_dir": "tests", "pattern": "test_*.py"},
            requirement=_requirement(),
        )
        self.assertEqual(raw["outcome"], OUTCOME_PASSED, raw)
        self.assertEqual(raw.get("tests_run"), 1, raw)
        self.assertEqual(_passed_count(raw), 1, raw)

    def test_new01_application_import_resolves_live_workspace(self) -> None:
        app = self.ws / "app"
        app.mkdir()
        (app / "__init__.py").write_text("", encoding="utf-8")
        (app / "core.py").write_text("def f():\n    return 42\n", encoding="utf-8")
        tests = self.ws / "tests"
        tests.mkdir()
        (tests / "__init__.py").write_text("", encoding="utf-8")
        (tests / "test_app.py").write_text(
            "import unittest\n"
            "from app.core import f\n"
            "class T(unittest.TestCase):\n"
            "    def test_app(self):\n"
            "        self.assertEqual(f(), 42)\n",
            encoding="utf-8",
        )
        raw = UnittestProvider().run(
            workspace=self.ws,
            check_id="u",
            config={"start_dir": "tests", "pattern": "test_*.py"},
            requirement=_requirement(),
        )
        self.assertEqual(raw["outcome"], OUTCOME_PASSED, raw)
        self.assertEqual(raw.get("tests_run"), 1, raw)
        self.assertEqual(_passed_count(raw), 1, raw)

    def test_new01_live_tree_untouched_packaged(self) -> None:
        start = self.ws / "tests"
        start.mkdir()
        (start / "__init__.py").write_text("# packaged\n", encoding="utf-8")
        (start / "test_ok.py").write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        before_names, before_hashes = _tree_state(start)
        raw = UnittestProvider().run(
            workspace=self.ws,
            check_id="u",
            config={"start_dir": "tests", "pattern": "test_*.py"},
            requirement=_requirement(),
        )
        self.assertEqual(raw["outcome"], OUTCOME_PASSED, raw)
        after_names, after_hashes = _tree_state(start)
        self.assertEqual(after_names, before_names)
        self.assertEqual(after_hashes, before_hashes)
        self.assertFalse(any(name.rstrip("/").endswith("__pycache__") or "/__pycache__/" in name or name.endswith(".pyc") for name in after_names))
        self.assertEqual((start / "__init__.py").read_text(encoding="utf-8"), "# packaged\n")

    def test_new01_live_tree_untouched_unpackaged(self) -> None:
        start = self.ws / "ut_plain"
        start.mkdir()
        (start / "test_ok.py").write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )
        self.assertFalse((start / "__init__.py").exists())
        before_names, before_hashes = _tree_state(start)
        raw = UnittestProvider().run(
            workspace=self.ws,
            check_id="u",
            config={"start_dir": "ut_plain", "pattern": "test_*.py"},
            requirement=_requirement(),
        )
        self.assertEqual(raw["outcome"], OUTCOME_PASSED, raw)
        after_names, after_hashes = _tree_state(start)
        self.assertEqual(after_names, before_names)
        self.assertEqual(after_hashes, before_hashes)
        self.assertFalse((start / "__init__.py").exists())
        self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in after_names))

    def test_new01_expected_failure_in_packaged_suite_not_passed(self) -> None:
        tests = self.ws / "tests"
        tests.mkdir()
        (tests / "__init__.py").write_text("", encoding="utf-8")
        (tests / "test_x.py").write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    @unittest.expectedFailure\n"
            "    def test_expected(self):\n"
            "        self.fail('expected')\n",
            encoding="utf-8",
        )
        raw = UnittestProvider().run(
            workspace=self.ws,
            check_id="u",
            config={"start_dir": "tests", "pattern": "test_*.py"},
            requirement=_requirement(),
        )
        self.assertNotEqual(raw["outcome"], OUTCOME_PASSED, raw)
        self.assertTrue(
            any(t.get("outcome") == "expected_failure" for t in raw["tests"])
            or raw.get("expected_failures", 0) >= 1,
            raw,
        )


if __name__ == "__main__":
    unittest.main()
