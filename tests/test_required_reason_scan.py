import importlib.util
import json
import plistlib
import tempfile
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'apps/macos/Scripts/scan_required_reason_apis.py'

class RequiredReasonScanTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('scan_required_reason_apis',SOURCE)
        self.scan=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.scan)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'Example.app';(self.root/'Contents/Resources').mkdir(parents=True)
        self.manifest(self.root/'Contents/Resources/PrivacyInfo.xcprivacy',{'UserDefaults':['CA92.1']})

    def manifest(self,path,categories):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(plistlib.dumps({'NSPrivacyAccessedAPITypes':[{'NSPrivacyAccessedAPIType':'NSPrivacyAccessedAPICategory'+k,'NSPrivacyAccessedAPITypeReasons':v} for k,v in categories.items()]}))

    def binary(self,path):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(bytes.fromhex('cffaedfe')+b'fixture');return path

    def test_scans_app_helper_and_framework_and_reports_undeclared_imports(self):
        self.binary(self.root/'Contents/MacOS/Example')
        self.binary(self.root/'Contents/Resources/Engine/Python')
        framework=self.root/'Contents/Frameworks/SDK.framework'
        self.binary(framework/'Versions/A/SDK')
        self.manifest(framework/'Resources/PrivacyInfo.xcprivacy',{'FileTimestamp':['C617.1']})
        texts={'Example':'_OBJC_CLASS_$_NSUserDefaults','Python':'_statvfs\n_fstatvfs','SDK':'_NSFileModificationDate'}
        result=self.scan.scan(self.root,read_symbols=lambda p:texts[p.name])
        self.assertEqual(len(result['binaries']),3)
        python=next(x for x in result['binaries'] if x['binary'].endswith('/Python'))
        self.assertEqual(python['undeclared_categories'],['DiskSpace'])
        sdk=next(x for x in result['binaries'] if x['binary'].endswith('/SDK'))
        self.assertEqual(sdk['undeclared_categories'],[])
        self.assertIn('SDK.framework/Resources',sdk['manifest'])
        self.assertEqual(result['undeclared_categories'],['DiskSpace'])
        json.dumps(result)

    def test_objc_required_reason_constants_are_classified(self):
        p=self.binary(self.root/'Contents/MacOS/Example')
        result=self.scan.scan(self.root,read_symbols=lambda _: '_NSURLContentModificationDateKey\n_NSURLCreationDateKey\n_NSURLVolumeAvailableCapacityForImportantUsageKey')
        self.assertEqual(set(result['undeclared_categories']),{'FileTimestamp','DiskSpace'})

    def test_failed_symbol_reader_is_an_error_not_an_empty_scan(self):
        self.binary(self.root/'Contents/MacOS/Example')
        def fail(_):raise RuntimeError('nm failed')
        with self.assertRaisesRegex(RuntimeError,'nm failed'):self.scan.scan(self.root,read_symbols=fail)

    def test_archive_entry_discovers_apps_and_ignores_plain_files(self):
        archive=Path(self.tmp.name)/'Example.xcarchive'
        app=archive/'Products/Applications/Example.app'
        self.binary(app/'Contents/MacOS/Example')
        self.manifest(app/'Contents/Resources/PrivacyInfo.xcprivacy',{'UserDefaults':['CA92.1']})
        (app/'plain.txt').write_text('not a Mach-O')
        result=self.scan.scan(archive,read_symbols=lambda _: '_OBJC_CLASS_$_NSUserDefaults')
        self.assertEqual(len(result['binaries']),1)

    def test_refuses_external_file_symlink(self):
        outside=self.binary(Path(self.tmp.name)/'outside')
        (self.root/'linked').symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'outside'):self.scan.scan(self.root,read_symbols=lambda _: '')
