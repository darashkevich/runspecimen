#!/usr/bin/env python3
"""Wheel and sdist bytes must not change between two builds of one tree."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import struct
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_release_check():
    path = ROOT / "scripts" / "release_check.py"
    spec = importlib.util.spec_from_file_location("release_check_reproducibility", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RELEASE = load_release_check()


class ReleaseArchiveReproducibilityTests(unittest.TestCase):
    def test_wheel_and_sdist_digests_repeat(self) -> None:
        RELEASE.ensure_build_backend()
        env = RELEASE.offline_env()
        built: list[tuple[bytes, bytes]] = []
        for _ in range(2):
            with tempfile.TemporaryDirectory(prefix="runspecimen-archive-") as raw:
                sdist, wheel, _extracted = RELEASE.build_release_archives(Path(raw), env)
                built.append((sdist.read_bytes(), wheel.read_bytes()))

        first_sdist, first_wheel = built[0]
        second_sdist, second_wheel = built[1]
        sdist_digest = hashlib.sha256(first_sdist).hexdigest()
        wheel_digest = hashlib.sha256(first_wheel).hexdigest()
        self.assertEqual(
            sdist_digest,
            hashlib.sha256(second_sdist).hexdigest(),
            "sdist SHA-256 differed across two builds of the same tree",
        )
        self.assertEqual(
            wheel_digest,
            hashlib.sha256(second_wheel).hexdigest(),
            "wheel SHA-256 differed across two builds of the same tree",
        )
        self.assertGreater(len(first_sdist), 1000)
        self.assertGreater(len(first_wheel), 1000)
        # Same-second builds can collide if only the wrapper clock moved.
        # Require the fixed metadata clock so a timestamp-only diff still fails.
        self.assertEqual(struct.unpack_from("<I", first_sdist, 4)[0], RELEASE.ARCHIVE_MTIME)
        with tarfile.open(fileobj=io.BytesIO(first_sdist), mode="r:gz") as archive:
            members = archive.getmembers()
            self.assertTrue(members)
            for member in members:
                self.assertEqual(member.mtime, RELEASE.ARCHIVE_MTIME, member.name)
        with zipfile.ZipFile(io.BytesIO(first_wheel)) as archive:
            entries = archive.infolist()
            self.assertTrue(entries)
            for info in entries:
                self.assertEqual(info.date_time, RELEASE.ARCHIVE_ZIP_DATE, info.filename)
        print(f"reproducible sdist {sdist_digest}")
        print(f"reproducible wheel {wheel_digest}")


if __name__ == "__main__":
    unittest.main()
