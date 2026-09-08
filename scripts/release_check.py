#!/usr/bin/env python3
"""Test, build, and smoke-test distributable releases without network access.

Build tools must already be installed (see bootstrap_dev.sh). All packaging and
CLI work happens in temporary directories. Use --output-dir to retain the
validated wheel, source archive, plugin ZIP, report, and SHA-256 checksums.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PYTHON_VERSION = "0.2.0rc6"
EXPECTED_PLUGIN_VERSION = "0.2.0-rc.6"
SOURCE_COMPONENTS = (
    "pyproject.toml", "MANIFEST.in", "README.md", "LICENSE", "CHANGELOG.md",
    "SECURITY.md", "src", "scripts", "tests", "docs", "examples", "work",
    "plugins", ".cursor", ".cursor-plugin", ".agents",
)
PLUGIN_COMPONENTS = (
    ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json", "README.md",
    "rules/runspecimen.mdc", "scripts/runspecimen_adapter.py",
    "skills/runspecimen/SKILL.md",
)
FORBIDDEN_PARTS = frozenset({".git", ".runspecimen", ".tools", "__pycache__"})


def run(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None,
        capture: bool = False) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(args), flush=True)
    return subprocess.run(
        args, cwd=cwd, env=env, check=True, text=True,
        stdin=subprocess.DEVNULL, capture_output=capture, timeout=300,
    )


def check_versions() -> None:
    for relative, pattern in (
        ("pyproject.toml", r'^version = "([^"]+)"$'),
        ("src/runspecimen/__init__.py", r'^__version__ = "([^"]+)"$'),
    ):
        match = re.search(pattern, (ROOT / relative).read_text(encoding="utf-8"), re.MULTILINE)
        if match is None or match.group(1) != EXPECTED_PYTHON_VERSION:
            raise SystemExit(f"{relative} version does not match release_check.py")
    plugin_root = ROOT / "plugins/runspecimen"
    plugin = json.loads((plugin_root / PLUGIN_COMPONENTS[0]).read_text(encoding="utf-8"))
    cursor = json.loads((plugin_root / PLUGIN_COMPONENTS[1]).read_text(encoding="utf-8"))
    if plugin.get("version", "").split("+", 1)[0] != EXPECTED_PLUGIN_VERSION:
        raise SystemExit("Codex plugin version does not match release_check.py")
    if cursor.get("version") != EXPECTED_PLUGIN_VERSION or cursor.get("name") != plugin.get("name"):
        raise SystemExit("Cursor plugin version/name is inconsistent")
    prompts = plugin.get("interface", {}).get("defaultPrompt")
    if not isinstance(prompts, list) or not prompts or not all(
        isinstance(item, str) and item for item in prompts
    ):
        raise SystemExit("Codex plugin defaultPrompt must be a non-empty string array")
    marketplace = json.loads((ROOT / ".cursor-plugin/marketplace.json").read_text(encoding="utf-8"))
    entries = marketplace.get("plugins")
    if not isinstance(entries, list) or len(entries) != 1:
        raise SystemExit("Cursor marketplace must contain exactly the RunSpecimen plugin")
    if any(entries[0].get(key) != value for key, value in (
        ("name", "runspecimen"), ("source", "plugins/runspecimen"),
        ("version", EXPECTED_PLUGIN_VERSION),
    )):
        raise SystemExit("Cursor marketplace entry is inconsistent")
    for relative in PLUGIN_COMPONENTS:
        if not (plugin_root / relative).is_file():
            raise SystemExit(f"missing plugin component: {relative}")


def ensure_build_backend() -> None:
    try:
        import setuptools
        import wheel  # noqa: F401
        import pip  # noqa: F401
    except ImportError as exc:
        raise SystemExit("pip, setuptools>=77, and wheel are required; run sh scripts/bootstrap_dev.sh first") from exc
    match = re.match(r"(\d+)", setuptools.__version__)
    if match is None or int(match.group(1)) < 77:
        raise SystemExit("setuptools>=77 is required; run sh scripts/bootstrap_dev.sh first")


def offline_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONUNBUFFERED"):
        env.pop(name, None)
    env.update({
        "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INDEX": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_CACHE_DIR": "1",
        "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


def stage_source(destination: Path) -> None:
    destination.mkdir()
    ignore = shutil.ignore_patterns(".runspecimen", "__pycache__", "*.py[cod]", "*.egg-info", ".DS_Store")
    for name in SOURCE_COMPONENTS:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, destination / name, ignore=ignore, symlinks=True)
        elif source.is_file():
            shutil.copy2(source, destination / name)
    links = [str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_symlink()]
    if links:
        raise SystemExit(f"release source must not contain symbolic links: {links}")


def safe_members(names: list[str]) -> None:
    if len(set(names)) != len(names):
        raise SystemExit("release archive contains duplicate members")
    for name in names:
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or "\\" in name
                or FORBIDDEN_PARTS.intersection(path.parts)
                or path.suffix in {".pyc", ".pyo"}):
            raise SystemExit(f"unexpected or unsafe release archive member: {name}")


def inspect_sdist(path: Path, destination: Path) -> Path:
    """Validate the distribution before extracting regular files/directories."""
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        safe_members([member.name for member in members])
        top = f"runspecimen-{EXPECTED_PYTHON_VERSION}"
        names = {member.name for member in members}
        required = {f"{top}/{relative}" for relative in (
            "pyproject.toml", "LICENSE", "README.md", "src/runspecimen/cli.py",
            "src/runspecimen/dashboard.py", "src/runspecimen/py.typed",
            "scripts/release_check.py", "tests/test_demo_cli.py", "work/compute.py",
            "examples/demo_contract.json",
            *(f"plugins/runspecimen/{name}" for name in PLUGIN_COMPONENTS),
        )}
        if not required.issubset(names):
            raise SystemExit(f"source archive is missing required files: {sorted(required - names)}")
        for member in members:
            if PurePosixPath(member.name).parts[0] != top or not (member.isfile() or member.isdir()):
                raise SystemExit(f"unsupported source archive member: {member.name}")
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise SystemExit(f"unreadable source archive member: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    return destination / top


def inspect_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        safe_members(names)
        dist_info = f"runspecimen-{EXPECTED_PYTHON_VERSION}.dist-info"
        required = {
            "runspecimen/cli.py", "runspecimen/dashboard.py", "runspecimen/py.typed",
            f"{dist_info}/METADATA", f"{dist_info}/RECORD",
            f"{dist_info}/entry_points.txt", f"{dist_info}/licenses/LICENSE",
        }
        if not required.issubset(names):
            raise SystemExit(f"wheel is missing required files: {sorted(required - set(names))}")
        metadata = archive.read(f"{dist_info}/METADATA").decode("utf-8")
        if f"\nVersion: {EXPECTED_PYTHON_VERSION}\n" not in metadata:
            raise SystemExit("wheel metadata has the wrong version")
        if "\nRequires-Dist:" in metadata:
            raise SystemExit("the dependency-free runtime unexpectedly declares a dependency")


def build_plugin(source: Path, output: Path) -> None:
    plugin = source / "plugins/runspecimen"
    files = sorted(path for path in plugin.rglob("*") if path.is_file())
    entries = [(f"runspecimen/{path.relative_to(plugin).as_posix()}", path) for path in files]
    entries.append(("runspecimen/LICENSE", source / "LICENSE"))
    safe_members([name for name, _ in entries])
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in entries:
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def smoke_dashboard(cli: Path, workspace: Path, contract: Path, env: dict[str, str]) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    url = f"http://127.0.0.1:{port}/"
    command = [str(cli), "dashboard", "--workspace", str(workspace), "--contract", str(contract), "--port", str(port)]
    print("+", " ".join(command), "[HTTP smoke]", flush=True)
    with tempfile.TemporaryFile(mode="w+t") as errors:
        process = subprocess.Popen(command, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=errors, text=True)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 15
            while True:
                try:
                    with opener.open(url, timeout=1) as response:
                        page = response.read().decode("utf-8")
                        if "RunSpecimen" not in page or response.headers.get("Cache-Control") != "no-store":
                            raise SystemExit("installed dashboard HTML/security smoke failed")
                    break
                except urllib.error.URLError as exc:
                    if time.monotonic() >= deadline:
                        raise SystemExit("dashboard did not accept loopback HTTP within 15 seconds") from exc
                    if process.poll() is not None:
                        raise SystemExit("dashboard exited before accepting loopback HTTP")
                    time.sleep(0.1)
            with opener.open(url + "api/status", timeout=5) as response:
                status = json.load(response)
                if status.get("campaign_id") != "release-smoke" or status.get("approval") is not None:
                    raise SystemExit("installed dashboard returned unexpected run state")
            try:
                opener.open(urllib.request.Request(url + "api/status", data=b"{}", method="POST"), timeout=5)
            except urllib.error.HTTPError as exc:
                if exc.code != 405:
                    raise SystemExit(f"dashboard mutation returned {exc.code}, expected 405") from exc
            else:
                raise SystemExit("dashboard accepted a mutation")
        except (ValueError, KeyError) as exc:
            raise SystemExit(f"dashboard emitted invalid startup/status JSON: {exc}") from exc
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            if process.stdout:
                process.stdout.close()
            errors.seek(0)
            diagnostics = errors.read()
            if diagnostics:
                print(diagnostics, file=sys.stderr, end="")


def smoke_install(wheel: Path, source: Path, temp: Path, env: dict[str, str]) -> None:
    venv = temp / "venv"
    run(sys.executable, "-m", "venv", str(venv), cwd=temp, env=env)
    python = venv / "bin/python"
    cli = venv / "bin/runspecimen"
    run(str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel), cwd=temp, env=env)
    smoke_env = dict(env, PATH=str(venv / "bin") + os.pathsep + env.get("PATH", ""))
    version = run(str(cli), "--version", cwd=temp, env=smoke_env, capture=True).stdout.strip()
    if version != f"runspecimen {EXPECTED_PYTHON_VERSION}":
        raise SystemExit(f"installed console script has an unexpected version: {version}")
    run(str(python), "-m", "runspecimen", "--version", cwd=temp, env=smoke_env)
    workspace = temp / "smoke-workspace"
    (workspace / "work").mkdir(parents=True)
    shutil.copy2(source / "work/compute.py", workspace / "work/compute.py")
    contract = workspace / "contract.json"
    doc = json.loads((source / "examples/demo_contract.json").read_text(encoding="utf-8"))
    doc.update(campaign_id="release-smoke", run_id="unapproved", argv=[str(python), "work/compute.py"])
    contract.write_text(json.dumps(doc), encoding="utf-8")
    for action in ("doctor", "validate", "status"):
        args = [str(cli), action, "--workspace", str(workspace)]
        if action != "doctor":
            args.extend(["--contract", str(contract)])
        if action == "status":
            args.extend(["--campaign-id", "release-smoke", "--run-id", "unapproved"])
        result = json.loads(run(*args, cwd=workspace, env=smoke_env, capture=True).stdout)
        if action != "status" and result.get("ok") is not True:
            raise SystemExit(f"installed {action} check failed")
    run(str(python), str(source / "plugins/runspecimen/scripts/runspecimen_adapter.py"),
        "doctor", "--workspace", str(workspace), cwd=workspace, env=smoke_env)
    smoke_dashboard(cli, workspace, contract, smoke_env)
    if list(workspace.rglob("approval.json")) or (workspace / "outputs").exists():
        raise SystemExit("read-only release smoke unexpectedly approved or executed its payload")


def retain_artifacts(artifacts: Path, destination: Path) -> None:
    """Never replace a prior release, even when it has the same version."""
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise SystemExit(f"output directory must be absent or empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(artifacts.iterdir()):
        with path.open("rb") as source, (destination / path.name).open("xb") as output:
            shutil.copyfileobj(source, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="retain validated artifacts in an absent or empty directory")
    args = parser.parse_args(argv)
    if args.output_dir is not None:
        args.output_dir = args.output_dir.resolve()
        if args.output_dir.exists() and (not args.output_dir.is_dir() or any(args.output_dir.iterdir())):
            parser.error(f"output directory must be absent or empty: {args.output_dir}")
    check_versions()
    ensure_build_backend()
    env = offline_env()
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v", env=env)
    with tempfile.TemporaryDirectory(prefix="runspecimen-release-") as directory:
        temp = Path(directory)
        artifacts = temp / "artifacts"
        artifacts.mkdir()
        source = temp / "source"
        stage_source(source)
        run(sys.executable, "-m", "compileall", "-q", "src", "scripts", cwd=source, env=env)
        run(sys.executable, "-c", "from setuptools.build_meta import build_sdist; build_sdist('" + str(artifacts) + "')",
            cwd=source, env=env)
        sdists = list(artifacts.glob("runspecimen-*.tar.gz"))
        if len(sdists) != 1:
            raise SystemExit(f"expected one source archive, got {sdists}")
        extracted = inspect_sdist(sdists[0], temp / "extracted")
        run(sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps", "--no-build-isolation",
            "--wheel-dir", str(artifacts), str(extracted), cwd=temp, env=env)
        wheels = list(artifacts.glob("runspecimen-*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected one wheel, got {wheels}")
        inspect_wheel(wheels[0])
        smoke_install(wheels[0], extracted, temp, env)
        build_plugin(extracted, artifacts / f"runspecimen-plugin-{EXPECTED_PLUGIN_VERSION}.zip")
        report = {
            "ok": True, "version": EXPECTED_PYTHON_VERSION, "plugin_version": EXPECTED_PLUGIN_VERSION,
            "python": sys.version.split()[0], "platform": sys.platform,
            "checks": ["unit-tests", "source-compile", "source-archive-contents", "wheel-from-source-archive",
                       "wheel-contents", "fresh-install-console-script", "installed-cli-doctor-validate-status",
                       "installed-plugin-adapter", "installed-dashboard-http", "dashboard-write-refusal"],
            "artifacts": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(artifacts.iterdir())},
        }
        (artifacts / "release-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        hashes = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in sorted(artifacts.iterdir())]
        (artifacts / "SHA256SUMS").write_text("".join(hashes), encoding="utf-8")
        if args.output_dir is not None:
            retain_artifacts(artifacts, args.output_dir)
            print(f"Validated release artifacts: {args.output_dir}")
    print("RunSpecimen release candidate checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
