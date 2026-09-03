"""Deterministic workspace/source hashing with excludes."""

from __future__ import annotations

import hashlib
import os
from fnmatch import fnmatch
from pathlib import Path

from runspecimen.errors import PathEscapeError, ProvenanceError
from runspecimen.paths import ensure_within


def canonical_json_bytes(obj: object) -> bytes:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def _is_excluded(rel_posix: str, name: str, excludes: list[str]) -> bool:
    for pattern in excludes:
        pat = pattern.replace("\\", "/").rstrip("/")
        if not pat:
            continue
        if pat.endswith("/**"):
            root = pat[:-3]
            if rel_posix == root or rel_posix.startswith(root + "/"):
                return True
        if fnmatch(rel_posix, pat) or fnmatch(name, pat):
            return True
        # Directory-name match: exclude any path segment equal to pattern.
        if "/" not in pat and "*" not in pat and "?" not in pat and "[" not in pat:
            parts = rel_posix.split("/")
            if pat in parts:
                return True
    return False


def _refuse_symlink(rel_posix: str) -> None:
    raise ProvenanceError(f"unexcluded symlink in source roots: {rel_posix}")


def iter_source_files(
    workspace: Path,
    roots: list[str],
    excludes: list[str],
) -> list[Path]:
    workspace = workspace.resolve()
    default_excludes = [
        ".runspecimen",
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        "*.pyc",
        ".DS_Store",
        ".tools",
    ]
    all_excludes = [*default_excludes, *excludes]
    files: list[Path] = []
    seen: set[Path] = set()

    for root in roots:
        abs_root = ensure_within(workspace, Path(root), label=f"source root {root!r}")
        rel_root = abs_root.relative_to(workspace).as_posix()
        if abs_root.is_symlink():
            if _is_excluded(rel_root, abs_root.name, all_excludes):
                continue
            _refuse_symlink(rel_root)
        if abs_root.is_file():
            if not _is_excluded(rel_root, abs_root.name, all_excludes):
                if abs_root not in seen:
                    files.append(abs_root)
                    seen.add(abs_root)
            continue
        if not abs_root.exists():
            raise PathEscapeError(f"source root does not exist: {root}")
        for dirpath, dirnames, filenames in os.walk(abs_root, topdown=True, followlinks=False):
            dpath = Path(dirpath)
            # Refuse if walk landed on a symlink directory (should not with followlinks=False
            # for descent, but defend if root somehow changed).
            if dpath.is_symlink():
                rel_dir = dpath.relative_to(workspace).as_posix()
                if not _is_excluded(rel_dir, dpath.name, all_excludes):
                    _refuse_symlink(rel_dir)
                dirnames[:] = []
                continue
            rel_dir = dpath.relative_to(workspace).as_posix()
            keep: list[str] = []
            for dn in dirnames:
                child_rel = f"{rel_dir}/{dn}" if rel_dir != "." else dn
                if _is_excluded(child_rel, dn, all_excludes):
                    continue
                child = dpath / dn
                if child.is_symlink():
                    _refuse_symlink(child_rel)
                keep.append(dn)
            dirnames[:] = sorted(keep)
            for fn in sorted(filenames):
                child_rel = f"{rel_dir}/{fn}" if rel_dir != "." else fn
                if _is_excluded(child_rel, fn, all_excludes):
                    continue
                fp = dpath / fn
                if fp.is_symlink():
                    _refuse_symlink(child_rel)
                if not fp.is_file():
                    continue
                if fp not in seen:
                    files.append(fp)
                    seen.add(fp)
    files.sort(key=lambda p: p.relative_to(workspace).as_posix())
    return files


def hash_source(
    workspace: Path,
    roots: list[str],
    excludes: list[str],
) -> tuple[str, list[dict[str, str]]]:
    """Return (aggregate_hash, manifest entries)."""
    workspace = workspace.resolve()
    entries: list[dict[str, str]] = []
    for path in iter_source_files(workspace, roots, excludes):
        rel = path.relative_to(workspace).as_posix()
        digest = sha256_file(path)
        entries.append({"path": rel, "sha256": digest})
    material = canonical_json_bytes({"entries": entries})
    return sha256_bytes(material), entries


def hash_contract_file(contract_path: Path) -> str:
    return sha256_file(contract_path)
