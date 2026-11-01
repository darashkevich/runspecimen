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
        self.assertIn("plugin **0.2.0-rc.16**", text)
        self.assertIn("Plugin version: `0.2.0-rc.16`", text)
        self.assertIn("GHSA-8357-m9wf-gjh9", text)
        self.assertIn("pip install --upgrade --pre runspecimen==0.2.0rc16", text)
        self.assertIn("setsid()", text)
        self.assertIn("SIGKILL of both the supervisor and the bind watchdog", text)
        self.assertIn("unwritable state directory", text)
        self.assertIn('schema_version": 2', text)

    def test_candidate_manifest_published_digests_are_rc16(self) -> None:
        text = (ROOT / "docs/CANDIDATE_MANIFEST.md").read_text(encoding="utf-8")
        self.assertIn("| Engine / package | published `0.2.0rc16` |", text)
        self.assertIn("| Plugin | published `0.2.0-rc.16` |", text)
        self.assertIn("59044b56fbe3fa798a5ebb8ead3f0460141c96c98e8d0861aafd4a83ede8e9cc", text)
        self.assertIn("83625441d316816107087870525a88d20cd42b61c69e7e398ce95cdcc3fe31d4", text)
        self.assertIn("1d5961b9c70b18efacb7ebf6babcdb6a51825f2a786d559b8a980677cc67c2bd", text)
        self.assertIn("the published engine is now `0.2.0rc16`", text)
        self.assertNotIn("Version stays `0.2.0rc15` (never published)", text)
        published_row = next(
            line for line in text.splitlines() if line.startswith("| Published wheel / sdist / plugin zip |")
        )
        self.assertNotIn("d720bf5163a2b250699c30e804f89708e71c1c0d22682fbb43a4644b59c45948", published_row)

    def test_next_changes_names_published_rc16(self) -> None:
        text = (ROOT / "docs/NEXT_CHANGES.md").read_text(encoding="utf-8")
        self.assertIn("published package is `0.2.0rc16`", text)
        self.assertNotIn("published package is `0.2.0rc15`", text)

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

    def test_human_acceptance_is_historical_published_rc15(self) -> None:
        text = (ROOT / "docs/HUMAN-ACCEPTANCE.md").read_text(encoding="utf-8")
        lead = "\n".join(text.splitlines()[:20])
        self.assertIn("# Human acceptance — historical 0.2.0rc15", lead)
        self.assertIn("This is a **historical** qafix32 sheet.", lead)
        self.assertIn("The current published engine is", lead)
        self.assertIn("**`0.2.0rc16`**", lead)
        self.assertIn("published rc15 bytes", lead)
        self.assertIn(
            "d9d0c9dfc978beb29ac34901d788e647812d3f663c703281da35d2172ac4f048",
            lead,
        )
        self.assertIn(
            "7abe59f54e974140e305f3b31f24767ca078eaafe0b606c26f606cb1ece9e63b",
            lead,
        )
        self.assertIn(
            "ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb",
            lead,
        )
        self.assertNotIn("never published", text)
        self.assertNotIn("unpublished 0.2.0rc15", text)
        self.assertIn("They are\nnot unpublished.", lead)
