#!/usr/bin/env python3
"""Compare the installed runspecimen tree to a pinned wheel's bytes.

Version strings are not proof. Two unpublished 0.2.0rc15 wheels can differ.
Exit 0 only when every hashed RECORD member (and every runspecimen/*.py in the
zip) matches the file installed under the absolute launcher's interpreter, the
effective origins of runspecimen, runspecimen.cli, runspecimen.approve, and
every other loaded runspecimen.* module realpath-equal the hashed installed
members, the environment has no import overrides, and the target venv has no
extra startup code.

Trusted-interpreter assumption: this helper trusts **only the Python
interpreter and its stdlib**. It is not a promise to resist arbitrary
replacement of Python, of this verifier script, or of the operator's own
decision to run a different interpreter. Venv-local metadata is not trust:
setuptools RECORD does not hash itself (``RECORD,,``) and is writable by the
same attacker who can replace ``_distutils_hack``. Any trust anchored in
venv-local metadata is attacker-controlled.

In the **target venv** it REJECTS:

- any ``.pth`` file with an executable (``import``) line, whatever its name
  or owner (including setuptools' ``distutils-precedence.pth``)
- any sitecustomize or usercustomize that is importable from a path that is
  not the interpreter's own stdlib
- any non-stdlib ``sys.meta_path`` or ``sys.path_hooks`` entry present after
  startup
- any ``_virtualenv*`` artifact

A stdlib finder or path hook is identified by its **class (or defining
function) living in a stdlib module whose realpath is under the interpreter's
stdlib dir**, not by claimed ``__name__`` / ``__module__``. Frozen/built-in
interpreter modules count as the interpreter. There is no DistutilsMetaFinder
allowlist and no RECORD-based trust of ``_distutils_hack``.

The probe runs with ``-I -B``. Any ``.pyc`` / ``__pycache__`` under the
installed runspecimen package is refused (timestamp-based, hash-based, any
optimisation level), as is ``PYTHONPYCACHEPREFIX`` / ``sys.pycache_prefix``
and a sourceless ``.pyc`` module. The launcher body after the shebang must
byte-match a pinned pip console-script template.

The venv ``bin/`` directory may contain only what ``python -m venv`` plus pip
plus this wheel create (python symlinks, activate scripts, pip and
runspecimen launchers). CPython 3.14 ``python -m venv`` also writes the exact
name ``𝜋thon`` (U+1D70B MATHEMATICAL ITALIC SMALL PI + ``thon``; gh-119535);
that name is allowlisted. A ``json.py`` (or any ``.py`` / ``.pyc`` / ``.so`` /
directory) there is refused because the real launcher puts ``bin/`` on
``sys.path[0]``. Module origins are taken from the real launcher process
(``runspecimen doctor``), not from ``python -c``.

Run with the venv interpreter that owns the install, under the same sanitized
environment the acceptance sheet uses for every launcher call:

  env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP -u PYTHONPYCACHEPREFIX \\
    PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \\
    "$VENV/bin/python" scripts/verify_installed_wheel.py \\
    --wheel /abs/path.whl --launcher "$VENV/bin/runspecimen"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
import zipfile


IMPORT_OVERRIDE_VARS = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")
BYTECODE_OVERRIDE_VARS = ("PYTHONPYCACHEPREFIX",)
HOOK_REFUSAL = (
    "This environment runs extra startup code we can't vouch for (file: {file}). "
    "Create a fresh one by following the acceptance sheet."
)
# Exact console-script bodies pip writes for entry point runspecimen.cli:main.
# Shebang is validated separately; these are the bytes after the first newline.
# No regex. Only these exact known bodies are accepted.
#
# 1) pip._vendor.distlib.scripts.SCRIPT_TEMPLATE (import at module level + re.sub).
#    Captured from pip 24.0 on this pack host (CPython 3.12.3) and from GHA
#    release-check 3.9 / 3.10 / 3.11 / 3.12 (ubuntu + macos 3.11). Also the
#    historical macOS 12+ system CPython 3.9.6 ensurepip body (pip 21.2.4).
PIP_DISTLIB_CONSOLE_SCRIPT_BODY = (
    b"# -*- coding: utf-8 -*-\n"
    b"import re\n"
    b"import sys\n"
    b"from runspecimen.cli import main\n"
    b"if __name__ == '__main__':\n"
    b"    sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])\n"
    b"    sys.exit(main())\n"
)
# 2) pip 25.1–25.3 PipScriptMaker override (pip/_internal/operations/install/wheel.py,
#    PR #13166). textwrap.dedent of that template instantiated for this entry
#    point. Not emitted by current GHA 3.9–3.12 (those still write (1)) or by
#    GHA 3.13/3.14 (those write (3)).
PIP_SCRIPTMAKER_ENDSWITH_BODY = (
    b"import sys\n"
    b"from runspecimen.cli import main\n"
    b"if __name__ == '__main__':\n"
    b"    if sys.argv[0].endswith('.exe'):\n"
    b"        sys.argv[0] = sys.argv[0][:-4]\n"
    b"    sys.exit(main())\n"
)
# 3) pip 26.0+ PipScriptMaker override (PR #13697, .removesuffix('.exe')).
#    Captured from GHA ubuntu 3.13, ubuntu 3.14, and macos 3.14: the unittest
#    shortening of the installed launcher body matches this 143-byte value
#    exactly and does not match (1) or (2).
PIP_SCRIPTMAKER_REMOVESUFFIX_BODY = (
    b"import sys\n"
    b"from runspecimen.cli import main\n"
    b"if __name__ == '__main__':\n"
    b"    sys.argv[0] = sys.argv[0].removesuffix('.exe')\n"
    b"    sys.exit(main())\n"
)
KNOWN_CONSOLE_SCRIPT_BODIES = (
    PIP_DISTLIB_CONSOLE_SCRIPT_BODY,
    PIP_SCRIPTMAKER_ENDSWITH_BODY,
    PIP_SCRIPTMAKER_REMOVESUFFIX_BODY,
)
PINNED_CONSOLE_SCRIPT_TARGET = "runspecimen.cli:main"
# Exact names plus pythonX.Y / pipX.Y generated by stdlib venv + pip + this wheel.
_VENV_BIN_EXACT = frozenset(
    {
        "activate",
        "activate.csh",
        "activate.fish",
        "activate.nu",
        "Activate.ps1",
        "activate.bat",
        "activate.ps1",
        "deactivate.bat",
        "runspecimen",
        "runspecimen.exe",
        "pip",
        "pip.exe",
        "pip3",
        "pip3.exe",
        "python",
        "python.exe",
        "pythonw.exe",
        "python3",
        "python3.exe",
        # CPython 3.14 POSIX venv easter egg (gh-119535). Exact name only;
        # lookalikes such as U+03C0 GREEK SMALL LETTER PI are refused.
        "\N{MATHEMATICAL ITALIC SMALL PI}thon",
    }
)
_BIN_FORBIDDEN_SUFFIXES = (".py", ".pyc", ".pyo", ".so", ".dylib")
PROBE_SCRIPT = r"""
import json, sys, site, pkgutil, sysconfig
from pathlib import Path
import runspecimen
import runspecimen.cli
import runspecimen.approve
import runspecimen.run
try:
    import runspecimen.present
except ImportError:
    pass

def _find(modname):
    if modname in sys.modules:
        mod = sys.modules[modname]
        path = getattr(mod, '__file__', None)
        if path:
            return str(Path(path).resolve())
    for entry in list(sys.path):
        if not entry:
            continue
        base = Path(entry)
        for suffix in ('.py', '.pyc'):
            cand = base / (modname + suffix)
            if cand.is_file():
                return str(cand.resolve())
        init = base / modname / '__init__.py'
        if init.is_file():
            return str(init.resolve())
    return None

def _origin(mod):
    path = getattr(mod, '__file__', None)
    return None if path is None else str(Path(path).resolve())

loaded = {}
for name, mod in list(sys.modules.items()):
    if name != 'runspecimen' and not name.startswith('runspecimen.'):
        continue
    loaded[name] = _origin(mod)

lazy_loaded = {}
lazy_errors = {}
try:
    for info in pkgutil.walk_packages(runspecimen.__path__, prefix='runspecimen.'):
        name = info.name
        if name in sys.modules:
            continue
        try:
            __import__(name)
        except Exception as exc:
            lazy_errors[name] = type(exc).__name__
            continue
        mod = sys.modules.get(name)
        lazy_loaded[name] = None if mod is None else _origin(mod)
except Exception as exc:
    lazy_errors['<walk>'] = type(exc).__name__ + ':' + str(exc)

def _stdlib_roots():
    roots = []
    for key in ('stdlib', 'platstdlib'):
        p = sysconfig.get_path(key)
        if p:
            roots.append(Path(p).resolve())
    return roots

_STDLIB_ROOTS = _stdlib_roots()

def _under_stdlib(path):
    try:
        resolved = Path(path).resolve()
    except Exception:
        return False
    for root in _STDLIB_ROOTS:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False

def _load_module(modname):
    if not modname:
        return None
    mod = sys.modules.get(modname)
    if mod is not None:
        return mod
    try:
        return __import__(modname, fromlist=['*'])
    except Exception:
        return None

def _module_is_interpreter_or_stdlib(mod):
    if mod is None:
        return False
    spec = getattr(mod, '__spec__', None)
    origin = getattr(spec, 'origin', None) if spec is not None else None
    if origin in ('frozen', 'built-in'):
        return True
    path = getattr(mod, '__file__', None)
    if not path:
        return False
    return _under_stdlib(path)

def _class_lives_in_stdlib(cls):
    if not isinstance(cls, type):
        return False
    modname = getattr(cls, '__module__', None)
    mod = _load_module(modname)
    if mod is None:
        return False
    name = getattr(cls, '__name__', None)
    if getattr(mod, name, None) is not cls and cls not in vars(mod).values():
        return False
    return _module_is_interpreter_or_stdlib(mod)

def _callable_is_stdlib(obj):
    if obj is None:
        return False
    if isinstance(obj, type):
        return _class_lives_in_stdlib(obj)
    code = getattr(obj, '__code__', None)
    if code is not None:
        filename = getattr(code, 'co_filename', '') or ''
        if filename.startswith('<frozen ') or filename.startswith('<built-in'):
            return _module_is_interpreter_or_stdlib(_load_module(getattr(obj, '__module__', None)))
        if filename and _under_stdlib(filename):
            return True
        return False
    return _class_lives_in_stdlib(type(obj))

def _is_stdlib_finder(finder):
    if finder is None:
        return False
    if isinstance(finder, type):
        return _class_lives_in_stdlib(finder)
    return _class_lives_in_stdlib(type(finder))

def _object_file(obj):
    if obj is None:
        return None
    cls = obj if isinstance(obj, type) else type(obj)
    mod = _load_module(getattr(cls, '__module__', None))
    path = getattr(mod, '__file__', None) if mod is not None else None
    if path:
        try:
            return str(Path(path).resolve())
        except Exception:
            return str(path)
    code = getattr(obj, '__code__', None)
    if code is not None and getattr(code, 'co_filename', None):
        return str(code.co_filename)
    return None

def _finder_rec(finder):
    if finder is None:
        return {'type': None, 'module': None, 'file': None}
    cls = finder if isinstance(finder, type) else type(finder)
    return {
        'type': getattr(cls, '__name__', None),
        'module': getattr(cls, '__module__', None),
        'file': _object_file(finder),
    }

meta_path = []
unexpected_meta_path = []
for finder in sys.meta_path:
    rec = _finder_rec(finder)
    meta_path.append(rec)
    if not _is_stdlib_finder(finder):
        unexpected_meta_path.append(rec)

path_hooks = []
unexpected_path_hooks = []
for hook in sys.path_hooks:
    rec = _finder_rec(hook)
    rec['repr'] = type(hook).__name__ if not isinstance(hook, type) else hook.__name__
    path_hooks.append(rec)
    if not _callable_is_stdlib(hook):
        unexpected_path_hooks.append(rec)

cached_bytecode = []
sourceless = []
for name, mod in list(sys.modules.items()):
    if name != 'runspecimen' and not name.startswith('runspecimen.'):
        continue
    origin = _origin(mod)
    if origin and origin.endswith(('.pyc', '.pyo')):
        sourceless.append({'name': name, 'file': origin})
    cached = getattr(mod, '__cached__', None)
    if cached:
        try:
            if Path(cached).is_file():
                cached_bytecode.append({'name': name, 'cached': str(Path(cached).resolve())})
        except Exception:
            cached_bytecode.append({'name': name, 'cached': str(cached)})

print(json.dumps({
    'runspecimen_file': str(Path(runspecimen.__file__).resolve()),
    'cli_file': str(Path(runspecimen.cli.__file__).resolve()),
    'approve_file': str(Path(runspecimen.approve.__file__).resolve()),
    'present_file': (
        str(Path(runspecimen.present.__file__).resolve())
        if 'runspecimen.present' in sys.modules
        else None
    ),
    'prefix': str(Path(sys.prefix).resolve()),
    'executable': str(Path(sys.executable).resolve()),
    'version': getattr(runspecimen, '__version__', None),
    'loaded_runspecimen': loaded,
    'lazy_loaded_runspecimen': lazy_loaded,
    'lazy_import_errors': lazy_errors,
    'meta_path': meta_path,
    'unexpected_meta_path': unexpected_meta_path,
    'path_hooks': path_hooks,
    'unexpected_path_hooks': unexpected_path_hooks,
    'sitecustomize': _find('sitecustomize'),
    'usercustomize': _find('usercustomize'),
    'enable_user_site': bool(getattr(site, 'ENABLE_USER_SITE', False)),
    'stdlib': [str(p) for p in _STDLIB_ROOTS],
    'pycache_prefix': sys.pycache_prefix,
    'dont_write_bytecode': bool(sys.dont_write_bytecode),
    'cached_bytecode': cached_bytecode,
    'sourceless_bytecode': sourceless,
}))
"""


class UnsupportedShebangError(ValueError):
    """Launcher shebang is env-based, missing, or not this venv's Python."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def hook_refusal_message(file_hint: str) -> str:
    return HOOK_REFUSAL.format(file=file_hint)


def _first_hook_file(
    pth_findings: list[dict[str, Any]],
    startup_findings: list[str],
    meta_path_findings: list[Any],
    path_hook_findings: list[Any],
) -> str | None:
    for item in pth_findings:
        path = item.get("path")
        if path:
            return str(path)
    for item in startup_findings:
        text = str(item)
        marker = ": "
        if marker in text:
            candidate = text.rsplit(marker, 1)[-1].strip()
            if candidate:
                return candidate
        return text
    for group in (meta_path_findings, path_hook_findings):
        for item in group:
            if isinstance(item, dict):
                path = item.get("file") or item.get("path")
                if path:
                    return str(path)
                module = item.get("module")
                kind = item.get("type")
                if module or kind:
                    return f"{module}.{kind}".strip(".")
            else:
                return str(item)
    return None


def scan_virtualenv_artifacts(site_packages: Path) -> list[dict[str, Any]]:
    """Refuse every ``_virtualenv*`` path in site-packages.

    HUMAN-ACCEPTANCE uses stdlib ``python3 -m venv``, which creates none.
    Trusting ``import _virtualenv`` by line body (or a pinned hash of
    ``_virtualenv.py``) is not used: the filename is not trust, and pinning
    virtualenv versions is fragile.
    """
    findings: list[dict[str, Any]] = []
    site_packages = site_packages.resolve()
    if not site_packages.is_dir():
        return findings
    reason = (
        "_virtualenv* is refused; HUMAN-ACCEPTANCE uses stdlib python3 -m venv, "
        "which creates none"
    )
    candidates: list[Path] = []
    for path in sorted(site_packages.iterdir()):
        if path.name.startswith("_virtualenv"):
            candidates.append(path)
    pycache = site_packages / "__pycache__"
    if pycache.is_dir():
        for path in sorted(pycache.iterdir()):
            if path.name.startswith("_virtualenv"):
                candidates.append(path)
    for path in candidates:
        findings.append({
            "path": str(path.resolve()),
            "line": 0,
            "reason": reason,
            "text": path.name,
        })
    return findings


def _parse_record(text: str) -> list[str]:
    names: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        path = line.split(",", 1)[0]
        if not path or path.endswith("/"):
            continue
        names.append(path)
    return names


def verify_site_against_wheel(*, site_packages: Path, wheel: Path) -> dict[str, Any]:
    """Return a report. ``ok`` is True only when installed bytes match the wheel."""
    wheel = wheel.resolve()
    site_packages = site_packages.resolve()
    report: dict[str, Any] = {
        "ok": False,
        "wheel": str(wheel),
        "wheel_sha256": sha256_file(wheel) if wheel.is_file() else None,
        "site_packages": str(site_packages),
        "mismatches": [],
        "missing": [],
        "extra_py": [],
        "checked": 0,
        "dist_info_record": None,
        "direct_url_json": None,
        "hashed_py_members": [],
        "hashed_members": [],
    }
    if not wheel.is_file():
        report["message"] = f"wheel not found: {wheel}"
        return report
    if not site_packages.is_dir():
        report["message"] = f"site-packages not found: {site_packages}"
        return report

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        record_members = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(record_members) != 1:
            report["message"] = f"expected one RECORD in the wheel, got {record_members}"
            return report
        record_name = record_members[0]
        record_files = _parse_record(archive.read(record_name).decode("utf-8"))
        to_check = []
        for name in record_files:
            if name.endswith(".dist-info/RECORD"):
                continue
            to_check.append(name)
        for name in sorted(names):
            if name.endswith("/") or name.endswith(".dist-info/RECORD"):
                continue
            if name.startswith("runspecimen/") and name.endswith(".py") and name not in to_check:
                to_check.append(name)

        mismatches: list[str] = []
        missing: list[str] = []
        for name in to_check:
            if name not in names:
                missing.append(name)
                continue
            expected = sha256_bytes(archive.read(name))
            installed = site_packages / name
            if not installed.is_file():
                missing.append(name)
                continue
            got = sha256_file(installed)
            if got != expected:
                mismatches.append(f"{name}: installed {got} != wheel {expected}")
            report["checked"] += 1

        wheel_py = {
            name
            for name in names
            if name.startswith("runspecimen/") and name.endswith(".py")
        }
        pkg = site_packages / "runspecimen"
        installed_py = set()
        if pkg.is_dir():
            for path in pkg.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                installed_py.add(path.relative_to(site_packages).as_posix())
        extra_py = sorted(installed_py - wheel_py)
        missing_py = sorted(wheel_py - installed_py)
        report["mismatches"] = mismatches
        report["missing"] = missing + missing_py
        report["extra_py"] = extra_py
        report["hashed_py_members"] = sorted(wheel_py)
        report["hashed_members"] = sorted(to_check)

    dist_infos = sorted(site_packages.glob("runspecimen-*.dist-info"))
    if dist_infos:
        dist_info = dist_infos[-1]
        installed_record = dist_info / "RECORD"
        if installed_record.is_file():
            report["dist_info_record"] = {
                "path": str(installed_record),
                "sha256": sha256_file(installed_record),
                "text": installed_record.read_text(encoding="utf-8"),
            }
        direct_url = dist_info / "direct_url.json"
        if direct_url.is_file():
            report["direct_url_json"] = {
                "path": str(direct_url),
                "sha256": sha256_file(direct_url),
                "text": direct_url.read_text(encoding="utf-8"),
            }

    report["ok"] = not report["mismatches"] and not report["missing"] and not report["extra_py"]
    if report["ok"]:
        report["message"] = (
            f"installed tree matches wheel {report['wheel_sha256']} "
            f"({report['checked']} files)"
        )
    else:
        report["message"] = (
            "installed tree does not match the pinned wheel "
            f"(missing={len(report['missing'])} mismatches={len(report['mismatches'])} "
            f"extra_py={len(report['extra_py'])})"
        )
    return report


def sanitized_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base if base is not None else os.environ)
    for key in IMPORT_OVERRIDE_VARS + BYTECODE_OVERRIDE_VARS:
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def import_overrides(env: dict[str, str] | None = None) -> list[str]:
    source = env if env is not None else os.environ
    found = [f"{key}={source[key]}" for key in IMPORT_OVERRIDE_VARS if source.get(key)]
    for key in BYTECODE_OVERRIDE_VARS:
        if source.get(key):
            found.append(f"{key}={source[key]}")
    usersite = source.get("PYTHONNOUSERSITE", "")
    if usersite not in {"1", "true", "True", "yes"}:
        found.append("PYTHONNOUSERSITE is not 1")
    return found


def discover_launcher(prefix: Path | None = None) -> Path | None:
    root = (prefix or Path(sys.prefix)).resolve()
    for parts in (("bin", "runspecimen"), ("Scripts", "runspecimen.exe"), ("Scripts", "runspecimen")):
        candidate = root.joinpath(*parts)
        if candidate.is_file():
            return candidate.resolve()
    return None


def _is_venv_own_python(shebang: Path, launcher: Path) -> bool:
    """True when the shebang names this venv's Python, not another prefix.

    Compare parent DIRECTORIES by filesystem identity (samefile), not lexical
    path strings. macOS default TMPDIR is ``/var/...`` which aliases
    ``/private/var/...``; ``/tmp`` aliases ``/private/tmp``. Do not realpath
    the interpreter file itself: two venvs can share the same base Python.
    """
    try:
        same_parent = shebang.parent.samefile(launcher.parent)
    except OSError:
        same_parent = os.path.realpath(str(shebang.parent)) == os.path.realpath(
            str(launcher.parent)
        )
    if not same_parent:
        return False
    name = shebang.name.lower()
    return name == "python.exe" or name.startswith("python")


def interpreter_from_launcher(launcher: Path) -> Path:
    """Return the venv interpreter named by an absolute shebang.

    Do not realpath the shebang: ``$VENV/bin/python`` is usually a symlink to
    the system interpreter, and resolving it drops ``pyvenv.cfg``. Do not
    guess a sibling for ``#!/usr/bin/env ...``, a missing shebang, or any
    interpreter that is not this venv's own Python. Pip's normal
    console-script shebang is an absolute path to ``$VENV/bin/python``.
    """
    data = launcher.read_bytes()
    if not data.startswith(b"#!"):
        raise UnsupportedShebangError(
            f"launcher {launcher} has no shebang; "
            "env-based and missing shebangs are not accepted"
        )
    first = data.splitlines()[0][2:].decode("utf-8", "replace").strip()
    if not first:
        raise UnsupportedShebangError(
            f"launcher {launcher} has an empty shebang; "
            "env-based and missing shebangs are not accepted"
        )
    parts = first.split()
    shebang = Path(parts[0])
    if shebang.name in {"env", "env.exe"} or not shebang.is_absolute():
        raise UnsupportedShebangError(
            f"launcher {launcher} uses unsupported shebang {first!r}; "
            "only an absolute path to the venv's own Python is accepted"
        )
    if not shebang.exists():
        raise UnsupportedShebangError(
            f"launcher shebang interpreter not found: {shebang}"
        )
    if not _is_venv_own_python(shebang, launcher):
        raise UnsupportedShebangError(
            f"launcher {launcher} shebang {first!r} is not this venv's own Python"
        )
    return shebang


def launcher_body_after_shebang(data: bytes) -> bytes:
    """Return launcher bytes after the shebang line (validated separately)."""
    if not data.startswith(b"#!"):
        return data
    newline = data.find(b"\n")
    if newline < 0:
        return b""
    return data[newline + 1 :]


def console_script_target(launcher: Path) -> str | None:
    """Return the pinned entry point only when the body is an exact known template.

    No regex. A file that merely contains ``from runspecimen.cli import main``
    but does not call ``main`` is refused.
    """
    try:
        data = launcher.read_bytes()
    except OSError:
        return None
    body = launcher_body_after_shebang(data)
    if body in KNOWN_CONSOLE_SCRIPT_BODIES:
        return PINNED_CONSOLE_SCRIPT_TARGET
    return None


def is_allowed_venv_bin_name(name: str) -> bool:
    """True for python/pip/activate/runspecimen names ``python -m venv`` plus pip write."""
    if name in _VENV_BIN_EXACT:
        return True
    stem = name[:-4] if name.endswith(".exe") else name
    if stem.startswith("python"):
        rest = stem[len("python") :]
        return rest == "" or all(ch.isdigit() or ch in ".t" for ch in rest)
    if stem.startswith("pip"):
        rest = stem[len("pip") :]
        return rest == "" or all(ch.isdigit() or ch == "." for ch in rest)
    return False


def scan_venv_bin(bin_dir: Path) -> list[str]:
    """Refuse unexpected files in the launcher's directory (WH-01)."""
    findings: list[str] = []
    if not bin_dir.is_dir():
        return [f"venv bin directory is missing: {bin_dir}"]
    try:
        entries = sorted(bin_dir.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        return [f"cannot list venv bin directory {bin_dir}: {exc}"]
    for path in entries:
        name = path.name
        if name in {".", ".."}:
            continue
        if path.is_symlink():
            # python/python3 are expected symlinks; still name-check.
            if not is_allowed_venv_bin_name(name):
                findings.append(f"unexpected symlink in venv bin: {path}")
            continue
        if path.is_dir() or name == "__pycache__":
            findings.append(f"unexpected directory in venv bin: {path}")
            continue
        lowered = name.lower()
        if lowered.endswith(_BIN_FORBIDDEN_SUFFIXES) or lowered.endswith(".so"):
            findings.append(f"unexpected module or extension in venv bin: {path}")
            continue
        if not is_allowed_venv_bin_name(name):
            findings.append(f"unexpected file in venv bin: {path}")
    return findings


def scan_package_bytecode(package_dir: Path) -> list[str]:
    """Refuse any ``.pyc`` / ``__pycache__`` under the installed package."""
    findings: list[str] = []
    if not package_dir.is_dir():
        return findings
    for path in sorted(package_dir.rglob("*")):
        try:
            relative_parts = path.relative_to(package_dir).parts
        except ValueError:
            continue
        if path.name == "__pycache__" or "__pycache__" in relative_parts:
            findings.append(f"bytecode cache path: {path}")
            continue
        if path.suffix.lower() in {".pyc", ".pyo"}:
            findings.append(f"bytecode file: {path}")
    return findings


def launcher_sysconfig(interpreter: Path, env: dict[str, str]) -> dict[str, str]:
    script = (
        "import json, sys, sysconfig\n"
        "from pathlib import Path\n"
        "print(json.dumps({\n"
        "    'purelib': str(Path(sysconfig.get_path('purelib')).resolve()),\n"
        "    'prefix': str(Path(sys.prefix).resolve()),\n"
        "    'base_prefix': str(Path(sys.base_prefix).resolve()),\n"
        "    'stdlib': str(Path(sysconfig.get_path('stdlib')).resolve()),\n"
        "    'platstdlib': str(Path(sysconfig.get_path('platstdlib')).resolve()),\n"
        "    'executable': str(Path(sys.executable).resolve()),\n"
        "}))\n"
    )
    result = subprocess.run(
        [str(interpreter), "-I", "-B", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"launcher interpreter sysconfig failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    payload = json.loads(result.stdout)
    return {
        key: str(payload[key])
        for key in ("purelib", "prefix", "base_prefix", "stdlib", "platstdlib", "executable")
    }


def probe_launcher_doctor(launcher: Path, env: dict[str, str]) -> dict[str, Any]:
    """Run the real console-script process (WH-01). ``python -c`` is not this probe."""
    with tempfile.TemporaryDirectory(prefix="rs-verify-doctor-") as raw:
        workspace = Path(raw) / "ws"
        workspace.mkdir()
        result = subprocess.run(
            [str(launcher), "doctor", "--workspace", str(workspace)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    if result.returncode not in (0, 1):
        raise RuntimeError(
            "launcher doctor probe failed: "
            + (result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}")
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"launcher doctor did not print JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("launcher doctor JSON is not an object")
    return payload


def _under_roots(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved_root = root.resolve()
        except OSError:
            resolved_root = root
        try:
            resolved.relative_to(resolved_root)
            return True
        except ValueError:
            continue
    return False


def _samefile(left: Path, right: Path) -> bool:
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def launcher_module_origin_findings(
    origins: dict[str, Any] | None,
    *,
    stdlib_roots: list[Path],
    hashed_files: set[Path],
    launcher: Path | None = None,
    venv_prefix: Path | None = None,
) -> list[str]:
    """Loaded modules must be stdlib, hashed wheel files, or interpreter-owned.

    The console-script process has ``__main__`` equal to the launcher file
    (not a wheel member). Debian/Ubuntu ``sitecustomize`` lives under
    ``/etc/pythonX.Y/`` outside the venv; QA-HOOKS-03 already treats that as
    interpreter-owned. Anything else inside the venv prefix that is not a
    hash-verified wheel file is refused (stdlib-shadowing ``bin/json.py``).
    ``json`` and ``re`` must still resolve under stdlib.
    """
    if not origins:
        return ["launcher doctor did not report loaded_module_origins"]
    findings: list[str] = []
    launcher_resolved = launcher.resolve() if launcher is not None else None
    prefix_resolved = venv_prefix.resolve() if venv_prefix is not None else None
    bin_dir = launcher_resolved.parent if launcher_resolved is not None else None
    for name, origin in sorted(origins.items(), key=lambda item: item[0]):
        if origin is None:
            continue
        text = str(origin)
        if text.startswith("<"):
            continue
        try:
            resolved = Path(text).resolve()
        except OSError:
            findings.append(f"loaded module {name} origin is not a readable path: {origin}")
            continue
        if name in {"json", "re"} and not _under_roots(resolved, stdlib_roots):
            findings.append(
                f"loaded module {name} origin {resolved} is not the interpreter stdlib"
            )
            continue
        if (
            name == "__main__"
            and launcher_resolved is not None
            and _samefile(resolved, launcher_resolved)
        ):
            continue
        if bin_dir is not None and _under_roots(resolved, [bin_dir]):
            if not (
                name == "__main__"
                and launcher_resolved is not None
                and _samefile(resolved, launcher_resolved)
            ):
                findings.append(
                    f"loaded module {name} origin {resolved} is in the venv bin directory"
                )
            continue
        if _under_roots(resolved, stdlib_roots):
            continue
        if resolved in hashed_files or any(_samefile(resolved, item) for item in hashed_files):
            continue
        if prefix_resolved is not None and not _under_roots(resolved, [prefix_resolved]):
            # Interpreter / distro paths (Debian sitecustomize, apport hook).
            continue
        findings.append(
            f"loaded module {name} origin {resolved} is not stdlib and is not a "
            "hash-verified file of the pinned wheel"
        )
    return findings


def probe_effective_origins(interpreter: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        [str(interpreter), "-I", "-B", "-c", PROBE_SCRIPT],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"launcher origin probe failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    payload = json.loads(result.stdout)
    return payload


def package_origin(module_file: Path) -> Path:
    resolved = module_file.resolve()
    if resolved.name == "__init__.py":
        return resolved.parent
    return resolved.parent


def _member_candidates(modname: str) -> list[str]:
    if modname == "runspecimen":
        return ["runspecimen/__init__.py"]
    if not modname.startswith("runspecimen."):
        return []
    rest = modname.split(".", 1)[1]
    rel = rest.replace(".", "/")
    return [f"runspecimen/{rel}.py", f"runspecimen/{rel}/__init__.py"]


def origins_bound_to_package(
    *,
    runspecimen_file: Path,
    cli_file: Path,
    package_dir: Path,
    site_packages: Path,
    loaded: dict[str, Any] | None = None,
    hashed_py_members: list[str] | None = None,
) -> tuple[bool, str | None]:
    expected_pkg = package_dir.resolve()
    site_packages = site_packages.resolve()
    rs_origin = package_origin(runspecimen_file)
    cli_origin = package_origin(cli_file)
    expected_init = expected_pkg / "__init__.py"
    expected_cli = expected_pkg / "cli.py"
    if rs_origin != expected_pkg:
        return False, (
            f"effective runspecimen origin {rs_origin} != verified package directory {expected_pkg}"
        )
    if runspecimen_file.resolve() != expected_init.resolve():
        return False, (
            f"effective runspecimen.__file__ {runspecimen_file.resolve()} "
            f"!= {expected_init.resolve()}"
        )
    if cli_origin != expected_pkg:
        return False, (
            f"effective CLI module origin {cli_origin} != verified package directory {expected_pkg}"
        )
    if cli_file.resolve() != expected_cli.resolve():
        return False, (
            f"effective runspecimen.cli.__file__ {cli_file.resolve()} "
            f"!= {expected_cli.resolve()}"
        )
    hashed = set(hashed_py_members or [])
    if "runspecimen/approve.py" in hashed:
        expected_approve = expected_pkg / "approve.py"
        if loaded and loaded.get("runspecimen.approve"):
            got = Path(str(loaded["runspecimen.approve"])).resolve()
            if got != expected_approve.resolve():
                return False, (
                    f"effective runspecimen.approve origin {got} "
                    f"!= hashed installed member {expected_approve.resolve()}"
                )
    if "runspecimen/present.py" in hashed:
        expected_present = expected_pkg / "present.py"
        if not loaded or not loaded.get("runspecimen.present"):
            return False, (
                "runspecimen.present was not loaded but is a hashed installed member "
                f"{expected_present.resolve()}"
            )
        got = Path(str(loaded["runspecimen.present"])).resolve()
        if got != expected_present.resolve():
            return False, (
                f"effective runspecimen.present origin {got} "
                f"!= hashed installed member {expected_present.resolve()}"
            )
    if loaded:
        for name in sorted(loaded):
            origin = loaded[name]
            if origin is None:
                return False, f"loaded {name} has no __file__"
            got = Path(str(origin)).resolve()
            candidates = _member_candidates(name)
            if not candidates:
                return False, f"loaded module {name} is not a runspecimen.* member"
            matched = None
            for member in candidates:
                installed = (site_packages / member).resolve()
                if installed.is_file() and installed == got:
                    matched = member
                    break
            if matched is None:
                return False, (
                    f"effective {name} origin {got} is not a hashed installed "
                    f"runspecimen member under {site_packages}"
                )
            if hashed and matched not in hashed:
                return False, (
                    f"effective {name} origin {got} member {matched} is not a hashed wheel member"
                )
    return True, None


def _normalize_pth_import_line(line: str) -> str:
    return line.replace("\t", " ").strip()


def scan_pth_files(site_packages: Path) -> list[dict[str, Any]]:
    """Reject .pth path prepends and every executable ``import`` line.

    Filename and owner are not trust. setuptools' ``distutils-precedence.pth``
    is refused the same as any other import hook. There is no known-safe body.
    """
    findings: list[dict[str, Any]] = []
    site_packages = site_packages.resolve()
    for pth in sorted(site_packages.glob("*.pth")):
        text = pth.read_text(encoding="utf-8", errors="replace")
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("import ") or line.startswith("import\t"):
                reason = "executable import .pth line"
                if pth.name == "distutils-precedence.pth" or "_distutils_hack" in line:
                    reason = (
                        "setuptools distutils-precedence.pth runs extra startup code; "
                        "follow the acceptance sheet"
                    )
                if "sys.path" in line:
                    reason = "pth prepends or mutates sys.path outside the verified install"
                findings.append({
                    "path": str(pth),
                    "line": lineno,
                    "reason": reason,
                    "text": _normalize_pth_import_line(line),
                })
                continue
            candidate = Path(line)
            if not candidate.is_absolute():
                candidate = site_packages / candidate
            resolved = candidate.resolve()
            try:
                resolved.relative_to(site_packages)
            except ValueError:
                findings.append({
                    "path": str(pth),
                    "line": lineno,
                    "reason": f"pth adds path outside the verified install: {resolved}",
                    "text": line,
                })
    return findings


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _stdlib_roots_from_origins(origins: dict[str, Any] | None) -> list[Path]:
    roots: list[Path] = []
    if origins:
        for item in origins.get("stdlib") or []:
            roots.append(Path(str(item)).resolve())
    if not roots:
        try:
            import sysconfig as _sysconfig
            for key in ("stdlib", "platstdlib"):
                value = _sysconfig.get_path(key)
                if value:
                    roots.append(Path(value).resolve())
        except Exception:
            pass
    return roots


def _path_is_interpreter_stdlib(path: Path, stdlib_roots: list[Path]) -> bool:
    resolved = path.resolve()
    for root in stdlib_roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def startup_customization_findings(
    origins: dict[str, Any] | None,
    *,
    prefix: Path,
    site_packages: Path,
) -> list[str]:
    """Reject sitecustomize/usercustomize that is importable from the target venv.

    The trusted interpreter includes its own stdlib and distro sitecustomize
    (Debian/Ubuntu ``/etc/pythonX.Y/sitecustomize.py``). A sitecustomize.py
    inside the venv prefix or site-packages is extra startup and is refused.
    usercustomize is refused when it is importable (user site enabled).
    """
    findings: list[str] = []
    prefix = prefix.resolve()
    site_packages = site_packages.resolve()
    stdlib_roots = _stdlib_roots_from_origins(origins)
    for name in ("sitecustomize.py", "sitecustomize.pyc"):
        cand = site_packages / name
        if cand.is_file():
            findings.append(f"unvetted sitecustomize on the import path: {cand.resolve()}")
    if origins is not None:
        sitecustomize = origins.get("sitecustomize")
        if sitecustomize:
            loaded = Path(str(sitecustomize)).resolve()
            already = any(loaded.as_posix() in item for item in findings)
            in_venv = _under(loaded, prefix)
            interpreter_owned = _path_is_interpreter_stdlib(loaded, stdlib_roots)
            if not already and in_venv and not interpreter_owned:
                findings.append(f"unvetted sitecustomize on the import path: {loaded}")
        enable_user_site = bool(origins.get("enable_user_site"))
        usercustomize = origins.get("usercustomize")
        if usercustomize and enable_user_site:
            findings.append(
                "unvetted usercustomize on the import path while user site is enabled: "
                f"{usercustomize}"
            )
    return findings


def verify_launcher_install(*, wheel: Path, launcher: Path | None) -> dict[str, Any]:
    incoming_overrides = import_overrides()
    env = sanitized_env()
    report: dict[str, Any] = {
        "ok": False,
        "wheel": str(wheel.resolve()) if wheel else None,
        "import_overrides": incoming_overrides,
        "pth_findings": [],
        "startup_findings": [],
        "meta_path_findings": [],
        "path_hook_findings": [],
        "lazy_loaded_runspecimen": {},
        "origins_bound": False,
        "launcher": None,
        "interpreter": None,
        "prefix": None,
        "console_script_target": None,
        "verified_package_dir": None,
        "runspecimen_file": None,
        "cli_file": None,
        "approve_file": None,
        "present_file": None,
        "loaded_runspecimen": {},
        "runspecimen_version": None,
        "bin_findings": [],
        "launcher_module_findings": [],
        "loaded_module_origins": {},
    }
    resolved_launcher = launcher.resolve() if launcher is not None else discover_launcher()
    if resolved_launcher is None or not resolved_launcher.is_file():
        report["message"] = f"absolute launcher not found: {launcher or '(discovered)'}"
        return report
    report["launcher"] = str(resolved_launcher)
    report["console_script_target"] = console_script_target(resolved_launcher)
    bin_findings = scan_venv_bin(resolved_launcher.parent)
    report["bin_findings"] = bin_findings
    try:
        interpreter = interpreter_from_launcher(resolved_launcher)
    except (OSError, UnsupportedShebangError) as exc:
        report["message"] = str(exc)
        return report
    report["interpreter"] = str(interpreter)
    if not interpreter.exists():
        report["message"] = f"launcher interpreter not found: {interpreter}"
        return report
    try:
        cfg = launcher_sysconfig(interpreter, env)
    except (RuntimeError, json.JSONDecodeError, KeyError) as exc:
        report["message"] = str(exc)
        return report
    report["prefix"] = cfg["prefix"]
    site = Path(cfg["purelib"]).resolve()
    package_dir = (site / "runspecimen").resolve()
    report["verified_package_dir"] = str(package_dir)
    report.update(verify_site_against_wheel(site_packages=site, wheel=wheel))
    report["import_overrides"] = incoming_overrides
    report["launcher"] = str(resolved_launcher)
    report["interpreter"] = str(interpreter)
    report["prefix"] = cfg["prefix"]
    report["console_script_target"] = console_script_target(resolved_launcher)
    report["verified_package_dir"] = str(package_dir)

    pth_findings = scan_pth_files(site) + scan_virtualenv_artifacts(site)
    report["pth_findings"] = pth_findings

    bytecode_findings = scan_package_bytecode(package_dir)
    report["bytecode_findings"] = bytecode_findings
    target = console_script_target(resolved_launcher)
    report["console_script_target"] = target

    hashed_py_members = list(report.get("hashed_py_members") or [])
    hashed_members = list(report.get("hashed_members") or hashed_py_members)
    hashed_files = {
        (site / member).resolve()
        for member in hashed_members
        if (site / member).is_file()
    }
    stdlib_roots = [
        Path(cfg[key]).resolve()
        for key in ("stdlib", "platstdlib")
        if cfg.get(key)
    ]
    launcher_module_findings: list[str] = []
    loaded_module_origins: dict[str, Any] = {}
    if not bytecode_findings and not bin_findings:
        try:
            doctor = probe_launcher_doctor(resolved_launcher, env)
            loaded_module_origins = dict(doctor.get("loaded_module_origins") or {})
            launcher_module_findings = launcher_module_origin_findings(
                loaded_module_origins or None,
                stdlib_roots=stdlib_roots,
                hashed_files=hashed_files,
                launcher=resolved_launcher,
                venv_prefix=Path(cfg["prefix"]),
            )
        except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            launcher_module_findings = [str(exc)]
    elif bin_findings:
        launcher_module_findings = list(bin_findings)
    report["loaded_module_origins"] = loaded_module_origins
    report["launcher_module_findings"] = launcher_module_findings
    bind_error: str | None = "effective origins were not probed"
    startup_findings: list[str] = []
    origins: dict[str, Any] | None = None
    # Do not import runspecimen while unhashed bytecode is sitting next to
    # hashed sources: -B still loads an existing .pyc.
    if not bytecode_findings:
        try:
            origins = probe_effective_origins(interpreter, env)
        except (RuntimeError, json.JSONDecodeError, KeyError) as exc:
            origins = None
            bind_error = str(exc)
    else:
        bind_error = (
            "installed runspecimen package contains bytecode "
            "(__pycache__ / .pyc); install with pip install --no-compile "
            "and PYTHONDONTWRITEBYTECODE=1"
        )
    if origins is not None:
        rs_file = Path(origins["runspecimen_file"])
        cli_file = Path(origins["cli_file"])
        report["runspecimen_file"] = str(rs_file)
        report["cli_file"] = str(cli_file)
        if origins.get("approve_file"):
            report["approve_file"] = str(origins["approve_file"])
        if origins.get("present_file"):
            report["present_file"] = str(origins["present_file"])
        loaded = dict(origins.get("loaded_runspecimen") or {})
        lazy_loaded = dict(origins.get("lazy_loaded_runspecimen") or {})
        report["loaded_runspecimen"] = loaded
        report["lazy_loaded_runspecimen"] = lazy_loaded
        report["meta_path_findings"] = list(origins.get("unexpected_meta_path") or [])
        report["path_hook_findings"] = list(origins.get("unexpected_path_hooks") or [])
        merged = dict(loaded)
        merged.update(lazy_loaded)
        report["runspecimen_version"] = origins.get("version")
        bound, bind_error = origins_bound_to_package(
            runspecimen_file=rs_file,
            cli_file=cli_file,
            package_dir=package_dir,
            site_packages=site,
            loaded=merged,
            hashed_py_members=hashed_py_members,
        )
        report["origins_bound"] = bound
        startup_findings = startup_customization_findings(
            origins,
            prefix=Path(cfg["prefix"]),
            site_packages=site,
        )
        if origins.get("pycache_prefix"):
            startup_findings.append(
                f"sys.pycache_prefix is set: {origins.get('pycache_prefix')}"
            )
        if not origins.get("dont_write_bytecode"):
            startup_findings.append("probe did not run with bytecode writing disabled")
        if origins.get("cached_bytecode"):
            startup_findings.append(
                "loaded runspecimen modules have existing bytecode: "
                + ", ".join(
                    str(item.get("cached") or item)
                    for item in origins["cached_bytecode"]
                )
            )
        if origins.get("sourceless_bytecode"):
            startup_findings.append(
                "loaded sourceless runspecimen bytecode: "
                + ", ".join(
                    str(item.get("file") or item)
                    for item in origins["sourceless_bytecode"]
                )
            )
    else:
        bound = False
        report["origins_bound"] = False
        startup_findings = startup_customization_findings(
            None,
            prefix=Path(cfg["prefix"]),
            site_packages=site,
        )
    report["startup_findings"] = startup_findings

    failures: list[str] = []
    if target != PINNED_CONSOLE_SCRIPT_TARGET:
        failures.append(
            "console-script body is not a pinned pip template for "
            f"{PINNED_CONSOLE_SCRIPT_TARGET}"
        )
    if bin_findings:
        failures.append(
            "venv bin contains files that python -m venv plus pip plus this "
            "wheel do not create: " + "; ".join(bin_findings)
        )
    if launcher_module_findings:
        failures.append(
            "real launcher process loaded a module that is not stdlib and is "
            "not a hash-verified wheel file: " + "; ".join(launcher_module_findings)
        )
    if bytecode_findings:
        failures.append(
            "installed runspecimen package contains bytecode "
            "(__pycache__ / .pyc); install with pip install --no-compile "
            "and PYTHONDONTWRITEBYTECODE=1"
        )
    if incoming_overrides:
        failures.append("import overrides: " + "; ".join(incoming_overrides))
    hook_file = _first_hook_file(
        pth_findings,
        startup_findings,
        list(report.get("meta_path_findings") or []),
        list(report.get("path_hook_findings") or []),
    )
    if hook_file:
        failures.append(hook_refusal_message(hook_file))
    if not bound:
        failures.append(bind_error or "effective origins are not bound to the verified package directory")
    if not report.get("ok"):
        failures.append(str(report.get("message") or "installed tree does not match the pinned wheel"))

    if failures:
        report["ok"] = False
        report["message"] = "; ".join(failures)
        return report
    report["ok"] = True
    report["message"] = (
        f"installed tree matches wheel {report['wheel_sha256']} "
        f"({report['checked']} files); origins bound to {package_dir}; "
        "no import overrides"
    )
    return report


def verify_current_interpreter(wheel: Path, launcher: Path | None = None) -> dict[str, Any]:
    """Backward-compatible wrapper used by tests and the CLI."""
    return verify_launcher_install(wheel=wheel, launcher=launcher)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True, help="Absolute path to the pinned wheel")
    parser.add_argument(
        "--launcher",
        type=Path,
        default=None,
        help="Absolute path to the venv console script (default: $prefix/bin/runspecimen)",
    )
    args = parser.parse_args(argv)
    report = verify_launcher_install(wheel=args.wheel, launcher=args.launcher)
    printable = {
        key: report[key]
        for key in (
            "ok",
            "message",
            "wheel",
            "wheel_sha256",
            "site_packages",
            "verified_package_dir",
            "launcher",
            "interpreter",
            "prefix",
            "runspecimen_file",
            "cli_file",
            "approve_file",
            "present_file",
            "console_script_target",
            "origins_bound",
            "loaded_runspecimen",
            "import_overrides",
            "pth_findings",
            "startup_findings",
            "bytecode_findings",
            "bin_findings",
            "launcher_module_findings",
            "meta_path_findings",
            "path_hook_findings",
            "lazy_loaded_runspecimen",
            "runspecimen_version",
            "checked",
            "missing",
            "mismatches",
            "extra_py",
        )
        if key in report
    }
    print(json.dumps(printable, indent=2, sort_keys=True))
    record = report.get("dist_info_record")
    if isinstance(record, dict):
        print("--- installed dist-info RECORD ---")
        print(f"path {record['path']}")
        print(f"sha256 {record['sha256']}")
        print(record["text"], end="" if str(record["text"]).endswith("\n") else "\n")
    else:
        print("--- installed dist-info RECORD ---")
        print("absent")
    direct = report.get("direct_url_json")
    if isinstance(direct, dict):
        print("--- installed direct_url.json ---")
        print(f"path {direct['path']}")
        print(f"sha256 {direct['sha256']}")
        print(direct["text"], end="" if str(direct["text"]).endswith("\n") else "\n")
    else:
        print("--- installed direct_url.json ---")
        print("absent")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
