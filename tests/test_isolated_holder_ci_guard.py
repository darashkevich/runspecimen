"""Guards for isolated holder CI and first-pass Swift recording.

These tests do not contact a live holder, do not install, and do not invoke
biometrics. They do not run ``swift test``.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOLDER_SCRIPT = REPO / "apps/holder/Scripts/test_holder_isolated.sh"
SMOKE_SCRIPT = REPO / "apps/macos/Scripts/smoke_macos.sh"
CI_WORKFLOW = REPO / ".github/workflows/ci.yml"


class IsolatedHolderCIGuardTests(unittest.TestCase):
    def test_holder_script_refuses_live_socket_env(self) -> None:
        env = os.environ.copy()
        env["RS_HOLDER_SOCKET"] = "/private/tmp/must-not-connect.sock"
        env["PATH"] = "/usr/bin:/bin"
        proc = subprocess.run(
            ["bash", str(HOLDER_SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
            cwd=str(REPO),
        )
        self.assertEqual(proc.returncode, 2)
        combined = proc.stdout + proc.stderr
        self.assertIn("REFUSED", combined)
        self.assertIn("RS_HOLDER_SOCKET", combined)
        self.assertNotIn("HOLDER_FIRST_PASS: running", combined)
        self.assertNotIn("swift test", combined)

    def test_holder_script_records_first_pass_only(self) -> None:
        text = HOLDER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("HOLDER_FIRST_PASS: FAIL — not retrying", text)
        self.assertIn("Does not install SMAppService", text)
        self.assertIn("does not touch /Applications", text)
        self.assertNotIn("retrying once", text)

    def test_smoke_retries_only_codesign_xattr_detritus(self) -> None:
        text = SMOKE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("FIRST_PASS: OK", text)
        self.assertIn("FIRST_PASS: FAIL (product or test assertion) — not retrying", text)
        self.assertIn(
            "resource fork|extended attributes|codesign.*not allowed|code object is not signed at path",
            text,
        )
        self.assertIn("FIRST_PASS: FAIL (codesign/xattr detritus) — retrying once after xattr clear", text)

    def test_ci_runs_holder_isolated_job_without_socket_env(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("holder-swift:", workflow)
        self.assertIn("apps/holder/Scripts/test_holder_isolated.sh", workflow)
        self.assertNotIn("RS_HOLDER_SOCKET", workflow)
