#!/usr/bin/env python3
"""Compare the installed runspecimen tree to a pinned wheel's bytes.

Version strings are not proof. Two unpublished 0.2.0rc15 wheels can differ.
Exit 0 only when every hashed RECORD member (and every runspecimen/*.py in the
zip) matches the file installed under the absolute launcher's interpreter, the
effective runspecimen and CLI module origins realpath-equal that verified
package directory, the environment has no import overrides, and no site-packages
.pth adds a path outside that install.

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
BENIGN_IMPORT_PTH_NAMES = frozenset({
    "_virtualenv.pth",
    "distutils-precedence.pth",
})
CONSOLE_FROM = re.compile(r"from\s+([\w.]+)\s+import\s+(\w+)")
PROBE_SCRIPT = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "import runspecimen\n"
    "import runspecimen.cli\n"
    "print(json.dumps({\n"
    "    'runspecimen_file': str(Path(runspecimen.__file__).resolve()),\n"
    "    'cli_file': str(Path(runspecimen.cli.__file__).resolve()),\n"
    "    'prefix': str(Path(sys.prefix).resolve()),\n"
    "    'executable': str(Path(sys.executable).resolve()),\n"
    "    'version': getattr(runspecimen, '__version__', None),\n"
    "}))\n"
)


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


def _launcher_sibling_python(launcher: Path) -> Path:
    return launcher.parent / ("python.exe" if os.name == "nt" else "python")


def interpreter_from_launcher(launcher: Path) -> Path:
    """Return the venv interpreter the console script actually execs.

    Do not realpath the shebang: ``$VENV/bin/python`` is usually a symlink to
    the system interpreter, and resolving it drops ``pyvenv.cfg``.
    """
    sibling = _launcher_sibling_python(launcher)
    data = launcher.read_bytes()
    if data.startswith(b"#!"):
        first = data.splitlines()[0][2:].decode("utf-8", "replace").strip()
        parts = first.split()
        if parts and Path(parts[0]).name not in {"env", "env.exe"}:
            shebang = Path(parts[0])
            if shebang.exists():
                return shebang
        if sibling.exists():
            return sibling
        if parts and Path(parts[0]).name in {"env", "env.exe"} and len(parts) >= 2:
            found = shutil_which(parts[1])
            if found:
                return Path(found)
    if sibling.exists():
        return sibling
    return Path(sys.executable)


def shutil_which(name: str) -> str | None:
    from shutil import which

    return which(name)


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


def probe_effective_origins(interpreter: Path, env: dict[str, str]) -> dict[str, str]:
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
    return {key: str(payload[key]) for key in payload}


def package_origin(module_file: Path) -> Path:
    resolved = module_file.resolve()
    if resolved.name == "__init__.py":
        return resolved.parent
    return resolved.parent


def origins_bound_to_package(
    *,
    runspecimen_file: Path,
    cli_file: Path,
    package_dir: Path,
) -> tuple[bool, str | None]:
    expected_pkg = package_dir.resolve()
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
    return True, None


def scan_pth_files(site_packages: Path) -> list[dict[str, Any]]:
    """Reject .pth entries that add a path outside the verified install."""
    findings: list[dict[str, Any]] = []
    site_packages = site_packages.resolve()
    for pth in sorted(site_packages.glob("*.pth")):
        text = pth.read_text(encoding="utf-8", errors="replace")
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("import ") or line.startswith("import\t"):
                if pth.name in BENIGN_IMPORT_PTH_NAMES and "sys.path" not in line:
                    continue
                reason = "import-style .pth is not on the allow-list or mutates sys.path"
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


def verify_launcher_install(*, wheel: Path, launcher: Path | None) -> dict[str, Any]:
    incoming_overrides = import_overrides()
    env = sanitized_env()
    report: dict[str, Any] = {
        "ok": False,
        "wheel": str(wheel.resolve()) if wheel else None,
        "import_overrides": incoming_overrides,
        "pth_findings": [],
        "origins_bound": False,
        "launcher": None,
        "interpreter": None,
        "prefix": None,
        "console_script_target": None,
        "verified_package_dir": None,
        "runspecimen_file": None,
        "cli_file": None,
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
    except OSError as exc:
        report["message"] = f"launcher interpreter unread: {exc}"
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

    bind_error: str | None = "effective origins were not probed"
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
        report["runspecimen_version"] = origins.get("version")
        bound, bind_error = origins_bound_to_package(
            runspecimen_file=rs_file,
            cli_file=cli_file,
            package_dir=package_dir,
        )
        report["origins_bound"] = bound
    else:
        bound = False
        report["origins_bound"] = False
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
            "console_script_target",
            "origins_bound",
            "import_overrides",
            "pth_findings",
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
