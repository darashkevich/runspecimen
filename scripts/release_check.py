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
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PYTHON_VERSION = "0.2.0rc10"
EXPECTED_PLUGIN_VERSION = "0.2.0-rc.10"
SOURCE_COMPONENTS = (
    "pyproject.toml", "MANIFEST.in", "README.md", "LICENSE", "CHANGELOG.md",
    "SECURITY.md", "src", "scripts", "tests", "docs", "examples", "work",
    "plugins", ".cursor", ".cursor-plugin", ".claude-plugin", ".junie-extension",
    ".agents",
)
PLUGIN_COMPONENTS = (
    ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json",
    ".claude-plugin/plugin.json", "gemini-extension.json", "extension.json",
    ".mcp.json", "mcp/.mcp.json", "GEMINI.md", "README.md",
    "assets/runspecimen-logo.png",
    "assets/logo.png",
    "assets/composer-icon.png",
    "assets/logo.svg",
    "assets/composer-icon.svg",
    "rules/runspecimen.mdc", "scripts/runspecimen_adapter.py",
    "scripts/block_approve_gate.py", "scripts/runspecimen_mcp.py",
    "hooks/hooks.json", "hooks/claude-hooks.json", "skills/runspecimen/SKILL.md",
    "commands/request-approval.md", "commands/request-approval.toml",
    "grok/README.md", "grok/AGENTS.md",
    "gemini/README.md", "jetbrains/README.md",
    "jetbrains/scripts/ide_actions.py",
    "windsurf/README.md", "windsurf/skills/runspecimen/SKILL.md",
    "windsurf/rules/runspecimen.md",
    "guidelines/runspecimen.md",
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
    plugin = json.loads((plugin_root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    cursor = json.loads((plugin_root / ".cursor-plugin/plugin.json").read_text(encoding="utf-8"))
    claude = json.loads((plugin_root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    gemini = json.loads((plugin_root / "gemini-extension.json").read_text(encoding="utf-8"))
    if plugin.get("version", "").split("+", 1)[0] != EXPECTED_PLUGIN_VERSION:
        raise SystemExit("Codex plugin version does not match release_check.py")
    if cursor.get("version") != EXPECTED_PLUGIN_VERSION or cursor.get("name") != plugin.get("name"):
        raise SystemExit("Cursor plugin version/name is inconsistent")
    if claude.get("version") != EXPECTED_PLUGIN_VERSION or claude.get("name") != plugin.get("name"):
        raise SystemExit("Claude plugin version/name is inconsistent")
    if gemini.get("version") != EXPECTED_PLUGIN_VERSION or gemini.get("name") != plugin.get("name"):
        raise SystemExit("Gemini extension version/name is inconsistent")
    if "approve" not in " ".join(gemini.get("excludeTools") or []).lower():
        raise SystemExit("Gemini extension must exclude approve-like shell tools")
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
    claude_market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    claude_entries = claude_market.get("plugins")
    if not isinstance(claude_entries, list) or len(claude_entries) != 1:
        raise SystemExit("Claude marketplace must contain exactly the RunSpecimen plugin")
    if any(claude_entries[0].get(key) != value for key, value in (
        ("name", "runspecimen"), ("source", "./plugins/runspecimen"),
        ("version", EXPECTED_PLUGIN_VERSION),
    )):
        raise SystemExit("Claude marketplace entry is inconsistent")
    junie_market = json.loads((ROOT / ".junie-extension/marketplace.json").read_text(encoding="utf-8"))
    junie_entries = junie_market.get("extensions")
    if not isinstance(junie_entries, list) or len(junie_entries) != 1:
        raise SystemExit("Junie marketplace must contain exactly the RunSpecimen extension")
    if any(junie_entries[0].get(key) != value for key, value in (
        ("name", "runspecimen"), ("source", "./plugins/runspecimen"),
        ("version", EXPECTED_PLUGIN_VERSION),
    )):
        raise SystemExit("Junie marketplace entry is inconsistent")
    mcp = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
    if "runspecimen" not in (mcp.get("mcpServers") or {}):
        raise SystemExit("plugin .mcp.json must declare runspecimen server")
    junie_mcp = json.loads((plugin_root / "mcp/.mcp.json").read_text(encoding="utf-8"))
    if "runspecimen" not in (junie_mcp.get("mcpServers") or {}):
        raise SystemExit("plugin mcp/.mcp.json must declare runspecimen server")
    hooks = json.loads((plugin_root / "hooks/hooks.json").read_text(encoding="utf-8"))
    if "BeforeTool" not in (hooks.get("hooks") or {}) or "PreToolUse" in (hooks.get("hooks") or {}):
        raise SystemExit("hooks/hooks.json must be Gemini BeforeTool-only (Claude rejects BeforeTool)")
    claude_hooks = json.loads((plugin_root / "hooks/claude-hooks.json").read_text(encoding="utf-8"))
    if "PreToolUse" not in (claude_hooks.get("hooks") or {}) or "BeforeTool" in (claude_hooks.get("hooks") or {}):
        raise SystemExit("hooks/claude-hooks.json must be Claude PreToolUse-only")
    claude_plugin = json.loads((plugin_root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    if claude_plugin.get("hooks") != "./hooks/claude-hooks.json":
        raise SystemExit("Claude plugin.json must point hooks at ./hooks/claude-hooks.json")
    plugin_xml = (
        plugin_root / "jetbrains/intellij-plugin/src/main/resources/META-INF/plugin.xml"
    ).read_text(encoding="utf-8")
    if "ApproveAction" in plugin_xml or re.search(r">\s*Approve\s*<", plugin_xml):
        raise SystemExit("IntelliJ plugin.xml must not expose an Approve action")
    for relative in PLUGIN_COMPONENTS:
        if not (plugin_root / relative).is_file():
            raise SystemExit(f"missing plugin component: {relative}")


def ensure_build_backend() -> None:
    """Require pip/setuptools/wheel visible under the same env the build uses.

    ``offline_env`` sets ``PYTHONNOUSERSITE=1``, so a user-site-only
    ``setuptools>=77`` must not pass this check — that combination produces
    ``UNKNOWN-0.0.0`` sdists when the system setuptools is too old for PEP 621.
    """
    probe = (
        "import re\n"
        "import setuptools\n"
        "import wheel  # noqa: F401\n"
        "import pip  # noqa: F401\n"
        "match = re.match(r'(\\d+)', setuptools.__version__)\n"
        "raise SystemExit(0 if match and int(match.group(1)) >= 77 else 2)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        env=offline_env(),
        text=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=60,
    )
    if result.returncode == 0:
        return
    if result.returncode == 2:
        raise SystemExit(
            "setuptools>=77 must be installed in this interpreter's site-packages "
            "(not only --user); offline release builds set PYTHONNOUSERSITE=1. "
            "Use a venv / .tools Python, or: python3 -m pip install --upgrade 'setuptools>=77' wheel"
        )
    detail = (result.stderr or result.stdout or "").strip()
    raise SystemExit(
        "pip, setuptools>=77, and wheel are required under PYTHONNOUSERSITE=1; "
        f"run sh scripts/bootstrap_dev.sh first ({detail})"
    )


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


# Optional extras may appear as Requires-Dist with an ``extra == "…"`` marker.
# Hard (unconditional) dependencies remain forbidden so default installs stay
# stdlib-only. Keep this list in sync with ``[project.optional-dependencies]``.
VETTED_OPTIONAL_EXTRAS = frozenset({"ed25519", "signing"})
_VETTED_OPTIONAL_REQUIREMENT_NAMES = frozenset({"pynacl"})
_REQUIRES_DIST_RE = re.compile(r"^Requires-Dist:\s*(.+)$", re.MULTILINE)
_EXTRA_MARKER_RE = re.compile(
    r"""extra\s*==\s*(?P<q>['"])(?P<extra>[A-Za-z0-9._-]+)(?P=q)"""
)
_REQUIREMENT_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def validate_requires_dist_metadata(metadata: str) -> None:
    """Ensure METADATA declares no hard deps; only vetted optional extras.

    Raises SystemExit with a clear message on policy violations.
    """
    for raw in _REQUIRES_DIST_RE.findall(metadata):
        line = raw.strip()
        if ";" not in line:
            raise SystemExit(
                "the dependency-free runtime unexpectedly declares a hard dependency: "
                f"Requires-Dist: {line}"
            )
        requirement, marker = line.split(";", 1)
        name_match = _REQUIREMENT_NAME_RE.match(requirement)
        if name_match is None:
            raise SystemExit(f"unparseable Requires-Dist requirement: {line}")
        req_name = name_match.group(1).lower().replace("_", "-")
        extras = {match.group("extra") for match in _EXTRA_MARKER_RE.finditer(marker)}
        if not extras:
            raise SystemExit(
                "Requires-Dist marker must bind to an optional extra "
                f"(got: Requires-Dist: {line})"
            )
        unknown = extras - VETTED_OPTIONAL_EXTRAS
        if unknown:
            raise SystemExit(
                f"unvetted optional extra(s) in Requires-Dist: {sorted(unknown)} "
                f"(allowed: {sorted(VETTED_OPTIONAL_EXTRAS)})"
            )
        if req_name not in _VETTED_OPTIONAL_REQUIREMENT_NAMES:
            raise SystemExit(
                f"unvetted optional dependency {req_name!r} for extras {sorted(extras)} "
                f"(allowed packages: {sorted(_VETTED_OPTIONAL_REQUIREMENT_NAMES)})"
            )


def inspect_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        safe_members(names)
        dist_info = f"runspecimen-{EXPECTED_PYTHON_VERSION}.dist-info"
        required = {
            "runspecimen/cli.py", "runspecimen/dashboard.py", "runspecimen/py.typed",
            f"{dist_info}/METADATA", f"{dist_info}/RECORD",
            f"{dist_info}/entry_points.txt",
            # Note: licenses/LICENSE may or may not be present depending on setuptools version
        }
        if not required.issubset(names):
            raise SystemExit(f"wheel is missing required files: {sorted(required - set(names))}")
        metadata = archive.read(f"{dist_info}/METADATA").decode("utf-8")
        if f"\nVersion: {EXPECTED_PYTHON_VERSION}\n" not in metadata:
            raise SystemExit("wheel metadata has the wrong version")
        validate_requires_dist_metadata(metadata)


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


def smoke_dashboard(python: Path, workspace: Path, contract: Path, env: dict[str, str]) -> None:
    """Exercise the installed wheel's loopback server in one process.

    macOS hosted runners do not reliably permit a parent process to probe a
    separately spawned loopback server, despite allowing the server itself.
    """
    script = """
import json, threading, urllib.error, urllib.request
from pathlib import Path
from runspecimen.dashboard import start_dashboard
workspace, contract = map(Path, __import__('sys').argv[1:3])
server, url = start_dashboard(workspace=workspace, contract_path=contract)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=5) as response:
        page = response.read().decode('utf-8')
        assert 'RunSpecimen' in page and response.headers.get('Cache-Control') == 'no-store'
    with opener.open(url + 'api/status', timeout=5) as response:
        status = json.load(response)
        assert status.get('campaign_id') == 'release-smoke' and status.get('approval') is None
    try:
        opener.open(urllib.request.Request(url + 'api/status', data=b'{}', method='POST'), timeout=5)
    except urllib.error.HTTPError as exc:
        assert exc.code == 405
    else:
        raise AssertionError('dashboard accepted a mutation')
finally:
    server.shutdown(); thread.join(timeout=5); server.server_close()
"""
    run(str(python), "-c", script, str(workspace), str(contract), cwd=workspace, env=env)


def _run_checked(cli: Path, *args: str, cwd: Path, env: dict[str, str],
                  expect_failure: bool = False) -> subprocess.CompletedProcess[str]:
    """Run CLI command and return result, optionally expecting failure."""
    cmd = [str(cli)] + list(args)
    print("+", " ".join(cmd), flush=True)
    result = subprocess.run(
        cmd, cwd=cwd, env=env, text=True, timeout=60,
        stdin=subprocess.DEVNULL, capture_output=True,
    )
    if expect_failure and result.returncode == 0:
        raise SystemExit(f"expected failure but command succeeded: {' '.join(cmd)}")
    if not expect_failure and result.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(cmd)}\nstderr: {result.stderr}")
    return result


def smoke_signing(cli: Path, python: Path, workspace: Path, contract: Path, env: dict[str, str]) -> None:
    """Exercise sign, verify-signature, keygen, and list-keys with real command entry.

    Tests keygen/list-keys success paths and sign/verify-signature error paths.
    Does not approve or execute any payload; validates that commands enter their
    logic branches and produce clean errors (no tracebacks) for controlled invalid inputs.
    """
    # --- keygen success ---
    result = _run_checked(cli, "keygen", "--workspace", str(workspace), "--key-id", "smoke-key",
                          cwd=workspace, env=env)
    keygen_output = json.loads(result.stdout)
    if not keygen_output.get("ok"):
        raise SystemExit(f"keygen failed: {result.stderr}")

    # --- list-keys success ---
    result = _run_checked(cli, "list-keys", "--workspace", str(workspace),
                          cwd=workspace, env=env)
    list_output = json.loads(result.stdout)
    if "smoke-key" not in list_output.get("key_ids", []):
        raise SystemExit(f"list-keys did not show created key: {result.stdout}")

    # --- sign: missing certificate file (enters command branch, expects clean error) ---
    missing_cert = workspace / "nonexistent-certificate.json"
    result = _run_checked(
        cli, "sign",
        "--workspace", str(workspace),
        "--key-id", "smoke-key",
        "--certificate", str(missing_cert),
        "--contract", str(contract),
        cwd=workspace, env=env, expect_failure=True,
    )
    if "Traceback" in result.stderr:
        raise SystemExit(f"sign with missing certificate produced traceback:\n{result.stderr}")
    if "error" not in result.stderr.lower() and "not found" not in result.stderr.lower():
        raise SystemExit(f"sign with missing certificate did not report error: {result.stderr}")

    # --- sign: invalid JSON certificate (enters command branch, expects clean error) ---
    invalid_cert = workspace / "invalid-certificate.json"
    invalid_cert.write_text("this is not valid json {{{{", encoding="utf-8")
    result = _run_checked(
        cli, "sign",
        "--workspace", str(workspace),
        "--key-id", "smoke-key",
        "--certificate", str(invalid_cert),
        "--contract", str(contract),
        cwd=workspace, env=env, expect_failure=True,
    )
    if "Traceback" in result.stderr:
        raise SystemExit(f"sign with invalid JSON produced traceback:\n{result.stderr}")

    # --- sign: missing key (enters command branch, expects clean error) ---
    # Create a minimal but valid JSON certificate to pass JSON parsing
    minimal_cert = workspace / "minimal-certificate.json"
    minimal_cert.write_text('{"campaign_id": "test", "run_id": "test"}', encoding="utf-8")
    result = _run_checked(
        cli, "sign",
        "--workspace", str(workspace),
        "--key-id", "nonexistent-key",
        "--certificate", str(minimal_cert),
        "--contract", str(contract),
        cwd=workspace, env=env, expect_failure=True,
    )
    if "Traceback" in result.stderr:
        raise SystemExit(f"sign with missing key produced traceback:\n{result.stderr}")
    if "error" not in result.stderr.lower():
        raise SystemExit(f"sign with missing key did not report error: {result.stderr}")

    # --- verify-signature: missing signed file (enters command branch, expects clean error) ---
    # Note: verify-signature outputs JSON to stdout even on failure
    missing_signed = workspace / "nonexistent.signed.json"
    result = _run_checked(
        cli, "verify-signature",
        "--workspace", str(workspace),
        "--key-id", "smoke-key",
        "--signed", str(missing_signed),
        "--contract", str(contract),
        cwd=workspace, env=env, expect_failure=True,
    )
    if "Traceback" in result.stderr or "Traceback" in result.stdout:
        raise SystemExit(f"verify-signature with missing file produced traceback:\n{result.stderr}\n{result.stdout}")
    combined = result.stderr.lower() + result.stdout.lower()
    if "error" not in combined and "not found" not in combined:
        raise SystemExit(f"verify-signature with missing file did not report error: stdout={result.stdout}, stderr={result.stderr}")

    # --- verify-signature: invalid JSON (enters command branch, expects clean error) ---
    invalid_signed = workspace / "invalid.signed.json"
    invalid_signed.write_text("not valid json }}}}", encoding="utf-8")
    result = _run_checked(
        cli, "verify-signature",
        "--workspace", str(workspace),
        "--key-id", "smoke-key",
        "--signed", str(invalid_signed),
        "--contract", str(contract),
        cwd=workspace, env=env, expect_failure=True,
    )
    if "Traceback" in result.stderr or "Traceback" in result.stdout:
        raise SystemExit(f"verify-signature with invalid JSON produced traceback:\n{result.stderr}\n{result.stdout}")

    # --- verify-signature: missing key (enters command branch, expects clean error) ---
    # Create a minimal signed structure
    minimal_signed = workspace / "minimal.signed.json"
    minimal_signed.write_text('{"certificate": {}, "signature": "abc", "key_id": "test"}', encoding="utf-8")
    result = _run_checked(
        cli, "verify-signature",
        "--workspace", str(workspace),
        "--key-id", "nonexistent-key",
        "--signed", str(minimal_signed),
        "--contract", str(contract),
        cwd=workspace, env=env, expect_failure=True,
    )
    if "Traceback" in result.stderr or "Traceback" in result.stdout:
        raise SystemExit(f"verify-signature with missing key produced traceback:\n{result.stderr}\n{result.stdout}")
    combined = result.stderr.lower() + result.stdout.lower()
    if "error" not in combined and "not found" not in combined:
        raise SystemExit(f"verify-signature with missing key did not report error: stdout={result.stdout}, stderr={result.stderr}")


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
    run(str(cli), "dashboard", "--help", cwd=workspace, env=smoke_env, capture=True)
    smoke_dashboard(python, workspace, contract, smoke_env)
    smoke_signing(cli, python, workspace, contract, smoke_env)
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
                       "installed-plugin-adapter", "installed-dashboard-http", "dashboard-write-refusal",
                       "installed-keygen-listkeys", "installed-sign-verify-error-handling"],
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
