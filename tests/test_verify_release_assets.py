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
    def test_rc_and_final_tags(self) -> None:
        self.assertEqual(VERIFY.pep440_to_tag("0.2.0rc11"), "v0.2.0-rc.11")
        self.assertEqual(VERIFY.pep440_to_tag("0.2.0rc12"), "v0.2.0-rc.12")
        self.assertEqual(VERIFY.pep440_to_tag("0.2.0"), "v0.2.0")


class VerifyReleaseAssetsTests(unittest.TestCase):
    def _names(self) -> tuple[str, str, str, str, str]:
        version = VERIFY.project_version(ROOT)
        tag = VERIFY.pep440_to_tag(version)
        plugin = f"runspecimen-plugin-{VERIFY.tag_to_plugin_version(tag)}.zip"
        wheel = f"runspecimen-{version}-py3-none-any.whl"
        sdist = f"runspecimen-{version}.tar.gz"
        return version, tag, wheel, sdist, plugin

    def test_matching_digests(self) -> None:
        _version, tag, wheel_name, sdist_name, plugin_name = self._names()
        wheel = b"wheel-bytes"
        sdist = b"sdist-bytes"
        plugin = b"plugin-bytes"
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / wheel_name).write_bytes(wheel)
            (directory / sdist_name).write_bytes(sdist)
            (directory / plugin_name).write_bytes(plugin)
            sums = "".join(
                f"{hashlib.sha256(body).hexdigest()}  {name}\n"
                for name, body in (
                    (wheel_name, wheel),
                    (sdist_name, sdist),
                    (plugin_name, plugin),
                )
            )
            (directory / "SHA256SUMS").write_text(sums, encoding="utf-8")
            self.assertEqual(
                VERIFY.main(
                    ["--dir", str(directory), "--repo", str(ROOT), "--tag", tag, "--require-pypi"]
                ),
                0,
            )

    def test_tampered_wheel_fails(self) -> None:
        _version, tag, wheel_name, sdist_name, plugin_name = self._names()
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            (directory / wheel_name).write_bytes(b"good")
            (directory / sdist_name).write_bytes(b"sdist")
            (directory / plugin_name).write_bytes(b"plugin")
            (directory / "SHA256SUMS").write_text(
                f"{hashlib.sha256(b'other').hexdigest()}  {wheel_name}\n"
                f"{hashlib.sha256(b'sdist').hexdigest()}  {sdist_name}\n"
                f"{hashlib.sha256(b'plugin').hexdigest()}  {plugin_name}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                VERIFY.main(["--dir", str(directory), "--repo", str(ROOT), "--tag", tag]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
