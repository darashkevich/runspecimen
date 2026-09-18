#!/usr/bin/env python3
"""Checksum contract helper for GitHub → PyPI identical bytes."""

from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_verify_module():
    path = ROOT / "scripts" / "verify_release_assets.py"
    spec = importlib.util.spec_from_file_location("verify_release_assets", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VERIFY = load_verify_module()


class Pep440TagTests(unittest.TestCase):
    def test_rc11_tag(self) -> None:
        self.assertEqual(VERIFY.pep440_to_tag("0.2.0rc11"), "v0.2.0-rc.11")


class VerifyReleaseAssetsTests(unittest.TestCase):
    def test_matching_digests(self) -> None:
        wheel = b"wheel-bytes"
        sdist = b"sdist-bytes"
        plugin = b"plugin-bytes"
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "runspecimen-0.2.0rc11-py3-none-any.whl").write_bytes(wheel)
            (directory / "runspecimen-0.2.0rc11.tar.gz").write_bytes(sdist)
            (directory / "runspecimen-plugin-0.2.0-rc.11.zip").write_bytes(plugin)
            sums = "".join(
                f"{hashlib.sha256(body).hexdigest()}  {name}\n"
                for name, body in (
                    ("runspecimen-0.2.0rc11-py3-none-any.whl", wheel),
                    ("runspecimen-0.2.0rc11.tar.gz", sdist),
                    ("runspecimen-plugin-0.2.0-rc.11.zip", plugin),
                )
            )
            (directory / "SHA256SUMS").write_text(sums, encoding="utf-8")
            self.assertEqual(
                VERIFY.main(
                    ["--dir", str(directory), "--repo", str(ROOT), "--tag", "v0.2.0-rc.11", "--require-pypi"]
                ),
                0,
            )

    def test_tampered_wheel_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / "runspecimen-0.2.0rc11-py3-none-any.whl").write_bytes(b"good")
            (directory / "runspecimen-0.2.0rc11.tar.gz").write_bytes(b"sdist")
            (directory / "runspecimen-plugin-0.2.0-rc.11.zip").write_bytes(b"plugin")
            (directory / "SHA256SUMS").write_text(
                f"{hashlib.sha256(b'other').hexdigest()}  runspecimen-0.2.0rc11-py3-none-any.whl\n"
                f"{hashlib.sha256(b'sdist').hexdigest()}  runspecimen-0.2.0rc11.tar.gz\n"
                f"{hashlib.sha256(b'plugin').hexdigest()}  runspecimen-plugin-0.2.0-rc.11.zip\n",
                encoding="utf-8",
            )
            self.assertEqual(
                VERIFY.main(["--dir", str(directory), "--repo", str(ROOT), "--tag", "v0.2.0-rc.11"]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
