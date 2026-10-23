"""Validate the release owner's exact Mac privacy declaration in a built bundle."""
import argparse
import json
import plistlib
from pathlib import Path

EXPECTED = {
    "NSPrivacyAccessedAPICategoryUserDefaults": ["CA92.1"],
    "NSPrivacyAccessedAPICategorySystemBootTime": ["35F9.1"],
    "NSPrivacyAccessedAPICategoryFileTimestamp": ["3B52.1", "C617.1"],
}

def audit(app):
    path = app / "Contents/Resources/PrivacyInfo.xcprivacy"
    if not path.is_file():
        raise ValueError("Mac Release privacy manifest missing")
    entries = plistlib.loads(path.read_bytes()).get("NSPrivacyAccessedAPITypes", [])
    actual = {}
    for entry in entries:
        category = entry["NSPrivacyAccessedAPIType"]
        if category in actual:
            raise ValueError("Duplicate Mac privacy category: " + category)
        actual[category] = sorted(entry["NSPrivacyAccessedAPITypeReasons"])
    if actual != EXPECTED:
        raise ValueError("Mac Release privacy categories/reasons differ from release decision: " + repr(actual))
    return actual

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    print(json.dumps(audit(parser.parse_args().app), sort_keys=True))
