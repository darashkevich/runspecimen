#!/usr/bin/env bash
# Verify marketplace macOS icon assets are present, opaque RGB, and correct sizes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RES="$ROOT/Resources"

test -f "$RES/AppIcon.icns"
test -f "$RES/AppIcon-1024.png"
test -d "$RES/AppIcon.iconset"

python3 - "$RES" <<'PY'
import struct, sys
from pathlib import Path
res = Path(sys.argv[1])
expected = {
  "icon_16x16.png": (16, 16),
  "icon_16x16@2x.png": (32, 32),
  "icon_32x32.png": (32, 32),
  "icon_32x32@2x.png": (64, 64),
  "icon_128x128.png": (128, 128),
  "icon_128x128@2x.png": (256, 256),
  "icon_256x256.png": (256, 256),
  "icon_256x256@2x.png": (512, 512),
  "icon_512x512.png": (512, 512),
  "icon_512x512@2x.png": (1024, 1024),
}

def png_info(path: Path):
    with open(path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
        length = struct.unpack(">I", f.read(4))[0]
        assert f.read(4) == b"IHDR"
        data = f.read(length)
        w, h = struct.unpack(">II", data[:8])
        color = data[9]  # 2 = RGB, 6 = RGBA
        return w, h, color

for name, size in expected.items():
    w, h, color = png_info(res / "AppIcon.iconset" / name)
    assert (w, h) == size, (name, w, h, size)
    assert color == 2, (name, "expected opaque RGB (no alpha), colorType=", color)
w, h, color = png_info(res / "AppIcon-1024.png")
assert (w, h, color) == (1024, 1024, 2)
assert (res / "AppIcon.icns").stat().st_size > 1000
plist = (res / "Info.plist").read_text()
assert "CFBundleIconFile" in plist and "AppIcon" in plist
print("Icon asset QA OK")
PY

echo "OK: AppIcon assets verified"
