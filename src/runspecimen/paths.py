"""Workspace-relative path helpers and state layout."""

from __future__ import annotations

import os
from pathlib import Path

from runspecimen.errors import PathEscapeError

STATE_DIRNAME = ".runspecimen"
EVENTS_FILENAME = "events.jsonl"
EVENTS_APPEND_LOCK_FILENAME = "events.append.lock"
STATE_FILENAME = "state.json"
APPROVAL_FILENAME = "approval.json"
LEASE_FILENAME = "execution.lock"
LEASE_META_FILENAME = "execution.meta.json"
CERTIFICATE_FILENAME = "certificate.json"
STDOUT_FILENAME = "stdout.capture"
STDERR_FILENAME = "stderr.capture"


def resolve_workspace(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve()


def ensure_within(workspace: Path, candidate: Path, *, label: str) -> Path:
    """Resolve candidate and require it to stay under workspace."""
    ws = workspace.resolve()
    raw = Path(candidate)
    abs_path = (ws / raw).resolve() if not raw.is_absolute() else raw.resolve()
    try:
        abs_path.relative_to(ws)
    except ValueError as exc:
        raise PathEscapeError(
            f"{label} escapes workspace: {candidate} -> {abs_path} (workspace={ws})"
        ) from exc
    return abs_path


def rel_to_workspace(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def workspace_state_root(workspace: Path) -> Path:
    """Workspace-wide control plane (execution lease lives here)."""
    return Path(workspace) / STATE_DIRNAME


def run_state_dir(workspace: Path, campaign_id: str, run_id: str) -> Path:
    safe_campaign = _safe_id(campaign_id)
    safe_run = _safe_id(run_id)
    return workspace_state_root(workspace) / "runs" / safe_campaign / safe_run


def campaign_state_dir(workspace: Path, campaign_id: str) -> Path:
    return workspace_state_root(workspace) / "runs" / _safe_id(campaign_id)


def _safe_id(value: str) -> str:
    if not value or not all(c.isalnum() or c in "-_." for c in value):
        raise PathEscapeError(f"unsafe id (use alnum/_/-/. only): {value!r}")
    if value in {".", ".."} or value.startswith("."):
        raise PathEscapeError(f"unsafe id: {value!r}")
    return value


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_with_workspace(workspace: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["RUNSPECIMEN_WORKSPACE"] = str(workspace)
    return env
