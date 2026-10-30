import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class IOSPrivacyGateTests(unittest.TestCase):
    def test_production_manifest_is_packaged_by_both_project_sources(self):
        manifest=ROOT/'apps/ios/Resources/PrivacyInfo.xcprivacy'
        self.assertTrue(manifest.is_file(),'shipping iPhone resources need a privacy manifest')
        data=plistlib.loads(manifest.read_bytes())
        entries={x['NSPrivacyAccessedAPIType']:x['NSPrivacyAccessedAPITypeReasons'] for x in data['NSPrivacyAccessedAPITypes']}
        self.assertIn('CA92.1',entries['NSPrivacyAccessedAPICategoryUserDefaults'])
        self.assertIn('Resources/PrivacyInfo.xcprivacy',(ROOT/'apps/ios/project.yml').read_text())
        self.assertIn('PrivacyInfo.xcprivacy in Resources',(ROOT/'apps/ios/RunSpecimenObserve.xcodeproj/project.pbxproj').read_text())

    def gate(self):
        spec=importlib.util.spec_from_file_location('ios_privacy_gate',ROOT/'apps/ios/Scripts/ios_privacy_gate.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_release_bundle_rejects_missing_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'manifest'):
                self.gate().audit(Path(directory),{'Observe':'_objc_msgSend'})

    def test_linked_timestamp_api_requires_its_own_category(self):
        with tempfile.TemporaryDirectory() as directory:
            app=Path(directory)
            plist={'NSPrivacyAccessedAPITypes':[{'NSPrivacyAccessedAPIType':'NSPrivacyAccessedAPICategoryUserDefaults','NSPrivacyAccessedAPITypeReasons':['CA92.1']}]}
            (app/'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps(plist))
            with self.assertRaisesRegex(ValueError,'FileTimestamp'):
                self.gate().audit(app,{'Observe':'                 U _fstat\n'})
            plist['NSPrivacyAccessedAPITypes'].append({'NSPrivacyAccessedAPIType':'NSPrivacyAccessedAPICategoryFileTimestamp','NSPrivacyAccessedAPITypeReasons':['C617.1']})
            (app/'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps(plist))
            self.gate().audit(app,{'Observe':'                 U _fstat\n'})

    def test_app_only_defaults_and_clean_linked_symbols_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            app=Path(directory)
            (app/'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps({'NSPrivacyAccessedAPITypes':[{'NSPrivacyAccessedAPIType':'NSPrivacyAccessedAPICategoryUserDefaults','NSPrivacyAccessedAPITypeReasons':['CA92.1']}]}))
            self.assertEqual(self.gate().audit(app,{'Observe':' U _objc_msgSend\n'})['binaries'],['Observe'])

    def test_qa2_objc_imports_and_unknown_reason_are_rejected(self):
        for symbol,category in [('_NSFileModificationDate','FileTimestamp'),('_NSURLContentModificationDateKey','FileTimestamp'),('_NSURLCreationDateKey','FileTimestamp'),('_NSURLVolumeAvailableCapacityForImportantUsageKey','DiskSpace')]:
            with self.subTest(symbol=symbol), tempfile.TemporaryDirectory() as directory:
                app=Path(directory)
                declarations=[{'NSPrivacyAccessedAPIType':'NSPrivacyAccessedAPICategoryUserDefaults','NSPrivacyAccessedAPITypeReasons':['CA92.1']}]
                (app/'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps({'NSPrivacyAccessedAPITypes':declarations}))
                with self.assertRaisesRegex(ValueError,category): self.gate().audit(app,{'Observe':' U '+symbol})
                declarations.append({'NSPrivacyAccessedAPIType':'NSPrivacyAccessedAPICategory'+category,'NSPrivacyAccessedAPITypeReasons':['BOGUS.1']})
                (app/'PrivacyInfo.xcprivacy').write_bytes(plistlib.dumps({'NSPrivacyAccessedAPITypes':declarations}))
                with self.assertRaisesRegex(ValueError,'reason'): self.gate().audit(app,{'Observe':' U '+symbol})
