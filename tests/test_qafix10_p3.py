"""Pin qafix10 P3 copy: about honesty, showcase order, schema 2, no whole-record claim."""

from __future__ import annotations

import json
import re
import sys
import unittest
from io import StringIO
from pathlib import Path

from tests.helpers import ROOT, SRC

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.cli import _ABOUT_SUMMARY, main


HONESTY_ADD = (
    "program running as you that can edit RunSpecimen's files can still "
    "add a fake approval to the record."
)
HONESTY_PROTECT = (
    "To protect against that, sign receipts with a key the agent can't access."
)
FORBIDDEN_REWRITE = (
    "rewrites the whole record",
    "rewrite the whole record",
    "rewrites the entire event log",
    "rewrite the entire event log",
    "rewrites the whole log",
    "full record rewrite",
)
SCAN_ROOTS = (ROOT / "src", ROOT / "docs", ROOT / "README.md", ROOT / "CHANGELOG.md")
SKIP_NAMES = {"BIOMETRIC_APPROVAL.md"}
UNQUALIFIED_APPROVE = re.compile(
    r"cannot approve(?![\s\S]{0,120}?through)",
    re.IGNORECASE,
)


def _iter_user_facing() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if root.is_file():
            files.append(root)
            continue
        files.extend(p for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".md"})
    return files


class TestQafix10P3Copy(unittest.TestCase):
    def test_about_summary_constant_is_the_honesty_wording(self) -> None:
        self.assertIn("Plugins/agents cannot approve through the app.", _ABOUT_SUMMARY)
        self.assertIn(HONESTY_ADD, _ABOUT_SUMMARY)
        self.assertIn(HONESTY_PROTECT, _ABOUT_SUMMARY)
        self.assertNotIn("Plugins/agents cannot approve.", _ABOUT_SUMMARY)

    def test_about_cli_json_matches_summary_constant(self) -> None:
        from contextlib import redirect_stdout

        out = StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["about"]), 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["summary"], _ABOUT_SUMMARY)

    def test_honesty_sentence_is_in_readme_changelog_faq_about_and_security_docs(self) -> None:
        targets = {
            ROOT / "README.md",
            ROOT / "CHANGELOG.md",
            ROOT / "docs" / "FAQ.md",
            ROOT / "docs" / "ABOUT.md",
            ROOT / "docs" / "THREAT_MODEL.md",
            ROOT / "docs" / "USER_GUIDE.md",
            ROOT / "src" / "runspecimen" / "cli.py",
            ROOT / "src" / "runspecimen" / "present.py",
        }
        for path in targets:
            collapsed = re.sub(r"\s+", " ", path.read_text(encoding="utf-8").replace('"', " "))
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertIn(HONESTY_ADD, collapsed)
                self.assertIn(HONESTY_PROTECT, collapsed)

    def test_src_and_docs_have_no_unqualified_or_inaccurate_honesty_claims(self) -> None:
        hits: list[str] = []
        for path in _iter_user_facing():
            if path.name in SKIP_NAMES:
                continue
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(ROOT))
            for needle in FORBIDDEN_REWRITE:
                if needle in text:
                    hits.append(f"{rel}: {needle!r}")
            if UNQUALIFIED_APPROVE.search(text):
                hits.append(f"{rel}: unqualified cannot approve")
        self.assertEqual(hits, [])
