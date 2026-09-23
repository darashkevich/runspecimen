"""Configuration diagnostics bundles: inspect / preview / apply / export.

Doctor never silently syncs. Apply is explicit, atomic where possible, with
backup/rollback. Secrets are excluded from exported bundles.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from runspecimen import __version__
from runspecimen.artifact import (
    CURRENT_ARTIFACT_SCHEMA_VERSION,
    assert_artifact_version,
    assert_schema_kind,
    bind_artifact_digest,
    verify_artifact_digest,
)
from runspecimen.atomic import atomic_write_json, atomic_write_text, read_json
from runspecimen.errors import RunSpecimenError
from runspecimen.events import utc_now_iso
from runspecimen.hashutil import sha256_bytes, canonical_json_bytes
from runspecimen.isolation import host_capabilities
from runspecimen.lease import Lease
from runspecimen.paths import ensure_dir, resolve_workspace, workspace_state_root


class ConfigSyncError(RunSpecimenError):
    """Config bundle validation or apply failed."""


_SECRET_KEY_FRAGMENTS = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
)


def _looks_secret(key: str) -> bool:
    lowered = key.lower()
    return any(frag in lowered for frag in _SECRET_KEY_FRAGMENTS)


def config_root(workspace: Path) -> Path:
    return workspace_state_root(workspace) / "config"


def active_bundle_path(workspace: Path) -> Path:
    return config_root(workspace) / "active_bundle.json"


def backup_dir(workspace: Path) -> Path:
    return config_root(workspace) / "backups"


def inspect_environment(*, workspace: Path, contract_path: Path | None = None) -> dict[str, Any]:
    """Doctor-facing capability and config inspection (read-only)."""
    from runspecimen import DOCS_URLS

    workspace = resolve_workspace(workspace)
    lease = Lease.for_workspace(workspace, holder="doctor-inspect") if workspace.is_dir() else None
    lease_held = lease.is_locked_by_other() if lease is not None else False
    lease_meta = lease.read_meta() if lease is not None and lease_held else None

    hooks_status = _hook_registration_hints()
    active = None
    active_path = active_bundle_path(workspace)
    if active_path.is_file():
        try:
            active = read_json(active_path)
            verify_artifact_digest(active)
        except Exception as exc:  # noqa: BLE001
            active = {"error": str(exc), "path": str(active_path)}

    env_overrides = {
        k: ("<redacted>" if _looks_secret(k) else v)
        for k, v in sorted(os.environ.items())
        if k.startswith("RUNSPECIMEN_")
    }

    return {
        "ok": workspace.is_dir() and os.access(str(workspace), os.W_OK),
        "engine_version": __version__,
        "platform": __import__("platform").platform(),
        "python": __import__("platform").python_version(),
        "workspace": str(workspace),
        "workspace_writable": os.access(str(workspace), os.W_OK) if workspace.exists() else False,
        "workspace_lease_held": lease_held,
        "active_lease": lease_meta.to_dict() if lease_meta else None,
        "docs": dict(DOCS_URLS),
        "isolation": host_capabilities(),
        "adapters": {
            "cli": True,
            "dashboard": "read_only_loopback",
            "mcp": "no_approve",
            "note": (
                "Host adapters route supported consequential ops through RunSpecimen CLI. "
                "Direct editor edits, raw shell subprocesses, and remote actions outside "
                "declared backends are not claimed as controlled."
            ),
        },
        "supported_ops": [
            "approve(TTY)",
            "preflight",
            "run",
            "postflight",
            "verify",
            "requirements",
            "freshness",
            "snapshot",
            "usage",
            "coordination",
            "eval",
        ],
        "uncovered_ops": [
            "direct_editor_file_writes",
            "unmediated_shell_subprocesses",
            "remote_side_effects_outside_contract",
            "agent_approval",
        ],
        "hooks": hooks_status,
        "config_locations": {
            "workspace_state": str(workspace_state_root(workspace)),
            "active_bundle": str(active_path),
            "env_prefix": "RUNSPECIMEN_*",
            "precedence": [
                "explicit CLI flags",
                "active config bundle (workspace)",
                "environment RUNSPECIMEN_*",
                "engine defaults",
            ],
        },
        "active_bundle": active,
        "env_overrides": env_overrides,
        "contract_path": str(contract_path) if contract_path else None,
        "sync": {
            "silent_sync_during_doctor": False,
            "note": "Use config preview/apply explicitly; doctor never mutates config.",
        },
    }


def _hook_registration_hints() -> dict[str, Any]:
    """Safe functional checks for known in-repo plugin hook files (presence only)."""
    # Relative to installed package we cannot assume repo layout; report discovery tips.
    return {
        "checks": "presence_only",
        "expected_plugin_hooks": [
            "plugins/runspecimen/hooks/hooks.json",
            "plugins/runspecimen/hooks/claude-hooks.json",
        ],
        "functional_smoke": (
            "Run plugin tests (tests/test_plugins.py) for approve-gate refusal. "
            "Doctor does not execute hooks."
        ),
    }


def build_bundle(
    *,
    bundle_id: str,
    settings: dict[str, Any],
    env: dict[str, str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    clean_settings = {k: v for k, v in settings.items() if not _looks_secret(k)}
    clean_env = {
        k: v
        for k, v in (env or {}).items()
        if not _looks_secret(k) and k.startswith("RUNSPECIMEN_")
    }
    excluded = sorted(
        {k for k in settings if _looks_secret(k)}
        | {k for k in (env or {}) if _looks_secret(k)}
    )
    doc = {
        "schema_kind": "config_bundle",
        "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
        "id": bundle_id,
        "created_at": utc_now_iso(),
        "settings": clean_settings,
        "env": clean_env,
        "secret_keys_excluded": excluded,
        "precedence": [
            "explicit CLI flags",
            "active config bundle",
            "environment",
            "defaults",
        ],
        "note": note,
    }
    return bind_artifact_digest(doc)


def preview_apply(workspace: Path, bundle: dict[str, Any]) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    assert_schema_kind(bundle.get("schema_kind"), expected="config_bundle")
    assert_artifact_version(bundle.get("schema_version"))
    verify_artifact_digest(bundle)
    current = None
    path = active_bundle_path(workspace)
    if path.is_file():
        current = read_json(path)
    conflicts: list[str] = []
    if current and isinstance(current, dict):
        cur_settings = current.get("settings") or {}
        new_settings = bundle.get("settings") or {}
        for key in sorted(set(cur_settings) & set(new_settings)):
            if cur_settings[key] != new_settings[key]:
                conflicts.append(key)
    return {
        "action": "preview",
        "bundle_id": bundle.get("id"),
        "bundle_digest": bundle.get("artifact_digest"),
        "current_digest": (current or {}).get("artifact_digest"),
        "conflicts": conflicts,
        "would_write": str(path),
        "secret_keys_excluded": bundle.get("secret_keys_excluded", []),
    }


def apply_bundle(workspace: Path, bundle: dict[str, Any]) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    preview = preview_apply(workspace, bundle)
    root = config_root(workspace)
    ensure_dir(root)
    ensure_dir(backup_dir(workspace))
    active = active_bundle_path(workspace)
    backup_path = None
    if active.is_file():
        stamp = utc_now_iso().replace(":", "").replace("-", "")
        backup_path = backup_dir(workspace) / f"active_bundle.{stamp}.json"
        shutil.copy2(active, backup_path)
    # Atomic replace of active bundle
    atomic_write_json(active, bundle)
    return {
        "ok": True,
        "action": "apply",
        "bundle_id": bundle.get("id"),
        "bundle_digest": bundle.get("artifact_digest"),
        "path": str(active),
        "backup": str(backup_path) if backup_path else None,
        "conflicts_at_preview": preview.get("conflicts"),
        "rollback_hint": (
            f"Copy backup over {active}" if backup_path else "No prior bundle to restore"
        ),
    }


def rollback_bundle(workspace: Path, backup: Path) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    backup = backup.expanduser().resolve()
    if not backup.is_file():
        raise ConfigSyncError(f"backup not found: {backup}")
    doc = read_json(backup)
    assert_schema_kind(doc.get("schema_kind"), expected="config_bundle")
    verify_artifact_digest(doc)
    return apply_bundle(workspace, doc)


def export_bundle(workspace: Path, out_path: Path) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    active = active_bundle_path(workspace)
    if not active.is_file():
        raise ConfigSyncError("no active config bundle to export")
    doc = read_json(active)
    verify_artifact_digest(doc)
    out_path = out_path.expanduser().resolve()
    ensure_dir(out_path.parent)
    atomic_write_json(out_path, doc)
    return {
        "ok": True,
        "exported": str(out_path),
        "bundle_digest": doc.get("artifact_digest"),
        "install_hint": (
            "On the target host: runspecimen config apply --workspace <ws> --bundle <file>. "
            "Do not paste secrets into bundles."
        ),
    }
