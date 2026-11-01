"""Current-facing docs must name published 0.2.0rc16 and the signal advisory."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublishedRc16DocsTests(unittest.TestCase):
    def test_readme_install_pins_rc16(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("pip install --pre runspecimen==0.2.0rc16", text)
        self.assertIn("https://pypi.org/project/runspecimen/0.2.0rc16/", text)
        self.assertIn("v0.2.0-rc.16", text)
        self.assertIn("tap still served `0.2.0rc15` on 2026-11-01", text)

    def test_faq_names_advisory_and_residuals(self) -> None:
        text = (ROOT / "docs/FAQ.md").read_text(encoding="utf-8")
        self.assertIn("**0.2.0rc16**", text)
        self.assertIn("GHSA-8357-m9wf-gjh9", text)
        self.assertIn("pip install --upgrade --pre runspecimen==0.2.0rc16", text)
        self.assertIn("setsid()", text)
        self.assertIn("SIGKILL of both the supervisor and the bind watchdog", text)
        self.assertIn("unwritable state directory", text)
        self.assertIn('schema_version": 2', text)

    def test_changelog_and_security_record_the_cut(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("## 0.2.0rc16 - 2026-11-01", changelog)
        self.assertIn("The DeepSeek Harness integration is not in the PyPI wheel.", changelog)
        self.assertIn("GHSA-8357-m9wf-gjh9", security)
        self.assertIn(">=0.2.0rc3,<0.2.0rc16", security)

    def test_release_checklist_published_bytes_are_rc16(self) -> None:
        text = (ROOT / "docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
        self.assertIn("Published engine bytes are **`0.2.0rc16`**", text)
        self.assertIn("This tree's engine is **`0.2.0rc16`**", text)
        self.assertIn("v0.2.0-rc.16", text)
        self.assertIn("ae94701", text)

    def test_website_is_declared_out_of_repo(self) -> None:
        identity = (ROOT / "docs/RELEASE_IDENTITY.md").read_text(encoding="utf-8")
        submission = (ROOT / "docs/SUBMISSION.md").read_text(encoding="utf-8")
        self.assertIn("darashkevich/darashkevich.com", identity)
        self.assertIn("sites/runspecimen/", identity)
        self.assertIn("not this repo", identity)
        self.assertIn("sites/runspecimen/", submission)
        self.assertFalse((ROOT / "site").exists())
        self.assertFalse((ROOT / "website").exists())
