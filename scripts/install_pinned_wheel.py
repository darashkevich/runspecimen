#!/usr/bin/env python3
"""Install one authenticated pure-Python wheel into a fresh pip-free venv.

Start this only with the trusted base interpreter::

    python -I -S scripts/install_pinned_wheel.py \\
        --wheel WHEEL --venv VENV --expected-sha256 HEX

``-I`` does not disable site startup. ``-S`` is required as well. This process
never executes the venv interpreter, pip, or any byte from the wheel. It does
not import installed code to choose a destination. Writes go through directory
descriptors and refuse a symlink at every component, so replacing a directory
after the first check cannot move a file outside the venv. A same-user process
can still rewrite the venv after this write; that is outside this installer.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import stat
import sys
import zipfile
from pathlib import Path


MAX_WHEEL_BYTES = 32 * 1024 * 1024
MAX_MEMBERS = 4000
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
CONSOLE_SCRIPT_BODY = (
    b"# -*- coding: utf-8 -*-\n"
    b"import re\n"
    b"import sys\n"
    b"from runspecimen.cli import main\n"
    b"if __name__ == '__main__':\n"
    b"    sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])\n"
    b"    sys.exit(main())\n"
)
PINNED_ENTRY = "runspecimen.cli:main"


class InstallRefusal(Exception):
    """The wheel was not written. The refusal text is safe to print."""


def _require_isolated_invocation() -> None:
    if not sys.flags.isolated or not sys.flags.no_site:
        raise SystemExit(
            "start install_pinned_wheel.py with the trusted base interpreter "
            "using -I -S; -I alone does not disable site startup"
        )


def venv_purelib(venv: Path) -> Path:
    """POSIX site-packages from ``pyvenv.cfg``, without running the venv."""
    version = _pyvenv_version(venv)
    return venv / "lib" / f"python{version[0]}.{version[1]}" / "site-packages"


def install_pinned_wheel(wheel: Path, venv: Path, expected_sha256: str) -> None:
    """Authenticate ``wheel`` and write it under ``venv``. Raise on refusal."""
    expected = expected_sha256.strip().lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise InstallRefusal("expected sha256 must be 64 hex characters")
    wheel_path = Path(wheel)
    venv_path = Path(venv)
    if not wheel_path.is_file() or wheel_path.is_symlink():
        raise InstallRefusal(f"wheel is not a regular file: {wheel_path}")
    data = _read_bounded(wheel_path, MAX_WHEEL_BYTES, "wheel")
    got = hashlib.sha256(data).hexdigest()
    if got != expected:
        raise InstallRefusal(
            f"wheel sha256 {got} does not match the pinned digest; nothing was written"
        )
    _require_fresh_venv(venv_path)
    purelib = venv_purelib(venv_path)
    _require_real_directory(venv_path, purelib)
    _refuse_existing_install(purelib, venv_path)
    members = _validated_members(data, wheel_path.name)
    version = _pyvenv_version(venv_path)
    purelib_parts = ("lib", f"python{version[0]}.{version[1]}", "site-packages")
    _write_members(venv_path, purelib_parts, members)
    _write_direct_url(venv_path, purelib_parts, members, wheel_path, expected)
    _write_launcher(venv_path)


def _read_bounded(path: Path, limit: int, label: str) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise InstallRefusal(f"cannot stat {label} {path}: {exc}") from exc
    if size > limit:
        raise InstallRefusal(f"{label} is larger than {limit} bytes")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise InstallRefusal(f"cannot read {label} {path}: {exc}") from exc
    if len(data) != size or len(data) > limit:
        raise InstallRefusal(f"{label} size changed while it was read")
    return data


def _pyvenv_version(venv: Path) -> tuple[int, int]:
    cfg = venv / "pyvenv.cfg"
    if not cfg.is_file() or cfg.is_symlink():
        raise InstallRefusal(f"pyvenv.cfg is not a regular file: {cfg}")
    values: dict[str, str] = {}
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError as exc:
        raise InstallRefusal(f"cannot read {cfg}: {exc}") from exc
    for raw in text.splitlines():
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        values[key.strip().lower()] = value.strip()
    system_site = values.get("include-system-site-packages", "")
    if system_site != "false":
        raise InstallRefusal(
            "pyvenv.cfg include-system-site-packages must be false; "
            "refusing to install into a venv that sees another site"
        )
    version = values.get("version", "")
    parts = version.split(".")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise InstallRefusal(f"pyvenv.cfg has no usable version: {version!r}")
    return int(parts[0]), int(parts[1])


def _require_fresh_venv(venv: Path) -> None:
    if not venv.is_dir() or venv.is_symlink():
        raise InstallRefusal(f"venv is not a real directory: {venv}")
    binary = venv / "bin" / "python"
    if not binary.exists():
        raise InstallRefusal(f"venv has no bin/python: {binary}")
    launcher = venv / "bin" / "runspecimen"
    if launcher.exists() or launcher.is_symlink():
        raise InstallRefusal(
            f"refusing to replace an existing launcher: {launcher}"
        )


def _require_real_directory(venv: Path, purelib: Path) -> None:
    try:
        relative = purelib.relative_to(venv)
    except ValueError as exc:
        raise InstallRefusal(f"site-packages is not inside the venv: {purelib}") from exc
    current = venv
    if current.is_symlink():
        raise InstallRefusal(f"symlinked destination ancestor: {current}")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise InstallRefusal(f"symlinked destination ancestor: {current}")
    bindir = venv / "bin"
    if bindir.is_symlink() or not bindir.is_dir():
        raise InstallRefusal(f"venv bin is not a real directory: {bindir}")
    if not purelib.is_dir():
        raise InstallRefusal(f"site-packages is not a real directory: {purelib}")


def _refuse_existing_install(purelib: Path, venv: Path) -> None:
    try:
        names = [path.name for path in purelib.iterdir()]
    except OSError as exc:
        raise InstallRefusal(f"cannot list {purelib}: {exc}") from exc
    occupied = [
        name
        for name in names
        if name == "runspecimen" or name.endswith(".dist-info") or name == "direct_url.json"
    ]
    if occupied:
        raise InstallRefusal(
            "refusing to write into a venv that already has "
            + ", ".join(sorted(occupied))
            + f" under {purelib}"
        )
    if (venv / "bin" / "pip").exists() or (venv / "bin" / "pip3").exists():
        raise InstallRefusal(
            "refusing a venv that already has pip; create it with "
            "python -I -S -m venv --without-pip"
        )


def _validated_members(data: bytes, wheel_name: str) -> list[tuple[str, bytes]]:
    version = _wheel_version(wheel_name)
    dist_info = f"runspecimen-{version}.dist-info/"
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise InstallRefusal(f"wheel is not a zip: {exc}") from exc
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        raise InstallRefusal(f"wheel has more than {MAX_MEMBERS} members")
    seen: set[str] = set()
    total = 0
    files: list[tuple[str, bytes]] = []
    for info in infos:
        name = info.filename
        if name in seen:
            raise InstallRefusal(f"duplicate wheel member: {name}")
        seen.add(name)
        _refuse_unsafe_name(name)
        if name.endswith("/"):
            if info.file_size != 0:
                raise InstallRefusal(f"directory member is not empty: {name}")
            continue
        if _is_symlink_member(info) or stat.S_ISLNK(_unix_mode(info)):
            raise InstallRefusal(f"wheel member is a link: {name}")
        if info.flag_bits & 0x1:
            raise InstallRefusal(f"wheel member is encrypted: {name}")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise InstallRefusal(f"wheel member uses an unexpected compression: {name}")
        if info.file_size < 0 or info.file_size > MAX_MEMBER_BYTES:
            raise InstallRefusal(f"wheel member exceeds the size bound: {name}")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise InstallRefusal("wheel uncompressed size exceeds the bound")
        payload = archive.read(info)
        if len(payload) != info.file_size:
            raise InstallRefusal(f"wheel member size does not match its payload: {name}")
        if not (name.startswith("runspecimen/") or name.startswith(dist_info)):
            raise InstallRefusal(f"unexpected wheel member: {name}")
        if name.endswith(".pyc") or name.endswith(".pyo") or "/__pycache__/" in name:
            raise InstallRefusal(f"wheel member is bytecode: {name}")
        files.append((name.replace("\\", "/"), payload))
    if not any(name == "runspecimen/__init__.py" for name, _payload in files):
        raise InstallRefusal("wheel has no runspecimen/__init__.py")
    entry = dist_info + "entry_points.txt"
    if not any(name == entry for name, _payload in files):
        raise InstallRefusal("wheel has no entry_points.txt")
    entry_text = next(payload for name, payload in files if name == entry)
    scripts = _console_scripts(entry_text.decode("utf-8"))
    if scripts != [("runspecimen", PINNED_ENTRY)]:
        raise InstallRefusal(
            "wheel must expose exactly one console script, "
            f"runspecimen = {PINNED_ENTRY}; got {scripts}"
        )
    return files


def _wheel_version(wheel_name: str) -> str:
    prefix = "runspecimen-"
    suffix = "-py3-none-any.whl"
    if not wheel_name.startswith(prefix) or not wheel_name.endswith(suffix):
        raise InstallRefusal(
            "only a runspecimen-*-py3-none-any.whl pure wheel is accepted: "
            + wheel_name
        )
    version = wheel_name[len(prefix) : -len(suffix)]
    if not version or "/" in version or ".." in version:
        raise InstallRefusal(f"unexpected wheel version: {version!r}")
    return version


def _refuse_unsafe_name(name: str) -> None:
    if "\\" in name or "\x00" in name:
        raise InstallRefusal(f"unsafe wheel member name: {name!r}")
    if name.startswith("/") or name.startswith("//"):
        raise InstallRefusal(f"absolute wheel member: {name}")
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise InstallRefusal(f"wheel member escapes its directory: {name}")


def _unix_mode(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0o170000


def _is_symlink_member(info: zipfile.ZipInfo) -> bool:
    return _unix_mode(info) == 0o120000


def _console_scripts(text: str) -> list[tuple[str, str]]:
    scripts: list[tuple[str, str]] = []
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = line == "[console_scripts]"
            continue
        if not in_section:
            continue
        name, sep, target = line.partition("=")
        if not sep:
            raise InstallRefusal(f"malformed entry point: {raw!r}")
        scripts.append((name.strip(), target.strip()))
    return scripts


def _dir_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _open_anchor(path: Path) -> int:
    """Open a directory without following its final symlink.

    Later writes use this descriptor. They do not resolve the path again, so
    replacing a child with a symlink cannot move the write outside.
    """
    try:
        return os.open(os.fspath(path), _dir_open_flags())
    except OSError as exc:
        raise InstallRefusal(
            f"refusing a symlinked or unreadable directory: {path} ({exc})"
        ) from exc


def _open_child_dir(parent_fd: int, name: str, *, create: bool) -> int:
    if name in {"", ".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise InstallRefusal(f"refusing path component {name!r}")
    try:
        return os.open(name, _dir_open_flags(), dir_fd=parent_fd)
    except FileNotFoundError:
        if not create:
            raise InstallRefusal(f"missing directory component: {name}")
        try:
            os.mkdir(name, dir_fd=parent_fd)
        except OSError as exc:
            raise InstallRefusal(f"cannot create {name}: {exc}") from exc
        try:
            return os.open(name, _dir_open_flags(), dir_fd=parent_fd)
        except OSError as exc:
            raise InstallRefusal(f"refusing to follow {name}: {exc}") from exc
    except OSError as exc:
        raise InstallRefusal(f"refusing to follow {name}: {exc}") from exc


def _walk_dirs(root_fd: int, parts: tuple[str, ...] | list[str], *, create: bool) -> int:
    fd = os.dup(root_fd)
    try:
        for part in parts:
            nxt = _open_child_dir(fd, part, create=create)
            os.close(fd)
            fd = nxt
        kept = fd
        fd = -1
        return kept
    finally:
        if fd >= 0:
            os.close(fd)


def _write_exclusive_at(parent_fd: int, name: str, payload: bytes, mode: int) -> None:
    if name in {"", ".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise InstallRefusal(f"refusing path component {name!r}")
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        fd = os.open(name, flags, mode, dir_fd=parent_fd)
    except OSError as exc:
        raise InstallRefusal(f"refusing to overwrite {name}: {exc}") from exc
    try:
        view = payload
        while view:
            wrote = os.write(fd, view)
            if wrote <= 0:
                raise InstallRefusal(f"short write of {name}")
            view = view[wrote:]
        os.lseek(fd, 0, os.SEEK_SET)
        got = bytearray()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            got.extend(chunk)
            if len(got) > len(payload):
                break
        if bytes(got) != payload:
            raise InstallRefusal(f"written bytes do not match the wheel member: {name}")
    except OSError as exc:
        raise InstallRefusal(f"cannot write {name}: {exc}") from exc
    finally:
        os.close(fd)


def _write_tree_file(root_fd: int, parts: list[str], payload: bytes, mode: int) -> None:
    if len(parts) < 1 or any(part in {"", ".", ".."} for part in parts):
        raise InstallRefusal(f"refusing to write {parts!r}")
    parent = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            nxt = _open_child_dir(parent, part, create=True)
            os.close(parent)
            parent = nxt
        _write_exclusive_at(parent, parts[-1], payload, mode)
    finally:
        os.close(parent)


def _write_members(
    venv: Path,
    purelib_parts: tuple[str, ...],
    members: list[tuple[str, bytes]],
) -> None:
    root = _open_anchor(venv)
    try:
        pure = _walk_dirs(root, purelib_parts, create=False)
        try:
            for name, payload in members:
                _write_tree_file(pure, name.split("/"), payload, 0o644)
        finally:
            os.close(pure)
    finally:
        os.close(root)


def _write_direct_url(
    venv: Path,
    purelib_parts: tuple[str, ...],
    members: list[tuple[str, bytes]],
    wheel: Path,
    digest: str,
) -> None:
    dist_names = sorted(
        {name.split("/")[0] for name, _payload in members if name.split("/")[0].endswith(".dist-info")}
    )
    if len(dist_names) != 1:
        raise InstallRefusal(f"expected one dist-info directory, got {dist_names}")
    if any(name == f"{dist_names[0]}/direct_url.json" for name, _payload in members):
        return
    url = Path(os.path.abspath(wheel)).as_uri()
    payload = (
        '{"archive_info":{"hashes":{"sha256":"'
        + digest
        + '"}},"url":"'
        + url
        + '"}\n'
    ).encode("utf-8")
    root = _open_anchor(venv)
    try:
        pure = _walk_dirs(root, purelib_parts, create=False)
        try:
            _write_tree_file(pure, [dist_names[0], "direct_url.json"], payload, 0o644)
        finally:
            os.close(pure)
    finally:
        os.close(root)


def _write_launcher(venv: Path) -> None:
    python = venv / "bin" / "python"
    shebang_path = os.path.abspath(python)
    if not shebang_path.startswith("/") or shebang_path.startswith("//"):
        raise InstallRefusal(f"launcher interpreter path is not accepted: {shebang_path}")
    try:
        shebang_path.encode("ascii")
    except UnicodeEncodeError as exc:
        raise InstallRefusal("launcher path must be ASCII") from exc
    if " " in shebang_path or "\n" in shebang_path:
        raise InstallRefusal("launcher path must not contain whitespace")
    shebang = b"#!" + shebang_path.encode("ascii") + b"\n"
    if len(shebang) > 127:
        raise InstallRefusal(
            "launcher path is longer than the kernel shebang limit; "
            "refusing to write a shell wrapper"
        )
    root = _open_anchor(venv)
    try:
        bindir = _walk_dirs(root, ("bin",), create=False)
        try:
            _write_exclusive_at(bindir, "runspecimen", shebang + CONSOLE_SCRIPT_BODY, 0o755)
        finally:
            os.close(bindir)
    finally:
        os.close(root)


def main(argv: list[str] | None = None) -> int:
    _require_isolated_invocation()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--venv", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        install_pinned_wheel(args.wheel, args.venv, args.expected_sha256)
    except InstallRefusal as exc:
        print(f"install refused: {exc}", file=sys.stderr)
        return 1
    print("installed pinned wheel without executing the venv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
