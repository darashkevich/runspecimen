"""The release CLI must refuse a symbol-clean tree whose bytes changed after signing."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / "apps" / "macos" / "Scripts" / "verify_mas_runtime.py"
COMMIT = "38b8613b959a628e33486b12da25dad15652052c"


def run_gate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        capture_output=True,
        text=True,
    )


class RuntimeIdentityCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = pathlib.Path(self.id().replace(".", "_"))
        base = pathlib.Path("/tmp/rs-identity-cli")
        base.mkdir(exist_ok=True)
        self.root = base / self.directory.name
        if self.root.exists():
            subprocess.run(["rm", "-rf", str(self.root)], check=True)
        self.root.mkdir()
        (self.root / "payload.bin").write_bytes(b"before-sign")
        self.pre_sign = self.root.parent / (self.root.name + ".pre.json")
        self.post_sign = self.root.parent / (self.root.name + ".post.json")

    def tearDown(self) -> None:
        subprocess.run(["rm", "-rf", str(self.root), str(self.pre_sign), str(self.post_sign)], check=False)

    def record(self, manifest: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return run_gate(
            "record-identity",
            "--stage",
            "signed-archive",
            "--git-commit",
            COMMIT,
            "--git-dirty",
            "false",
            str(self.root),
            str(manifest),
        )

    def test_verify_without_a_manifest_fails_closed(self) -> None:
        missing = self.root.parent / "missing-identity.json"
        result = run_gate(
            "verify-identity",
            "--expect",
            str(missing),
            "--stage",
            "signed-archive",
            str(self.root),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("required identity manifest is absent", result.stderr)

    def test_a_label_is_not_a_git_commit(self) -> None:
        result = run_gate(
            "record-identity",
            "--stage",
            "signed-archive",
            "--git-commit",
            "local-build",
            "--git-dirty",
            "false",
            str(self.root),
            str(self.post_sign),
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.post_sign.exists())
        self.assertIn("not a 40-character source attestation", result.stderr)

    def test_frozen_helper_identity_does_not_satisfy_the_signed_archive(self) -> None:
        frozen = self.root.parent / (self.root.name + ".frozen.json")
        recorded = run_gate(
            "record-identity",
            "--stage",
            "frozen-helper",
            "--git-commit",
            COMMIT,
            "--git-dirty",
            "false",
            str(self.root),
            str(frozen),
        )
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        verified = run_gate(
            "verify-identity",
            "--expect",
            str(frozen),
            "--stage",
            "signed-archive",
            str(self.root),
        )
        self.assertEqual(verified.returncode, 1)
        self.assertIn("does not match required stage", verified.stderr)
        frozen.unlink(missing_ok=True)

    def test_a_second_record_does_not_replace_an_existing_identity(self) -> None:
        first = self.record(self.post_sign)
        self.assertEqual(first.returncode, 0, first.stderr)
        original = self.post_sign.read_bytes()
        (self.root / "payload.bin").write_bytes(b"second-sign")
        again = run_gate(
            "record-identity",
            "--stage",
            "signed-archive",
            "--git-commit",
            COMMIT,
            "--git-dirty",
            "true",
            "--fail-if-exists",
            str(self.root),
            str(self.post_sign),
        )
        self.assertEqual(again.returncode, 1)
        self.assertIn("will not be replaced", again.stderr)
        self.assertEqual(self.post_sign.read_bytes(), original)

    def test_a_symlink_that_leaves_the_root_is_not_recorded(self) -> None:
        outside = self.root.parent / (self.root.name + ".outside")
        outside.write_bytes(b"outside")
        self.addCleanup(outside.unlink, missing_ok=True)
        (self.root / "escape").symlink_to(outside)
        result = self.record(self.post_sign)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.post_sign.exists())
        self.assertIn("symlink escapes root", result.stderr)

    def test_signing_records_new_bytes_and_a_later_change_fails(self) -> None:
        before = self.record(self.pre_sign)
        self.assertEqual(before.returncode, 0, before.stderr)
        pre = json.loads(self.pre_sign.read_text())
        self.assertEqual(pre["git_commit"], COMMIT)
        self.assertIs(pre["git_dirty"], False)
        self.assertEqual(len(pre["artifact_sha256"]), 64)

        (self.root / "payload.bin").write_bytes(b"after-sign")
        after = self.record(self.post_sign)
        self.assertEqual(after.returncode, 0, after.stderr)
        post = json.loads(self.post_sign.read_text())
        self.assertNotEqual(pre["artifact_sha256"], post["artifact_sha256"])

        still_signed = run_gate(
            "verify-identity",
            "--expect",
            str(self.post_sign),
            "--stage",
            "signed-archive",
            str(self.root),
        )
        self.assertEqual(still_signed.returncode, 0, still_signed.stderr)
        stale = run_gate(
            "verify-identity",
            "--expect",
            str(self.pre_sign),
            "--stage",
            "signed-archive",
            str(self.root),
        )
        self.assertEqual(stale.returncode, 1)
        self.assertIn("do not match the recorded post-sign identity", stale.stderr)

        link = self.root / "alias"
        link.symlink_to("payload.bin")
        linked = self.record(self.post_sign)
        self.assertEqual(linked.returncode, 0, linked.stderr)
        link.unlink()
        link.symlink_to("missing.bin")
        retargeted = run_gate(
            "verify-identity",
            "--expect",
            str(self.post_sign),
            "--stage",
            "signed-archive",
            str(self.root),
        )
        self.assertEqual(retargeted.returncode, 1)
        self.assertIn("do not match the recorded post-sign identity", retargeted.stderr)
        link.unlink()

        (self.root / "payload.bin").write_bytes(b"tampered-after-sign")
        tampered = run_gate(
            "verify-identity",
            "--expect",
            str(self.post_sign),
            "--stage",
            "signed-archive",
            str(self.root),
        )
        self.assertEqual(tampered.returncode, 1)
        self.assertNotEqual(
            hashlib.sha256((self.root / "payload.bin").read_bytes()).hexdigest(),
            post["files"]["payload.bin"],
        )
