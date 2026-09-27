"""Deterministic exact-match fast path (no generative-model inference).

RunSpecimen is not an LLM product. The only provider-dispatch boundary is the
eval suite. This module intercepts explicitly configured exact inputs *before*
``EvalProvider.run_task``. It does not approve runs, settle remote confirm, or
skip contract/workspace validation.

Zero tokens means zero generative-model inference tokens — not zero CPU, disk,
or application work. Estimated token/cost savings are not invented.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from runspecimen.artifact import (
    CURRENT_ARTIFACT_SCHEMA_VERSION,
    assert_artifact_version,
    assert_schema_kind,
    bind_artifact_digest,
    verify_artifact_digest,
)
from runspecimen.contract import (
    _object_without_duplicates,
    _reject_unknown,
    _require_dict,
    _require_list,
    _require_str,
)
from runspecimen.errors import RunSpecimenError
from runspecimen.paths import resolve_workspace, validate_id

OUTCOME_RESPOND = "respond"
OUTCOME_NO_RESPONSE = "no_response"
ROUTE_FASTPATH = "fastpath"
ROUTE_PROVIDER = "provider"
ROUTE_FALLTHROUGH = "fallthrough"

_WS_RE = re.compile(r"\s+")
_TERMINAL_PUNCT_RE = re.compile(r"[.!]+$")
_APPROVE_PHRASE = "approve"

_CONFIG_FIELDS = {
    "schema_kind",
    "schema_version",
    "enabled",
    "rules",
    "artifact_digest",
}
_RULE_FIELDS = {"id", "exact", "outcome"}
_OUTCOME_FIELDS = {"type", "text"}
_UNSAFE_TASK_FIELDS = frozenset(
    {"action", "tool", "tools", "confirm", "approval", "pending"}
)


class FastpathError(RunSpecimenError):
    """Fast-path configuration or execution failed."""


def normalize_fastpath_text(text: str) -> str:
    """Normalize one input or configured variant.

    1. strip; 2. Unicode casefold; 3. collapse internal whitespace;
    4. strip a trailing run of ``.`` / ``!`` only; 5. strip again.
    ``?``, commas, emoji, and words are kept.
    """
    if not isinstance(text, str):
        raise FastpathError("fastpath text must be a string")
    folded = text.strip().casefold()
    folded = _WS_RE.sub(" ", folded)
    folded = _TERMINAL_PUNCT_RE.sub("", folded)
    return folded.strip()


def parse_fastpath_config(data: dict[str, Any], *, require_kind: bool = True) -> dict[str, Any]:
    """Validate and compile a fast-path document. Collisions fail closed."""
    data = _require_dict(data, "fastpath")
    if require_kind or "schema_kind" in data:
        _reject_unknown(data, _CONFIG_FIELDS, "fastpath")
        assert_schema_kind(data.get("schema_kind"), expected="fastpath_config")
        assert_artifact_version(data.get("schema_version"))
        if "artifact_digest" in data:
            verify_artifact_digest(data)
    else:
        _reject_unknown(data, {"enabled", "rules"}, "fastpath")

    enabled = data.get("enabled", False)
    if not isinstance(enabled, bool):
        raise FastpathError("fastpath.enabled must be a JSON boolean")
    rules_raw = _require_list(data.get("rules", []), "fastpath.rules")
    rules, index = _compile_rules(rules_raw)
    compiled = {
        "schema_kind": "fastpath_config",
        "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
        "enabled": enabled,
        "rules": rules,
        "index": index,
    }
    return compiled


def load_fastpath_config(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FastpathError(f"malformed fastpath config: {exc}") from exc
    if not isinstance(data, dict):
        raise FastpathError("fastpath config must be a JSON object")
    return parse_fastpath_config(data, require_kind=True)


def _compile_rules(rules_raw: list[Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rules: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    index: dict[str, str] = {}
    for i, raw in enumerate(rules_raw):
        label = f"fastpath.rules[{i}]"
        obj = _require_dict(raw, label)
        _reject_unknown(obj, _RULE_FIELDS, label)
        rule_id = _require_str(obj.get("id"), f"{label}.id")
        try:
            validate_id(rule_id)
        except Exception as exc:  # noqa: BLE001
            raise FastpathError(f"{label}.id is not a path-safe id: {exc}") from exc
        if rule_id in seen_ids:
            raise FastpathError(f"duplicate fastpath rule id: {rule_id!r}")
        seen_ids.add(rule_id)
        exact = _require_list(obj.get("exact"), f"{label}.exact")
        if not exact:
            raise FastpathError(f"{label}.exact must be a non-empty array")
        originals: list[str] = []
        for j, item in enumerate(exact):
            raw_text = _require_str(item, f"{label}.exact[{j}]")
            normalized = normalize_fastpath_text(raw_text)
            if not normalized:
                raise FastpathError(f"{label}.exact[{j}] normalizes to an empty string")
            owner = index.get(normalized)
            if owner is not None and owner != rule_id:
                raise FastpathError(
                    f"fastpath match {normalized!r} is claimed by both "
                    f"{owner!r} and {rule_id!r}"
                )
            index[normalized] = rule_id
            originals.append(raw_text)
        outcome = _parse_outcome(obj.get("outcome"), f"{label}.outcome")
        # Persist the author's strings. Normalization is one-pass and not idempotent.
        rules.append({"id": rule_id, "exact": originals, "outcome": outcome})
    return rules, index


def _parse_outcome(raw: Any, label: str) -> dict[str, Any]:
    obj = _require_dict(raw, label)
    _reject_unknown(obj, _OUTCOME_FIELDS, label)
    kind = _require_str(obj.get("type"), f"{label}.type")
    if kind == OUTCOME_RESPOND:
        text = _require_str(obj.get("text"), f"{label}.text")
        if not text.strip():
            raise FastpathError(f"{label}.text must be non-empty for type=respond")
        return {"type": OUTCOME_RESPOND, "text": text}
    if kind == OUTCOME_NO_RESPONSE:
        if "text" in obj and obj["text"] not in (None, ""):
            raise FastpathError(f"{label}.text must be omitted for type=no_response")
        return {"type": OUTCOME_NO_RESPONSE, "text": None}
    raise FastpathError(
        f"{label}.type must be {OUTCOME_RESPOND!r} or {OUTCOME_NO_RESPONSE!r}"
    )


def match_fastpath(
    text: str,
    config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the compiled rule on an exact normalized hit, else None."""
    if not config or not config.get("enabled"):
        return None
    normalized = normalize_fastpath_text(text)
    rule_id = config.get("index", {}).get(normalized)
    if rule_id is None:
        return None
    for rule in config.get("rules") or []:
        if rule["id"] == rule_id:
            return rule
    return None


def fastpath_eligibility(
    *,
    workspace: Path,
    text: str,
    task: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Decline (fall through) when the text may settle another workflow.

    Suite tasks are eligible only when they explicitly declare
    ``capability: text_completion``. Requirement-check providers, including
    ``local_deterministic``, stay on the provider path. Standalone completion
    has no task and is text completion by the command itself.
    """
    if normalize_fastpath_text(text) == _APPROVE_PHRASE:
        return False, "unsafe_approval_phrase"
    if task is not None:
        if task.get("requires_human") is True:
            return False, "unsafe_requires_human"
        if task.get("provider") == "local_deterministic" or task.get("capability") != "text_completion":
            return False, "not_text_completion"
        overlap = sorted(set(task) & _UNSAFE_TASK_FIELDS)
        if overlap:
            return False, f"unsafe_structured_fields:{','.join(overlap)}"
    if _workspace_has_live_pending_confirmation(workspace):
        return False, "unsafe_pending_confirmation"
    return True, "ok"


def _workspace_has_live_pending_confirmation(workspace: Path) -> bool:
    root = resolve_workspace(workspace) / ".runspecimen"
    if not root.is_dir():
        return False
    try:
        from runspecimen.remote_confirm import PENDING_FILENAME, pending_is_live
    except Exception:  # noqa: BLE001
        PENDING_FILENAME = "remote_confirm_pending.json"
        pending_is_live = None  # type: ignore[assignment]
    inaccessible = False

    def _on_walk_error(_exc: OSError) -> None:
        nonlocal inaccessible
        inaccessible = True

    for dirpath, _dirnames, filenames in os.walk(root, onerror=_on_walk_error):
        if PENDING_FILENAME not in filenames:
            continue
        if _pending_file_is_live(Path(dirpath) / PENDING_FILENAME, pending_is_live):
            return True
    # Unreadable state is conservative: do not route around a confirmation
    # file we could not inspect.
    return inaccessible


def _pending_file_is_live(path: Path, pending_is_live: Any) -> bool:
    """Malformed or unreadable pending state stays conservative (live)."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return True
    if not isinstance(payload, dict):
        return True
    if pending_is_live is None:
        return True
    try:
        return bool(pending_is_live(payload))
    except Exception:  # noqa: BLE001
        return True


def _zero_inference_fields(
    *,
    hit: bool,
    rule_id: str | None,
    route: str,
    model_calls_avoided: int = 0,
    provider_dispatches_avoided: int = 0,
) -> dict[str, Any]:
    return {
        "route": route,
        "rule_id": rule_id,
        "fastpath_hit": hit,
        "provider_called": False,
        "llm_input_tokens": 0 if hit else None,
        "llm_output_tokens": 0 if hit else None,
        "llm_inference_cost": 0 if hit else None,
        "actual_llm_tokens_used": 0 if hit else None,
        "actual_llm_cost": 0 if hit else None,
        "model_calls_avoided": model_calls_avoided if hit else 0,
        "provider_dispatches_avoided": provider_dispatches_avoided if hit else 0,
        "deterministic_completions": 1 if hit else 0,
        "estimated_token_savings": None,
        "estimated_cost_savings": None,
        "note": (
            "Deterministic text completion. No generative-model inference. "
            "Application work is not zero. model_calls_avoided is 1 only when "
            "the skipped fallback was an explicit model task. Token/cost savings "
            "are not estimated."
            if hit
            else "No fast-path hit. Estimated token/cost savings are not invented."
        ),
    }


def complete_fastpath_request(
    *,
    workspace: Path,
    text: str,
    config: dict[str, Any] | None,
    task: dict[str, Any] | None = None,
    model_fallback: bool = False,
) -> dict[str, Any]:
    """Resolve one text request against a compiled config.

    Invalid configuration must be rejected by the caller before this function.
    A non-match or an unsafe state is a successful fallthrough, not an error.
    """
    started = time.time()
    workspace = resolve_workspace(workspace)
    routing_started = time.time()
    if config is None or not config.get("enabled"):
        routing_elapsed = time.time() - routing_started
        result = {
            "ok": True,
            "outcome_type": None,
            "text": None,
            "reason": "disabled" if config is not None else "absent",
            "elapsed_sec": round(time.time() - started, 6),
            "routing_elapsed_sec": round(routing_elapsed, 6),
            **_zero_inference_fields(hit=False, rule_id=None, route=ROUTE_FALLTHROUGH),
        }
        return result

    eligible, reason = fastpath_eligibility(workspace=workspace, text=text, task=task)
    routing_elapsed = time.time() - routing_started
    if not eligible:
        return {
            "ok": True,
            "outcome_type": None,
            "text": None,
            "reason": reason,
            "elapsed_sec": round(time.time() - started, 6),
            "routing_elapsed_sec": round(routing_elapsed, 6),
            **_zero_inference_fields(hit=False, rule_id=None, route=ROUTE_FALLTHROUGH),
        }

    rule = match_fastpath(text, config)
    routing_elapsed = time.time() - routing_started
    if rule is None:
        return {
            "ok": True,
            "outcome_type": None,
            "text": None,
            "reason": "no_match",
            "elapsed_sec": round(time.time() - started, 6),
            "routing_elapsed_sec": round(routing_elapsed, 6),
            **_zero_inference_fields(hit=False, rule_id=None, route=ROUTE_FALLTHROUGH),
        }

    outcome = rule["outcome"]
    return {
        "ok": True,
        "outcome_type": outcome["type"],
        "text": outcome["text"],
        "reason": "matched",
        "elapsed_sec": round(time.time() - started, 6),
        "routing_elapsed_sec": round(routing_elapsed, 6),
        **_zero_inference_fields(
            hit=True,
            rule_id=rule["id"],
            route=ROUTE_FASTPATH,
            model_calls_avoided=1 if model_fallback else 0,
            provider_dispatches_avoided=1 if task is not None else 0,
        ),
    }


def _measured_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _measured_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def provider_telemetry(
    *,
    called: bool,
    input_tokens: Any = None,
    output_tokens: Any = None,
    inference_cost: Any = None,
) -> dict[str, Any]:
    """Derived observability for a provider (non-fast-path) execution.

    Missing measurements stay unknown (None). A supplied zero stays zero.
    """
    if not called:
        raise FastpathError("provider telemetry requires a real dispatch")
    in_tokens = _measured_int(input_tokens)
    out_tokens = _measured_int(output_tokens)
    cost = _measured_number(inference_cost)
    if in_tokens is None or out_tokens is None:
        actual_tokens: int | None = None
    else:
        actual_tokens = in_tokens + out_tokens
    return {
        "route": ROUTE_PROVIDER,
        "rule_id": None,
        "fastpath_hit": False,
        "provider_called": True,
        "llm_input_tokens": in_tokens,
        "llm_output_tokens": out_tokens,
        "llm_inference_cost": cost,
        "actual_llm_tokens_used": actual_tokens,
        "actual_llm_cost": cost,
        "model_calls_avoided": 0,
        "provider_dispatches_avoided": 0,
        "deterministic_completions": 0,
        "estimated_token_savings": None,
        "estimated_cost_savings": None,
        "note": "Provider path. Token and cost fields are measured, not configured. Unknown stays unknown.",
    }


def summarize_fastpath_tasks(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    hits = sum(1 for t in tasks if t.get("fastpath_hit"))
    provider = sum(1 for t in tasks if t.get("provider_called"))
    considered = sum(1 for t in tasks if t.get("fastpath_considered"))
    model_avoided = sum(int(t.get("model_calls_avoided") or 0) for t in tasks)
    dispatches_avoided = sum(int(t.get("provider_dispatches_avoided") or 0) for t in tasks)
    return {
        "fastpath_executions": hits,
        "deterministic_completions": hits,
        "fastpath_considered": considered,
        "provider_dispatches": provider,
        "provider_dispatches_avoided": dispatches_avoided,
        "model_calls_avoided": model_avoided,
        "fastpath_hit_rate": (hits / considered) if considered else None,
        "actual_llm_tokens_fastpath": 0 if hits else None,
        "estimated_token_savings": None,
        "estimated_cost_savings": None,
    }


def bind_fastpath_config(doc: dict[str, Any]) -> dict[str, Any]:
    compiled = parse_fastpath_config(doc, require_kind=True)
    material = {
        "schema_kind": "fastpath_config",
        "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
        "enabled": compiled["enabled"],
        "rules": [
            {
                "id": rule["id"],
                "exact": list(rule["exact"]),
                "outcome": dict(rule["outcome"]),
            }
            for rule in compiled["rules"]
        ],
    }
    return bind_artifact_digest(material)
