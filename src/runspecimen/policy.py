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
    # Additive template fields (ADR-005). Unknown keys still fail closed.
    "protected_paths",
    "expected_outputs",
    "required_verification",
    "ops_requiring_distinct_run",
    "required_predecessor_evidence",
    "template_id",
    "template_version",
    "nl_constraint_notes",
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
        _template_constraints(contract, obj, workspace)
    except ContractError as exc:
        raise PreflightError(str(exc)) from exc

    receipt = {"id": ref.id, "path": ref.path, "sha256": digest}
    if "template_id" in obj:
        receipt["template_id"] = obj["template_id"]
    if "template_version" in obj:
        receipt["template_version"] = obj["template_version"]
    return receipt


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


def _template_constraints(contract: Contract, obj: dict[str, Any], workspace: Path) -> None:
    """Enforce additive policy template fields without a second execution engine."""
    if "protected_paths" in obj:
        paths = _require_list(obj.get("protected_paths"), "policy.protected_paths")
        for i, item in enumerate(paths):
            rel = _require_str(item, f"policy.protected_paths[{i}]")
            ensure_within(workspace, Path(rel), label=f"policy.protected_paths[{i}]")
            # Protected paths must not be argv script targets for mutation contracts.
            # v1 refuses writing them via required outputs collision.
            for out in contract.asserted_output_paths:
                if out == rel or out.startswith(rel.rstrip("/") + "/"):
                    raise PreflightError(
                        format_refusal(
                            violated_constraint="protected_paths",
                            contract_policy=obj.get("id"),
                            observed_op=f"asserted_output:{out}",
                            next_step=(
                                "Remove the protected path from outputs or obtain a "
                                "distinct human-approved run that explicitly scopes the change. "
                                "Contracts are never auto-weakened."
                            ),
                        )
                    )

    if "expected_outputs" in obj:
        expected = _require_list(obj.get("expected_outputs"), "policy.expected_outputs")
        expected_set = {
            _require_str(item, f"policy.expected_outputs[{i}]")
            for i, item in enumerate(expected)
        }
        required = set(contract.outputs_required)
        missing = sorted(expected_set - required)
        if missing:
            raise PreflightError(
                format_refusal(
                    violated_constraint="expected_outputs",
                    contract_policy=obj.get("id"),
                    observed_op=f"outputs.required missing {missing}",
                    next_step=(
                        "Add the expected outputs to the contract or use a different "
                        "policy template. Do not auto-weaken the policy."
                    ),
                )
            )

    if "required_verification" in obj:
        req = _require_list(obj.get("required_verification"), "policy.required_verification")
        for i, item in enumerate(req):
            _require_str(item, f"policy.required_verification[{i}]")
        # Presence is recorded; enforcement is via requirements check command,
        # not a silent pass at preflight.
        if not req:
            raise ContractError("policy.required_verification must be non-empty when present")

    if "ops_requiring_distinct_run" in obj:
        ops = _require_list(
            obj.get("ops_requiring_distinct_run"), "policy.ops_requiring_distinct_run"
        )
        for i, item in enumerate(ops):
            _require_str(item, f"policy.ops_requiring_distinct_run[{i}]")

    if "required_predecessor_evidence" in obj:
        flag = obj.get("required_predecessor_evidence")
        if not isinstance(flag, bool):
            raise ContractError(
                "policy.required_predecessor_evidence must be a JSON boolean"
            )
        if flag and contract.predecessor is None:
            raise PreflightError(
                format_refusal(
                    violated_constraint="required_predecessor_evidence",
                    contract_policy=obj.get("id"),
                    observed_op="predecessor=null",
                    next_step=(
                        "Name a postflighted predecessor run in the contract before approval."
                    ),
                )
            )

    if "nl_constraint_notes" in obj:
        notes = _require_list(obj.get("nl_constraint_notes"), "policy.nl_constraint_notes")
        for i, item in enumerate(notes):
            note = _require_dict(item, f"policy.nl_constraint_notes[{i}]")
            _reject_unknown(
                note,
                {"text", "status", "derived_constraint"},
                f"policy.nl_constraint_notes[{i}]",
            )
            _require_str(note.get("text"), f"policy.nl_constraint_notes[{i}].text")
            status = _require_str(note.get("status"), f"policy.nl_constraint_notes[{i}].status")
            if status not in {"enforced", "advisory", "ambiguous"}:
                raise ContractError(
                    f"policy.nl_constraint_notes[{i}].status must be "
                    "enforced|advisory|ambiguous"
                )
            # Ambiguous NL stays advisory — never silently becomes enforcement.
            if status == "ambiguous" and note.get("derived_constraint"):
                raise ContractError(
                    f"policy.nl_constraint_notes[{i}]: ambiguous notes must not "
                    "carry derived_constraint (keep visible and advisory)"
                )


def format_refusal(
    *,
    violated_constraint: str,
    contract_policy: Any,
    observed_op: str,
    next_step: str,
) -> str:
    """Actionable refusal text: constraint, policy, observed op, legitimate next step."""
    return (
        f"policy refusal: constraint={violated_constraint!r} "
        f"policy={contract_policy!r} observed={observed_op!r}. "
        f"Next: {next_step}"
    )


def execution_constraints(
    contract: Contract, workspace: Path
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Resolve isolation and policy. Raises PreflightError when either cannot be enforced."""
    plan = effective_plan(contract.isolation)
    assert_tool_outside_workspace(plan, workspace)
    policy = enforce_policy(contract, workspace)
    return plan, policy
