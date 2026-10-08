#!/usr/bin/env python3
"""Compare the installed runspecimen tree to a pinned wheel's bytes.

Version strings are not proof. Two unpublished 0.2.0rc15 wheels can differ.
Exit 0 only when every hashed RECORD member (and every runspecimen/*.py in the
zip) matches the file installed under the absolute launcher's interpreter, the
effective origins of runspecimen, runspecimen.cli, runspecimen.approve, and
every other loaded runspecimen.* module realpath-equal the hashed installed
members, the environment has no import overrides, no unvetted startup
customization is on the import path, and no site-packages .pth adds a foreign
path or an executable import that is not a known-safe exact body.

Trusted-interpreter assumption: this helper is not a promise to resist
arbitrary replacement of Python, of this verifier script, or of the operator's
own decision to run a different interpreter. It does refuse env-based and
unsupported launcher shebangs instead of guessing a sibling, and it does
refuse unvetted sitecustomize/usercustomize and executable .pth hooks.

Run with the venv interpreter that owns the install, under the same sanitized
environment the acceptance sheet uses for every launcher call:

  env -u PYTHONPATH -u PYTHONHOME -u PYTHONSTARTUP PYTHONNOUSERSITE=1 \\
    "$VENV/bin/python" scripts/verify_installed_wheel.py \\
    --wheel /abs/path.whl --launcher "$VENV/bin/runspecimen"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
import zipfile


IMPORT_OVERRIDE_VARS = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")
# Content-matched only. Filename is not trust. These are the exact bodies of
# virtualenv's ``_virtualenv.pth`` (``import _virtualenv``) and setuptools'
# ``distutils-precedence.pth`` distutils shim. They do not add paths and do
# not import runspecimen. Any other import line, including ``import qa_compat``
# inside ``_virtualenv.pth``, is refused.
KNOWN_SAFE_PTH_IMPORT_LINES = frozenset({
    "import _virtualenv",
    "import os; var = 'SETUPTOOLS_USE_DISTUTILS'; enabled = os.environ.get(var, 'local') == 'local'; enabled and __import__('_distutils_hack').add_shim();",
    "import os; var = 'SETUPTOOLS_USE_DISTUTILS'; enabled = os.environ.get(var, 'local') == 'local'; enabled and __import__('_distutils_hack').add_shim()",
})
CONSOLE_FROM = re.compile(r"from\s+([\w.]+)\s+import\s+(\w+)")
PROBE_SCRIPT = (
    "import json, sys, site\n"
    "from pathlib import Path\n"
    "import runspecimen\n"
    "import runspecimen.cli\n"
    "import runspecimen.approve\n"
    "import runspecimen.run\n"
    "loaded = {}\n"
    "for name, mod in list(sys.modules.items()):\n"
    "    if name != 'runspecimen' and not name.startswith('runspecimen.'):\n"
    "        continue\n"
    "    path = getattr(mod, '__file__', None)\n"
    "    loaded[name] = None if path is None else str(Path(path).resolve())\n"
    "\n"
    "def _find(modname):\n"
    "    if modname in sys.modules:\n"
    "        mod = sys.modules[modname]\n"
    "        path = getattr(mod, '__file__', None)\n"
    "        if path:\n"
    "            return str(Path(path).resolve())\n"
    "    for entry in list(sys.path):\n"
    "        if not entry:\n"
    "            continue\n"
    "        base = Path(entry)\n"
    "        for suffix in ('.py', '.pyc'):\n"
    "            cand = base / (modname + suffix)\n"
    "            if cand.is_file():\n"
    "                return str(cand.resolve())\n"
    "        init = base / modname / '__init__.py'\n"
    "        if init.is_file():\n"
    "            return str(init.resolve())\n"
    "    return None\n"
    "\n"
    "print(json.dumps({\n"
    "    'runspecimen_file': str(Path(runspecimen.__file__).resolve()),\n"
    "    'cli_file': str(Path(runspecimen.cli.__file__).resolve()),\n"
    "    'approve_file': str(Path(runspecimen.approve.__file__).resolve()),\n"
    "    'prefix': str(Path(sys.prefix).resolve()),\n"
    "    'executable': str(Path(sys.executable).resolve()),\n"
    "    'version': getattr(runspecimen, '__version__', None),\n"
    "    'loaded_runspecimen': loaded,\n"
    "    'sitecustomize': _find('sitecustomize'),\n"
    "    'usercustomize': _find('usercustomize'),\n"
    "    'enable_user_site': bool(getattr(site, 'ENABLE_USER_SITE', False)),\n"
    "}))\n"
)


class UnsupportedShebangError(ValueError):
    """Launcher shebang is env-based, missing, or not this venv's Python."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


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
    for key in IMPORT_OVERRIDE_VARS:
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def import_overrides(env: dict[str, str] | None = None) -> list[str]:
    source = env if env is not None else os.environ
    found = [f"{key}={source[key]}" for key in IMPORT_OVERRIDE_VARS if source.get(key)]
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

    Compare bin directories without following the ``python`` symlink: two
    venvs can realpath to the same system interpreter.
    """
    shebang_dir = os.path.normpath(os.path.abspath(str(shebang.parent)))
    launcher_dir = os.path.normpath(os.path.abspath(str(launcher.parent)))
    if shebang_dir != launcher_dir:
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


def console_script_target(launcher: Path) -> str | None:
    try:
        text = launcher.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    match = CONSOLE_FROM.search(text)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    return None


def launcher_sysconfig(interpreter: Path, env: dict[str, str]) -> dict[str, str]:
    script = (
        "import json, sys, sysconfig\n"
        "from pathlib import Path\n"
        "print(json.dumps({\n"
        "    'purelib': str(Path(sysconfig.get_path('purelib')).resolve()),\n"
        "    'prefix': str(Path(sys.prefix).resolve()),\n"
        "    'executable': str(Path(sys.executable).resolve()),\n"
        "}))\n"
    )
    result = subprocess.run(
        [str(interpreter), "-c", script],
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
    return {key: str(payload[key]) for key in ("purelib", "prefix", "executable")}


def probe_effective_origins(interpreter: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        [str(interpreter), "-c", PROBE_SCRIPT],
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
    """Reject .pth entries that add a path outside the verified install.

    Executable ``import`` lines are allowed only when the stripped line is one
    of ``KNOWN_SAFE_PTH_IMPORT_LINES``. Filename is not trust.
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
                normalized = _normalize_pth_import_line(line)
                if normalized in KNOWN_SAFE_PTH_IMPORT_LINES:
                    continue
                reason = "executable import .pth line is not a known-safe body"
                if "sys.path" in line:
                    reason = "pth prepends or mutates sys.path outside the verified install"
                findings.append({
                    "path": str(pth),
                    "line": lineno,
                    "reason": reason,
                    "text": line,
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


def startup_customization_findings(
    origins: dict[str, Any] | None,
    *,
    prefix: Path,
    site_packages: Path,
) -> list[str]:
    """Reject unvetted sitecustomize/usercustomize under this install.

    A distro sitecustomize such as Debian/Ubuntu ``/etc/pythonX.Y/sitecustomize.py``
    is part of the trusted interpreter and is not refused. A sitecustomize.py
    inside the venv prefix or site-packages is unvetted and is refused.
    usercustomize is refused only when user site is enabled.
    """
    findings: list[str] = []
    prefix = prefix.resolve()
    site_packages = site_packages.resolve()
    for name in ("sitecustomize.py", "sitecustomize.pyc"):
        cand = site_packages / name
        if cand.is_file():
            findings.append(f"unvetted sitecustomize on the import path: {cand.resolve()}")
    if origins is not None:
        sitecustomize = origins.get("sitecustomize")
        if sitecustomize:
            loaded = Path(str(sitecustomize)).resolve()
            if _under(loaded, prefix) and not any(loaded.as_posix() in item for item in findings):
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
        "origins_bound": False,
        "launcher": None,
        "interpreter": None,
        "prefix": None,
        "console_script_target": None,
        "verified_package_dir": None,
        "runspecimen_file": None,
        "cli_file": None,
        "approve_file": None,
        "loaded_runspecimen": {},
        "runspecimen_version": None,
    }
    resolved_launcher = launcher.resolve() if launcher is not None else discover_launcher()
    if resolved_launcher is None or not resolved_launcher.is_file():
        report["message"] = f"absolute launcher not found: {launcher or '(discovered)'}"
        return report
    report["launcher"] = str(resolved_launcher)
    report["console_script_target"] = console_script_target(resolved_launcher)
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

    pth_findings = scan_pth_files(site)
    report["pth_findings"] = pth_findings

    hashed_py_members = list(report.get("hashed_py_members") or [])
    bind_error: str | None = "effective origins were not probed"
    startup_findings: list[str] = []
    try:
        origins = probe_effective_origins(interpreter, env)
    except (RuntimeError, json.JSONDecodeError, KeyError) as exc:
        origins = None
        bind_error = str(exc)
    if origins is not None:
        rs_file = Path(origins["runspecimen_file"])
        cli_file = Path(origins["cli_file"])
        report["runspecimen_file"] = str(rs_file)
        report["cli_file"] = str(cli_file)
        if origins.get("approve_file"):
            report["approve_file"] = str(origins["approve_file"])
        loaded = origins.get("loaded_runspecimen") or {}
        report["loaded_runspecimen"] = loaded
        report["runspecimen_version"] = origins.get("version")
        bound, bind_error = origins_bound_to_package(
            runspecimen_file=rs_file,
            cli_file=cli_file,
            package_dir=package_dir,
            site_packages=site,
            loaded=loaded,
            hashed_py_members=hashed_py_members,
        )
        report["origins_bound"] = bound
        startup_findings = startup_customization_findings(
            origins,
            prefix=Path(cfg["prefix"]),
            site_packages=site,
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
    expected_target = "runspecimen.cli:main"
    target = report.get("console_script_target")
    if target not in {None, expected_target}:
        report["ok"] = False
        report["message"] = (
            f"console-script target {target} is not {expected_target}"
        )
        return report

    failures: list[str] = []
    if incoming_overrides:
        failures.append("import overrides: " + "; ".join(incoming_overrides))
    if pth_findings:
        failures.append(
            f"{len(pth_findings)} .pth path(s) outside the verified install"
        )
    if startup_findings:
        failures.append("; ".join(startup_findings))
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
            "console_script_target",
            "origins_bound",
            "loaded_runspecimen",
            "import_overrides",
            "pth_findings",
            "startup_findings",
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
