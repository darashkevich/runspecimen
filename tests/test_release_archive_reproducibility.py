#!/usr/bin/env python3
"""Wheel and sdist bytes must not change between two builds of one tree."""

from __future__ import annotations

import gzip
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
GOLDEN_PACK = ROOT / "artifacts" / "rc15-2026-10-05-golden-master"
SDIST_NAME = "runspecimen-0.2.0rc15.tar.gz"
WHEEL_NAME = "runspecimen-0.2.0rc15-py3-none-any.whl"


def load_release_check():
    path = ROOT / "scripts" / "release_check.py"
    spec = importlib.util.spec_from_file_location("release_check_reproducibility", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RELEASE = load_release_check()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _committed_digest(filename: str) -> str | None:
    sums = GOLDEN_PACK / "SHA256SUMS"
    if not sums.is_file():
        return None
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if separator and name == filename:
            return digest.strip()
    return None


def _wheel_stable_member_digests(blob: bytes) -> dict[str, str]:
    """Per-file digests that must not depend on the setuptools Generator line.

    CI installs the newest setuptools for each Python. 3.9 currently gets
    82.0.1 and 3.10+ get 84.0.0, so ``WHEEL`` / ``RECORD`` bytes move while
    the package payload stays the same. OPEN-SDIST still requires the sdist
    archive itself to be byte-identical across those interpreters.
    """
    stable: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for info in archive.infolist():
            name = info.filename
            if name.endswith(".dist-info/WHEEL") or name.endswith(".dist-info/RECORD"):
                continue
            stable[name] = _sha256(archive.read(name))
    return stable


class ReleaseArchiveReproducibilityTests(unittest.TestCase):
    def test_normalize_sdist_strips_builder_identity(self) -> None:
        buffer = io.BytesIO()
        with gzip.GzipFile(filename="moving.tar", mode="wb", fileobj=buffer, mtime=123, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                payload = b"hello-sdist\n"
                late = tarfile.TarInfo("runspecimen-0.2.0rc15/z.txt")
                late.mtime = 99
                late.uid = 1000
                late.gid = 1000
                late.uname = "ubuntu"
                late.gname = "ubuntu"
                late.size = len(payload)
                archive.addfile(late, io.BytesIO(payload))
                early = tarfile.TarInfo("runspecimen-0.2.0rc15/a.txt")
                early.mtime = 88
                early.uid = 501
                early.gid = 20
                early.uname = "builder"
                early.gname = "staff"
                early.size = len(payload)
                archive.addfile(early, io.BytesIO(payload))
        with tempfile.TemporaryDirectory(prefix="runspecimen-sdist-norm-") as raw:
            path = Path(raw) / "runspecimen-0.2.0rc15.tar.gz"
            path.write_bytes(buffer.getvalue())
            RELEASE.normalize_sdist_timestamps(path)
            rewritten = path.read_bytes()
        self.assertEqual(struct.unpack_from("<I", rewritten, 4)[0], RELEASE.GZIP_MTIME)
        self.assertEqual(rewritten[3] & 0x08, 0)
        with tarfile.open(fileobj=io.BytesIO(rewritten), mode="r:gz") as archive:
            members = archive.getmembers()
            self.assertEqual([member.name for member in members], [
                "runspecimen-0.2.0rc15/a.txt",
                "runspecimen-0.2.0rc15/z.txt",
            ])
            for member in members:
                self.assertEqual(member.mtime, RELEASE.ARCHIVE_MTIME, member.name)
                self.assertEqual(member.uid, 0, member.name)
                self.assertEqual(member.gid, 0, member.name)
                self.assertEqual(member.uname, "", member.name)
                self.assertEqual(member.gname, "", member.name)
                self.assertEqual(member.mode, 0o644, member.name)
                extracted = archive.extractfile(member)
                assert extracted is not None
                self.assertEqual(extracted.read(), b"hello-sdist\n")

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
        sdist_digest = _sha256(first_sdist)
        wheel_digest = _sha256(first_wheel)
        self.assertEqual(
            sdist_digest,
            _sha256(second_sdist),
            "sdist SHA-256 differed across two builds of the same tree",
        )
        self.assertEqual(
            wheel_digest,
            _sha256(second_wheel),
            "wheel SHA-256 differed across two builds of the same tree",
        )
        self.assertGreater(len(first_sdist), 1000)
        self.assertGreater(len(first_wheel), 1000)
        # Same-second builds can collide if only the wrapper clock moved.
        # Require the fixed metadata clock so a timestamp-only diff still fails.
        self.assertEqual(struct.unpack_from("<I", first_sdist, 4)[0], RELEASE.GZIP_MTIME)
        self.assertEqual(first_sdist[3] & 0x08, 0)
        with tarfile.open(fileobj=io.BytesIO(first_sdist), mode="r:gz") as archive:
            members = archive.getmembers()
            self.assertTrue(members)
            names = [member.name for member in members]
            self.assertEqual(names, sorted(names))
            for member in members:
                self.assertEqual(member.mtime, RELEASE.ARCHIVE_MTIME, member.name)
                self.assertEqual(member.uid, 0, member.name)
                self.assertEqual(member.gid, 0, member.name)
                self.assertEqual(member.uname, "", member.name)
                self.assertEqual(member.gname, "", member.name)
        with zipfile.ZipFile(io.BytesIO(first_wheel)) as archive:
            entries = archive.infolist()
            self.assertTrue(entries)
            for info in entries:
                self.assertEqual(info.date_time, RELEASE.ARCHIVE_ZIP_DATE, info.filename)
        committed_sdist = _committed_digest(SDIST_NAME)
        if committed_sdist is None:
            self.skipTest("golden-master SHA256SUMS is not packed into the sdist")
        self.assertEqual(
            sdist_digest,
            committed_sdist,
            "rebuilt sdist SHA-256 must match artifacts/rc15-2026-10-05-golden-master/SHA256SUMS",
        )
        packed_sdist = GOLDEN_PACK / SDIST_NAME
        if packed_sdist.is_file():
            self.assertEqual(_sha256(packed_sdist.read_bytes()), committed_sdist)
        packed_wheel = GOLDEN_PACK / WHEEL_NAME
        if packed_wheel.is_file():
            self.assertEqual(
                _wheel_stable_member_digests(first_wheel),
                _wheel_stable_member_digests(packed_wheel.read_bytes()),
                "rebuilt wheel payload differed from the golden wheel "
                "(WHEEL/RECORD Generator lines may differ across setuptools)",
            )
        print(f"reproducible sdist {sdist_digest}")
        print(f"reproducible wheel {wheel_digest}")


if __name__ == "__main__":
    unittest.main()
