"""Exercise the shared shipping parser with hostile display text, on macOS."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(sys.platform=='darwin' and shutil.which('swiftc'), 'macOS CryptoKit compiler required')
class ApprovalTextTests(unittest.TestCase):
    def test_untrusted_approval_text_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            main=directory/'main.swift'
            shutil.copyfile(ROOT/'tests/fixtures/approval_text_probe.swift', main)
            subprocess.run(['swiftc',str(ROOT/'apps/macos/Sources/RunSpecimenCore/RSBA2Package.swift'),str(main),'-o',str(directory/'probe')],check=True,capture_output=True,text=True)
            subprocess.run([str(directory/'probe')],check=True,capture_output=True,text=True)
