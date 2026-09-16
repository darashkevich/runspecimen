from __future__ import annotations

import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "plugins" / "runspecimen" / "assets"


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path} is not a PNG")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


class PluginBrandAssetTests(unittest.TestCase):
    def test_required_rasters_are_opaque_squares(self) -> None:
        expected = {
            "runspecimen-logo.png": (256, 256),
            "logo.png": (512, 512),
            "composer-icon.png": (128, 128),
        }
        for name, size in expected.items():
            path = ASSETS / name
            self.assertTrue(path.is_file(), name)
            self.assertEqual(png_size(path), size, name)
            # Store masters are flattened RGB (no tRNS / alpha chunk expected for brand pack).
            data = path.read_bytes()
            self.assertNotIn(b"tRNS", data, name)

    def test_codex_manifest_points_at_brand_assets(self) -> None:
        manifest = json.loads((ROOT / "plugins/runspecimen/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
        interface = manifest["interface"]
        self.assertEqual(interface["logo"], "assets/logo.png")
        self.assertEqual(interface["composerIcon"], "assets/composer-icon.png")
        self.assertTrue((ASSETS / "logo.png").is_file())
        self.assertTrue((ASSETS / "composer-icon.png").is_file())

    def test_cursor_manifest_logo(self) -> None:
        manifest = json.loads((ROOT / "plugins/runspecimen/.cursor-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["logo"], "assets/runspecimen-logo.png")
        self.assertTrue((ASSETS / "runspecimen-logo.png").is_file())


if __name__ == "__main__":
    unittest.main()
