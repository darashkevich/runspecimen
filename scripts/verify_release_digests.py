#!/usr/bin/env python3
"""Verify SHA256SUMS against files on disk (release integrity helper)."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sums", type=Path, required=True, help="SHA256SUMS path")
    parser.add_argument("--dir", type=Path, required=True, help="directory containing artifacts")
    parser.add_argument(
        "--require-names",
        nargs="*",
        default=[],
        help="filenames that must appear in both SHA256SUMS and --dir",
    )
    args = parser.parse_args(argv)

    sums_path = args.sums.resolve()
    root = args.dir.resolve()
    if not sums_path.is_file():
        raise SystemExit(f"missing SHA256SUMS: {sums_path}")
    if not root.is_dir():
        raise SystemExit(f"missing artifact directory: {root}")

    sums = load_sums(sums_path)
    errors: list[str] = []

    for name in args.require_names:
        if name not in sums:
            errors.append(f"SHA256SUMS missing required name: {name}")
        if not (root / name).is_file():
            errors.append(f"artifact directory missing required file: {name}")

    for name, expected in sorted(sums.items()):
        path = root / name
        if name == sums_path.name:
            continue
        if not path.is_file():
            errors.append(f"listed in SHA256SUMS but missing on disk: {name}")
            continue
        got = file_digest(path)
        if got != expected:
            errors.append(f"digest mismatch for {name}: got {got}, expected {expected}")

    for path in sorted(root.iterdir()):
        if not path.is_file() or path.name == sums_path.name:
            continue
        if path.name not in sums:
            errors.append(f"on disk but missing from SHA256SUMS: {path.name}")

    if errors:
        print("verify_release_digests failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"OK: {len(sums)} digests match under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
