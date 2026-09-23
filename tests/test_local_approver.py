"""Approver identity must come from the OS account, not env spoofing."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runspecimen.approve import local_approver  # noqa: E402


@unittest.skipUnless(os.name == "posix" and hasattr(os, "getuid"), "POSIX uid resolution")
class LocalApproverIdentityTests(unittest.TestCase):
    def test_env_logname_user_do_not_change_recorded_name(self) -> None:
        import pwd

        real = pwd.getpwuid(os.getuid()).pw_name
        spoofed = {
            "LOGNAME": "qa_spoofed_identity",
            "USER": "qa_spoofed_identity",
            "USERNAME": "qa_spoofed_identity",
        }
        with mock.patch.dict(os.environ, spoofed, clear=False):
            # getpass.getuser() would return the spoof; local_approver must not.
            import getpass

            self.assertEqual(getpass.getuser(), "qa_spoofed_identity")
            doc = local_approver()
        self.assertEqual(doc["kind"], "local_os_user")
        self.assertEqual(doc["uid"], os.getuid())
        self.assertEqual(doc["user"], real)
        self.assertNotEqual(doc["user"], "qa_spoofed_identity")


if __name__ == "__main__":
    unittest.main()
