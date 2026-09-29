"""Fail closed on the binary references Apple rejected in 0.1.3 (8).

Apple's 2.5.1 note was specific: Python 3.9 ``_hashlib`` and ``_ssl`` linked
Apple's private ``TrustEvaluationAgent.framework``, and the ``_lzma`` extension
referenced the disallowed ``lzma_code`` / ``lzma_end`` / stream / properties /
raw / decoder / encoder symbols. The scanner checks every architecture slice's
Mach-O dependencies and both defined and undefined symbols.

The CPython module-table string ``_lzma`` between ``_lsprof`` and
``_markupbase`` is the standard library's name. It is not one of those
symbols, it is not a ``liblzma`` load command, and the approved 0.1.4 (9)
binary contains the same string. Do not treat that string as a rejection and
do not strip it out of CPython.

A clean symbol scan is acceptance only when the caller also passes the
SHA-256 of every Mach-O, so a mutable build directory cannot stand in for a
recorded artifact.
"""
from __future__ import annotations

import hashlib
import json
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


def inspect_slices(arches: list[str], dependencies_for, symbols_for) -> list[str]:
    """Visit every slice. A tool failure is a violation, not a skipped slice."""
    if not arches:
        return ["no architecture slice inspected"]
    errors = []
    seen = []
    for arch in arches:
        if arch in seen:
            continue
        seen.append(arch)
        dependencies, dependency_error = dependencies_for(arch)
        if dependency_error:
            errors.append(dependency_error)
            continue
        symbols, symbol_error = symbols_for(arch)
        if symbol_error:
            errors.append(symbol_error)
            continue
        for issue in violations(dependencies, symbols):
            errors.append(f"{arch}: {issue}")
    return errors


def identity_errors(actual: dict[str, str], expected: dict[str, str]) -> list[str]:
    if actual != expected:
        return ["Mach-O identity does not match the recorded exact-source artifact"]
    return []


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _architecture_slices(path: pathlib.Path) -> tuple[list[str], str | None]:
    lipo = subprocess.run(
        ["/usr/bin/lipo", "-archs", str(path)],
        capture_output=True,
        text=True,
    )
    if lipo.returncode == 0:
        arches = lipo.stdout.split()
        if arches:
            return arches, None
    kind = subprocess.run(["/usr/bin/file", "-b", str(path)], capture_output=True, text=True)
    if kind.returncode != 0:
        return [], f"cannot identify Mach-O slices: {kind.stderr.strip()}"
    text = kind.stdout
    found = [arch for arch in ("arm64e", "arm64", "x86_64h", "x86_64") if arch in text.split()]
    if found:
        return found, None
    if "Mach-O" in text:
        return [], f"Mach-O has no recognized architecture: {text.strip()}"
    return [], None


def _slice_text(tool: str, path: pathlib.Path, arch: str) -> tuple[str, str | None]:
    if tool == "otool":
        args = ["/usr/bin/otool", "-arch", arch, "-L", str(path)]
    else:
        args = ["/usr/bin/nm", "-arch", arch, str(path)]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout, None
    detail = (result.stderr or result.stdout).strip()
    if tool == "nm" and ("no name list" in detail.lower() or "no symbols" in detail.lower()):
        return "", None
    return "", f"{tool} failed for {arch}: {detail or 'no output'}"


def scan(
    root: pathlib.Path,
    *,
    expected_identities: dict[str, str] | None = None,
    report_path: pathlib.Path | None = None,
    source_id: str = "",
) -> int:
    if not root.is_dir():
        raise SystemExit(f"Missing runtime/app directory: {root}")
    checked = set()
    failures = []
    identities: dict[str, str] = {}
    slices: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root.resolve()):
            failures.append(f"Bundle symlink escapes root: {path}")
            continue
        if resolved in checked:
            continue
        kind = subprocess.run(["/usr/bin/file", "-b", str(path)], capture_output=True, text=True)
        if kind.returncode != 0:
            failures.append(f"file(1) failed: {path}")
            continue
        if "Mach-O" not in kind.stdout:
            continue
        checked.add(resolved)
        relative = path.relative_to(root).as_posix()
        identities[relative] = _sha256(path)
        arches, arch_error = _architecture_slices(path)
        slices[relative] = arches
        if arch_error:
            failures.append(f"{relative}: {arch_error}")
            continue
        for issue in inspect_slices(
            arches,
            lambda arch, binary=path: _slice_text("otool", binary, arch),
            lambda arch, binary=path: _slice_text("nm", binary, arch),
        ):
            failures.append(f"{relative}: {issue}")
    if not checked:
        failures.append("No Mach-O files inspected")
    if expected_identities is not None:
        failures.extend(identity_errors(identities, expected_identities))
    report = {
        "source_id": source_id,
        "root": str(root),
        "mach_o_files": len(checked),
        "files": [
            {"path": name, "sha256": identities[name], "slices": slices.get(name, [])}
            for name in sorted(identities)
        ],
        "violations": failures,
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for issue in failures:
        print(f"FAIL: {issue}", file=sys.stderr)
    print(f"MAS runtime scan: {len(checked)} Mach-O files; {len(failures)} violations")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: verify_mas_runtime.py APP [report.json] [source-id]")
    raise SystemExit(
        scan(
            pathlib.Path(sys.argv[1]),
            report_path=pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None,
            source_id=sys.argv[3] if len(sys.argv) > 3 else "",
        )
    )
