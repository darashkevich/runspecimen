"""Opt-in confinement backends.

``none`` is the default and does not wrap the approved argv. ``sandbox-exec``
and ``bwrap`` are used only when the contract names them and the tool is on
PATH. A missing declared tool fails closed. These integrations confine writes
(and, when asked, network). They are not an OS sandbox product.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from runspecimen.contract import IsolationSpec
from runspecimen.errors import PreflightError
from runspecimen.hashutil import sha256_file

_PLAN_IDENTITY_KEYS = ("backend", "enforced", "network", "tool", "tool_sha256")


def discover_tool(backend: str) -> str | None:
    """Locate a backend by name. This does not execute it."""
    if backend == "none":
        return None
    if backend == "sandbox-exec":
        return shutil.which("sandbox-exec")
    if backend == "bwrap":
        return shutil.which("bwrap")
    return None


def fingerprint_tool(path: str) -> dict[str, str]:
    """Hash the resolved tool file. Never executes it."""
    try:
        resolved = Path(path).resolve(strict=True)
    except OSError as exc:
        raise PreflightError(f"isolation tool is not a readable file: {path}") from exc
    if not resolved.is_file():
        raise PreflightError(f"isolation tool is not a regular file: {resolved}")
    if not os.access(resolved, os.X_OK):
        raise PreflightError(f"isolation tool is not executable: {resolved}")
    return {"tool": str(resolved), "tool_sha256": sha256_file(resolved)}


def assert_tool_outside_workspace(plan: dict[str, Any], workspace: Path) -> None:
    tool = plan.get("tool")
    if not isinstance(tool, str) or not tool:
        return
    resolved = Path(tool).resolve()
    root = workspace.resolve()
    if resolved == root or root in resolved.parents:
        raise PreflightError(
            "isolation tool must not live inside the workspace "
            f"({resolved})"
        )


def host_capabilities() -> dict[str, Any]:
    """Discovery only. Does not claim a backend is in effect."""
    return {
        "default_backend": "none",
        "claim": (
            "Default execution is not confined. Opt in with contract.isolation. "
            "Resource limits are not an OS sandbox."
        ),
        "backends": {
            "none": {"available": True, "enforced": False},
            "sandbox-exec": {
                "available": discover_tool("sandbox-exec") is not None,
                "platform": "darwin",
            },
            "bwrap": {
                "available": discover_tool("bwrap") is not None,
                "platform": "linux",
            },
        },
    }


def effective_plan(spec: IsolationSpec) -> dict[str, Any]:
    """Return the receipt object for this host, or refuse a missing backend."""
    if spec.backend == "none":
        return {
            "backend": "none",
            "claim": "No isolation backend. The workload is not confined by RunSpecimen.",
            "enforced": False,
            "network": "not-enforced",
            "residual": (
                "Orchestration limits only: one workspace lease, wall clock, "
                "capture bounds, and process-group stop. Writes and network are not confined."
            ),
            "tool": None,
            "tool_sha256": None,
        }

    found = discover_tool(spec.backend)
    if found is None:
        raise PreflightError(
            f"isolation backend {spec.backend!r} was declared but is not available on this host"
        )
    finger = fingerprint_tool(found)

    network = "allowed" if spec.network else "denied"
    if spec.backend == "sandbox-exec":
        claim = "seatbelt write confinement to the workspace; network " + network
        residual = (
            "Not an OS sandbox. The seatbelt profile allows host reads, process "
            "execution, and Mach lookup so the approved program can start. It denies "
            "writes outside the workspace"
            + (" and allows network." if spec.network else " and denies network.")
            + " Profile escape and a hostile approved payload stay the operator's risk."
        )
    elif spec.backend == "bwrap":
        claim = "bubblewrap workspace bind with a read-only host root; network " + network
        residual = (
            "Not an OS sandbox. The host root is mounted read-only and the workspace "
            "is bind-mounted read-write. Missing user namespaces or bwrap features fail "
            "the spawn. The approved program keeps whatever authority the mount allows."
        )
    else:
        raise PreflightError(f"unknown isolation backend {spec.backend!r}")

    return {
        "backend": spec.backend,
        "claim": claim,
        "enforced": True,
        "network": network,
        "residual": residual,
        "tool": finger["tool"],
        "tool_sha256": finger["tool_sha256"],
    }


def assert_tool_unchanged(plan: dict[str, Any]) -> str:
    """Re-read the approved tool file. Refuse if the path or bytes changed."""
    if plan.get("backend") == "none":
        return ""
    tool = plan.get("tool")
    expected = plan.get("tool_sha256")
    if not isinstance(tool, str) or not tool or not isinstance(expected, str) or len(expected) != 64:
        raise PreflightError("isolation plan is missing the approved tool fingerprint")
    current = fingerprint_tool(tool)
    if current["tool"] != str(Path(tool).resolve()) or current["tool_sha256"] != expected:
        raise PreflightError(
            "isolation tool changed since approval; refusing to launch "
            f"(approved {expected}, live {current['tool_sha256']})"
        )
    return current["tool"]


def plan_identity(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: plan.get(key) for key in _PLAN_IDENTITY_KEYS}


def plans_match(approved: dict[str, Any] | None, live: dict[str, Any]) -> bool:
    if not isinstance(approved, dict):
        return False
    return plan_identity(approved) == plan_identity(live)


def _scheme_string(path: Path) -> str:
    text = str(path)
    if any(ch in text for ch in "\n\r()"):
        raise PreflightError(
            "workspace path cannot be expressed in a seatbelt profile; "
            "move the workspace off characters () or newlines"
        )
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped + '"'


def seatbelt_profile(workspace: Path, *, network_allowed: bool) -> str:
    root = workspace.resolve()
    if root == Path("/"):
        raise PreflightError("refusing seatbelt confinement for a workspace of /")
    workspace_lit = _scheme_string(root)
    network_rule = "(allow network*)" if network_allowed else "(deny network*)"
    return "\n".join(
        [
            "(version 1)",
            "(deny default)",
            "(allow process*)",
            "(allow signal)",
            "(allow sysctl-read)",
            "(allow mach-lookup)",
            "(allow ipc-posix-shm*)",
            "(allow system-socket)",
            "(allow file-ioctl)",
            "(allow file-read*)",
            "(allow file-read-metadata)",
            "(allow file-map-executable)",
            f"(allow file-write* (subpath {workspace_lit}))",
            network_rule,
            "",
        ]
    )


def confinement_argv(
    plan: dict[str, Any],
    launch_argv: list[str],
    *,
    workspace: Path,
    cwd: Path,
    profile_path: Path,
) -> list[str]:
    """Wrap an approved argv. ``none`` returns the argv unchanged."""
    backend = plan.get("backend")
    if backend == "none":
        return list(launch_argv)
    tool = assert_tool_unchanged(plan)

    workspace = workspace.resolve()
    if workspace == Path("/"):
        raise PreflightError("refusing confinement for a workspace of /")

    if backend == "sandbox-exec":
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(
            seatbelt_profile(workspace, network_allowed=plan.get("network") == "allowed"),
            encoding="utf-8",
        )
        return [tool, "-f", str(profile_path), *launch_argv]

    if backend == "bwrap":
        # Map this process into a new user namespace as uid/gid 0 so
        # ``--unshare-net`` can configure loopback (needed on GitHub Actions
        # runners where the outer user lacks CAP_NET_ADMIN).
        argv = [
            tool,
            "--die-with-parent",
            "--unshare-user",
            "--uid",
            "0",
            "--gid",
            "0",
            "--ro-bind",
            "/",
            "/",
            "--bind",
            str(workspace),
            str(workspace),
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--chdir",
            str(cwd),
        ]
        if plan.get("network") == "denied":
            argv.append("--unshare-net")
        argv.append("--")
        argv.extend(launch_argv)
        return argv

    raise PreflightError(f"unknown isolation backend {backend!r}")
