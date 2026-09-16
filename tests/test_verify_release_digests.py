from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.verify_release_digests import main as verify_main


class VerifyReleaseDigestsTests(unittest.TestCase):
    def test_matching_sums_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b"runspecimen-release-bytes"
            (root / "artifact.bin").write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            sums = root / "SHA256SUMS"
            sums.write_text(f"{digest}  artifact.bin\n", encoding="utf-8")
            self.assertEqual(verify_main(["--sums", str(sums), "--dir", str(root), "--require-names", "artifact.bin"]), 0)

    def test_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "artifact.bin").write_bytes(b"a")
            sums = root / "SHA256SUMS"
            sums.write_text(f"{'0' * 64}  artifact.bin\n", encoding="utf-8")
            self.assertEqual(verify_main(["--sums", str(sums), "--dir", str(root)]), 1)


if __name__ == "__main__":
    unittest.main()
