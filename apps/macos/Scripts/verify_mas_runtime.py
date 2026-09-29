"""Fail closed on the binary references Apple rejected in 0.1.3 (8).

Apple's 2.5.1 note was specific: Python 3.9 ``_hashlib`` and ``_ssl`` linked
Apple's private ``TrustEvaluationAgent.framework``, and the ``_lzma`` extension
referenced the disallowed ``lzma_code`` / ``lzma_end`` / stream / properties /
raw / decoder / encoder symbols. The scanner checks Mach-O dependencies and
both defined and undefined symbols.

The CPython module-table string ``_lzma`` between ``_lsprof`` and
``_markupbase`` is the standard library's name. It is not one of those
symbols, it is not a ``liblzma`` load command, and the approved 0.1.4 (9)
binary contains the same string. Do not treat that string as a rejection and
do not strip it out of CPython.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys


def violations(dependencies: str, symbols: str) -> list[str]:
    errors = []
    for line in dependencies.splitlines()[1:]:
        dependency = line.strip().split(" (", 1)[0]
        if "/PrivateFrameworks/" in dependency or "TrustEvaluationAgent" in dependency:
            errors.append(f"private framework: {dependency}")
        if dependency.startswith(("/opt/", "/usr/local/", "/Library/", "/Applications/", "/Users/")):
            errors.append(f"non-system absolute dependency: {dependency}")
        if "liblzma" in dependency.lower():
            errors.append(f"unneeded lzma dependency: {dependency}")
    for line in symbols.splitlines():
        if "_lzma_" in line or "TrustEvaluationAgent" in line:
            errors.append(f"rejected API reference: {line.strip()}")
    return errors


def scan(root: pathlib.Path) -> int:
    if not root.is_dir():
        raise SystemExit(f"Missing runtime/app directory: {root}")
    checked = set()
    failures = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root.resolve()):
            failures.append(f"Bundle symlink escapes root: {path}")
            continue
        if resolved in checked:
            continue
        kind = subprocess.check_output(["/usr/bin/file", "-b", str(path)], text=True)
        if "Mach-O" not in kind:
            continue
        checked.add(resolved)
        deps = subprocess.check_output(["/usr/bin/otool", "-L", str(path)], text=True)
        symbols = subprocess.check_output(["/usr/bin/nm", str(path)], text=True, stderr=subprocess.STDOUT)
        for issue in violations(deps, symbols):
            failures.append(f"{path.relative_to(root)}: {issue}")
    if not checked:
        failures.append("No Mach-O files inspected")
    for issue in failures:
        print(f"FAIL: {issue}", file=sys.stderr)
    print(f"MAS runtime scan: {len(checked)} Mach-O files; {len(failures)} violations")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(scan(pathlib.Path(sys.argv[1])))
