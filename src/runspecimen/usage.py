"""Usage attribution from documented exports / provider APIs (honest local import).

Unknown stays unknown (not zero). Ambiguous stays unallocated or explicitly
estimated. Idempotent imports. Does not scrape undocumented Cursor DBs.
Does not promise exact billing or hard spend enforcement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from runspecimen.artifact import (
    CURRENT_ARTIFACT_SCHEMA_VERSION,
    assert_artifact_version,
    assert_schema_kind,
    bind_artifact_digest,
    verify_artifact_digest,
)
from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.contract import (
    _object_without_duplicates,
    _reject_unknown,
    _require_dict,
    _require_list,
    _require_str,
)
from runspecimen.errors import RunSpecimenError
from runspecimen.events import utc_now_iso
from runspecimen.hashutil import sha256_bytes, canonical_json_bytes
from runspecimen.paths import ensure_dir, resolve_workspace, workspace_state_root


class UsageError(RunSpecimenError):
    """Usage import or summary failed."""


_EVENT_FIELDS = {
    "import_key",
    "provider",
    "model",
    "units",
    "unit_type",
    "currency",
    "amount",
    "amount_kind",  # billed | estimated | included | unknown
    "timestamp",
    "run_id",
    "task_id",
    "project_id",
    "campaign_id",
    "confidence",  # high | medium | low | unknown
    "notes",
}

_AMOUNT_KINDS = frozenset({"billed", "estimated", "included", "unknown"})
_CONFIDENCE = frozenset({"high", "medium", "low", "unknown"})


class UsageProvider(Protocol):
    name: str

    def parse_export(self, payload: Any) -> list[dict[str, Any]]:
        ...


class LocalJsonUsageProvider:
    """Documented local JSON export: ``{"events": [ ... ]}`` or a bare event list."""

    name = "local_json"

    def parse_export(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            events = payload.get("events")
            if events is None:
                raise UsageError("local_json export must contain an events array")
            events = _require_list(events, "events")
        elif isinstance(payload, list):
            events = payload
        else:
            raise UsageError("local_json export must be an object or array")
        return [_normalize_event(item, i) for i, item in enumerate(events)]


def _normalize_event(raw: Any, index: int) -> dict[str, Any]:
    label = f"events[{index}]"
    obj = _require_dict(raw, label)
    _reject_unknown(obj, _EVENT_FIELDS, label)
    import_key = _require_str(obj.get("import_key"), f"{label}.import_key")
    provider = _require_str(obj.get("provider"), f"{label}.provider")
    amount_kind = obj.get("amount_kind", "unknown")
    if amount_kind not in _AMOUNT_KINDS:
        raise UsageError(f"{label}.amount_kind must be one of {sorted(_AMOUNT_KINDS)}")
    confidence = obj.get("confidence", "unknown")
    if confidence not in _CONFIDENCE:
        raise UsageError(f"{label}.confidence must be one of {sorted(_CONFIDENCE)}")
    amount = obj.get("amount")
    if amount_kind == "unknown":
        # Unknown must stay unknown — refuse coercing null to 0.
        if amount is not None:
            raise UsageError(
                f"{label}: amount_kind=unknown must omit amount (do not invent zero)"
            )
    else:
        if amount is not None and (
            isinstance(amount, bool) or not isinstance(amount, (int, float))
        ):
            raise UsageError(f"{label}.amount must be a number when present")

    currency = obj.get("currency")
    if amount_kind in {"billed", "estimated"} and amount is not None:
        if not isinstance(currency, str) or not currency:
            raise UsageError(
                f"{label}.currency required for billed/estimated amounts"
            )

    # Attribution: if run/task/project all missing → unallocated.
    run_id = obj.get("run_id")
    task_id = obj.get("task_id")
    project_id = obj.get("project_id")
    campaign_id = obj.get("campaign_id")
    allocated = any(
        isinstance(x, str) and x for x in (run_id, task_id, project_id, campaign_id)
    )

    return {
        "import_key": import_key,
        "provider": provider,
        "model": obj.get("model"),
        "units": obj.get("units"),
        "unit_type": obj.get("unit_type"),
        "currency": currency,
        "amount": amount,
        "amount_kind": amount_kind,
        "timestamp": obj.get("timestamp"),
        "run_id": run_id,
        "task_id": task_id,
        "project_id": project_id,
        "campaign_id": campaign_id,
        "confidence": confidence,
        "notes": obj.get("notes"),
        "allocation": "allocated" if allocated else "unallocated",
    }


_PROVIDERS: dict[str, UsageProvider] = {
    LocalJsonUsageProvider.name: LocalJsonUsageProvider(),
}


def get_usage_provider(name: str) -> UsageProvider:
    provider = _PROVIDERS.get(name)
    if provider is None:
        raise UsageError(f"usage provider unavailable: {name!r}")
    return provider


def ledger_path(workspace: Path) -> Path:
    return workspace_state_root(workspace) / "usage" / "ledger.json"


def load_ledger(workspace: Path) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    path = ledger_path(workspace)
    if not path.is_file():
        return bind_artifact_digest(
            {
                "schema_kind": "usage_ledger",
                "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
                "events": [],
                "import_keys": [],
                "updated_at": utc_now_iso(),
                "note": (
                    "External usage is distinct from facts RunSpecimen measured. "
                    "Unknown amounts are not treated as zero."
                ),
            }
        )
    doc = read_json(path)
    assert_schema_kind(doc.get("schema_kind"), expected="usage_ledger")
    assert_artifact_version(doc.get("schema_version"))
    verify_artifact_digest(doc)
    return doc


def import_usage(
    *,
    workspace: Path,
    provider_name: str,
    export_path: Path,
) -> dict[str, Any]:
    workspace = resolve_workspace(workspace)
    provider = get_usage_provider(provider_name)
    export_path = export_path.expanduser().resolve()
    if not export_path.is_file():
        raise UsageError(f"usage export not found: {export_path}")
    try:
        payload = json.loads(
            export_path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UsageError(f"malformed usage export: {exc}") from exc

    try:
        incoming = provider.parse_export(payload)
    except UsageError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise UsageError(f"usage provider failed: {exc}") from exc

    ledger = load_ledger(workspace)
    known = set(ledger.get("import_keys") or [])
    events = list(ledger.get("events") or [])
    added = 0
    duplicates = 0
    unallocated = 0
    for event in incoming:
        key = event["import_key"]
        if key in known:
            duplicates += 1
            continue
        known.add(key)
        events.append(event)
        added += 1
        if event.get("allocation") == "unallocated":
            unallocated += 1

    ledger = {
        "schema_kind": "usage_ledger",
        "schema_version": CURRENT_ARTIFACT_SCHEMA_VERSION,
        "events": events,
        "import_keys": sorted(known),
        "updated_at": utc_now_iso(),
        "last_import": {
            "provider": provider_name,
            "export_path": str(export_path),
            "added": added,
            "duplicates": duplicates,
            "unallocated_added": unallocated,
        },
        "note": (
            "External usage is distinct from facts RunSpecimen measured. "
            "Unknown amounts are not treated as zero. "
            "No hard spend enforcement."
        ),
    }
    ledger = bind_artifact_digest(ledger)
    path = ledger_path(workspace)
    ensure_dir(path.parent)
    atomic_write_json(path, ledger)
    return {
        "ok": True,
        "added": added,
        "duplicates": duplicates,
        "unallocated_added": unallocated,
        "total_events": len(events),
        "ledger_digest": ledger["artifact_digest"],
    }


def summarize_usage(workspace: Path) -> dict[str, Any]:
    ledger = load_ledger(workspace)
    by_provider: dict[str, dict[str, Any]] = {}
    by_task: dict[str, dict[str, Any]] = {}
    by_campaign: dict[str, dict[str, Any]] = {}
    by_project: dict[str, dict[str, Any]] = {}
    unallocated = 0
    unknown_amount = 0
    currencies: set[str] = set()

    def _bucket(store: dict[str, dict[str, Any]], key: str, event: dict[str, Any]) -> None:
        slot = store.setdefault(
            key,
            {"events": 0, "billed_sum": None, "estimated_sum": None, "currencies": []},
        )
        slot["events"] += 1
        kind = event.get("amount_kind")
        amount = event.get("amount")
        cur = event.get("currency")
        if isinstance(cur, str):
            if cur not in slot["currencies"]:
                slot["currencies"].append(cur)
            currencies.add(cur)
        if kind == "billed" and isinstance(amount, (int, float)):
            slot["billed_sum"] = (slot["billed_sum"] or 0) + amount
        elif kind == "estimated" and isinstance(amount, (int, float)):
            slot["estimated_sum"] = (slot["estimated_sum"] or 0) + amount

    for event in ledger.get("events") or []:
        if event.get("allocation") == "unallocated":
            unallocated += 1
        if event.get("amount_kind") == "unknown" or event.get("amount") is None:
            unknown_amount += 1
        _bucket(by_provider, str(event.get("provider") or "unknown"), event)
        if event.get("task_id"):
            _bucket(by_task, str(event["task_id"]), event)
        if event.get("campaign_id"):
            _bucket(by_campaign, str(event["campaign_id"]), event)
        if event.get("project_id"):
            _bucket(by_project, str(event["project_id"]), event)

    return {
        "total_events": len(ledger.get("events") or []),
        "unallocated_events": unallocated,
        "unknown_amount_events": unknown_amount,
        "currencies_seen": sorted(currencies),
        "by_provider": by_provider,
        "by_task": by_task,
        "by_campaign": by_campaign,
        "by_project": by_project,
        "ledger_digest": ledger.get("artifact_digest"),
        "note": (
            "Sums omit unknown amounts. Mixed currencies are listed, not silently converted. "
            "This is attribution, not a billing guarantee."
        ),
    }
