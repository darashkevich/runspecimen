"""Guard the preparation contract without exporting or using signing credentials."""
from pathlib import Path
import plistlib
import re
import unittest
ROOT = Path(__file__).resolve().parents[1]
class StoreExportDefaultsTests(unittest.TestCase):
    def test_committed_template_defaults_to_local_export(self):
        options = plistlib.loads((ROOT/'apps/macos/Config/ExportOptions.mas.plist').read_bytes())
        self.assertEqual(options['destination'], 'export')
    def test_export_refuses_unresolved_team_before_xcode(self):
        script = (ROOT/'apps/macos/Scripts/export_mas.sh').read_text()
        self.assertIn('"$TEAM" =~ ^[A-Z0-9]{10}$', script)
        self.assertLess(script.index('"$TEAM" =~'), script.index('xcodebuild -exportArchive'))
    def test_checklists_use_the_validated_script(self):
        for name in ['apps/macos/RELEASE_CHECKLIST.md', 'docs/SUBMISSION.md']:
            with self.subTest(name=name):
                text=(ROOT/name).read_text()
                self.assertIn('./Scripts/export_mas.sh',text)
                self.assertNotIn('xcodebuild -exportArchive',text)
