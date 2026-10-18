"""Reject Store preparation metadata that disagrees with the packaged app identity."""
from pathlib import Path
import plistlib
import re
import sys

FILES = (
    "apps/macos/Config/Info-mas.plist",
    "apps/macos/Resources/Info.plist",
    "apps/macos/project.yml",
    "apps/macos/RunSpecimen.xcodeproj/project.pbxproj",
    "apps/macos/asc-kit/metadata.md",
    "apps/macos/APP_STORE.md",
)

def check(root):
    root = Path(root)
    identity = plistlib.loads((root / FILES[0]).read_bytes())
    version = str(identity["CFBundleShortVersionString"])
    build = str(identity["CFBundleVersion"])
    errors = []
    other = plistlib.loads((root / FILES[1]).read_bytes())
    if (other["CFBundleShortVersionString"], str(other["CFBundleVersion"])) != (version, build):
        errors.append(FILES[1])
    for name in FILES[2:4]:
        text = (root / name).read_text()
        for setting, expected in [("MARKETING_VERSION", version), ("CURRENT_PROJECT_VERSION", build)]:
            values = re.findall(r"\b" + setting + r"\s*[:=]\s*[\"]?([0-9.]+)", text)
            if not values or any(value != expected for value in values):
                errors.append(name + ": " + setting)
    for name in FILES[4:]:
        text = (root / name).read_text()
        short = re.search(r"^\| Short version \| `?([0-9.]+)`? \|", text, re.M)
        number = re.search(r"^\| Build \| `?([0-9]+)`?", text, re.M)
        if not short or short[1] != version or not number or number[1] != build:
            errors.append(name)
    if errors:
        raise ValueError("Mac release identity mismatch: " + ", ".join(errors))
    return version, build

if __name__ == "__main__":
    try:
        version, build = check(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
        print("Mac release identity consistent: " + version + " (" + build + ")")
    except ValueError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
