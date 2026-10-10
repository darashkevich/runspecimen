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

The check has two phases. The static phase uses the base interpreter named
by ``pyvenv.cfg`` (never the venv's python) with ``-I -S``. It refuses to
run at all when this process was itself started by a virtual environment's
Python. It does not run any file from the venv. It asks that interpreter's ``site`` module which
directories this venv would process, including Debian ``dist-packages`` and
paths driven by ``pyvenv.cfg``. The user site is included only when that
``site`` logic would enable it. A normal venv (``include-system-site-packages``
false) turns the user site off, so a ``usercustomize`` there is not startup.
The scan refuses executable ``.pth`` lines, every directory or zip a ``.pth``
path line would add (followed recursively), ``sitecustomize`` /
``usercustomize`` in every importable form (source, bytecode, extension, or
package), bytecode under ``dist-packages``, unexpected ``bin/`` files, a
launcher body that is not a pinned pip template, and a ``pyvenv.cfg`` whose
``home`` is not that base interpreter or that turns on system site-packages.
``python``, ``python3``, ``python3.X``, and the CPython 3.14 ``𝜋thon`` name
must be a symlink to that base interpreter, or a byte-for-byte copy of it.
Only a clean static phase runs a probe, and the probe uses the base
interpreter with ``-I -S`` and an explicit site-packages path. It does not
execute the venv's Python, so site hooks and the Debian ``sitecustomize``
import chain do not run.

Stdlib means the base interpreter's own library directories, minus every
site-packages or dist-packages directory and minus anything under the venv.
A path is not stdlib just because a broader directory contains it.

The probe runs with ``-I -S -B`` on that base interpreter after the scan.
``-S`` skips site startup, so a ``.pth`` file, ``sitecustomize``, and the
Debian ``sitecustomize`` import chain (``apport_python_hook``) do not run.
Any module that chain would import is still refused when it is present on
the venv's effective path. Any ``.pyc`` / ``__pycache__`` under the installed
runspecimen package is refused (timestamp-based, hash-based, any
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

Start this script with the base interpreter, not the venv's python. The
venv's python runs site hooks before the first line of this file. Follow
``$VENV/bin/python`` to the real binary, then:

  env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP -u PYTHONPYCACHEPREFIX \\
    PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \\
    "$BASE_PY" -I scripts/verify_installed_wheel.py \\
    --wheel /abs/path.whl --launcher "$VENV/bin/runspecimen"
"""

from __future__ import annotations

import argparse
import ast
import errno
import hashlib
import json
import os
import stat
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
    for raw in globals().get('_STDLIB_EXCLUSIONS') or []:
        try:
            resolved.relative_to(Path(raw))
            return False
        except ValueError:
            continue
    roots = globals().get('_TRUSTED_STDLIB') or _STDLIB_ROOTS
    for root in roots:
        try:
            resolved.relative_to(root if isinstance(root, Path) else Path(root))
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


def _plain_scan_refusal(text: str) -> bool:
    """Sentences that must be printed as themselves, not as a file name."""
    return text.startswith((
        "pyvenv.cfg ",
        "too many directories",
        "cannot ",
        "followed too many",
    ))


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
    try:
        shebang.lstat()
    except OSError:
        raise UnsupportedShebangError(
            f"launcher shebang interpreter not found: {shebang}"
        )
    _final, walk_error = _final_regular_file(shebang)
    if walk_error:
        raise UnsupportedShebangError(walk_error)
    if _final is None:
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
    try:
        paths = sorted(package_dir.rglob("*"))
    except OSError as exc:
        return [f"cannot list the installed package: {package_dir} ({exc})"]
    for path in paths:
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


def probe_launcher_doctor(
    launcher: Path,
    env: dict[str, str],
    *,
    base: Path,
    extra_paths: list[Path],
) -> dict[str, Any]:
    """Run the known launcher body on the verified base interpreter.

    The venv's ``bin/python`` is not executed. ``-S`` skips site startup, so
    a ``.pth`` file, ``sitecustomize``, and Debian's apport hook do not run.
    The launcher file itself was already checked against a pinned pip template.
    """
    script = (
        "import runpy, sys\n"
        "from pathlib import Path\n"
        "launcher, workspace = sys.argv[1], sys.argv[2]\n"
        "for item in sys.argv[3:]:\n"
        "    if item not in sys.path:\n"
        "        sys.path.append(item)\n"
        "sys.argv = [launcher, 'doctor', '--workspace', workspace]\n"
        "runpy.run_path(launcher, run_name='__main__')\n"
    )
    with tempfile.TemporaryDirectory(prefix="rs-verify-doctor-") as raw:
        workspace = Path(raw) / "ws"
        workspace.mkdir()
        result = subprocess.run(
            [
                str(base),
                "-I",
                "-S",
                "-B",
                "-c",
                script,
                str(launcher),
                str(workspace),
                *[str(path) for path in extra_paths],
            ],
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


def path_is_real_stdlib(path: Path, stdlib_roots: list[Path], exclusions: list[Path]) -> bool:
    """True only for the base interpreter's library, not site or the venv.

    Prefix containment alone is not enough: Debian's stdlib directory also
    contains ``dist-packages``, and a venv ``platstdlib`` contains
    ``site-packages``. Those directories are excluded.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in exclusions:
        try:
            resolved.relative_to(root.resolve())
            return False
        except ValueError:
            continue
    for root in stdlib_roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def launcher_module_origin_findings(
    origins: dict[str, Any] | None,
    *,
    stdlib_roots: list[Path],
    hashed_files: set[Path],
    launcher: Path | None = None,
    venv_prefix: Path | None = None,
    exclusions: list[Path] | None = None,
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
        if name in {"json", "re"} and not path_is_real_stdlib(
            resolved, stdlib_roots, exclusions or []
        ):
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
        if path_is_real_stdlib(resolved, stdlib_roots, exclusions or []):
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


def probe_effective_origins(
    interpreter: Path,
    env: dict[str, str],
    *,
    trusted_stdlib: list[Path] | None = None,
    exclusions: list[Path] | None = None,
    extra_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Import the installed tree with the base interpreter and ``-I -S``.

    ``extra_paths`` is the verified site-packages directory. Site startup is
    not run, so venv ``.pth`` files and ``sitecustomize`` do not run.
    """
    prelude = "import sys\n"
    for path in extra_paths or []:
        prelude += f"if {str(path)!r} not in sys.path:\n    sys.path.append({str(path)!r})\n"
    if trusted_stdlib is not None or exclusions is not None:
        prelude += (
            "_TRUSTED_STDLIB = "
            + json.dumps([str(path) for path in (trusted_stdlib or [])])
            + "\n_STDLIB_EXCLUSIONS = "
            + json.dumps([str(path) for path in (exclusions or [])])
            + "\n"
        )
    result = subprocess.run(
        [str(interpreter), "-I", "-S", "-B", "-c", prelude + PROBE_SCRIPT],
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


def read_pth_text(path: Path) -> tuple[str | None, str | None]:
    """Read a .pth file as UTF-8. A problem string means the file was not scanned."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, f"cannot read this .pth file: {path} ({exc})"
    if b"\x00" in data:
        return None, (
            f"cannot read this .pth file: {path} (it contains a null byte)"
        )
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, (
            f"cannot read this .pth file: {path} (it is not UTF-8 text)"
        )


def _pth_problem(path: Path, reason: str, *, line: int = 0, text: str = "") -> dict[str, Any]:
    return {"path": str(path), "line": line, "reason": reason, "text": text}


def scan_pth_files(site_packages: Path) -> list[dict[str, Any]]:
    """Reject .pth path prepends and every executable ``import`` line.

    Filename and owner are not trust. setuptools' ``distutils-precedence.pth``
    is refused the same as any other import hook. There is no known-safe body.
    A file that cannot be decoded is a refusal, not a skip.
    """
    findings: list[dict[str, Any]] = []
    try:
        site_packages = site_packages.resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, RuntimeError) or getattr(exc, "errno", None) == errno.ELOOP:
            return [_pth_problem(
                site_packages,
                f"cannot resolve this path because it is a symlink loop: {site_packages}",
            )]
        return [_pth_problem(site_packages, f"cannot resolve the site directory {site_packages}: {exc}")]
    try:
        pth_files = sorted(site_packages.glob("*.pth"))
    except OSError as exc:
        return [_pth_problem(site_packages, f"cannot list .pth files in {site_packages}: {exc}")]
    for pth in pth_files:
        text, problem = read_pth_text(pth)
        if problem or text is None:
            findings.append(_pth_problem(pth, problem or f"cannot read this .pth file: {pth}"))
            continue
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
            try:
                candidate = Path(line)
                if not candidate.is_absolute():
                    candidate = site_packages / candidate
                resolved = candidate.resolve()
            except (OSError, ValueError, RuntimeError) as exc:
                if isinstance(exc, RuntimeError) or getattr(exc, "errno", None) == errno.ELOOP:
                    reason = f"cannot resolve this path because it is a symlink loop: {candidate}"
                else:
                    reason = f"cannot resolve a path named by this .pth file: {exc}"
                findings.append(_pth_problem(
                    pth,
                    reason,
                    line=lineno,
                    text=line,
                ))
                continue
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


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return os.path.realpath(str(left)) == os.path.realpath(str(right))


def _parse_pyvenv_cfg(path: Path) -> tuple[dict[str, str], str | None]:
    """Parse ``pyvenv.cfg``. A repeated ``home`` or ``executable`` is refused.

    This check does not guess which copy CPython would keep. A repeated
    setting is a refusal in plain English.
    """
    data: dict[str, str] = {}
    seen: dict[str, int] = {}
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        name = key.strip().lower()
        if name in {"home", "executable"}:
            seen[name] = seen.get(name, 0) + 1
        data[name] = value.strip()
    if seen.get("home", 0) > 1 or seen.get("executable", 0) > 1:
        return data, (
            "pyvenv.cfg repeats home or executable. "
            "This check does not accept a repeated setting: "
            f"{path}"
        )
    return data, None


def base_interpreter_in_use() -> Path:
    """Real path of the file that was started.

    ``sys._base_executable`` is not this file. A venv's Python reports the
    base there even when this process was started by the venv symlink.
    """
    return Path(os.path.realpath(sys.executable))


def _pyvenv_cfg_above(executable: Path) -> Path | None:
    """``pyvenv.cfg`` in the started file's directory or a parent.

    The walk uses the path that was started, not its realpath. A venv
    ``bin/python`` is often a symlink to the base interpreter; walking the
    real path would miss the venv's ``pyvenv.cfg``.
    """
    current = Path(os.path.abspath(str(executable)))
    seen: set[str] = set()
    while True:
        key = str(current)
        if key in seen:
            return None
        seen.add(key)
        candidate = current / "pyvenv.cfg"
        try:
            present = candidate.is_file()
        except OSError as exc:
            raise OSError(f"pyvenv.cfg cannot be read: {candidate} ({exc})") from exc
        if present:
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def running_interpreter_problem() -> str | None:
    """Refuse when this process is a virtual environment's Python.

    ``-I -S`` makes ``sys.prefix == sys.base_prefix``, so the prefix compare
    is not enough. A ``pyvenv.cfg`` next to or above the started file is
    also a venv.
    """
    started_venv = sys.prefix != sys.base_prefix
    if not started_venv:
        try:
            started_venv = _pyvenv_cfg_above(Path(sys.executable)) is not None
        except OSError as exc:
            return str(exc)
    if not started_venv:
        return None
    return (
        "This check was started with a virtual environment's Python. "
        "Start it with the base Python, using -I -S, so site hooks do not run."
    )


def _interpreter_names_for_home(base: Path, executable: str) -> list[str]:
    """File names ``pyvenv.cfg`` home may use for this base interpreter."""
    names: list[str] = []

    def add(name: str) -> None:
        if name and name not in names:
            names.append(name)

    add("python")
    add("python3")
    add(f"python{sys.version_info[0]}.{sys.version_info[1]}")
    add(base.name)
    if executable:
        add(Path(executable).name)
    return names


def _pyvenv_names_base(home: str, executable: str, base: Path) -> bool:
    """True when ``home/<name>`` and ``executable`` both name ``base``.

    Comparison is filesystem identity (``samefile`` / ``realpath``). Neither
    file is executed. Python 3.9 and 3.10 omit ``executable``; ``home/<name>``
    is enough in that case. A venv created through a symlink records ``home``
    as the symlink's directory and ``executable`` as the real binary.
    """
    if not home:
        return False
    home_dir = Path(home)
    named = False
    for name in _interpreter_names_for_home(base, executable):
        if _same_file(home_dir / name, base):
            named = True
            break
    if not named:
        return False
    if executable and not _same_file(Path(executable), base):
        return False
    return True


def validate_pyvenv(venv_root: Path, base: Path) -> list[str]:
    """Refuse a venv whose config does not name this base interpreter."""
    path = venv_root / "pyvenv.cfg"
    if not path.is_file():
        return [f"pyvenv.cfg is missing: {path}"]
    try:
        cfg, duplicate = _parse_pyvenv_cfg(path)
    except (OSError, UnicodeError) as exc:
        return [f"pyvenv.cfg cannot be read: {path} ({exc})"]
    if duplicate:
        return [duplicate]
    findings: list[str] = []
    home = cfg.get("home", "")
    executable = cfg.get("executable", "")
    if not _pyvenv_names_base(home, executable, base):
        findings.append(
            "pyvenv.cfg does not name the Python that is running this check: "
            f"{path}"
        )
    if cfg.get("include-system-site-packages", "").lower() != "false":
        findings.append(f"include-system-site-packages is turned on: {path}")
    version = cfg.get("version", "")
    parts = version.split(".")
    try:
        major_minor = (int(parts[0]), int(parts[1])) if len(parts) >= 2 else None
    except ValueError:
        major_minor = None
    if major_minor != tuple(sys.version_info[:2]):
        findings.append(
            "pyvenv.cfg version does not match the Python that is running this check: "
            f"{path}"
        )
    return findings


_SITE_LAYOUT_QUERY = r"""
import json, os, sys, site, sysconfig
from pathlib import Path
venv_prefix = sys.argv[1]
saved = sys.prefix
sys.prefix = venv_prefix
try:
    venv_sites = list(site.getsitepackages([venv_prefix]))
finally:
    sys.prefix = saved
user_site = site.getusersitepackages()
system_sites = list(site.getsitepackages())
stdlib = []
for key in ("stdlib", "platstdlib"):
    value = sysconfig.get_path(key)
    if value:
        stdlib.append(str(Path(value).resolve()))
# site.venv() turns user site off unless include-system-site-packages is
# exactly true. This query is started with -I, so do not trust
# ENABLE_USER_SITE or check_enableusersite() here.
enable_user_site = False
cfg_path = os.path.join(venv_prefix, "pyvenv.cfg")
system_site = "true"
if os.path.isfile(cfg_path):
    with open(cfg_path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip().lower() == "include-system-site-packages":
                system_site = value.strip().lower()
    enable_user_site = system_site == "true" and not os.environ.get("PYTHONNOUSERSITE")
print(json.dumps({
    "venv_site_dirs": venv_sites,
    "user_site": user_site,
    "enable_user_site": enable_user_site,
    "system_site_dirs": system_sites,
    "stdlib": stdlib,
    "version": "%d.%d.%d" % sys.version_info[:3],
}))
"""


def debian_venv_site_dirs(prefix: Path, version_text: str) -> list[Path]:
    """Directories Debian/Ubuntu site.py adds under a venv prefix.

    Also scanned when this host's site.py is not the Debian patch, so a
    simulated layout is still refused.
    """
    parts = version_text.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        short = f"python{parts[0]}.{parts[1]}"
    else:
        short = f"python{sys.version_info[0]}.{sys.version_info[1]}"
    return [
        prefix / "lib" / short / "site-packages",
        prefix / "lib" / short / "dist-packages",
        prefix / "lib" / "python3" / "dist-packages",
        prefix / "local" / "lib" / short / "dist-packages",
    ]


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    chosen: list[Path] = []
    for path in paths:
        try:
            key = str(path.resolve()) if path.exists() else str(path.absolute())
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(path)
    return chosen


def query_site_layout(base: Path, venv_prefix: Path, env: dict[str, str]) -> dict[str, Any]:
    """Ask the base interpreter which directories site would process.

    Runs ``base -I -S``. That process does not import the venv's site hooks.
    """
    result = subprocess.run(
        [str(base), "-I", "-S", "-c", _SITE_LAYOUT_QUERY, str(venv_prefix)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise RuntimeError(f"base interpreter site layout failed: {detail}")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("base interpreter site layout was not a JSON object")
    return payload


def _purelib_from_site_dirs(venv_root: Path, site_dirs: list[Path], version_text: str) -> Path:
    for directory in site_dirs:
        if directory.name == "site-packages":
            return directory
    parts = version_text.split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        short = f"python{parts[0]}.{parts[1]}"
    else:
        short = f"python{sys.version_info[0]}.{sys.version_info[1]}"
    return venv_root / "lib" / short / "site-packages"


def _hook_finding(name: str, location: Path, chain_names: set[str]) -> str:
    if name in chain_names:
        return (
            f"unvetted {name} imported by the interpreter sitecustomize: {location}"
        )
    return f"unvetted {name} on the import path: {location}"


# A longer chain is a refusal with a reason, not a silent stop.
LINK_WALK_LIMIT = 40


def _symlink_loop_reason(path: Path) -> str:
    return f"cannot read an import path because it is a symlink loop: {path}"


def _unreadable_import_reason(path: Path, exc: BaseException | None = None) -> str:
    if exc is None:
        return f"cannot read an import path: {path}"
    return f"cannot read an import path: {path} ({exc})"


def _classify_import_path(path: Path) -> tuple[str, str | None]:
    """Classify a path a ``.pth`` line would add.

    Returns ``(kind, finding)``. ``kind`` is ``missing``, ``dir``, or
    ``zip``. A finding means the path exists but cannot be fully read or
    is not a directory or a readable zip. A missing path is not a finding.
    ``zipfile.is_zipfile`` turns ``EACCES`` into ``False``; that is not a
    reason to skip the path.
    """
    current = path
    seen: set[str] = set()
    st: os.stat_result | None = None
    for _ in range(LINK_WALK_LIMIT):
        key = os.path.abspath(str(current))
        if key in seen:
            return "bad", _symlink_loop_reason(path)
        seen.add(key)
        try:
            st = current.lstat()
        except FileNotFoundError:
            return "missing", None
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                return "missing", None
            if exc.errno == errno.ELOOP:
                return "bad", _symlink_loop_reason(path)
            return "bad", _unreadable_import_reason(path, exc)
        if not stat.S_ISLNK(st.st_mode):
            break
        try:
            raw = os.readlink(current)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                return "bad", _symlink_loop_reason(path)
            return "bad", _unreadable_import_reason(path, exc)
        nxt = Path(raw)
        current = nxt if nxt.is_absolute() else (current.parent / nxt)
    else:
        return "bad", _symlink_loop_reason(path)
    if st is None:
        return "bad", _unreadable_import_reason(path)
    if stat.S_ISDIR(st.st_mode):
        try:
            os.listdir(current)
        except OSError as exc:
            return "bad", _unreadable_import_reason(path, exc)
        return "dir", None
    if not stat.S_ISREG(st.st_mode):
        return "bad", (
            "cannot read an import path because it is not a regular file "
            f"or a directory: {path}"
        )
    try:
        with open(current, "rb") as handle:
            handle.read(4)
    except OSError as exc:
        return "bad", _unreadable_import_reason(path, exc)
    try:
        is_zip = zipfile.is_zipfile(current)
    except OSError as exc:
        return "bad", _unreadable_import_reason(path, exc)
    if not is_zip:
        return "bad", (
            "cannot read an import path because it is not a directory "
            f"or a readable zip file: {path}"
        )
    try:
        with zipfile.ZipFile(current) as archive:
            archive.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        return "bad", f"cannot read this zip: {path} ({exc})"
    return "zip", None


def scan_customization_hooks(
    directory: Path,
    extra_names: tuple[str, ...] = (),
) -> list[str]:
    """Refuse startup hooks in every form importlib would load.

    ``extra_names`` are modules the base interpreter's own ``sitecustomize``
    imports (Debian ``apport_python_hook``). They are read from that file;
    the file is not executed. A copy on the venv path would run when the
    venv's Python starts, so it is refused here.
    """
    names = ["sitecustomize", "usercustomize"]
    chain_names: set[str] = set()
    for name in extra_names:
        if not name.isidentifier() or name in names:
            continue
        names.append(name)
        chain_names.add(name)
    kind, problem = _classify_import_path(directory)
    if problem:
        return [problem]
    if kind == "missing":
        return []
    if kind == "zip":
        return _scan_zip_hooks(directory, names, chain_names)
    if kind != "dir":
        return [f"cannot read an import path: {directory}"]
    findings: list[str] = []
    suffixes = _import_suffixes()
    for name in names:
        candidates: list[Path] = []
        for suffix in suffixes:
            candidates.append(directory / f"{name}{suffix}")
            candidates.append(directory / name / f"__init__{suffix}")
        for cache in (directory / "__pycache__", directory / name / "__pycache__"):
            try:
                cache_is_dir = cache.is_dir()
            except OSError as exc:
                findings.append(
                    "cannot tell whether a startup hook is present: "
                    f"{cache} ({exc})"
                )
                continue
            if not cache_is_dir:
                continue
            prefix = name if cache.parent == directory else "__init__"
            try:
                cache_entries = list(cache.iterdir())
            except OSError as exc:
                findings.append(
                    "cannot tell whether a startup hook is present: "
                    f"{cache} ({exc})"
                )
                continue
            for path in cache_entries:
                if path.name.startswith(prefix + "."):
                    candidates.append(path)
        reported: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in reported:
                continue
            try:
                present = candidate.is_file() or candidate.is_symlink()
            except OSError as exc:
                findings.append(
                    "cannot tell whether a startup hook is present: "
                    f"{candidate} ({exc})"
                )
                continue
            if not present:
                continue
            reported.add(key)
            findings.append(_hook_finding(name, candidate, chain_names))
    return findings


def _import_suffixes() -> list[str]:
    """Source, bytecode, and extension suffixes for this base interpreter."""
    import importlib.machinery as machinery

    suffixes: list[str] = []
    for item in (
        *machinery.SOURCE_SUFFIXES,
        *machinery.BYTECODE_SUFFIXES,
        *machinery.EXTENSION_SUFFIXES,
    ):
        if item not in suffixes:
            suffixes.append(item)
    for extra in (".pyd", ".pyo"):
        if extra not in suffixes:
            suffixes.append(extra)
    return suffixes


def _scan_zip_hooks(
    path: Path,
    hook_names: list[str],
    chain_names: set[str],
) -> list[str]:
    """Refuse a startup hook stored in a zip that a .pth line would put on sys.path."""
    findings: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"cannot read this zip: {path} ({exc})"]
    suffixes = _import_suffixes()
    for hook in hook_names:
        matched = False
        for suffix in suffixes:
            if f"{hook}{suffix}" in names or f"{hook}/__init__{suffix}" in names:
                matched = True
                break
        if not matched:
            for name in names:
                marker = f"__pycache__/{hook}."
                init_marker = f"{hook}/__pycache__/__init__."
                if name.startswith(marker) or name.startswith(init_marker):
                    matched = True
                    break
        if matched:
            findings.append(_hook_finding(hook, path, chain_names))
    return findings


def _imported_module_names(source: str) -> list[str]:
    """Top-level and nested import targets. The source is not executed."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    found.append(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append(node.module.split(".", 1)[0])
    chosen: list[str] = []
    seen: set[str] = set()
    for name in found:
        if name and name not in seen:
            seen.add(name)
            chosen.append(name)
    return chosen


def interpreter_sitecustomize_imports(
    stdlib_roots: list[Path],
) -> tuple[tuple[str, ...], list[str]]:
    """Modules the base interpreter's sitecustomize would import.

    The file is read as text. It is not imported and not executed. If that
    file exists but cannot be read or parsed, the check refuses.
    """
    for root in stdlib_roots:
        path = root / "sitecustomize.py"
        try:
            present = path.is_file()
        except OSError as exc:
            return (), [f"cannot read the interpreter sitecustomize: {path} ({exc})"]
        if not present:
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            return (), [f"cannot read the interpreter sitecustomize: {path} ({exc})"]
        if b"\x00" in data:
            return (), [
                f"cannot read the interpreter sitecustomize: {path} (it contains a null byte)"
            ]
        try:
            source = data.decode("utf-8")
        except UnicodeDecodeError:
            return (), [
                f"cannot read the interpreter sitecustomize: {path} (it is not UTF-8 text)"
            ]
        try:
            ast.parse(source)
        except (SyntaxError, ValueError):
            return (), [f"cannot read the interpreter sitecustomize: {path}"]
        return tuple(_imported_module_names(source)), []
    return (), []


def pth_import_entries(directory: Path) -> tuple[list[Path], list[str]]:
    """Directories and zips a non-import .pth line would add to sys.path.

    Matches site.py: the line is joined with the .pth directory and kept when
    that path exists. A path that does not exist is not returned. Import lines
    are reported separately and are not listed here. An unreadable .pth file
    is a refusal, not a skip.
    """
    kind, problem = _classify_import_path(directory)
    if problem:
        return [], [problem]
    if kind != "dir":
        return [], []
    added: list[Path] = []
    findings: list[str] = []
    seen: set[str] = set()
    try:
        pth_files = sorted(directory.glob("*.pth"))
    except OSError as exc:
        return [], [f"cannot list .pth files in {directory}: {exc}"]
    for pth in pth_files:
        text, problem = read_pth_text(pth)
        if problem or text is None:
            findings.append(problem or f"cannot read this .pth file: {pth}")
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("import ") or line.startswith("import\t"):
                continue
            try:
                candidate = Path(line)
                if not candidate.is_absolute():
                    candidate = directory / candidate
            except (OSError, ValueError, RuntimeError) as exc:
                if isinstance(exc, RuntimeError) or getattr(exc, "errno", None) == errno.ELOOP:
                    findings.append(f"cannot resolve this path because it is a symlink loop: {line}")
                else:
                    findings.append(f"cannot tell whether a path named by {pth} exists: {exc}")
                continue
            listed, listed_problem = _classify_import_path(candidate)
            if listed_problem:
                findings.append(listed_problem)
                continue
            if listed == "missing":
                continue
            try:
                key = str(candidate.resolve())
            except (OSError, ValueError, RuntimeError) as exc:
                if isinstance(exc, RuntimeError) or getattr(exc, "errno", None) == errno.ELOOP:
                    findings.append(
                        f"cannot resolve this path because it is a symlink loop: {candidate}"
                    )
                else:
                    findings.append(f"cannot resolve a path named by {pth}: {exc}")
                continue
            if key in seen:
                continue
            seen.add(key)
            added.append(candidate)
    return added, findings


# High enough that a long .pth is fully scanned. Hitting it refuses; it does
# not drop the rest of the path. Paths that do not exist are not counted.
SITE_PATH_LIMIT = 4096


def expand_site_paths(site_dirs: list[Path]) -> tuple[list[Path], list[str]]:
    """Site directories plus every existing path a .pth line would add.

    A path that does not exist is not scanned and does not count toward the
    safety ceiling. If more existing paths remain after that ceiling, the
    scan refuses instead of dropping them.
    """
    chosen: list[Path] = []
    seen: set[str] = set()
    findings: list[str] = []
    queue: list[Path] = list(site_dirs)
    while queue:
        directory = queue.pop(0)
        kind, problem = _classify_import_path(directory)
        if problem:
            findings.append(problem)
            continue
        if kind == "missing":
            continue
        try:
            key = str(directory.resolve())
        except (OSError, ValueError, RuntimeError) as exc:
            if isinstance(exc, RuntimeError) or getattr(exc, "errno", None) == errno.ELOOP:
                findings.append(
                    f"cannot resolve this path because it is a symlink loop: {directory}"
                )
            else:
                findings.append(f"cannot resolve an import path: {directory} ({exc})")
            continue
        if key in seen:
            continue
        if len(chosen) >= SITE_PATH_LIMIT:
            findings.append(
                "too many directories on the import path to check them all. "
                "Create a fresh environment by following the acceptance sheet."
            )
            break
        seen.add(key)
        chosen.append(directory)
        if kind != "dir":
            continue
        extras, extra_findings = pth_import_entries(directory)
        findings.extend(extra_findings)
        queue.extend(extras)
    return chosen, findings


def _is_venv_interpreter_entry(name: str) -> bool:
    """True for python, python3, python3.X, and the CPython 3.14 pi name."""
    stem = name[:-4] if name.lower().endswith(".exe") else name
    if stem == "\N{MATHEMATICAL ITALIC SMALL PI}thon":
        return True
    if stem in {"python", "python3", "pythonw"}:
        return True
    if not stem.startswith("python3."):
        return False
    rest = stem[len("python3.") :]
    if rest.endswith("t") and rest[:-1].replace(".", "").isdigit():
        rest = rest[:-1]
    return bool(rest) and all(ch.isdigit() or ch == "." for ch in rest)


def _final_regular_file(path: Path) -> tuple[Path | None, str | None]:
    """Walk symlinks without executing the target.

    Returns ``(regular file, None)`` or ``(None, reason)``. A reason means
    the walk could not be finished and the caller must refuse.
    """
    current = path
    seen: set[str] = set()
    for _ in range(LINK_WALK_LIMIT):
        key = os.path.abspath(str(current))
        if key in seen:
            return None, f"venv interpreter link loop: {path}"
        seen.add(key)
        try:
            st = current.lstat()
        except OSError as exc:
            return None, f"cannot follow the venv interpreter {path}: {exc}"
        if stat.S_ISLNK(st.st_mode):
            try:
                raw = os.readlink(current)
            except OSError as exc:
                return None, f"cannot follow the venv interpreter {path}: {exc}"
            nxt = Path(raw)
            current = nxt if nxt.is_absolute() else current.parent / nxt
            continue
        if stat.S_ISREG(st.st_mode):
            return current, None
        return None, (
            "venv interpreter is not the base interpreter named by pyvenv.cfg: "
            f"{path}"
        )
    return None, f"followed too many links while checking the venv interpreter: {path}"


def scan_venv_interpreters(bin_dir: Path, base: Path) -> list[str]:
    """Refuse a venv Python entry that is not the base interpreter.

    A symlink must resolve, by filesystem identity, to ``base``. A regular
    file must be a byte-for-byte copy (Windows copies mode or a hard link).
    The file is not executed.
    """
    if not bin_dir.is_dir():
        return []
    findings: list[str] = []
    try:
        base_digest = sha256_file(base)
    except OSError as exc:
        return [f"cannot read the base interpreter {base}: {exc}"]
    try:
        entries = sorted(bin_dir.iterdir(), key=lambda item: item.name.lower())
    except OSError as exc:
        return [f"cannot list venv bin directory {bin_dir}: {exc}"]
    for path in entries:
        if not _is_venv_interpreter_entry(path.name):
            continue
        final, walk_error = _final_regular_file(path)
        if walk_error or final is None:
            findings.append(
                walk_error
                or (
                    "venv interpreter is not the base interpreter named by pyvenv.cfg: "
                    f"{path}"
                )
            )
            continue
        try:
            same = _same_file(final, base)
        except OSError:
            same = False
        if same:
            continue
        try:
            linked = path.is_symlink()
        except OSError:
            linked = True
        if linked or sha256_file(final) != base_digest:
            findings.append(
                "venv interpreter is not the base interpreter named by pyvenv.cfg: "
                f"{path}"
            )
    return findings


def scan_dist_packages_modules(directory: Path) -> list[str]:
    """Refuse modules planted where Debian site.py would put them on sys.path."""
    if directory.name != "dist-packages":
        return []
    kind, problem = _classify_import_path(directory)
    if problem:
        return [problem]
    if kind != "dir":
        return []
    findings: list[str] = []
    try:
        paths = sorted(directory.rglob("*"))
    except OSError as exc:
        return [f"cannot list dist-packages: {directory} ({exc})"]
    for path in paths:
        if path.is_dir():
            continue
        if path.suffix.lower() == ".pth":
            continue
        suffix = path.suffix.lower()
        if suffix in {".py", ".pyc", ".pyo", ".so"} or "__pycache__" in path.parts:
            findings.append(f"unexpected module in dist-packages: {path}")
    return findings


def startup_customization_findings(
    origins: dict[str, Any] | None,
    *,
    prefix: Path,
    site_packages: Path,
    stdlib_roots: list[Path] | None = None,
    exclusions: list[Path] | None = None,
) -> list[str]:
    """Reject sitecustomize/usercustomize that is importable from the target venv.

    The trusted interpreter includes its own stdlib and distro sitecustomize
    (Debian/Ubuntu ``/etc/pythonX.Y/sitecustomize.py``). A sitecustomize module
    or package inside the venv is extra startup and is refused. usercustomize
    is refused when it is importable (user site enabled).
    """
    findings: list[str] = []
    prefix = prefix.resolve()
    site_packages = site_packages.resolve()
    roots = list(stdlib_roots) if stdlib_roots is not None else _stdlib_roots_from_origins(origins)
    excluded = list(exclusions or [])
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
            interpreter_owned = path_is_real_stdlib(loaded, roots, excluded) if roots else False
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
    """Static scan, then probe, then the verdict.

    Nothing in the venv is executed until the static phase is clean.
    A check started by a virtual environment's Python is refused before
    any of that work, including when ``-I -S`` hid the venv prefix.
    """
    started = running_interpreter_problem()
    if started:
        return {"ok": False, "message": started}
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
        "bytecode_findings": [],
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

    # --- static phase: base interpreter only, no venv code ---
    venv_root = resolved_launcher.parent.parent
    base = base_interpreter_in_use()
    pyvenv_findings = validate_pyvenv(venv_root, base)
    pth_findings: list[dict[str, Any]] = []
    startup_findings: list[str] = list(pyvenv_findings)
    bytecode_findings: list[str] = []
    stdlib_roots: list[Path] = []
    exclusions: list[Path] = []
    site: Path | None = None
    package_dir: Path | None = None
    layout_error: str | None = None
    version_text = ".".join(str(part) for part in sys.version_info[:3])
    if not pyvenv_findings:
        try:
            layout = query_site_layout(base, venv_root, env)
        except (RuntimeError, json.JSONDecodeError, OSError) as exc:
            layout_error = str(exc)
            startup_findings.append(layout_error)
        else:
            version_text = str(layout.get("version") or version_text)
            queried = [Path(str(item)) for item in layout.get("venv_site_dirs") or []]
            site_dirs = _dedupe_paths(queried + debian_venv_site_dirs(venv_root, version_text))
            user_site = layout.get("user_site")
            if user_site and layout.get("enable_user_site"):
                site_dirs = _dedupe_paths(site_dirs + [Path(str(user_site))])
            site = _purelib_from_site_dirs(venv_root, site_dirs, version_text)
            package_dir = (site / "runspecimen").resolve()
            report["prefix"] = str(venv_root.resolve())
            report["verified_package_dir"] = str(package_dir)
            report.update(verify_site_against_wheel(site_packages=site, wheel=wheel))
            report["import_overrides"] = incoming_overrides
            report["launcher"] = str(resolved_launcher)
            report["interpreter"] = str(interpreter)
            report["prefix"] = str(venv_root.resolve())
            report["console_script_target"] = console_script_target(resolved_launcher)
            report["verified_package_dir"] = str(package_dir)
            seen_pth: set[tuple[str, int, str]] = set()
            stdlib_roots = [Path(str(item)).resolve() for item in layout.get("stdlib") or []]
            chain_names, chain_problems = interpreter_sitecustomize_imports(stdlib_roots)
            startup_findings.extend(chain_problems)
            scan_roots, path_problems = expand_site_paths(site_dirs)
            startup_findings.extend(path_problems)
            for directory in scan_roots:
                kind, problem = _classify_import_path(directory)
                if problem:
                    startup_findings.append(problem)
                    continue
                if kind == "dir":
                    for item in scan_pth_files(directory):
                        marker = (str(item.get("path")), int(item.get("line") or 0), str(item.get("text")))
                        if marker in seen_pth:
                            continue
                        seen_pth.add(marker)
                        reason = str(item.get("reason") or "")
                        if _plain_scan_refusal(reason) and reason not in startup_findings:
                            startup_findings.append(reason)
                        pth_findings.append(item)
                startup_findings.extend(scan_customization_hooks(directory, chain_names))
                startup_findings.extend(scan_dist_packages_modules(directory))
            if site.is_dir():
                pth_findings.extend(scan_virtualenv_artifacts(site))
            bytecode_findings = scan_package_bytecode(package_dir)
            exclusions = [venv_root.resolve()]
            for directory in site_dirs:
                try:
                    exclusions.append(directory.resolve() if directory.exists() else directory.absolute())
                except (OSError, ValueError) as exc:
                    startup_findings.append(
                        f"cannot resolve an import path: {directory} ({exc})"
                    )
            for item in layout.get("system_site_dirs") or []:
                exclusions.append(Path(str(item)).resolve())
    report["pth_findings"] = pth_findings
    report["bytecode_findings"] = bytecode_findings
    bin_findings = list(bin_findings) + scan_venv_interpreters(resolved_launcher.parent, base)
    report["bin_findings"] = bin_findings
    target = console_script_target(resolved_launcher)
    report["console_script_target"] = target

    hashed_py_members = list(report.get("hashed_py_members") or [])
    hashed_members = list(report.get("hashed_members") or hashed_py_members)
    hashed_files: set[Path] = set()
    if site is not None:
        hashed_files = {
            (site / member).resolve()
            for member in hashed_members
            if (site / member).is_file()
        }
    static_blocked = bool(
        pyvenv_findings
        or layout_error
        or pth_findings
        or startup_findings
        or bytecode_findings
        or bin_findings
        or target != PINNED_CONSOLE_SCRIPT_TARGET
        or incoming_overrides
        or not report.get("ok")
        or site is None
        or package_dir is None
    )

    # --- probe phase: only after a clean static phase ---
    launcher_module_findings: list[str] = []
    loaded_module_origins: dict[str, Any] = {}
    origins: dict[str, Any] | None = None
    bind_error: str | None = "effective origins were not probed"
    bound = False
    if not static_blocked and package_dir is not None and site is not None:
        try:
            doctor = probe_launcher_doctor(
                resolved_launcher,
                env,
                base=base,
                extra_paths=[site],
            )
            loaded_module_origins = dict(doctor.get("loaded_module_origins") or {})
            launcher_module_findings = launcher_module_origin_findings(
                loaded_module_origins or None,
                stdlib_roots=stdlib_roots,
                hashed_files=hashed_files,
                launcher=resolved_launcher,
                venv_prefix=venv_root,
                exclusions=exclusions,
            )
        except (RuntimeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            launcher_module_findings = [str(exc)]
        try:
            origins = probe_effective_origins(
                base,
                env,
                trusted_stdlib=stdlib_roots,
                exclusions=exclusions,
                extra_paths=[site],
            )
        except (RuntimeError, json.JSONDecodeError, KeyError) as exc:
            origins = None
            bind_error = str(exc)
    report["loaded_module_origins"] = loaded_module_origins
    report["launcher_module_findings"] = launcher_module_findings

    # --- evidence / verdict ---
    if origins is not None and package_dir is not None and site is not None:
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
        startup_findings.extend(
            startup_customization_findings(
                origins,
                prefix=venv_root,
                site_packages=site,
                stdlib_roots=stdlib_roots,
                exclusions=exclusions,
            )
        )
        if origins.get("pycache_prefix"):
            startup_findings.append(f"sys.pycache_prefix is set: {origins.get('pycache_prefix')}")
        if not origins.get("dont_write_bytecode"):
            startup_findings.append("probe did not run with bytecode writing disabled")
        if origins.get("cached_bytecode"):
            startup_findings.append(
                "loaded runspecimen modules have existing bytecode: "
                + ", ".join(str(item.get("cached") or item) for item in origins["cached_bytecode"])
            )
        if origins.get("sourceless_bytecode"):
            startup_findings.append(
                "loaded sourceless runspecimen bytecode: "
                + ", ".join(str(item.get("file") or item) for item in origins["sourceless_bytecode"])
            )
    else:
        report["origins_bound"] = False
        if bytecode_findings:
            bind_error = (
                "installed runspecimen package contains bytecode "
                "(__pycache__ / .pyc); install with pip install --no-compile "
                "and PYTHONDONTWRITEBYTECODE=1"
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
    if pyvenv_findings:
        failures.extend(pyvenv_findings)
    if layout_error:
        failures.append(layout_error)
    already_reported = set(pyvenv_findings)
    if layout_error:
        already_reported.add(layout_error)
    for item in startup_findings:
        text = str(item)
        if text in already_reported or not _plain_scan_refusal(text):
            continue
        failures.append(text)
        already_reported.add(text)
    hook_file = _first_hook_file(
        pth_findings,
        [item for item in startup_findings if not _plain_scan_refusal(str(item))],
        list(report.get("meta_path_findings") or []),
        list(report.get("path_hook_findings") or []),
    )
    if hook_file:
        failures.append(hook_refusal_message(hook_file))
    if not bound:
        failures.append(bind_error or "effective origins are not bound to the verified package directory")
    if site is not None and not report.get("ok"):
        failures.append(str(report.get("message") or "installed tree does not match the pinned wheel"))
    elif site is None and not pyvenv_findings and not layout_error:
        failures.append("installed tree does not match the pinned wheel")

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
    try:
        report = verify_launcher_install(wheel=args.wheel, launcher=args.launcher)
    except Exception as exc:
        report = {
            "ok": False,
            "message": f"the installed-wheel check stopped: {exc}",
        }
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
