"""Workspace-local shared policy files.

A contract may name a JSON policy inside the workspace. The file's SHA-256 is
part of the contract the human approves. There is no network fetch and no
remote policy service.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runspecimen.contract import (
    Contract,
    _reject_unknown,
    _require_dict,
    _require_int,
    _require_list,
    _require_str,
)
from runspecimen.errors import ContractError, PreflightError
from runspecimen.hashutil import sha256_file
from runspecimen.isolation import assert_tool_outside_workspace, effective_plan
from runspecimen.paths import ensure_within, resolve_workspace

_POLICY_FIELDS = {
    "version",
    "id",
    "max_wall_timeout_sec",
    "max_stdout_max_bytes",
    "max_stderr_max_bytes",
    "argv0_allow",
    "require_isolation_backend",
}
_BACKENDS = frozenset({"none", "sandbox-exec", "bwrap"})


def enforce_policy(contract: Contract, workspace: Path) -> dict[str, Any] | None:
    """Return the policy receipt, or None when the contract names no policy."""
    ref = contract.policy
    if ref is None:
        return None
    workspace = resolve_workspace(workspace)
    path = ensure_within(workspace, Path(ref.path), label="policy.path")
    if not path.is_file():
        raise PreflightError(f"policy file missing: {ref.path}")
    digest = sha256_file(path)
    if digest != ref.sha256:
        raise PreflightError(
            f"policy sha256 does not match the contract "
            f"(file {digest}, contract {ref.sha256})"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"policy file is not JSON: {exc}") from exc

    try:
        obj = _require_dict(data, "policy file")
        _reject_unknown(obj, _POLICY_FIELDS, "policy file")
        version = _require_int(obj.get("version"), "policy.version")
        if version != 1:
            raise ContractError(
                f"unsupported policy version: {version} (supported: 1; "
                "see docs/SCHEMA_COMPATIBILITY.md)"
            )
        policy_id = _require_str(obj.get("id"), "policy.id")
        if policy_id != ref.id:
            raise PreflightError(
                f"policy id {policy_id!r} does not match contract policy.id {ref.id!r}"
            )
        _ceilings(contract, obj)
        _argv_allow(contract, obj)
        _backend_requirement(contract, obj)
    except ContractError as exc:
        raise PreflightError(str(exc)) from exc

    return {"id": ref.id, "path": ref.path, "sha256": digest}


def _ceilings(contract: Contract, obj: dict[str, Any]) -> None:
    checks = (
        ("max_wall_timeout_sec", contract.caps.wall_timeout_sec, "caps.wall_timeout_sec"),
        ("max_stdout_max_bytes", contract.caps.stdout_max_bytes, "caps.stdout_max_bytes"),
        ("max_stderr_max_bytes", contract.caps.stderr_max_bytes, "caps.stderr_max_bytes"),
    )
    for key, actual, label in checks:
        if key not in obj:
            continue
        limit = _require_int(obj.get(key), f"policy.{key}")
        if limit < 1:
            raise ContractError(f"policy.{key} must be >= 1")
        if actual > limit:
            raise PreflightError(
                f"{label} {actual} exceeds shared policy {key} {limit}"
            )


def _argv_allow(contract: Contract, obj: dict[str, Any]) -> None:
    if "argv0_allow" not in obj:
        return
    raw = _require_list(obj.get("argv0_allow"), "policy.argv0_allow")
    if not raw:
        raise ContractError("policy.argv0_allow must be non-empty when present")
    allowed = [_require_str(item, "policy.argv0_allow[]") for item in raw]
    if contract.argv[0] not in allowed:
        raise PreflightError(
            f"argv[0] {contract.argv[0]!r} is not in the shared policy argv0_allow list"
        )


def _backend_requirement(contract: Contract, obj: dict[str, Any]) -> None:
    if "require_isolation_backend" not in obj:
        return
    backend = _require_str(obj.get("require_isolation_backend"), "policy.require_isolation_backend")
    if backend not in _BACKENDS:
        raise ContractError(
            "policy.require_isolation_backend must be one of: none, sandbox-exec, bwrap"
        )
    if contract.isolation.backend != backend:
        raise PreflightError(
            f"contract isolation.backend {contract.isolation.backend!r} "
            f"does not satisfy policy.require_isolation_backend {backend!r}"
        )


def execution_constraints(
    contract: Contract, workspace: Path
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Resolve isolation and policy. Raises PreflightError when either cannot be enforced."""
    plan = effective_plan(contract.isolation)
    assert_tool_outside_workspace(plan, workspace)
    policy = enforce_policy(contract, workspace)
    return plan, policy
