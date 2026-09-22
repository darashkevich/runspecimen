"""Loopback-only, read-only dashboard for a single RunSpecimen contract.

The dashboard is deliberately a *guide*, not a second execution API.  The CLI
remains the sole enforcement boundary and approval remains a real TTY action.
"""

from __future__ import annotations

import html
import json
import shlex
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from runspecimen import DOCS_URLS
from runspecimen.contract import Contract, load_contract
from runspecimen.errors import RunSpecimenError
from runspecimen.paths import resolve_workspace
from runspecimen.status import status_for


_PHASE_LABELS = {
    "none": "Ready to review",
    "approved": "Approved",
    "preflighted": "Preflight passed",
    "running": "Running",
    "completed": "Run completed",
    "failed": "Attention required",
    "postflighted": "Postflight recorded",
    "abandoned": "Abandoned (terminal)",
}


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.0f} KiB"
    return f"{value / (1024 * 1024):.1f} MiB"


def _lifecycle_states(status: dict[str, Any]) -> list[str]:
    """Describe recorded progress; viewing status never verifies a receipt."""
    phase = str(status.get("phase") or "none")
    state = status.get("state") or {}
    next_step = {
        "none": 0,
        "approved": 2,
        "preflighted": 3,
        "running": 3,
        "completed": 4,
        "failed": 4 if state.get("postflight_ok") is False else 3,
        "postflighted": 5,
        "abandoned": 3,  # Terminal at run phase
    }.get(phase, 0)

    states = ["recorded" if index < next_step else "upcoming" for index in range(6)]
    if next_step < len(states):
        states[next_step] = "current"

    if phase == "running":
        states[3] = "current"
    elif phase == "failed":
        failed_step = 4 if state.get("postflight_ok") is False else 3
        states[failed_step] = "failed"
    elif phase == "abandoned":
        states[3] = "failed"  # Abandoned is terminal at run phase
    if phase == "postflighted":
        states[5] = "not-checked"
    return states


def _happened_summary(status: dict[str, Any], certificate_id: str | None) -> str:
    """Plain-language answer to “What happened?” from recorded evidence only."""
    phase = str(status.get("phase") or "none")
    state = status.get("state") or {}
    if phase == "none":
        return "No run has started. Only the contract is in scope."
    if phase == "approved":
        return "A human approval was recorded. Launch has not occurred."
    if phase == "preflighted":
        return "Preflight checks passed under the workspace lease. The command has not executed yet."
    if phase == "running":
        return "Execution was recorded as in progress. Treat this as live or interrupted until the lease and result settle."
    if phase == "completed":
        return "The command finished. Postflight assertions have not certified outcomes yet."
    if phase == "failed":
        if state.get("timed_out"):
            return "The run exceeded its wall timeout. It cannot become a certified success."
        if state.get("postflight_ok") is False:
            return "Postflight assertions failed. Evidence is preserved; this run ID stays failed."
        return "The run failed before a successful certificate. Preserve evidence; do not reuse this run ID."
    if phase == "abandoned":
        return "A human abandoned this run after a crash or stuck state. The run ID is permanently terminal."
    if phase == "postflighted":
        if certificate_id:
            return "Postflight succeeded and a certificate was issued. This dashboard has not live-verified the receipt."
        return "Postflight is recorded but the certificate file is missing."
    return "Inspect recorded state before deciding the next step."


def _continue_verdict(
    *,
    phase: str,
    warnings: list[str],
    certificate_id: str | None,
    busy: bool,
) -> tuple[str, str, str]:
    """Answer “Is it safe to continue?” without encouraging unsafe retries."""
    if warnings:
        return (
            "Not safe to continue yet",
            "Resolve the issues below. Preserve evidence; do not force a retry of a started run ID.",
            "bad",
        )
    if phase == "abandoned":
        return (
            "Do not continue this run ID",
            "Abandoned runs are permanently terminal. Author a new contract with a new run ID.",
            "bad",
        )
    if phase == "failed":
        return (
            "Do not continue this run ID",
            "Failed runs stay failed. Inspect evidence, then use a new run ID if you still need the work.",
            "bad",
        )
    if phase == "running":
        if busy:
            return (
                "Wait",
                "A workspace lease is held. Do not start another run or abandon while execution may still be live.",
                "warn",
            )
        return (
            "Inspect before acting",
            "Running state without an active lease may mean a crash. Check recovery-status in a terminal before abandon.",
            "warn",
        )
    if phase == "postflighted":
        if certificate_id:
            return (
                "Safe to verify — not yet live-verified",
                "A certificate exists as recorded history. Run verify in a terminal before trusting the receipt.",
                "warn",
            )
        return (
            "Not safe to trust",
            "Postflight without a certificate is incomplete. Inspect the workspace evidence.",
            "bad",
        )
    if phase == "completed":
        return (
            "Continue to postflight",
            "Outcomes are not certified until postflight assertions pass.",
            "active",
        )
    if phase in {"approved", "preflighted"}:
        return (
            "Continue with care",
            "Proceed only through the next CLI step. Launch rechecks approval, provenance, and lease.",
            "active",
        )
    return (
        "Review before approval",
        "Validate and read the contract review below, then approve in a real terminal — never via this dashboard.",
        "active",
    )


def _trust_ladder(status: dict[str, Any], certificate_id: str | None) -> list[dict[str, str]]:
    """Distinguish recorded history, postflight, receipt issuance, and live verify."""
    phase = str(status.get("phase") or "none")
    chain_ok = status.get("event_chain_ok")
    count = int(status.get("event_count") or 0)

    def rung(label: str, state: str, detail: str) -> dict[str, str]:
        return {"label": label, "state": state, "detail": detail}

    history = "empty"
    history_detail = "No events recorded yet"
    if count and chain_ok is True:
        history, history_detail = "recorded", f"{count} events · chain intact (history only)"
    elif count and chain_ok is False:
        history, history_detail = "failed", "Event chain invalid"
    elif count:
        history, history_detail = "recorded", f"{count} events · chain not confirmed"

    postflight = "upcoming"
    postflight_detail = "Not completed"
    if phase == "postflighted":
        postflight, postflight_detail = "recorded", "Assertions recorded as passed"
    elif phase == "failed" and (status.get("state") or {}).get("postflight_ok") is False:
        postflight, postflight_detail = "failed", "Assertions failed"

    receipt = "upcoming"
    receipt_detail = "No certificate issued"
    if certificate_id:
        receipt, receipt_detail = "issued", "Certificate on disk — not live verified here"
    elif phase == "postflighted":
        receipt, receipt_detail = "failed", "Expected certificate missing"

    return [
        rung("Recorded history", history, history_detail),
        rung("Successful postflight", postflight, postflight_detail),
        rung("Receipt issued", receipt, receipt_detail),
        rung("Live verification", "not-checked", "Dashboard never marks this green; use CLI verify"),
    ]


def _presentation(status: dict[str, Any], contract: Contract) -> dict[str, Any]:
    """One presentation model for initial HTML and subsequent JSON refreshes."""
    phase = str(status.get("phase") or "none")
    state = status.get("state") or {}
    approval = status.get("approval") or {}
    certificate = status.get("certificate") or {}
    warnings: list[str] = []
    approval_label, approval_detail, approval_tone = "Not recorded", "Approve in your terminal after validation.", ""
    if approval:
        expires = approval.get("expires_at_unix")
        if (approval.get("campaign_id"), approval.get("run_id"), approval.get("contract_hash")) != (contract.campaign_id, contract.run_id, contract.contract_hash):
            approval_label, approval_detail, approval_tone = "Contract mismatch", "Recorded approval refers to a different contract.", "bad"
            warnings.append(approval_detail)
        elif not isinstance(expires, (int, float)) or isinstance(expires, bool):
            approval_label, approval_detail, approval_tone = "Invalid record", "Approval expiry is missing or invalid.", "bad"
            warnings.append(approval_detail)
        elif expires < time.time():
            approval_label, approval_detail = "Expired", "Historical approval; it cannot authorize a new launch."
            approval_tone = "bad" if phase in {"none", "approved", "preflighted"} else ""
            if approval_tone:
                warnings.append("Approval has expired. Review and approve again before launch.")
        else:
            approval_label, approval_detail = "Recorded", "Within expiry; preflight must recheck source and runtime."
            who = approval.get("approver")
            if isinstance(who, dict) and isinstance(who.get("user"), str) and who.get("user"):
                approval_detail += f" Local OS user {who['user']}."
    count = status.get("event_count", 0)
    chain_ok = status.get("event_chain_ok")
    chain_label = "No events" if not count else "Intact" if chain_ok is True else "Invalid"
    chain_tone = "good" if count and chain_ok is True else "bad" if chain_ok is False else ""
    if chain_ok is False:
        warnings.append("Event history is invalid: " + str(status.get("event_chain_msg", "unknown error")))
    if phase == "failed":
        failures = state.get("postflight_failures") or []
        warnings.extend(str(item) for item in failures)
        if state.get("timed_out"):
            warnings.append("The run exceeded its wall timeout and cannot be certified.")
        if not failures and not state.get("timed_out"):
            warnings.append("The run failed. Inspect its evidence before taking another step.")
    busy = bool(status.get("workspace_lease_held_by_other"))
    if phase == "running" and not busy:
        warnings.append("A running state has no active lease. The runner may have stopped unexpectedly; inspect the evidence.")
    if state.get("stdout_truncated") or state.get("stderr_truncated"):
        warnings.append("Captured output reached its size limit; the saved capture is truncated.")
    if state.get("contract_hash") and state["contract_hash"] != contract.contract_hash:
        warnings.append("Current contract differs from the recorded run. Receipt verification will check this mismatch.")
    certificate_id = certificate.get("certificate_id")
    if phase == "postflighted" and not certificate_id:
        warnings.append("Postflight is recorded but the certificate is missing.")
    cards = {
        "approval": [approval_label, approval_detail, approval_tone],
        "chain": [chain_label, f"{count} recorded events · history integrity only", chain_tone],
        "certificate": ["Recorded" if certificate_id else "Not issued", "Live verification required" if certificate_id else "Issued after successful postflight", ""],
        "lease": ["Busy" if busy else "Clear", "Another process holds the lease" if busy else "No active holder", ""],
        "result": [str(state.get("run_result") or "Not run").capitalize(), f"Exit code: {state.get('exit_code') if state.get('exit_code') is not None else '—'}", "bad" if phase == "failed" else ""],
    }
    next_action = {
        "none": "Start with Validate, then approve the reviewed command in your terminal.",
        "approved": "Run preflight to recheck approval, source, runtime, and output paths.",
        "preflighted": "The run is ready for its single execution. Launch rechecks all conditions.",
        "running": "Execution is in progress. Wait for the run result before postflight.",
        "completed": "Run postflight to evaluate the assertions and issue a certificate.",
        "failed": "Stop and inspect the failure. Preserve the evidence; do not reuse this run ID.",
        "postflighted": "Run Verify receipt in your terminal to check current files and provenance. This dashboard has not performed that verification. Do not reuse this run ID.",
        "abandoned": "This run was abandoned after a crash. The run ID is permanently terminal; use a new run ID.",
    }.get(phase, "Inspect the recorded state before continuing.")
    continue_label, continue_detail, continue_tone = _continue_verdict(
        phase=phase, warnings=warnings, certificate_id=certificate_id, busy=busy
    )
    happened = _happened_summary(status, certificate_id if isinstance(certificate_id, str) else None)
    return {
        "phase_label": "Attention required" if warnings else _PHASE_LABELS.get(phase, phase),
        "phase_tone": "danger" if warnings else "active",
        "cards": cards,
        "steps": _lifecycle_states(status),
        "warnings": warnings,
        "next_action": next_action,
        "certificate_id": certificate_id or "No certificate recorded",
        "happened": happened,
        "continue_label": continue_label,
        "continue_detail": continue_detail,
        "continue_tone": continue_tone,
        "trust_ladder": _trust_ladder(status, certificate_id if isinstance(certificate_id, str) else None),
        "run_identity": f"{contract.campaign_id} / {contract.run_id}",
    }


def _isolation_copy(contract: Contract) -> str:
    backend = contract.isolation.backend
    if backend == "none":
        return (
            "This contract's isolation backend is none. The payload is not confined. "
            "Wall clock and capture limits are not an OS sandbox."
        )
    network = "network allowed" if contract.isolation.network else "network denied"
    return (
        f"This contract asks for isolation backend {backend} ({network}). "
        "That profile is applied only at run, and only if the tool is on PATH. "
        "The receipt records the residual risk. This page does not apply it, and it is not an OS sandbox."
    )


def dashboard_document(*, workspace: Path, contract_path: Path, status: dict[str, Any], contract: Contract | None = None) -> str:
    """Render a self-contained dashboard without third-party browser assets."""
    contract = contract or load_contract(contract_path)
    phase = str(status.get("phase") or "none")
    view = _presentation(status, contract)
    phase_label, phase_tone = view["phase_label"], view["phase_tone"]
    continue_tone = view["continue_tone"]

    workspace_path = workspace.resolve()
    resolved_contract_path = contract_path.resolve()
    workspace_arg = shlex.quote(str(workspace_path))
    contract_arg = shlex.quote(str(resolved_contract_path))
    campaign_arg = shlex.quote(contract.campaign_id)
    run_arg = shlex.quote(contract.run_id)
    payload_command = shlex.join(contract.argv)

    lifecycle = [
        (
            "Validate",
            "Check the contract, paths, bounds, and executable provenance.",
            f"runspecimen validate --workspace {workspace_arg} --contract {contract_arg}",
        ),
        (
            "Approve in a terminal",
            "A human must type approval in a real terminal.",
            f"runspecimen approve --workspace {workspace_arg} --contract {contract_arg}",
        ),
        (
            "Preflight",
            "Recheck hashes, approval freshness, outputs, and the workspace lease.",
            f"runspecimen preflight --workspace {workspace_arg} --contract {contract_arg}",
        ),
        (
            "Run once",
            "Execute the exact argument vector within the declared bounds.",
            f"runspecimen run --workspace {workspace_arg} --contract {contract_arg}",
        ),
        (
            "Postflight",
            "Assert outcomes and issue the tamper-evident certificate.",
            f"runspecimen postflight --workspace {workspace_arg} --contract {contract_arg}",
        ),
        (
            "Verify receipt",
            "Rehash live contract, source, runtime, outputs, and event history.",
            f"runspecimen verify --workspace {workspace_arg} --contract {contract_arg} --campaign-id {campaign_arg} --run-id {run_arg}",
        ),
    ]
    lifecycle_states = _lifecycle_states(status)
    steps = "".join(
        f"""<li class="step {lifecycle_states[index]}" data-step="{index}">
          <span class="step-marker" aria-hidden="true">{index + 1}</span>
          <div class="step-content">
            <div class="step-heading"><h3>{_escape(label)}</h3><span class="step-state">{_escape(lifecycle_states[index])}</span></div>
            <p>{_escape(description)}</p>
            <div class="command-row"><code>{_escape(command)}</code><button class="copy-button" type="button" data-copy="{_escape(command)}" aria-label="Copy {_escape(label)} command">Copy</button></div>
          </div>
        </li>"""
        for index, (label, description, command) in enumerate(lifecycle)
    )

    required_outputs = ", ".join(contract.outputs_required) or "None declared"
    source_roots = ", ".join(contract.source.roots) or "None declared"
    predecessor = (
        f"{contract.predecessor.campaign_id} / {contract.predecessor.run_id}"
        if contract.predecessor
        else "None"
    )
    card_labels = {"approval": "Approval", "chain": "Event chain", "certificate": "Certificate", "lease": "Workspace lease", "result": "Run result"}
    cards = "".join(
        f'<article class="metric"><span class="metric-label">{label}</span><strong id="{key}-value" class="{view["cards"][key][2]}">{_escape(view["cards"][key][0])}</strong><small id="{key}-detail">{_escape(view["cards"][key][1])}</small></article>'
        for key, label in card_labels.items()
    )
    warnings_html = "".join(f'<li>{_escape(item)}</li>' for item in view["warnings"])
    trust_html = "".join(
        f'<li class="trust-rung {_escape(rung["state"])}"><span class="trust-label">{_escape(rung["label"])}</span>'
        f'<span class="trust-state">{_escape(rung["state"])}</span>'
        f'<span class="trust-detail">{_escape(rung["detail"])}</span></li>'
        for rung in view["trust_ladder"]
    )
    runtime_line = "Default (resolved executable hashed at approval)"
    if contract.runtime is not None:
        parts = []
        if contract.runtime.interpreter:
            parts.append(f"interpreter {contract.runtime.interpreter}")
        if contract.runtime.env_allowlist:
            parts.append("env " + ", ".join(contract.runtime.env_allowlist))
        parts.append("capture_libs=" + ("yes" if contract.runtime.capture_libs else "no"))
        runtime_line = "; ".join(parts)
    assertion_count = (
        len(contract.postflight.json_equals) + len(contract.postflight.output_sha256)
    )
    status_json = html.escape(json.dumps(status, indent=2, sort_keys=True, default=str))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RunSpecimen — {_escape(contract.campaign_id)} / {_escape(contract.run_id)}</title>
<style>
:root{{--ink:#142033;--muted:#4a5a6e;--line:#d7dee8;--soft:#eef2f7;--panel:#fff;--brand:#1f4b99;--brand-soft:#e8f0fb;--success:#0f6b4c;--success-soft:#e7f6ef;--warn:#8a5a00;--warn-soft:#fff6e5;--danger:#a82a38;--danger-soft:#fdecee;--shadow:0 10px 28px rgba(20,32,51,.07)}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(1200px 600px at 10% -10%,#dfe9f7 0%,transparent 55%),linear-gradient(180deg,#f4f7fb,#e8eef5);color:var(--ink);font:15px/1.55 "Avenir Next","Segoe UI","Helvetica Neue",sans-serif}}button{{font:inherit}}code,pre,.hash{{font:13px/1.55 "SF Mono",SFMono-Regular,Menlo,Consolas,monospace}}
.topbar{{height:56px;background:#0f1a2c;color:#fff;display:flex;align-items:center;justify-content:space-between;padding:0 max(20px,calc((100vw - 1120px)/2))}}.brand{{display:flex;align-items:center;gap:10px;font-weight:700;letter-spacing:.02em}}.brand-mark{{width:28px;height:28px;border-radius:6px;display:grid;place-items:center;background:linear-gradient(145deg,#3d6ec7,#1f4b99);font-size:11px;font-weight:800}}.topbar-meta{{display:flex;align-items:center;gap:12px}}.docs-nav{{display:flex;gap:12px;font-size:12px}}.docs-nav a{{color:#c5cedc;text-decoration:none}}.docs-nav a:hover{{color:#fff;text-decoration:underline}}.read-only{{font-size:11px;color:#c5cedc;border:1px solid #3d4a61;border-radius:4px;padding:3px 8px}}
main{{max-width:1120px;margin:0 auto;padding:28px 20px 56px}}
.compose{{display:grid;gap:16px;margin-bottom:22px}}.compose-hero{{display:grid;gap:14px;padding:22px 24px;background:rgba(255,255,255,.86);border:1px solid var(--line);border-radius:4px;box-shadow:var(--shadow)}}.brand-line{{margin:0;font-size:13px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--brand)}}.run-title{{margin:0;font-size:clamp(26px,4vw,36px);line-height:1.15;letter-spacing:-.03em;font-weight:700}}.run-meta{{margin:0;color:var(--muted);max-width:46rem}}.phase-row{{display:flex;flex-wrap:wrap;gap:10px;align-items:center}}.phase-badge{{border-radius:4px;padding:7px 11px;font-size:13px;font-weight:750;background:var(--brand-soft);color:var(--brand)}}.phase-badge.success{{background:var(--success-soft);color:var(--success)}}.phase-badge.danger{{background:var(--danger-soft);color:var(--danger)}}
.answer-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.answer{{padding:14px 16px;background:var(--panel);border:1px solid var(--line);border-radius:4px;min-width:0}}.answer h2{{margin:0 0 6px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:800}}.answer p{{margin:0;font-size:14px;overflow-wrap:anywhere}}.answer.continue.bad{{border-color:#f0c2c7;background:var(--danger-soft)}}.answer.continue.warn{{border-color:#efd39a;background:var(--warn-soft)}}.answer.continue.active{{border-color:#b7ccee;background:var(--brand-soft)}}.answer .continue-label{{display:block;font-weight:750;margin-bottom:4px}}.next-action{{padding:14px 16px;background:#122038;color:#e8eef8;border-radius:4px}}.next-action h2{{margin:0 0 6px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#9eb0c9;font-weight:800}}.next-action p{{margin:0;font-size:15px;font-weight:600}}
.notice{{display:flex;gap:12px;align-items:flex-start;background:var(--warn-soft);border:1px solid #efd39a;border-radius:4px;padding:12px 14px;margin:0 0 18px;color:#65420c}}.notice-icon{{font-weight:900}}.notice strong{{color:#523405}}.notice p{{margin:2px 0 0}}
.trust-ladder{{list-style:none;margin:0 0 18px;padding:0;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}}.trust-rung{{padding:12px;background:var(--panel);border:1px solid var(--line);border-radius:4px;display:grid;gap:4px}}.trust-label{{font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}.trust-state{{font-size:12px;font-weight:750;text-transform:uppercase;letter-spacing:.04em}}.trust-rung.recorded .trust-state,.trust-rung.issued .trust-state{{color:var(--success)}}.trust-rung.failed .trust-state{{color:var(--danger)}}.trust-rung.not-checked .trust-state,.trust-rung.warn .trust-state{{color:var(--warn)}}.trust-rung.upcoming .trust-state,.trust-rung.empty .trust-state{{color:var(--muted)}}.trust-detail{{font-size:12px;color:var(--muted)}}
.about{{margin:0 0 18px}}.about summary{{cursor:pointer;font-weight:700;color:var(--brand);padding:12px 0}}.about-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 24px;padding-bottom:8px}}.about-grid h3{{margin:0 0 6px;font-size:14px}}.about-grid p,.about-grid ol{{margin:0;color:var(--muted);font-size:13px}}.about-grid ol{{padding-left:18px}}.about-docs{{display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}}.about-docs a{{color:var(--brand);font-weight:700;font-size:13px;text-decoration:none}}.about-docs a:hover{{text-decoration:underline}}
.status-grid{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:18px}}.metric{{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:14px;min-height:88px}}.metric-label{{display:block;color:var(--muted);font-size:12px;margin-bottom:6px}}.metric strong{{display:block;font-size:15px;overflow-wrap:anywhere}}.metric small{{display:block;color:var(--muted);margin-top:3px}}.good{{color:var(--success)}}.bad{{color:var(--danger)}}
.dashboard-grid{{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(280px,.75fr);gap:18px;align-items:start}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:4px;box-shadow:var(--shadow);overflow:hidden}}.panel-header{{padding:18px 20px 14px;border-bottom:1px solid var(--line)}}.panel-header h2{{margin:0;font-size:17px}}.panel-header p{{margin:4px 0 0;color:var(--muted);font-size:13px}}.panel-body{{padding:18px 20px}}
.payload{{border-left:4px solid var(--brand)}}.payload-command{{display:block;margin:10px 0 14px;padding:12px 13px;border-radius:4px;background:#111a2e;color:#edf2ff;white-space:pre-wrap;overflow-wrap:anywhere}}.facts{{display:grid;grid-template-columns:1fr 1fr;gap:0 18px;margin:0}}.fact{{padding:10px 0;border-top:1px solid var(--line);min-width:0}}.fact dt{{color:var(--muted);font-size:12px}}.fact dd{{margin:3px 0 0;font-weight:650;overflow-wrap:anywhere}}.fact.wide{{grid-column:1/-1}}
.timeline{{list-style:none;padding:0;margin:0}}.step{{display:grid;grid-template-columns:34px minmax(0,1fr);gap:12px;position:relative;padding:0 0 20px}}.step:last-child{{padding-bottom:0}}.step:not(:last-child)::before{{content:"";position:absolute;left:16px;top:32px;bottom:0;width:2px;background:var(--line)}}.step-marker{{position:relative;z-index:1;width:34px;height:34px;display:grid;place-items:center;border-radius:50%;background:var(--soft);border:2px solid var(--line);color:var(--muted);font-size:12px;font-weight:800}}.step.complete .step-marker{{background:var(--success);border-color:var(--success);color:#fff;font-size:0}}.step.complete .step-marker::after{{content:"✓";font-size:15px}}.step.current .step-marker{{background:var(--brand);border-color:var(--brand);color:#fff}}.step.failed .step-marker{{background:var(--danger);border-color:var(--danger);color:#fff}}.step.complete:not(:last-child)::before{{background:#8dceb2}}.step-heading{{display:flex;align-items:center;justify-content:space-between;gap:10px}}.step h3{{font-size:15px;margin:4px 0 0}}.step-state{{text-transform:uppercase;letter-spacing:.06em;font-size:10px;font-weight:800;color:var(--muted)}}.step.complete .step-state{{color:var(--success)}}.step.current .step-state{{color:var(--brand)}}.step.failed .step-state{{color:var(--danger)}}.step p{{margin:4px 0 9px;color:var(--muted);font-size:13px}}
.command-row{{display:flex;gap:8px;align-items:stretch}}.command-row code{{flex:1;min-width:0;padding:9px 10px;background:var(--soft);border:1px solid var(--line);border-radius:4px;overflow-wrap:anywhere;color:#273550;white-space:pre-wrap}}.copy-button,.refresh-button{{border:1px solid #cbd4e2;background:#fff;color:#28364e;border-radius:4px;padding:7px 11px;font-size:12px;font-weight:700;cursor:pointer}}.copy-button:hover,.refresh-button:hover{{border-color:var(--brand);color:var(--brand)}}.skip{{position:absolute;left:8px;top:-48px;background:#fff;color:#142033;padding:8px 12px;z-index:5;font-weight:700}}.skip:focus{{top:8px}}.copy-button:focus-visible,.refresh-button:focus-visible,summary:focus-visible,a:focus-visible{{outline:3px solid rgba(31,75,153,.55);outline-offset:2px}}
.side-stack{{display:grid;gap:18px}}.path-list{{margin:0}}.path-list div{{padding:10px 0;border-bottom:1px solid var(--line)}}.path-list div:last-child{{border-bottom:0}}.path-list dt{{color:var(--muted);font-size:12px}}.path-list dd{{margin:3px 0 0;overflow-wrap:anywhere}}
.evidence-summary{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;cursor:pointer;font-weight:750}}.evidence-summary::marker{{color:var(--brand)}}.evidence-body{{padding:0 18px 18px}}.evidence-body pre{{margin:0;max-height:420px;overflow:auto;padding:14px;border-radius:4px;background:#10182b;color:#dbe4f4;white-space:pre-wrap;overflow-wrap:anywhere}}
.refresh-message{{min-height:20px;margin:9px 0 0;color:var(--muted);font-size:12px}}.refresh-message.error{{color:var(--danger)}}
.refresh-toolbar{{display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin:0 0 16px}}.refresh-toolbar label{{font-size:12px;color:var(--muted)}}.refresh-toolbar .refresh-message{{margin:0}}
.step.recorded .step-marker{{background:#e9eef6;color:#475975;border-color:#bfcbdd}}.step.recorded .step-state{{color:#52637e}}.step.not-checked .step-state{{color:var(--warn)}}.step.not-checked .step-marker{{border-color:#d99800;color:var(--warn)}}#warnings{{margin:0 0 16px;padding:14px 16px 14px 34px;background:var(--danger-soft);color:var(--danger);border:1px solid #f0c2c7;border-radius:4px}}[hidden]{{display:none!important}}.terminal-help{{margin:0 0 18px}}.terminal-help summary{{cursor:pointer;color:var(--brand);font-weight:700}}.terminal-help p{{color:var(--muted);font-size:13px}}.connection-stale .status-grid,.connection-stale .compose{{opacity:.6}}button:disabled{{opacity:.5;cursor:default}}.step-content{{min-width:0}}.evidence-summary::after{{content:"+";color:var(--brand)}}details[open]>.evidence-summary::after{{content:"−"}}
@media(max-width:900px){{.status-grid,.trust-ladder,.answer-grid{{grid-template-columns:repeat(2,1fr)}}.dashboard-grid{{grid-template-columns:1fr}}.about-grid{{grid-template-columns:1fr}}}}
@media(max-width:580px){{main{{padding:20px 14px 40px}}.topbar{{padding:0 14px}}.read-only{{display:none}}.docs-nav{{gap:8px;font-size:11px}}.status-grid,.trust-ladder,.answer-grid,.facts{{grid-template-columns:1fr}}.fact.wide{{grid-column:auto}}.command-row{{display:block}}.copy-button{{margin-top:7px;width:100%}}.footer-docs{{flex-direction:column;align-items:flex-start}}}}
@media(prefers-reduced-motion:no-preference){{.copy-button,.refresh-button{{transition:border-color .15s,color .15s}}.compose-hero{{animation:rise .45s ease-out}}.next-action{{animation:rise .55s ease-out}}.trust-ladder{{animation:rise .65s ease-out}}@keyframes rise{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
.site-footer{{margin-top:28px;padding-top:18px;border-top:1px solid var(--line);display:grid;gap:8px}}.footer-docs{{display:flex;flex-wrap:wrap;gap:10px 16px}}.footer-docs a{{color:var(--brand);font-weight:700;font-size:13px;text-decoration:none}}.footer-docs a:hover{{text-decoration:underline}}.footer-note{{margin:0;color:var(--muted);font-size:12px}}
</style></head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="topbar"><div class="brand"><span class="brand-mark" aria-hidden="true">RS</span><span>RunSpecimen</span></div><div class="topbar-meta"><nav class="docs-nav" aria-label="Documentation"><a href="#about">About</a><a href="{_escape(DOCS_URLS['user_guide'])}" target="_blank" rel="noopener noreferrer">User guide</a><a href="{_escape(DOCS_URLS['faq'])}" target="_blank" rel="noopener noreferrer">FAQ</a></nav><span class="read-only">Local · loopback only · read-only</span></div></header>
<main id="main">
  <section class="compose" aria-label="Run overview">
    <div class="compose-hero">
      <p class="brand-line">RunSpecimen</p>
      <h1 class="run-title" id="run-identity">{_escape(view['run_identity'])}</h1>
      <p class="run-meta">Local oversight for one bounded, human-approved run. This page inspects evidence; it cannot approve or execute.</p>
      <div class="phase-row"><span id="phase-badge" class="phase-badge {phase_tone}" data-phase="{_escape(phase)}">{_escape(phase_label)}</span></div>
    </div>
    <div class="answer-grid">
      <article class="answer"><h2>What happened?</h2><p id="happened">{_escape(view['happened'])}</p></article>
      <article class="answer continue {continue_tone}" id="continue-panel"><h2>Is it safe to continue?</h2><span id="continue-label" class="continue-label">{_escape(view['continue_label'])}</span><p id="continue-detail">{_escape(view['continue_detail'])}</p></article>
    </div>
    <div class="next-action"><h2>What do I do next?</h2><p id="next-action">{_escape(view['next_action'])}</p></div>
  </section>

  <aside class="notice"><span class="notice-icon" aria-hidden="true">!</span><div><strong>Safety boundary</strong><p>This dashboard can inspect evidence and copy commands, but it cannot approve or execute a run. Approval must be typed by a human in a real terminal.</p></div></aside>

  <ol class="trust-ladder" id="trust-ladder" aria-label="Evidence trust ladder">{trust_html}</ol>

  <div class="refresh-toolbar"><button id="refresh-button" class="refresh-button" type="button">Refresh status</button><label><input id="auto-refresh" type="checkbox" checked> Auto-refresh every 5s</label><span id="refresh-message" class="refresh-message" role="status">Loaded local evidence. Live receipt verification has not been performed.</span></div>
  <ul id="warnings" aria-live="polite" {'hidden' if not view['warnings'] else ''}>{warnings_html}</ul>

  <section class="status-grid" aria-label="Current run status">
    {cards}
  </section>

  <div class="dashboard-grid">
    <div class="side-stack">
      <section class="panel payload" aria-labelledby="contract-review-heading">
        <div class="panel-header"><h2 id="contract-review-heading">Contract review</h2><p>Read this before human TTY approval. Exact command, bounds, provenance, and assertions.</p></div>
        <div class="panel-body"><code class="payload-command">{_escape(payload_command)}</code>
          <dl class="facts">
            <div class="fact"><dt>Working directory</dt><dd>{_escape(contract.cwd)}</dd></div>
            <div class="fact"><dt>Wall timeout</dt><dd>{_escape(contract.caps.wall_timeout_sec)} seconds</dd></div>
            <div class="fact"><dt>Required outputs</dt><dd>{_escape(required_outputs)}</dd></div>
            <div class="fact"><dt>Capture bounds</dt><dd>{_escape(_format_bytes(contract.caps.stdout_max_bytes))} stdout · {_escape(_format_bytes(contract.caps.stderr_max_bytes))} stderr</dd></div>
            <div class="fact wide"><dt>Source roots</dt><dd>{_escape(source_roots)}</dd></div>
            <div class="fact wide"><dt>Excluded source paths</dt><dd>{_escape(', '.join(contract.source.excludes) or 'None')}</dd></div>
            <div class="fact wide"><dt>Runtime provenance</dt><dd>{_escape(runtime_line)}</dd></div>
            <div class="fact wide"><dt>Predecessor</dt><dd>{_escape(predecessor)}</dd></div>
            <div class="fact wide"><dt>Postflight assertions</dt><dd>Exit code {_escape(contract.postflight.exit_code)} · {_escape(assertion_count)} digests/JSON checks · source unchanged: {_escape('required' if contract.postflight.source_unchanged else 'not required')}</dd></div>
            <div class="fact wide"><dt>Declared isolation</dt><dd>{_escape(_isolation_copy(contract))}</dd></div>
            <div class="fact wide"><dt>Shared policy</dt><dd>{_escape(contract.policy.id if contract.policy is not None else 'none')}</dd></div>
          </dl>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header"><h2>Guided lifecycle</h2><p>Progress describes recorded history. Stop at the first refusal or failure.</p></div>
        <div class="panel-body"><details class="terminal-help"><summary>Terminal instructions</summary><p>Open Terminal on this computer and paste the relevant command below. The absolute workspace and contract paths are included. For approval, review the command, outputs and limits, then type APPROVE yourself when prompted. Run one step at a time.</p><p>A finished or failed run ID cannot be reused. Create a new contract and run ID for a new execution. {_escape(_isolation_copy(contract))}</p></details><ol class="timeline">{steps}</ol><p id="copy-message" class="refresh-message" aria-live="polite"></p></div>
      </section>
    </div>

    <aside class="side-stack">
      <section class="panel"><div class="panel-header"><h2>Paths and digests</h2><p>Identity boundaries for this contract-scoped view.</p></div><div class="panel-body">
        <dl class="path-list">
          <div><dt>Workspace</dt><dd>{_escape(workspace_path)}</dd></div>
          <div><dt>Contract</dt><dd>{_escape(resolved_contract_path)}</dd></div>
          <div><dt>Contract hash</dt><dd class="hash">{_escape(contract.contract_hash)}</dd></div>
          <div><dt>Approval lifetime</dt><dd>{_escape(contract.approval.ttl_sec)} seconds</dd></div>
          <div><dt>Certificate ID · recorded, not live verified</dt><dd id="certificate-id" class="hash">{_escape(view['certificate_id'])}</dd></div>
        </dl>
      </div></section>

      <details class="panel">
        <summary class="evidence-summary">Raw evidence</summary>
        <div class="evidence-body"><pre id="status">{status_json}</pre></div>
      </details>
    </aside>
  </div>

  <details id="about" class="panel about">
    <summary>About RunSpecimen — background</summary>
    <div class="panel-body">
      <div class="about-grid">
        <div>
          <h3>What it does</h3>
          <p>Exactly one human-approved, bounded local run at a time, with provenance binding and a tamper-evident receipt of what happened.</p>
        </div>
        <div>
          <h3>Core lifecycle</h3>
          <ol>
            <li>Approve on a real TTY</li>
            <li>Preflight provenance and lease checks</li>
            <li>Run the exact declared command once</li>
            <li>Postflight assertions and certificate</li>
            <li>Verify the live receipt</li>
          </ol>
        </div>
        <div>
          <h3>Safety model</h3>
          <p>TTY approval, workspace lease, hash-chained events, and certificates are evidence controls. {_escape(_isolation_copy(contract))}</p>
        </div>
        <div>
          <h3>This dashboard</h3>
          <p>Loopback-only and read-only: a guide for phase, evidence, and copyable CLI commands. It cannot approve or execute. Use the CLI in a terminal for every mutating step.</p>
        </div>
      </div>
      <nav class="about-docs" aria-label="Learn more">
        <a href="{_escape(DOCS_URLS['about'])}" target="_blank" rel="noopener noreferrer" aria-label="About RunSpecimen documentation">About (full)</a>
        <a href="{_escape(DOCS_URLS['user_guide'])}" target="_blank" rel="noopener noreferrer" aria-label="RunSpecimen user guide">User guide</a>
        <a href="{_escape(DOCS_URLS['faq'])}" target="_blank" rel="noopener noreferrer" aria-label="RunSpecimen FAQ">FAQ</a>
      </nav>
    </div>
  </details>
  <footer class="site-footer">
    <nav class="footer-docs" aria-label="Documentation">
      <a href="#about">About</a>
      <a href="{_escape(DOCS_URLS['user_guide'])}" target="_blank" rel="noopener noreferrer">User guide</a>
      <a href="{_escape(DOCS_URLS['faq'])}" target="_blank" rel="noopener noreferrer">FAQ</a>
      <a href="{_escape(DOCS_URLS['about'])}" target="_blank" rel="noopener noreferrer">About (full)</a>
    </nav>
    <p class="footer-note">Loopback · read-only · receipt issued ≠ live verification</p>
  </footer>
</main>
<script>
const text=(id,value)=>{{const el=document.getElementById(id);if(el)el.textContent=String(value)}};
if(window.matchMedia("(prefers-reduced-motion: reduce)").matches){{const box=document.getElementById("auto-refresh");if(box)box.checked=false;}}
function renderTrust(ladder){{
  const root=document.getElementById("trust-ladder");if(!root||!Array.isArray(ladder))return;
  root.replaceChildren();
  for(const rung of ladder){{
    const li=document.createElement("li");li.className=`trust-rung ${{rung.state}}`;
    const label=document.createElement("span");label.className="trust-label";label.textContent=rung.label;
    const state=document.createElement("span");state.className="trust-state";state.textContent=rung.state;
    const detail=document.createElement("span");detail.className="trust-detail";detail.textContent=rung.detail;
    li.append(label,state,detail);root.append(li);
  }}
}}
function renderStatus(doc){{
  const view=doc.view;if(!view||!view.cards||!Array.isArray(view.steps))throw new Error("Unexpected status response");
  document.body.classList.remove("connection-stale");
  const badge=document.getElementById("phase-badge");badge.textContent=view.phase_label;badge.dataset.phase=doc.phase;badge.className=`phase-badge ${{view.phase_tone}}`;
  for(const [key,values] of Object.entries(view.cards)){{text(`${{key}}-value`,values[0]);text(`${{key}}-detail`,values[1]);document.getElementById(`${{key}}-value`).className=values[2];}}
  const warnings=document.getElementById("warnings");warnings.replaceChildren();for(const warning of view.warnings){{const li=document.createElement("li");li.textContent=warning;warnings.append(li);}}warnings.hidden=!view.warnings.length;
  text("next-action",view.next_action);text("certificate-id",view.certificate_id);
  text("happened",view.happened);text("continue-label",view.continue_label);text("continue-detail",view.continue_detail);
  const panel=document.getElementById("continue-panel");if(panel)panel.className=`answer continue ${{view.continue_tone}}`;
  if(view.run_identity)text("run-identity",view.run_identity);
  renderTrust(view.trust_ladder);
  document.querySelectorAll(".step").forEach((step,index)=>{{step.className=`step ${{view.steps[index]}}`;step.querySelector(".step-state").textContent=view.steps[index];}});
  const {{view: _view, ...evidence}}=doc;text("status",JSON.stringify(evidence,null,2));
  document.querySelectorAll(".copy-button").forEach(button=>button.disabled=false);
}}
let refreshing=false;let stopped=false;
async function refreshStatus(){{
  if(refreshing||stopped)return;refreshing=true;
  const button=document.getElementById("refresh-button"),message=document.getElementById("refresh-message");button.disabled=true;
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),4000);
  try{{const response=await fetch("/api/status",{{cache:"no-store",signal:controller.signal}});const doc=await response.json();if(!response.ok){{if(response.status===409)stopped=true;throw new Error(doc.error||`Status request failed (${{response.status}})`);}}renderStatus(doc);message.className="refresh-message";message.textContent=`Updated ${{new Date().toLocaleTimeString()}} · Live receipt verification not performed`;}}
  catch(error){{document.body.classList.add("connection-stale");text("phase-badge",stopped?"Contract changed":"Evidence unavailable");document.getElementById("phase-badge").className="phase-badge danger";message.className="refresh-message error";message.textContent=`${{error.name==="AbortError"?"Status request timed out":error.message}}. Displayed evidence is stale.${{stopped?" Restart the dashboard for the changed contract.":""}}`;document.querySelectorAll(".copy-button").forEach(button=>button.disabled=true);}}
  finally{{clearTimeout(timeout);button.disabled=stopped;refreshing=false;}}
}}
document.getElementById("refresh-button").addEventListener("click",()=>refreshStatus());
document.querySelectorAll(".copy-button").forEach(button=>button.addEventListener("click",async()=>{{
  const message=document.getElementById("copy-message");try{{await navigator.clipboard.writeText(button.dataset.copy);message.className="refresh-message";message.textContent="Command copied. Run it in a real terminal.";button.textContent="Copied";setTimeout(()=>button.textContent="Copy",1200);}}catch(_error){{message.className="refresh-message error";message.textContent="Clipboard unavailable. Select the command text and copy it manually.";}}
}}));
setInterval(()=>{{if(!document.hidden&&document.getElementById("auto-refresh").checked)refreshStatus();}},5000);
document.addEventListener("visibilitychange",()=>{{if(!document.hidden&&document.getElementById("auto-refresh").checked)refreshStatus();}});
</script>
</body></html>"""


def make_handler(*, workspace: Path, contract_path: Path):
    """Create a handler restricted to one resolved workspace and contract."""
    workspace = resolve_workspace(workspace)
    contract_path = contract_path.resolve()
    contract = load_contract(contract_path)

    def current_status() -> dict[str, Any]:
        live = load_contract(contract_path)
        if live.contract_hash != contract.contract_hash:
            raise _ContractChanged("Contract changed since dashboard startup; restart the dashboard to review it.")
        doc = status_for(
            workspace=workspace,
            campaign_id=contract.campaign_id,
            run_id=contract.run_id,
            contract_path=contract_path,
        )
        if load_contract(contract_path).contract_hash != contract.contract_hash:
            raise _ContractChanged("Contract changed while reading evidence; restart the dashboard.")
        if not isinstance(doc.get("state"), dict):
            raise ValueError("Run state must be an object")
        for field in ("approval", "certificate"):
            if doc.get(field) is not None and not isinstance(doc[field], dict):
                raise ValueError(f"{field} must be an object")
        doc["view"] = _presentation(doc, contract)
        return doc

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "RunSpecimen"
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)

        def _respond(self, code: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _error(self, code: int, message: str) -> None:
            self._respond(code, json.dumps({"error": message}).encode("utf-8"))

        def _local_request(self) -> bool:
            authority = f"127.0.0.1:{self.server.server_address[1]}"
            if self.headers.get_all("Host", []) != [authority]:
                self._error(403, "Use the exact loopback URL printed by the dashboard.")
                return False
            origins = self.headers.get_all("Origin", [])
            if origins and origins != [f"http://{authority}"]:
                self._error(403, "Cross-origin access is not allowed.")
                return False
            if self.headers.get("Sec-Fetch-Site") not in (None, "none", "same-origin"):
                self._error(403, "Cross-site access is not allowed.")
                return False
            return True

        def do_GET(self) -> None:  # noqa: N802
            if not self._local_request():
                return
            if self.path not in ("/", "/api/status"):
                self._error(404, "Not found")
                return
            try:
                doc = current_status()
                if self.path == "/":
                    body = dashboard_document(workspace=workspace, contract_path=contract_path, status=doc, contract=contract).encode("utf-8")
                    self._respond(200, body, "text/html; charset=utf-8")
                else:
                    self._respond(200, json.dumps(doc, sort_keys=True, default=str).encode("utf-8"))
            except _ContractChanged as exc:
                self._error(409, str(exc))
            except (RunSpecimenError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                self._error(503, f"Local evidence is unavailable: {exc}")

        def do_POST(self) -> None:  # noqa: N802
            self._error(405, "Dashboard is read-only; use the CLI lifecycle in a terminal.")

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST
        do_OPTIONS = do_POST

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return DashboardHandler


class _ContractChanged(RunSpecimenError):
    """The dashboard's contract binding changed while serving."""


def start_dashboard(*, workspace: Path, contract_path: Path, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Bind a dashboard to loopback only and return its server and URL."""
    if not 0 <= port <= 65535:
        raise RunSpecimenError("dashboard port must be between 0 and 65535")
    if not workspace.is_dir():
        raise RunSpecimenError(f"workspace is not a directory: {workspace}")
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(
        workspace=workspace, contract_path=contract_path
    ))
    host, selected_port = server.server_address[:2]
    return server, f"http://{host}:{selected_port}/"
