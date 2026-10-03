#!/usr/bin/env python3
"""Copy a CPython into a holder bundle and rewrite non-system library paths.

The payload interpreter is the copy under dest/bin. This script does not use
/usr/bin/python3 as that payload, does not read PYTHONPATH, and does not
install anything. It never starts ``--source``. The process that launched
this file is the intact interpreter.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

SYSTEM_PREFIXES = ("/usr/lib/", "/System/")
HOSTILE_MARKERS = ("/opt/homebrew", "/usr/local", "/Users/")
MAX_STAGED_LIBRARIES = 512
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
}


def _fail(message: str) -> None:
    print(f"REFUSING: {message}", file=sys.stderr)
    raise SystemExit(2)


def _is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) in MACHO_MAGICS
    except OSError:
        return False


def _otool(path: Path) -> list[str]:
    out = subprocess.check_output(["/usr/bin/otool", "-L", str(path)], text=True)
    deps: list[str] = []
    for line in out.splitlines()[1:]:
        dep = line.strip().split(" (", 1)[0]
        if dep:
            deps.append(dep)
    return deps


def _ignore_stdlib(directory: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", "site-packages"}
    return {
        name
        for name in names
        if name in ignored or name.endswith((".pyc", ".a")) or name.startswith("config-")
    }


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _inode(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino


def assign_staged_name(canonical: Path, used: dict[str, Path]) -> str:
    """One stable destination name.

    A second file with the same basename gets a single short hash suffix.
    Names are never built by stacking a parent directory onto itself.
    """

    base = canonical.name
    if not base or len(base) > 120 or base.startswith("lib-lib-"):
        _fail("staged library name is not canonical")
    owner = used.get(base)
    if owner is None or owner == canonical:
        used[base] = canonical
        return base
    digest = hashlib.sha256(os.fsencode(str(canonical))).hexdigest()[:12]
    stem = canonical.stem[:48]
    suffix = canonical.suffix[:8]
    name = f"{stem}-{digest}{suffix}"
    if len(name) > 80 or name.startswith("lib-lib-"):
        _fail("staged library name collision is bounded")
    other = used.get(name)
    if other is not None and other != canonical:
        _fail("staged library name collision is bounded")
    used[name] = canonical
    return name


def plan_external_copies(
    roots: list[str],
    dependencies,
    *,
    inside_dest,
    max_nodes: int = 8,
) -> list[str]:
    """Copy each external dependency once. Cycles and self-edges stop.

    ``dependencies(node)`` returns the nodes that node links. ``inside_dest``
    is true for files that are already in the staged tree and must not be
    copied again under a longer name.
    """

    used: dict[str, Path] = {}
    staged: dict[str, str] = {}
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        if len(seen) >= max_nodes:
            _fail("runtime dependency graph exceeded the staged library bound")
        seen.add(current)
        for dep in dependencies(current):
            if dep == current or inside_dest(dep):
                continue
            if dep in staged:
                continue
            if len(staged) >= max_nodes:
                _fail("runtime dependency graph exceeded the staged library bound")
            name = assign_staged_name(Path(dep), used)
            staged[dep] = name
            pending.append(dep)
    return list(staged.values())


def _load_prefix(macho: Path, lib_dir: Path) -> str:
    relative = os.path.relpath(lib_dir, macho.parent)
    if relative == ".":
        relative = ""
    base = "@executable_path" if macho.parent.name == "bin" else "@loader_path"
    if not relative:
        return base
    return f"{base}/{relative}"


def bundle(source: Path, dest: Path) -> None:
    if not source.is_file() or source.is_symlink():
        _fail("runtime source must be a regular interpreter file")
    if source.resolve() == Path("/usr/bin/python3"):
        _fail("/usr/bin/python3 is not the payload interpreter")
    if not _is_macho(source):
        _fail("runtime source is not a Mach-O interpreter")
    bin_dir = dest / "bin"
    lib_dir = dest / "lib"
    if dest.exists():
        shutil.rmtree(dest)
    bin_dir.mkdir(parents=True)
    lib_dir.mkdir()
    python = bin_dir / "python3"
    shutil.copy2(source, python)
    python.chmod(0o755)
    runner = Path(sys.executable).resolve()
    if source.resolve() != runner and source.stat().st_size != runner.stat().st_size:
        _fail("bundle runner does not match the source image and the source was not executed")
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    prefix = Path(sys.base_prefix)
    stdlib = Path(prefix) / "lib" / f"python{version}"
    if not stdlib.is_dir():
        _fail(f"stdlib missing at {stdlib}")
    shutil.copytree(stdlib, lib_dir / f"python{version}", ignore=_ignore_stdlib, symlinks=False)
    app_src = Path(prefix) / "Resources/Python.app/Contents/MacOS/Python"
    app_dest = lib_dir / "Resources/Python.app/Contents/MacOS/Python"
    if app_src.is_file():
        app_dest.parent.mkdir(parents=True)
        shutil.copy2(app_src, app_dest)
        app_dest.chmod(0o755)

    copied: dict[tuple[int, int], Path] = {}
    used_names: dict[str, Path] = {}
    dep_names: dict[str, str] = {}
    pending = [python]
    if app_dest.is_file():
        pending.append(app_dest)
    pending.extend(
        path
        for path in (lib_dir / f"python{version}").rglob("*")
        if path.is_file() and path.suffix != ".a" and _is_macho(path)
    )
    seen: set[tuple[int, int]] = set()
    seen_machos: set[Path] = set()
    while pending:
        macho = pending.pop()
        if not macho.is_file():
            continue
        macho_id = _inode(macho)
        if macho_id in seen:
            continue
        if len(seen) >= MAX_STAGED_LIBRARIES:
            _fail("runtime dependency graph exceeded the staged library bound")
        seen.add(macho_id)
        if _inside(macho, dest):
            seen_machos.add(macho)
        for dep in _otool(macho):
            if dep.startswith(SYSTEM_PREFIXES) or dep.startswith("@"):
                continue
            resolved = Path(dep).resolve()
            if not resolved.is_file():
                _fail(f"missing runtime dependency {dep}")
            dep_id = _inode(resolved)
            if dep_id == macho_id or _inside(resolved, dest):
                continue
            target = copied.get(dep_id)
            if target is None:
                if len(copied) >= MAX_STAGED_LIBRARIES:
                    _fail("runtime dependency graph exceeded the staged library bound")
                name = assign_staged_name(resolved, used_names)
                target = lib_dir / name
                if target.exists() and _inode(target) != dep_id:
                    _fail("staged library destination already belongs to another file")
                shutil.copy2(resolved, target)
                copied[dep_id] = target
                seen_machos.add(target)
                pending.append(resolved)
            dep_names[dep] = target.name
            dep_names[str(resolved)] = target.name

    for macho in list(seen_machos):
        prefix_token = _load_prefix(macho, lib_dir)
        for dep in _otool(macho):
            name = dep_names.get(dep) or dep_names.get(str(Path(dep).resolve()))
            if not name:
                continue
            new = f"{prefix_token}/{name}" if prefix_token else name
            subprocess.check_call(
                ["/usr/bin/install_name_tool", "-change", dep, new, str(macho)],
                stderr=subprocess.DEVNULL,
            )
        if macho.suffix == ".dylib" or macho.parent == lib_dir:
            subprocess.check_call(
                ["/usr/bin/install_name_tool", "-id", f"@loader_path/{macho.name}", str(macho)],
                stderr=subprocess.DEVNULL,
            )
        subprocess.check_call(
            ["/usr/bin/codesign", "--force", "--sign", "-", str(macho)],
            stderr=subprocess.DEVNULL,
        )

    for macho in seen_machos:
        listed = subprocess.check_output(["/usr/bin/otool", "-L", str(macho)], text=True)
        for marker in HOSTILE_MARKERS:
            if marker in listed:
                _fail(f"relocated runtime still links a build-machine path in {macho.name}")

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONHOME"] = str(dest)
    env["PYTHONNOUSERSITE"] = "1"
    probed = subprocess.run(
        [
            str(python),
            "-c",
            "import encodings,sys\nprint(sys.prefix)\nprint(encodings.__file__)\n",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    if probed.returncode != 0:
        _fail(probed.stderr.strip() or "embedded interpreter failed to import encodings")
    lines = [line.strip() for line in probed.stdout.splitlines() if line.strip()]
    if len(lines) != 2:
        _fail("embedded interpreter did not report its prefix")
    runtime_root = dest.resolve()
    if Path(lines[0]).resolve() != runtime_root or not Path(lines[1]).resolve().is_relative_to(runtime_root):
        _fail("embedded interpreter did not relocate onto the bundle prefix")
    if any(marker in lines[1] for marker in HOSTILE_MARKERS):
        _fail("embedded encodings path still points at the build machine")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--dest", required=True, type=Path)
    args = parser.parse_args()
    bundle(args.source, args.dest)


if __name__ == "__main__":
    main()
