"""Mac App Store preparation locks for the 0.1.6 (16) / 0.2.0rc16 cut."""
from pathlib import Path
import plistlib
import unittest

ROOT = Path(__file__).resolve().parents[1]
MACOS = ROOT / "apps/macos"


class MacosAppStoreReadinessTests(unittest.TestCase):
    def test_submission_doc_lists_human_only_steps(self) -> None:
        text = (ROOT / "docs/MACOS_APPSTORE_SUBMISSION.md").read_text(encoding="utf-8")
        self.assertIn("0.1.6 (16)", text)
        self.assertIn("0.2.0rc16", text)
        self.assertIn("Never pass `-allowProvisioningUpdates`", text)
        self.assertIn("Export compliance", text)
        self.assertIn("Privacy nutrition labels", text)
        self.assertIn("Screenshots", text)
        self.assertIn("EU trader status", text)
        self.assertIn("archive_unsigned_release.sh", text)
        self.assertIn("**STALE**", text)
        self.assertIn("0.1.3 (4)", text)
        self.assertIn("0.2.0rc10", text)
        self.assertNotIn("listing is now live", text)

    def test_store_listing_is_removed_not_live(self) -> None:
        submission = (ROOT / "docs/SUBMISSION.md").read_text(encoding="utf-8")
        kit = (MACOS / "asc-kit/README.md").read_text(encoding="utf-8")
        checklist = (ROOT / "docs/MACOS_APPSTORE_SUBMISSION.md").read_text(encoding="utf-8")
        for text in (submission, kit, checklist):
            self.assertIn("Removed from App Store", text)
            self.assertNotIn("listing is now live", text)
        self.assertNotIn("READY_FOR_SALE", submission)
        self.assertIn("mas-python312", submission)
        self.assertNotIn("freeze312", submission)
        self.assertIn("DiskSpace", submission)

    def test_unsigned_archive_script_is_ad_hoc_only(self) -> None:
        script = MACOS / "Scripts/archive_unsigned_release.sh"
        text = script.read_text(encoding="utf-8")
        self.assertTrue(script.is_file())
        self.assertIn("CODE_SIGN_IDENTITY=-", text)
        self.assertIn("AD_HOC_CODE_SIGNING_ALLOWED=YES", text)
        self.assertIn("allowProvisioningUpdates is forbidden", text)
        xcodebuild = text[text.index("xcodebuild") :]
        self.assertNotIn("allowProvisioningUpdates", xcodebuild)
        smoke = (MACOS / "Scripts/smoke_macos.sh").read_text(encoding="utf-8")
        self.assertIn("archive_unsigned_release.sh", smoke)

    def test_mas_entitlements_and_privacy_surface(self) -> None:
        mas = plistlib.loads((MACOS / "Entitlements/RunSpecimen.mas.entitlements").read_bytes())
        helper = plistlib.loads((MACOS / "Entitlements/RunSpecimen.helper.entitlements").read_bytes())
        privacy = plistlib.loads((MACOS / "Resources/PrivacyInfo.xcprivacy").read_bytes())
        info_mas = plistlib.loads((MACOS / "Config/Info-mas.plist").read_bytes())
        info_local = plistlib.loads((MACOS / "Resources/Info.plist").read_bytes())
        self.assertTrue(mas["com.apple.security.app-sandbox"])
        self.assertNotIn("com.apple.security.network.server", mas)
        self.assertTrue(helper["com.apple.security.app-sandbox"])
        self.assertTrue(helper["com.apple.security.inherit"])
        self.assertFalse(privacy["NSPrivacyTracking"])
        self.assertEqual(privacy["NSPrivacyCollectedDataTypes"], [])
        self.assertFalse(info_mas["ITSAppUsesNonExemptEncryption"])
        self.assertFalse(info_local["ITSAppUsesNonExemptEncryption"])
        self.assertEqual(info_mas["CFBundleShortVersionString"], "0.1.6")
        self.assertEqual(str(info_mas["CFBundleVersion"]), "16")
        project = (MACOS / "project.yml").read_text(encoding="utf-8")
        self.assertIn("ENABLE_HARDENED_RUNTIME: YES", project)
        self.assertIn('CFBundleShortVersionString: "0.1.6"', project)
        self.assertIn('CFBundleVersion: "16"', project)

    def test_asc_metadata_is_current_for_rc16(self) -> None:
        metadata = (MACOS / "asc-kit/metadata.md").read_text(encoding="utf-8")
        self.assertIn("| Short version | 0.1.6 |", metadata)
        self.assertIn("| Build | 16 |", metadata)
        self.assertIn("| Bundled engine | 0.2.0rc16 source", metadata)
        self.assertIn("## What's New (0.1.6)", metadata)
        self.assertIn("GHSA-8357-m9wf-gjh9", metadata)
        self.assertIn("https://runspecimen.darashkevich.com/support/", metadata)
        self.assertIn("https://runspecimen.darashkevich.com/privacy/", metadata)
        self.assertFalse((MACOS / "fastlane").exists())
        self.assertFalse((ROOT / "fastlane").exists())
