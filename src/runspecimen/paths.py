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

CONTROL_PLANE_SYMLINK_REFUSAL = (
    "control-plane path must not be a symlink (or contain a symlinked component)"
)


def resolve_workspace(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve()


def ensure_within(workspace: Path, candidate: Path, *, label: str) -> Path:
    """Resolve candidate and require it to stay under workspace."""
    ws = workspace.resolve()
    raw = Path(candidate)
    try:
        abs_path = (ws / raw).resolve() if not raw.is_absolute() else raw.resolve()
        abs_path.relative_to(ws)
    except ValueError as exc:
        message = str(exc).lower()
        if "\x00" in str(candidate) or "null" in message or "embedded null" in message:
            raise PathEscapeError(
                f"{label} contains an unsafe path component: {candidate!r}"
            ) from exc
        # relative_to failure → escape
        try:
            abs_path  # type: ignore[name-defined]
        except NameError:
            raise PathEscapeError(
                f"{label} contains an unsafe path component: {candidate!r}"
            ) from exc
        raise PathEscapeError(
            f"{label} escapes workspace: {candidate} -> {abs_path} (workspace={ws})"
        ) from exc
    return abs_path


def rel_to_workspace(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def workspace_state_root(workspace: Path) -> Path:
    """Workspace-wide control plane (execution lease lives here)."""
    root = Path(workspace) / STATE_DIRNAME
    _assert_unlinked(root)
    return root


def run_state_dir(workspace: Path, campaign_id: str, run_id: str) -> Path:
    safe_campaign = _safe_id(campaign_id)
    safe_run = _safe_id(run_id)
    path = workspace_state_root(workspace) / "runs" / safe_campaign / safe_run
    assert_control_plane_not_symlinked(path)
    return path


def campaign_state_dir(workspace: Path, campaign_id: str) -> Path:
    path = workspace_state_root(workspace) / "runs" / _safe_id(campaign_id)
    assert_control_plane_not_symlinked(path)
    return path


def _control_plane_chain(path: Path) -> list[Path]:
    """``.runspecimen`` ancestor down to *path*, or just *path* if none."""
    chain: list[Path] = []
    cursor = Path(path)
    found = False
    while True:
        chain.append(cursor)
        if cursor.name == STATE_DIRNAME:
            found = True
            break
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    if not found:
        return [Path(path)]
    chain.reverse()
    return chain


def _assert_unlinked(path: Path) -> None:
    if path.is_symlink():
        try:
            target = path.resolve()
        except OSError:
            target = path
        raise PathEscapeError(f"{CONTROL_PLANE_SYMLINK_REFUSAL}: {path} -> {target}")


def assert_control_plane_not_symlinked(path: Path) -> None:
    """Refuse a symlinked ``.runspecimen``, campaign, or run dir (WH-04).

    Only components from the ``.runspecimen`` ancestor downward are checked, so
    host aliases such as macOS ``/var`` → ``/private/var`` stay accepted.
    """
    for item in _control_plane_chain(path):
        _assert_unlinked(item)


def validate_id(value: str) -> str:
    """Public path-safe id check (campaign/run/predecessor)."""
    return _safe_id(value)


def _safe_id(value: str) -> str:
    if not value or not all(c.isalnum() or c in "-_." for c in value):
        raise PathEscapeError(f"unsafe id (use alnum/_/-/. only): {value!r}")
    if value in {".", ".."} or value.startswith("."):
        raise PathEscapeError(f"unsafe id: {value!r}")
    return value


def ensure_dir(path: Path) -> Path:
    """Create *path* without following a control-plane symlink (WH-04)."""
    assert_control_plane_not_symlinked(path)
    missing: list[Path] = []
    cursor = Path(path)
    while not cursor.exists():
        if cursor.is_symlink():
            _assert_unlinked(cursor)
        missing.append(cursor)
        if cursor.name == STATE_DIRNAME:
            break
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    if cursor.is_symlink():
        _assert_unlinked(cursor)
    for item in reversed(missing):
        _assert_unlinked(item)
        item.mkdir(exist_ok=True)
        _assert_unlinked(item)
    return path


def env_with_workspace(workspace: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["RUNSPECIMEN_WORKSPACE"] = str(workspace)
    return env
