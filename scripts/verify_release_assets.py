#!/usr/bin/env python3
"""Verify GitHub/PyPI release bytes: tag, PEP 440 version, and SHA-256 digests.

This is checksum integrity, not SLSA provenance. `gh attestation verify`
returning HTTP 404 means the candidate is checksum-only.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path


def pep440_to_tag(version: str) -> str:
    return "v" + re.sub(r"(a|b|rc)(\d+)$", r"-\1.\2", version)


def tag_to_plugin_version(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def load_sums(path: Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(None, 1)
        sums[name.strip()] = digest.strip().lower()
    return sums


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_version(repo: Path) -> str:
    text = (repo / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if match is None:
        raise SystemExit(f"could not parse project version from {repo / 'pyproject.toml'}")
    return match.group(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sums", type=Path, help="SHA256SUMS path (default: --dir/SHA256SUMS)")
    parser.add_argument("--dir", type=Path, required=True, help="directory containing artifacts")
    parser.add_argument("--repo", type=Path, default=Path("."), help="repository root with pyproject.toml")
    parser.add_argument(
        "--tag",
        default=os.environ.get("RELEASE_TAG", ""),
        help="release tag (default: RELEASE_TAG env)",
    )
    parser.add_argument(
        "--require-pypi",
        action="store_true",
        help="require wheel + sdist whose names match pyproject version",
    )
    args = parser.parse_args(argv)

    root = args.dir.resolve()
    repo = args.repo.resolve()
    sums_path = (args.sums or (root / "SHA256SUMS")).resolve()
    if not sums_path.is_file():
        raise SystemExit(f"missing SHA256SUMS: {sums_path}")
    if not root.is_dir():
        raise SystemExit(f"missing artifact directory: {root}")

    version = project_version(repo)
    expected_tag = pep440_to_tag(version)
    release_tag = args.tag.strip()
    if release_tag and release_tag != expected_tag:
        raise SystemExit(
            f"release tag {release_tag!r} does not match package version {version!r}; "
            f"expected {expected_tag!r}"
        )
    plugin_version = tag_to_plugin_version(expected_tag)
    expected_wheel = f"runspecimen-{version}-py3-none-any.whl"
    expected_sdist = f"runspecimen-{version}.tar.gz"
    expected_plugin = f"runspecimen-plugin-{plugin_version}.zip"

    sums = load_sums(sums_path)
    errors: list[str] = []
    required = [expected_wheel, expected_sdist, expected_plugin]
    for name in required:
        if name not in sums:
            errors.append(f"SHA256SUMS missing required name: {name}")
        if not (root / name).is_file():
            errors.append(f"artifact directory missing required file: {name}")

    ignore = {sums_path.name, "release-report.json"}
    for name, expected in sorted(sums.items()):
        if name in ignore:
            continue
        path = root / name
        if not path.is_file():
            errors.append(f"listed in SHA256SUMS but missing on disk: {name}")
            continue
        got = file_digest(path)
        if got != expected:
            errors.append(f"digest mismatch for {name}: got {got}, expected {expected}")

    for path in sorted(root.iterdir()):
        if not path.is_file() or path.name in ignore:
            continue
        if path.name not in sums:
            errors.append(f"on disk but missing from SHA256SUMS: {path.name}")

    if args.require_pypi:
        for name in (expected_wheel, expected_sdist):
            if not (root / name).is_file():
                errors.append(f"PyPI payload missing: {name}")

    if errors:
        print("verify_release_assets failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"OK: version={version} tag={expected_tag} digests={len(sums)} under {root}")
    print("PROVENANCE: checksum-only (no SLSA attestations required for this candidate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
