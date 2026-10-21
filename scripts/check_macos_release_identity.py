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

ACTIVE_DOCS = {
    "apps/macos/RELEASE_CHECKLIST.md": r"next candidate is \*\*([0-9.]+) \(([0-9]+)\)\*\*",
    "docs/RELEASE_CHECKLIST.md": r"current local successor label is \*\*([0-9.]+) \(([0-9]+)\)\*\*",
    "docs/SUBMISSION.md": r"next candidate is \*\*([0-9.]+) \(([0-9]+)\)\*\*",
    "apps/macos/asc-kit/STATUS.md": r"Current candidate: ([0-9.]+) \(([0-9]+)\)",
    "README.md": r"local label on this branch is \*\*([0-9.]+) \(([0-9]+)\)\*\*",
    "docs/FAQ.md": r"branch's local label is \*\*([0-9.]+) \(([0-9]+)\)\*\*",
    "docs/CANDIDATE_MANIFEST.md": r"App marketing version in the project \| \*\*([0-9.]+) \(([0-9]+)\)\*\*",
    "docs/NATIVE_FEATURE_COVERAGE.md": r"branch's local label is marketing \*\*([0-9.]+)\*\*, build \*\*([0-9]+)\*\*",
}

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
        short = re.findall(r"^\| Short version \| `?([0-9.]+)`? \|", text, re.M)
        number = re.findall(r"^\| Build \| `?([0-9]+)`?", text, re.M)
        if not short or any(value != version for value in short) or not number or any(value != build for value in number):
            errors.append(name)
    for name, pattern in ACTIVE_DOCS.items():
        matches = list(re.finditer(pattern, (root / name).read_text()))
        if not matches or any(match.groups() != (version, build) for match in matches):
            errors.append(name)
    # Inspect every version/build pair, not just the first matching sentence.
    # Old artifact identities must be explicitly labelled historical immediately
    # before the pair; an old current-candidate row cannot hide in a history section.
    for name in (*FILES[4:], *ACTIVE_DOCS):
        for line_number, line in enumerate((root / name).read_text().splitlines(), 1):
            for match in re.finditer(r"\b(\d+\.\d+\.\d+)\s*\((\d+)\)", line):
                historical = re.search(r"historical[:\s]*(?:\*\*|`)?$", line[:match.start()], re.I)
                if match.groups() != (version, build) and not historical:
                    errors.append(f"{name}:{line_number}: unlabelled stale version {match[0]}")
            for match in re.finditer(r"(?<![\w/.-])(\d+\.\d+\.\d+)(?![\w-]|\.\d)", line):
                historical = re.search(r"historical[:\s]*(?:\*\*|`)?$", line[:match.start()], re.I)
                if match[1] != version and not historical:
                    errors.append(f"{name}:{line_number}: unlabelled stale version {match[0]}")
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
