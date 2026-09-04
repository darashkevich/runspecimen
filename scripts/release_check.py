#!/usr/bin/env python3
"""Build and smoke-test a RunSpecimen release candidate without network access."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PYTHON_VERSION = "0.2.0rc3"
EXPECTED_PLUGIN_VERSION = "0.2.0-rc.3"


def run(*args: str, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def check_versions() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    if match is None or match.group(1) != EXPECTED_PYTHON_VERSION:
        raise SystemExit("pyproject version does not match release_check.py")
    plugin = json.loads(
        (ROOT / "plugins/runspecimen/.codex-plugin/plugin.json").read_text(encoding="utf-8")
    )
    if plugin.get("version", "").split("+", 1)[0] != EXPECTED_PLUGIN_VERSION:
        raise SystemExit("plugin version does not match release_check.py")
    cursor_plugin = json.loads(
        (ROOT / "plugins/runspecimen/.cursor-plugin/plugin.json").read_text(
            encoding="utf-8"
        )
    )
    if cursor_plugin.get("version") != EXPECTED_PLUGIN_VERSION:
        raise SystemExit("Cursor plugin version does not match release_check.py")
    if cursor_plugin.get("name") != plugin.get("name"):
        raise SystemExit("Codex and Cursor plugin names do not match")
    prompts = plugin.get("interface", {}).get("defaultPrompt")
    if not isinstance(prompts, list) or not prompts or not all(
        isinstance(item, str) and item for item in prompts
    ):
        raise SystemExit("Codex plugin defaultPrompt must be a non-empty string array")

    cursor_marketplace = json.loads(
        (ROOT / ".cursor-plugin/marketplace.json").read_text(encoding="utf-8")
    )
    cursor_entries = cursor_marketplace.get("plugins")
    if not isinstance(cursor_entries, list) or len(cursor_entries) != 1:
        raise SystemExit("Cursor marketplace must contain exactly the RunSpecimen plugin")
    cursor_entry = cursor_entries[0]
    if (
        cursor_entry.get("name") != "runspecimen"
        or cursor_entry.get("source") != "plugins/runspecimen"
        or cursor_entry.get("version") != EXPECTED_PLUGIN_VERSION
    ):
        raise SystemExit("Cursor marketplace entry is inconsistent")

    for required in (
        "plugins/runspecimen/README.md",
        "plugins/runspecimen/rules/runspecimen.mdc",
        "plugins/runspecimen/scripts/runspecimen_adapter.py",
        "plugins/runspecimen/skills/runspecimen/SKILL.md",
    ):
        if not (ROOT / required).is_file():
            raise SystemExit(f"missing plugin component: {required}")


def ensure_build_backend() -> None:
    """Fail clearly when the already-installed backend cannot build this project.

    The release check promises to work offline. Installing or upgrading build
    dependencies here would silently turn that promise into a network request.
    ``scripts/bootstrap_dev.sh`` is the explicit setup step for a fresh host.
    """
    try:
        import setuptools
    except ImportError as exc:
        raise SystemExit(
            "setuptools>=77 is required; run sh scripts/bootstrap_dev.sh first"
        ) from exc

    def version_tuple(value: str) -> tuple[int, ...]:
        match = re.match(r"(\d+(?:\.\d+)*)", value)
        if match is None:
            return ()
        return tuple(int(part) for part in match.group(1).split("."))

    if version_tuple(setuptools.__version__) < (77,):
        raise SystemExit(
            "setuptools>=77 is required; run sh scripts/bootstrap_dev.sh first"
        )


def main() -> int:
    check_versions()
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
    run(sys.executable, "-m", "compileall", "-q", "src", "scripts")
    ensure_build_backend()

    with tempfile.TemporaryDirectory(prefix="runspecimen-rc-") as temp:
        temp_path = Path(temp)
        wheel_dir = temp_path / "wheel"
        install_dir = temp_path / "install"
        wheel_dir.mkdir()
        install_dir.mkdir()
        run(
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
            str(ROOT),
        )
        wheels = list(wheel_dir.glob("runspecimen-*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected one wheel, got {wheels}")
        run(
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(install_dir),
            str(wheels[0]),
        )
        smoke_env = os.environ.copy()
        smoke_env["PYTHONPATH"] = str(install_dir)
        run(sys.executable, "-m", "runspecimen", "--version", env=smoke_env)
        run(
            sys.executable,
            "-m",
            "runspecimen",
            "doctor",
            "--workspace",
            temp,
            env=smoke_env,
        )
        adapter_env = smoke_env.copy()
        adapter_env["PATH"] = str(install_dir / "bin") + os.pathsep + adapter_env.get(
            "PATH", ""
        )
        run(
            sys.executable,
            str(ROOT / "plugins/runspecimen/scripts/runspecimen_adapter.py"),
            "doctor",
            "--workspace",
            temp,
            env=adapter_env,
        )

    print("RunSpecimen release candidate checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
