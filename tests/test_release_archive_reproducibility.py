#!/usr/bin/env python3
"""Wheel and sdist bytes must not change between two builds of one tree."""

from __future__ import annotations

import base64
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
GOLDEN_PACK = ROOT / "artifacts" / "rc15-2026-10-06-isolated-evidence"
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


def _urlsafe_sha256(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii").rstrip("=")
    return f"sha256={digest}"


def _committed_digest(filename: str) -> str | None:
    sums = GOLDEN_PACK / "SHA256SUMS"
    if not sums.is_file():
        return None
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if separator and name == filename:
            return digest.strip()
    return None


def _is_wheel_meta(name: str) -> bool:
    return name.endswith(".dist-info/WHEEL") or name.endswith(".dist-info/RECORD")


def _wheel_member_names(blob: bytes) -> set[str]:
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        return {info.filename for info in archive.infolist()}


def _wheel_payload_digests(blob: bytes) -> dict[str, str]:
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
            if _is_wheel_meta(name):
                continue
            stable[name] = _sha256(archive.read(name))
    return stable


def _wheel_stable_member_digests(blob: bytes) -> dict[str, str]:
    return _wheel_payload_digests(blob)


def _parse_record(text: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        if not line:
            continue
        name, separator, rest = line.partition(",")
        if not separator:
            raise ValueError(f"malformed RECORD line: {line!r}")
        digest, size_separator, size = rest.partition(",")
        if not size_separator:
            raise ValueError(f"malformed RECORD line: {line!r}")
        rows.append((name, digest, size))
    return rows


def _record_payload_hashes(blob: bytes) -> dict[str, str]:
    """Validate RECORD hashes against zip members. Return payload RECORD hashes.

    ``WHEEL`` is excluded from the returned map because its Generator line
    (and therefore its RECORD hash) moves across setuptools versions. Payload
    hashes must still match the bytes in the zip, so a payload change cannot
    hide behind the WHEEL/RECORD exclusion.
    """
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = {info.filename for info in archive.infolist()}
        record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(record_names) != 1:
            raise AssertionError(f"expected one RECORD member, got {record_names}")
        record_name = record_names[0]
        rows = _parse_record(archive.read(record_name).decode("utf-8"))
        listed = {name for name, _digest, _size in rows}
        if listed != names:
            raise AssertionError(
                f"RECORD member set {sorted(listed)} != zip member set {sorted(names)}"
            )
        payload_hashes: dict[str, str] = {}
        for name, digest, size in rows:
            data = archive.read(name)
            if name.endswith(".dist-info/RECORD"):
                if digest != "":
                    raise AssertionError(f"RECORD hashed itself: {digest}")
                continue
            expected = _urlsafe_sha256(data)
            if digest != expected:
                raise AssertionError(f"RECORD hash for {name} does not match payload")
            if size != str(len(data)):
                raise AssertionError(f"RECORD size for {name} does not match payload")
            if not name.endswith(".dist-info/WHEEL"):
                payload_hashes[name] = digest
        wheel_names = [name for name in names if name.endswith(".dist-info/WHEEL")]
        if len(wheel_names) != 1:
            raise AssertionError(f"expected one WHEEL member, got {wheel_names}")
        return payload_hashes


def _assert_wheels_match_across_setuptools(rebuilt: bytes, packed: bytes) -> None:
    rebuilt_names = _wheel_member_names(rebuilt)
    packed_names = _wheel_member_names(packed)
    if rebuilt_names != packed_names:
        raise AssertionError(
            "wheel member set differed: "
            f"added={sorted(rebuilt_names - packed_names)} "
            f"removed={sorted(packed_names - rebuilt_names)}"
        )
    if _wheel_payload_digests(rebuilt) != _wheel_payload_digests(packed):
        raise AssertionError("rebuilt wheel payload differed from the golden wheel")
    if _record_payload_hashes(rebuilt) != _record_payload_hashes(packed):
        raise AssertionError("RECORD payload hashes differed from the golden wheel")


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            info = zipfile.ZipInfo(name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            archive.writestr(info, data)
    return buffer.getvalue()


def _record_text(members: dict[str, bytes], record_name: str, *, lie: dict[str, str] | None = None) -> bytes:
    lines = []
    for name, data in members.items():
        digest = _urlsafe_sha256(data)
        if lie and name in lie:
            digest = lie[name]
        lines.append(f"{name},{digest},{len(data)}")
    lines.append(f"{record_name},,")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _fixture_wheel(*, generator: str = "setuptools (84.0.0)", extra: dict[str, bytes] | None = None,
                   payload: bytes = b"hello\n", drop_record: bool = False,
                   lie: dict[str, str] | None = None) -> bytes:
    dist = "pkg-1.0.dist-info"
    wheel = (
        "Wheel-Version: 1.0\n"
        f"Generator: {generator}\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    ).encode("utf-8")
    members: dict[str, bytes] = {
        "pkg/__init__.py": payload,
        f"{dist}/WHEEL": wheel,
        f"{dist}/METADATA": b"Name: pkg\nVersion: 1.0\n",
    }
    if extra:
        members.update(extra)
    record_name = f"{dist}/RECORD"
    if not drop_record:
        members[record_name] = _record_text(
            {name: data for name, data in members.items()},
            record_name,
            lie=lie,
        )
    return _zip_bytes(members)


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
            f"rebuilt sdist SHA-256 must match {GOLDEN_PACK}/SHA256SUMS",
        )
        packed_sdist = GOLDEN_PACK / SDIST_NAME
        if packed_sdist.is_file():
            self.assertEqual(_sha256(packed_sdist.read_bytes()), committed_sdist)
        packed_wheel = GOLDEN_PACK / WHEEL_NAME
        if packed_wheel.is_file():
            _assert_wheels_match_across_setuptools(first_wheel, packed_wheel.read_bytes())
        print(f"reproducible sdist {sdist_digest}")
        print(f"reproducible wheel {wheel_digest}")

    def test_wheel_member_set_and_record_hashes_close_the_exclusion_gap(self) -> None:
        golden = _fixture_wheel(generator="setuptools (84.0.0)")
        rebuilt = _fixture_wheel(generator="setuptools (82.0.1)")
        _assert_wheels_match_across_setuptools(rebuilt, golden)
        self.assertNotEqual(_sha256(rebuilt), _sha256(golden))

        with self.assertRaises(AssertionError):
            _assert_wheels_match_across_setuptools(
                _fixture_wheel(extra={"pkg/extra.py": b"new\n"}),
                golden,
            )
        with self.assertRaises(AssertionError):
            _assert_wheels_match_across_setuptools(
                _fixture_wheel(payload=b"changed\n"),
                golden,
            )
        with self.assertRaises(AssertionError):
            _assert_wheels_match_across_setuptools(
                _fixture_wheel(drop_record=True),
                golden,
            )
        with self.assertRaises(AssertionError):
            _record_payload_hashes(
                _fixture_wheel(lie={"pkg/__init__.py": "sha256=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"})
            )


if __name__ == "__main__":
    unittest.main()
