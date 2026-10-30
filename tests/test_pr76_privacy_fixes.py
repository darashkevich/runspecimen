"""PR76 QA2-P2-04, archive enforcement, and clipboard wait regressions."""
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'apps/macos/Scripts'


class PR76PrivacyFixTests(unittest.TestCase):
    def test_embedded_runtime_rejects_disk_space_imports_in_every_slice(self):
        spec = importlib.util.spec_from_file_location('runtime', SCRIPTS / 'verify_mas_runtime.py')
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        for symbol in ('_statvfs', '_fstatvfs', '_statfs', '_fstatfs', '_statfs64', '_fstatfs64'):
            with self.subTest(symbol=symbol):
                errors = runtime.inspect_slices(
                    ['arm64', 'x86_64'], lambda _: ('binary:\n /usr/lib/libSystem.B.dylib (x)', None),
                    lambda arch: ('U ' + symbol if arch == 'x86_64' else '', None))
                self.assertEqual(len(errors), 1)
                self.assertIn('x86_64: unneeded DiskSpace API', errors[0])

    def test_freeze_uses_source_exclusion_and_refuses_stock_cpython(self):
        builder_path = SCRIPTS / 'build_mas_python.sh'
        self.assertTrue(builder_path.is_file(), 'missing private CPython builder')
        builder = builder_path.read_text()
        self.assertIn('ac_cv_func_statvfs=no ac_cv_func_fstatvfs=no', builder)
        self.assertIn('shasum -a 256 --check', builder)
        freeze = (SCRIPTS / 'freeze_helper.sh').read_text()
        guard = freeze.index('Freeze requires CPython without DiskSpace APIs')
        self.assertLess(guard, freeze.index('$PYI \\\n'))
        self.assertIn("('statvfs', 'fstatvfs')", freeze[:guard])
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertIn('bash apps/macos/Scripts/build_mas_python.sh "$prefix"', workflow)
        self.assertNotIn('export RS_FREEZE_PYTHON="$(command -v python)"', workflow)

    def test_archive_privacy_block_runs_scanner_and_stops_on_undeclared_api(self):
        source = (SCRIPTS / 'archive_mas.sh').read_text()
        start = source.index('python3 "$ROOT/Scripts/macos_privacy_gate.py"')
        end = source.index('# ITMS-90546', start)
        # Execute the actual archive commands against a built-bundle fixture;
        # no xcodebuild, signing, provisioning or export is performed.
        commands = 'set -eu\n' + source[start:end] + '\necho ARCHIVE_CONTINUED\n'
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app = base / 'Example.app'
            resources = app / 'Contents/Resources'
            resources.mkdir(parents=True)
            shutil.copyfile(ROOT / 'apps/macos/Resources/PrivacyInfo.xcprivacy', resources / 'PrivacyInfo.xcprivacy')
            binary = app / 'Contents/MacOS/Example'
            binary.parent.mkdir()
            binary.write_bytes(bytes.fromhex('cffaedfe') + b'fixture')
            tools = base / 'bin'
            tools.mkdir()
            xcrun = tools / 'xcrun'
            xcrun.write_text('#!/bin/sh\necho scanned >> "$SCAN_MARKER"\nprintf "%s\\n" "$IMPORTS"\n')
            xcrun.chmod(0o755)
            marker = base / 'scans'
            env = dict(os.environ, ROOT=str(ROOT / 'apps/macos'), APP_IN_ARCHIVE=str(app),
                       SCAN_MARKER=str(marker), PATH=str(tools) + os.pathsep + os.environ['PATH'])
            for imports, expected in (('_statvfs\n_fstatvfs', 1), ('_mach_absolute_time', 0)):
                with self.subTest(imports=imports):
                    result = subprocess.run(['bash', '-c', commands], env=dict(env, IMPORTS=imports),
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                    self.assertEqual('ARCHIVE_CONTINUED' in result.stdout, expected == 0)
                    self.assertTrue(marker.is_file(), 'archive never invoked the symbol scanner')
                    if expected:
                        self.assertIn('"DiskSpace"', result.stdout)

    def test_clipboard_waits_once_for_copy_without_increasing_any_wait(self):
        source = (ROOT / 'apps/ios/Tests/ObserveRecoveryUITests/RecoveryClipboardUITests.swift').read_text()
        self.assertEqual(source.count('waitForExistence('), 2)
        self.assertEqual(re.findall(r'timeout:\s*(\d+)', source), ['15', '15', '15'])
        self.assertNotRegex(source, r'copy\.waitForExistence|sleep\(|Task\.sleep|Thread\.sleep')
        self.assertLess(source.index('waitForExistence(timeout: 15)'), source.index('copy.tap()'))
