#!/usr/bin/env bash
# Verify marketplace macOS icon assets: iconset, AppIcon.appiconset catalog,
# and a warning-free actool compile when Xcode is present.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RES="$ROOT/Resources"
CATALOG="$ROOT/Assets.xcassets/AppIcon.appiconset"

test -f "$RES/AppIcon.icns"
test -f "$RES/AppIcon-1024.png"
test -d "$RES/AppIcon.iconset"
test -d "$CATALOG"
test -f "$CATALOG/Contents.json"

python3 - "$RES" "$CATALOG" <<'PY'
import json, re, struct, sys
from pathlib import Path

res = Path(sys.argv[1])
catalog = Path(sys.argv[2])
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
NAME_RE = re.compile(r"^icon_\d+x\d+(@2x)?\.png$")


def png_info(path: Path):
    with open(path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n", path
        length = struct.unpack(">I", f.read(4))[0]
        assert f.read(4) == b"IHDR"
        data = f.read(length)
        w, h = struct.unpack(">II", data[:8])
        color = data[9]  # 2 = RGB, 6 = RGBA
        return w, h, color


def check_png_set(root: Path, label: str) -> None:
    for name, size in expected.items():
        path = root / name
        assert path.is_file(), f"{label} missing {name}"
        w, h, color = png_info(path)
        assert (w, h) == size, f"{label} {name}: {w}x{h} != {size[0]}x{size[1]}"
        assert color == 2, f"{label} {name}: expected opaque RGB, colorType={color}"


check_png_set(res / "AppIcon.iconset", "iconset")
w, h, color = png_info(res / "AppIcon-1024.png")
assert (w, h, color) == (1024, 1024, 2)
assert (res / "AppIcon.icns").stat().st_size > 1000
plist = (res / "Info.plist").read_text()
assert "CFBundleIconFile" in plist and "AppIcon" in plist

contents = json.loads((catalog / "Contents.json").read_text())
seen = []
for image in contents["images"]:
    filename = image.get("filename")
    assert filename, f"catalog entry missing filename: {image}"
    assert NAME_RE.match(filename), (
        f"catalog filename must be icon_<size>.png or icon_<size>@2x.png, not {filename!r}"
    )
    size_w, size_h = (int(part) for part in image["size"].split("x"))
    scale = int(image["scale"].rstrip("x"))
    expected_px = (size_w * scale, size_h * scale)
    assert expected[filename] == expected_px, (
        f"Contents.json {filename} slot {image['size']}@{image['scale']} "
        f"expects {expected_px}, table has {expected[filename]}"
    )
    seen.append(filename)

assert sorted(seen) == sorted(expected), (sorted(seen), sorted(expected))
check_png_set(catalog, "appiconset")

strays = sorted(
    path.name
    for path in catalog.iterdir()
    if path.is_file() and path.name not in {"Contents.json", *expected}
)
assert not strays, f"unexpected AppIcon.appiconset files: {strays}"
print("Icon asset QA OK (iconset + AppIcon.appiconset)")
PY

if command -v xcrun >/dev/null 2>&1 && xcrun --find actool >/dev/null 2>&1; then
  ACTOOL_OUT="$(mktemp -d -t rs-actool)"
  trap 'rm -rf "$ACTOOL_OUT"' EXIT
  set +e
  ACTOOL_LOG="$(
    xcrun actool \
      --output-format human-readable-text \
      --notices --warnings --errors \
      --output-partial-info-plist "$ACTOOL_OUT/partial.plist" \
      --app-icon AppIcon \
      --enable-on-demand-resources NO \
      --development-region en \
      --target-device mac \
      --minimum-deployment-target 14.0 \
      --platform macosx \
      --compile "$ACTOOL_OUT" \
      "$ROOT/Assets.xcassets" 2>&1
  )"
  ACTOOL_RC=$?
  set -e
  printf '%s\n' "$ACTOOL_LOG"
  if [[ "$ACTOOL_RC" -ne 0 ]]; then
    echo "ERROR: actool failed (rc=$ACTOOL_RC)" >&2
    exit 1
  fi
  if printf '%s\n' "$ACTOOL_LOG" | grep -Ei ': warning:|: error:| warning: | error: '; then
    echo "ERROR: actool emitted warnings or errors" >&2
    exit 1
  fi
  test -f "$ACTOOL_OUT/Assets.car" || {
    echo "ERROR: actool did not produce Assets.car" >&2
    exit 1
  }
  echo "OK: actool compiled AppIcon with no warnings"
else
  echo "NOTE: actool not available; skipped warning-free catalog compile"
fi

echo "OK: AppIcon assets verified"
