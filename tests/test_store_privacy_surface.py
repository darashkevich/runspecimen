"""Store target must exclude the standalone diagnostic's required-reason APIs."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class StorePrivacySurfaceTests(unittest.TestCase):
    def test_diagnostic_filesystem_gate_is_excluded_from_store_target(self):
        spec=(ROOT/'apps/macos/project.yml').read_text()
        self.assertIn('TouchIDDiagnosticGate.swift',spec)
        project=(ROOT/'apps/macos/RunSpecimen.xcodeproj/project.pbxproj').read_text()
        self.assertNotIn('TouchIDDiagnosticGate.swift in Sources',project)
        core=(ROOT/'apps/macos/Sources/RunSpecimenCore/BiometricApproval.swift').read_text()
        self.assertNotIn('fstat(',core)
        self.assertNotIn('fstatat(',core)
        self.assertNotIn('lstat(',core)
    def test_cli_discovery_uses_bounded_content_instead_of_file_metadata(self):
        source=(ROOT/'apps/macos/Sources/RunSpecimenApp/Services/CLIService.swift').read_text()
        self.assertNotIn('attributesOfItem',source)
        self.assertIn('read(upToCount: 64)',source)
