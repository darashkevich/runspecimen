"""Opt-in human presentation for CLI stdout/stderr.

Default command output stays JSON. This module is used only when the user
passes ``--pretty`` (or runs ``quickstart``), and for the TTY approve prompt
which was already human-only. It does not change leases, hashes, approval
gates, certificates, or exit codes.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from typing import Any, Iterable, Sequence, TextIO

from runspecimen import DOCS_URLS, PRODUCT_NAME, __version__
from runspecimen.terminaltext import escape_for_terminal


# Exact last line of the TTY approve prompt. The macOS MAS e2e harness
# (MasSandboxE2E.swift) waits for this substring and must keep matching.
APPROVE_BIND_PROMPT = "Type 'APPROVE' to bind this approval:"

PHASE_LABELS = {
    "none": "Ready to review",
    "approved": "Approved — not launched",
    "preflighted": "Preflight passed — not launched",
    "running": "Running",
    "completed": "Run completed — not certified",
    "failed": "Failed (this run ID is terminal)",
    "postflighted": "Postflight recorded",
    "abandoned": "Abandoned (this run ID is terminal)",
}

_STYLES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
}

# Substring → next-step copy. Matched against str(exc); the original
# exception text is always printed unchanged on the first line.
_ERROR_HINTS: tuple[tuple[str, str], ...] = (
    (
        "no approval present",
        "Approve on a real TTY first (agents cannot type APPROVE through the app):\n"
        "  runspecimen approve --workspace <dir> --contract <file>",
    ),
    (
        "Planted or edited approval files cannot launch",
        "This approval file is not bound to the event log. Approve again on a real TTY. "
        "A program running as you that can edit RunSpecimen's files can still add a fake approval to the record. Signing with a key the agent can't access lets you check afterwards that a receipt is authentic, when a signature is required and checked; it does not stop a program running as you from adding a fake approval or running the job.",
    ),
    (
        "This receipt has no bound approval event",
        "This receipt is not bound to a recorded approve step. Planted or edited approvals cannot verify. "
        "A bound approval event is a recorded local step, not cryptographic proof of a human. "
        "A program running as you that can edit RunSpecimen's files can still add a fake approval to the record. Signing with a key the agent can't access lets you check afterwards that a receipt is authentic, when a signature is required and checked; it does not stop a program running as you from adding a fake approval or running the job.",
    ),
    (
        "certificate contains unknown field",
        "certificate.json has extra fields this engine does not bind. The receipt cannot verify.",
    ),
    (
        "approval expired",
        "The previous approval TTL elapsed. Review the current contract and approve again:\n"
        "  runspecimen approve --workspace <dir> --contract <file>",
    ),
    (
        "source_hash mismatch",
        "Source files changed after approval. Re-approve the current tree, or restore the approved files.",
    ),
    (
        "source hash drift",
        "Source files changed after approval. Re-approve the current tree, or restore the approved files.",
    ),
    (
        "contract_hash mismatch",
        "The contract file bytes changed (even whitespace). Re-approve, or restore the approved contract.",
    ),
    (
        "contract hash drift",
        "The contract file bytes changed (even whitespace). Re-approve, or restore the approved contract.",
    ),
    (
        "confirmation phrase mismatch",
        "Type the confirmation word exactly, in uppercase, on a real TTY. Nothing else is accepted.",
    ),
    (
        "interactive TTY",
        "Open a real terminal (not a pipe, not CI). Plugins and agents cannot approve through the app. Planted or edited approvals show up as broken receipts.",
    ),
    (
        "refuse re-entry",
        "A started run ID cannot be reused. Author a new contract with a new run_id.",
    ),
    (
        "refuse re-approval",
        "This run already started or finished. Author a new contract with a new run_id.",
    ),
    (
        "asserted output already exists",
        "Preflight refuses to overwrite declared outputs. Move or delete that file, or use a new run_id.",
    ),
    (
        "workspace execution lease unavailable",
        "Another lifecycle command holds this workspace. Wait, or inspect:\n"
        "  runspecimen status --workspace <dir> --campaign-id <id> --run-id <id>",
    ),
    (
        "predecessor not postflighted",
        "Finish postflight (and verify) on the predecessor before starting this successor.",
    ),
    (
        "predecessor not found",
        "The contract names a predecessor that has no state in this workspace.",
    ),
    (
        "certificate not found",
        "Run postflight after a successful run to issue a certificate, then verify.",
    ),
    (
        "campaign-id/run-id flags do not match",
        "Pass the campaign_id and run_id that are inside the contract JSON.",
    ),
    (
        "needs recovery",
        "Inspect recovery-status. If the process is gone, abandon on a TTY (type ABANDON),\n"
        "then start a new run_id. Do not reuse this one.",
    ),
    (
        "wall timeout",
        "The run exceeded caps.wall_timeout_sec and cannot become a certified success. Use a new run_id.",
    ),
    (
        "Demo destination already exists",
        "init-demo never overwrites. Pass a directory that does not exist yet.",
    ),
    (
        "contract not found",
        "Pass a contract JSON path that exists inside the workspace:\n"
        "  runspecimen validate --workspace <dir> --contract <file>",
    ),
    (
        "no typed-phrase fallback",
        "Holder policies need a separately qualified holder; typed-phrase approval isn't available here.",
    ),
)


def color_enabled(mode: str, stream: TextIO | None = None) -> bool:
    """Return whether ANSI color should be used.

    ``--pretty`` is required by the caller; this only interprets ``--color``.
    JSON default output never calls this for stdout.
    """
    stream = stream or sys.stdout
    normalized = (mode or "auto").lower()
    if normalized == "never":
        return False
    if normalized == "always":
        return True
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def paint(text: str, style: str | None, *, enabled: bool) -> str:
    if not enabled or not style:
        return text
    code = _STYLES.get(style)
    if not code:
        return text
    return f"{code}{text}{_STYLES['reset']}"


def format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.0f} KiB ({value} B)"
    return f"{value / (1024 * 1024):.1f} MiB ({value} B)"


def format_duration(seconds: int | float) -> str:
    sec = int(seconds)
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        minutes, rem = divmod(sec, 60)
        return f"{sec}s ({minutes}m {rem}s)" if rem else f"{sec}s ({minutes}m)"
    hours, rem = divmod(sec, 3600)
    minutes = rem // 60
    if minutes:
        return f"{sec}s ({hours}h {minutes}m)"
    return f"{sec}s ({hours}h)"


def _scalar(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        if abs(value) >= 1_000_000:
            return f"{value:.6f}".rstrip("0").rstrip(".")
        return f"{value:.4g}"
    if isinstance(value, dict):
        if not value:
            return "(empty)"
        return ", ".join(
            f"{escape_for_terminal(str(key))}={_scalar(item)}"
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        if not value:
            return "(none)"
        return ", ".join(_scalar(item) for item in value)
    return escape_for_terminal(str(value))


def _join_paths(items: Sequence[Any] | None) -> str:
    if not items:
        return "(none)"
    return ", ".join(escape_for_terminal(str(item)) for item in items)


def kv_block(rows: Iterable[tuple[str, Any]], *, width: int = 14) -> list[str]:
    lines: list[str] = []
    for label, value in rows:
        label_text = escape_for_terminal(str(label))
        text = _scalar(value)
        if "\n" in text:
            lines.append(f"  {label_text:<{width}}")
            for part in text.splitlines():
                lines.append(f"  {'':<{width}} {escape_for_terminal(part)}")
        else:
            lines.append(f"  {label_text:<{width}} {text}")
    return lines


def _heading(title: str, *, enabled: bool, style: str = "bold") -> str:
    return paint(title, style, enabled=enabled)


def _next_lifecycle_command(kind: str, ctx: dict[str, Any]) -> list[str]:
    workspace = ctx.get("workspace") or "."
    contract = ctx.get("contract")
    campaign = ctx.get("campaign_id")
    run_id = ctx.get("run_id")
    ws = shlex.quote(str(workspace))
    if contract:
        ct = shlex.quote(str(contract))
        pair = f"--workspace {ws} --contract {ct}"
    else:
        pair = f"--workspace {ws} --contract <contract.json>"
    follow = {
        "init-demo": [
            f"cd {ws}",
            f"runspecimen doctor --workspace {ws}",
            f"runspecimen validate {pair}",
            f"runspecimen approve {pair}",
            "# Then type APPROVE yourself on a real TTY.",
        ],
        "validate": [f"runspecimen approve {pair}"],
        "approve": [f"runspecimen preflight {pair}"],
        "preflight": [f"runspecimen run {pair}"],
        "run": [f"runspecimen postflight {pair}"],
        "postflight": [
            "runspecimen verify "
            + (f"--workspace {ws} --contract {shlex.quote(str(contract))} " if contract else pair + " ")
            + (
                f"--campaign-id {shlex.quote(str(campaign))} --run-id {shlex.quote(str(run_id))}"
                if campaign and run_id
                else "--campaign-id <id> --run-id <id>"
            ),
        ],
        "verify": [
            "Keep the workspace evidence. digest/diff summarize certificates; they are not verify."
        ],
    }
    return follow.get(kind, [])


def hint_for_error(message: str) -> str | None:
    lowered = message.lower()
    for needle, hint in _ERROR_HINTS:
        if needle.lower() in lowered:
            return hint
    return None


def format_error(message: str, *, pretty: bool, color_mode: str = "auto") -> str:
    """Stderr text for a refusal.

    Default (pretty=False) is exactly ``RunSpecimen error: {message}`` so
    existing tests and scrapers keep working. Pretty adds a hint block.
    """
    first = f"{PRODUCT_NAME} error: {escape_for_terminal(message)}"
    if not pretty:
        return first
    enabled = color_enabled(color_mode, sys.stderr)
    lines = [paint(first, "red", enabled=enabled)]
    hint = hint_for_error(message)
    if hint:
        lines.append("")
        lines.append(paint("What to do", "bold", enabled=enabled))
        lines.extend(f"  {row}" if not row.startswith("  ") else row for row in hint.splitlines())
    return "\n".join(lines)


def format_quickstart() -> str:
    return f"""{PRODUCT_NAME} {__version__}
One human-approved bounded run at a time, with a tamper-evident receipt.
Not an OS sandbox. Plugins and agents cannot approve through the app.

Quick start (fresh directory; pip or Homebrew install):

  runspecimen init-demo --workspace ./runspecimen-demo
  cd ./runspecimen-demo
  runspecimen doctor --workspace .
  runspecimen validate --workspace . --contract contract.json
  runspecimen approve --workspace . --contract contract.json
  # Type APPROVE yourself on a real TTY. Agents must not type it.
  runspecimen preflight --workspace . --contract contract.json
  runspecimen run --workspace . --contract contract.json
  runspecimen postflight --workspace . --contract contract.json
  runspecimen verify --workspace . --contract contract.json \\
    --campaign-id demo-campaign --run-id run-001

Lifecycle:  approve → preflight → run → postflight → verify

Human-readable view (opt-in). JSON is still the default:

  runspecimen --pretty doctor --workspace .
  runspecimen doctor --pretty --workspace .
  runspecimen --pretty status --workspace . --campaign-id demo-campaign --run-id run-001

Read-only dashboard (cannot approve or run through the app):

  runspecimen dashboard --workspace . --contract contract.json --open

More:  runspecimen --help   ·   runspecimen about
Docs:  {DOCS_URLS['user_guide']}
"""


HELP_EPILOG = f"""
Quick start:
  runspecimen quickstart
  runspecimen init-demo --workspace ./runspecimen-demo
  cd ./runspecimen-demo
  runspecimen doctor --workspace . && runspecimen validate --workspace . --contract contract.json
  runspecimen approve --workspace . --contract contract.json    # type APPROVE on a real TTY
  runspecimen preflight --workspace . --contract contract.json
  runspecimen run --workspace . --contract contract.json
  runspecimen postflight --workspace . --contract contract.json
  runspecimen verify --workspace . --contract contract.json --campaign-id demo-campaign --run-id run-001

Human-readable output (opt-in; JSON remains the default for every command):
  runspecimen --pretty status --workspace . --campaign-id demo-campaign --run-id run-001
  runspecimen doctor --pretty --workspace .

Core lifecycle: approve → preflight → run → postflight → verify
Plugins/agents cannot approve through the app. The dashboard is loopback-only and read-only.

Docs: About {DOCS_URLS['about']}
      User guide {DOCS_URLS['user_guide']}
      FAQ {DOCS_URLS['faq']}
      or run: runspecimen about   ·   runspecimen quickstart
"""


def format_approve_prompt(
    *,
    campaign_id: str,
    run_id: str,
    argv: Sequence[str],
    cwd: str,
    sources: Sequence[str],
    excludes: Sequence[str],
    outputs: Sequence[str],
    timeout_sec: int,
    stdout_max_bytes: int,
    stderr_max_bytes: int,
    predecessor: Any,
    isolation_claim: str,
    policy_line: str,
    approver_user: str,
    contract_hash: str,
    source_hash: str,
    runtime_path: str,
    runtime_id: str,
    ttl_sec: int,
    confirm_phrase: str,
    manifest_line: str = "none",
    check_lines: Sequence[str] | None = None,
) -> str:
    """TTY review text. Last line stays the historical bind prompt."""
    # Escape each argv element before join so ESC/CSI/OSC/CR/BS/bidi cannot
    # rewrite the review, while shlex still keeps argument boundaries.
    escaped_argv = [escape_for_terminal(str(part)) for part in argv]
    try:
        command = shlex.join(escaped_argv)
    except (TypeError, ValueError):
        command = " ".join(escaped_argv)
    if predecessor is None:
        pred = "none"
    elif hasattr(predecessor, "campaign_id") and hasattr(predecessor, "run_id"):
        pred = (
            f"{escape_for_terminal(str(predecessor.campaign_id))}/"
            f"{escape_for_terminal(str(predecessor.run_id))}"
        )
    else:
        pred = escape_for_terminal(repr(predecessor))
    first_rows: list[tuple[str, Any]] = [
        ("Campaign", campaign_id),
        ("Run", run_id),
        ("Command", command),
        ("Working dir", cwd),
        ("Sources", _join_paths(sources)),
        ("Excludes", _join_paths(excludes)),
        ("Outputs", _join_paths(outputs)),
        ("Timeout", format_duration(timeout_sec)),
        (
            "Capture",
            f"stdout {format_bytes(stdout_max_bytes)} · "
            f"stderr {format_bytes(stderr_max_bytes)}",
        ),
        ("Predecessor", pred),
        ("Isolation", isolation_claim),
        ("Policy", policy_line),
        ("Manifest", manifest_line),
        ("Approver", f"{approver_user} (local OS user on this machine)"),
        ("TTL", f"{format_duration(ttl_sec)} after you approve"),
    ]
    body = [
        "Review this bounded run. Typing APPROVE binds the contract, source tree,",
        "and resolved executable below. Agents and plugins cannot approve through the app.",
        "",
        *kv_block(first_rows),
    ]
    if check_lines:
        body.append("  Checks bound before approval:")
        body.extend(escape_for_terminal(str(line)) for line in check_lines)
    body.extend(
        [
            "",
            "Fingerprints (full SHA-256 — compare these if you re-approve):",
            *kv_block(
                [
                    ("Contract", contract_hash),
                    ("Source", source_hash),
                    ("Runtime", runtime_path),
                    ("Runtime id", runtime_id),
                ]
            ),
            "",
            f"Type {confirm_phrase!r} to bind this approval: ",
        ]
    )
    # The last line is written without a trailing newline so input follows it.
    return "\n".join(body[:-1]) + "\n" + body[-1]


def _status_next_step(doc: dict[str, Any]) -> str:
    phase = str((doc.get("phase") or "none"))
    if doc.get("needs_recovery"):
        return (
            "This looks interrupted. Check recovery-status; abandon on a TTY "
            "only if the process is gone. Then use a new run_id."
        )
    if doc.get("workspace_lease_held_by_other") or doc.get("lease_held_by_other"):
        return "A workspace lease is held. Wait; do not start another lifecycle command."
    if phase == "none":
        return "Validate the contract, then approve on a real TTY."
    if phase == "approved":
        return "Continue with preflight (or run, which rechecks under the lease)."
    if phase == "preflighted":
        return "Continue with run."
    if phase == "running":
        return "Wait for the run to finish, or inspect recovery-status if it looks stuck."
    if phase == "completed":
        return "Continue with postflight to certify outcomes."
    if phase in {"failed", "abandoned"}:
        return "Do not reuse this run_id. Inspect evidence, then author a new run_id."
    if phase == "postflighted":
        return "Run verify in a terminal before trusting the receipt. This status view is not live verify."
    return "Inspect recorded state before the next lifecycle command."


def format_pretty(
    payload: Any,
    *,
    kind: str,
    context: dict[str, Any] | None = None,
    color_mode: str = "auto",
    stream: TextIO | None = None,
) -> str:
    stream = stream or sys.stdout
    enabled = color_enabled(color_mode, stream)
    ctx = dict(context or {})
    formatter = {
        "about": _format_about,
        "doctor": _format_doctor,
        "init-demo": _format_init_demo,
        "validate": _format_validate,
        "approve": _format_approve_result,
        "preflight": _format_preflight,
        "run": _format_run,
        "postflight": _format_postflight,
        "verify": _format_verify,
        "status": _format_status,
        "digest": _format_digest,
        "diff": _format_diff,
        "isolation": _format_isolation,
        "recovery-status": _format_recovery,
        "abandon": _format_abandon,
        "bundle": _format_bundle,
        "retain": _format_bundle,
        "list-keys": _format_list_keys,
        "keygen": _format_keygen,
        "sign": _format_sign,
        "verify-signature": _format_verify_signature,
        "export-public-key": _format_export_pub,
        "remote-confirm": _format_generic,
    }.get(kind, _format_generic)
    body = formatter(payload, enabled=enabled, context=ctx)
    steps = _next_lifecycle_command(kind, {**ctx, **_ids_from_payload(payload)})
    if steps:
        body += "\n" + paint("Next", "bold", enabled=enabled) + "\n"
        body += "\n".join(f"  {line}" for line in steps) + "\n"
    return body.rstrip() + "\n"


def _ids_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    inner = payload.get("approval") or payload.get("certificate") or payload
    if not isinstance(inner, dict):
        inner = payload
    out = {}
    for key in ("campaign_id", "run_id"):
        if payload.get(key):
            out[key] = payload[key]
        elif isinstance(inner, dict) and inner.get(key):
            out[key] = inner[key]
    return out


def _banner(ok: bool | None, title: str, *, enabled: bool) -> str:
    if ok is True:
        tag = paint("OK", "green", enabled=enabled)
    elif ok is False:
        tag = paint("REFUSED", "red", enabled=enabled)
    else:
        tag = paint(PRODUCT_NAME, "cyan", enabled=enabled)
    return f"{tag}  {_heading(title, enabled=enabled)}"


def _strict_ok(payload: Any) -> bool:
    """Security-relevant pretty banners: only an explicit boolean True is success.

    Missing, null, or non-boolean ``ok`` must not render as a success banner.
    """
    if not isinstance(payload, dict):
        return False
    return payload.get("ok") is True


def _format_about(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    lines = [
        _banner(True, f"{payload.get('product', PRODUCT_NAME)} {payload.get('version', __version__)}", enabled=enabled),
        "",
        str(payload.get("summary") or ""),
        "",
        paint("Lifecycle", "bold", enabled=enabled),
    ]
    for i, step in enumerate(payload.get("lifecycle") or [], 1):
        lines.append(f"  {i}. {escape_for_terminal(str(step))}")
    docs = payload.get("docs") or {}
    if docs:
        lines.append("")
        lines.append(paint("Docs", "bold", enabled=enabled))
        lines.extend(kv_block(list(docs.items())))
    lines.append("")
    lines.append("Human-readable CLI: pass --pretty. JSON remains the default.")
    lines.append("Try: runspecimen quickstart")
    return "\n".join(lines) + "\n"


def _format_doctor(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    ok = _strict_ok(payload)
    lines = [
        _banner(ok, "Host and workspace readiness", enabled=enabled),
        "",
        *kv_block(
            [
                ("Workspace", payload.get("workspace")),
                ("Writable", payload.get("workspace_writable")),
                ("Platform", payload.get("platform")),
                ("Python", payload.get("python")),
                ("Lease busy", payload.get("workspace_lease_held")),
            ]
        ),
    ]
    lease = payload.get("active_lease")
    if isinstance(lease, dict):
        holder = escape_for_terminal(str(lease.get("holder") or ""))
        pid = escape_for_terminal(str(lease.get("pid") or ""))
        lines.append(f"  {'Holder':<14} {holder} (pid {pid})")
    isolation = payload.get("isolation")
    if isinstance(isolation, dict):
        lines.append("")
        lines.append(paint("Isolation on this host", "bold", enabled=enabled))
        backends = isolation.get("backends") or isolation
        if isinstance(backends, dict):
            lines.extend(kv_block(list(backends.items())[:8]))
        else:
            lines.append(f"  {escape_for_terminal(str(backends))}")
    lines.append("")
    lines.append("Doctor does not approve or run anything.")
    return "\n".join(lines) + "\n"


def _format_init_demo(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    lines = [
        _banner(True, "Demo workspace created (not approved, not executed)", enabled=enabled),
        "",
        *kv_block(
            [
                ("Workspace", payload.get("workspace")),
                ("Contract", payload.get("contract")),
                ("Approved", payload.get("approved")),
                ("Executed", payload.get("executed")),
            ]
        ),
        "",
        "init-demo never overwrites an existing directory and never types APPROVE.",
    ]
    return "\n".join(lines) + "\n"


def _format_validate(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
    isolation = payload.get("isolation") if isinstance(payload.get("isolation"), dict) else {}
    lines = [
        _banner(_strict_ok(payload), "Contract is well-formed", enabled=enabled),
        "",
        *kv_block(
            [
                ("Campaign", payload.get("campaign_id")),
                ("Run", payload.get("run_id")),
                ("Contract", payload.get("contract_hash")),
                ("Executable", runtime.get("resolved_executable")),
                ("Runtime id", runtime.get("runtime_id")),
                ("Isolation", isolation.get("backend") or isolation.get("claim")),
            ]
        ),
        "",
        "Validate does not bind approval. Next step is a real-TTY approve.",
    ]
    return "\n".join(lines) + "\n"


def _format_approve_result(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    doc = payload.get("approval") if isinstance(payload.get("approval"), dict) else payload
    lines = [
        _banner(True, "Approval bound", enabled=enabled),
        "",
        *kv_block(
            [
                ("Campaign", doc.get("campaign_id")),
                ("Run", doc.get("run_id")),
                ("Channel", doc.get("confirm_channel")),
                ("Approver", (doc.get("approver") or {}).get("user") if isinstance(doc.get("approver"), dict) else None),
                ("TTL", format_duration(doc["ttl_sec"]) if isinstance(doc.get("ttl_sec"), (int, float)) else doc.get("ttl_sec")),
                ("Expires unix", doc.get("expires_at_unix")),
                ("Contract", doc.get("contract_hash")),
                ("Source", doc.get("source_hash")),
            ]
        ),
        "",
        "This is evidence of a TTY (or remote-confirm) bind, not an OS sandbox.",
    ]
    return "\n".join(lines) + "\n"


def _format_preflight(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    lines = [
        _banner(True, "Preflight passed", enabled=enabled),
        "",
        *kv_block(
            [
                ("Campaign", payload.get("campaign_id")),
                ("Run", payload.get("run_id")),
                ("Contract", payload.get("contract_hash")),
                ("Source", payload.get("source_hash")),
                ("Isolation", payload.get("isolation_backend")),
                ("Enforced", payload.get("isolation_enforced")),
                ("Approval exp", payload.get("approval_expires_at_unix")),
            ]
        ),
        "",
        "Launch will recheck approval, provenance, and the workspace lease.",
    ]
    return "\n".join(lines) + "\n"


def _format_run(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    result = payload.get("run_result")
    exit_code = payload.get("exit_code")
    nonzero = isinstance(exit_code, int) and exit_code != 0
    if nonzero:
        title = f"Process finished with exit code {exit_code}"
        tag = paint("DONE", "yellow", enabled=enabled)
        heading = _heading(title, enabled=enabled)
        lines = [f"{tag}  {heading}", ""]
    else:
        ok = result == "completed"
        title = "Run completed" if ok else f"Run {result or 'finished'}"
        lines = [_banner(ok, title, enabled=enabled), ""]
    lines.extend(
        [
            *kv_block(
                [
                    ("Result", result),
                    ("Exit code", payload.get("exit_code")),
                    ("Timed out", payload.get("timed_out")),
                    ("Stdout", format_bytes(int(payload["stdout_bytes"])) if isinstance(payload.get("stdout_bytes"), int) else payload.get("stdout_bytes")),
                    ("Stderr", format_bytes(int(payload["stderr_bytes"])) if isinstance(payload.get("stderr_bytes"), int) else payload.get("stderr_bytes")),
                    ("Stdout cut", payload.get("stdout_truncated")),
                    ("Stderr cut", payload.get("stderr_truncated")),
                ]
            ),
            "",
            "Outcomes are not certified until postflight succeeds.",
        ]
    )
    return "\n".join(lines) + "\n"


def _cert_from(payload: dict[str, Any]) -> dict[str, Any]:
    cert = payload.get("certificate")
    return cert if isinstance(cert, dict) else payload


def _format_outputs(digests: Any) -> list[str]:
    if not isinstance(digests, dict) or not digests:
        return ["  (none recorded)"]
    rows = []
    for path, digest in sorted(digests.items()):
        rows.append(f"  {path}")
        rows.append(f"    {digest}")
    return rows


def _format_postflight(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    cert = _cert_from(payload)
    lines = [
        _banner(True, "Certificate issued (recorded — not live-verified here)", enabled=enabled),
        "",
        *kv_block(
            [
                ("Campaign", cert.get("campaign_id")),
                ("Run", cert.get("run_id")),
                ("Certificate", cert.get("certificate_id")),
                ("Issued at", cert.get("issued_at")),
                ("Exit code", cert.get("exit_code")),
                ("Result", cert.get("run_result")),
                ("Contract", cert.get("contract_hash")),
                ("Source", cert.get("source_hash")),
                ("Event head", cert.get("event_head")),
            ]
        ),
        "",
        paint("Output digests", "bold", enabled=enabled),
        *_format_outputs(cert.get("output_digests")),
        "",
        "This table is the recorded receipt. Run verify to rehash live files.",
    ]
    return "\n".join(lines) + "\n"


def _format_verify(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    doc = payload if isinstance(payload, dict) else {}
    ok = _strict_ok(doc)
    title = (
        "Receipt verification (files/chain; not signatures)"
        if ok
        else "Receipt verification failed"
    )
    lines = [
        _banner(ok, title, enabled=enabled),
        "",
        *kv_block(
            [
                ("Campaign", doc.get("campaign_id")),
                ("Run", doc.get("run_id")),
                ("Certificate", doc.get("certificate_id")),
                ("Event chain", doc.get("event_chain")),
                ("Event head", doc.get("event_head")),
                ("Confirm", doc.get("confirm_channel")),
            ]
        ),
    ]
    note = doc.get("confirm_channel_note")
    if note:
        lines.append("")
        lines.append(escape_for_terminal(str(note)))
    lines.extend(
        [
            "",
            "This is live receipt verification of the certificate, event chain, and current files.",
            "It does not check HMAC or Ed25519 signatures. verify-signature does that, with its required trust inputs.",
        ]
    )
    return "\n".join(lines) + "\n"


def _format_status(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    phase = str(payload.get("phase") or "none")
    label = PHASE_LABELS.get(phase, phase)
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    approval = payload.get("approval") if isinstance(payload.get("approval"), dict) else {}
    cert = payload.get("certificate") if isinstance(payload.get("certificate"), dict) else {}
    chain_ok = payload.get("event_chain_ok")
    tone = "green" if phase == "postflighted" and chain_ok else "red" if phase in {"failed", "abandoned"} or chain_ok is False else "yellow"
    lines = [
        f"{paint(label, tone, enabled=enabled)}  ({phase})",
        "",
        paint("What this means", "bold", enabled=enabled),
        f"  {_status_next_step(payload)}",
        "",
        *kv_block(
            [
                ("Workspace", payload.get("workspace")),
                ("Campaign", payload.get("campaign_id")),
                ("Run", payload.get("run_id")),
                ("Lease busy", payload.get("workspace_lease_held_by_other") or payload.get("lease_held_by_other")),
                ("Events", payload.get("event_count")),
                ("Chain", "ok" if chain_ok else payload.get("event_chain_msg") or "invalid"),
                ("Recovery", payload.get("recovery_reason") if payload.get("needs_recovery") else "not needed"),
                ("Exit code", state.get("exit_code")),
                ("Run result", state.get("run_result")),
            ]
        ),
    ]
    if approval:
        who = approval.get("approver")
        user = who.get("user") if isinstance(who, dict) else None
        lines.extend(
            [
                "",
                paint("Approval (recorded)", "bold", enabled=enabled),
                *kv_block(
                    [
                        ("Channel", approval.get("confirm_channel")),
                        ("Approver", user),
                        ("Expires unix", approval.get("expires_at_unix")),
                        ("Contract", approval.get("contract_hash")),
                        ("Source", approval.get("source_hash")),
                    ]
                ),
            ]
        )
    if cert:
        lines.extend(
            [
                "",
                paint("Certificate (recorded — not live verify)", "bold", enabled=enabled),
                *kv_block(
                    [
                        ("Certificate", cert.get("certificate_id")),
                        ("Event head", cert.get("event_head")),
                    ]
                ),
            ]
        )
    lines.append("")
    lines.append("status never takes the execution lease and never live-verifies a receipt.")
    return "\n".join(lines) + "\n"


def _format_digest(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    lines = [
        _banner(None, "Recorded receipt digest (not verify)", enabled=enabled),
        "",
        escape_for_terminal(str(payload.get("note") or "Recorded certificate fields only.")),
        "",
        *kv_block(
            [
                ("Campaign", payload.get("campaign_id")),
                ("Run", payload.get("run_id")),
                ("Certificate", payload.get("certificate_id")),
                ("Issued at", payload.get("issued_at")),
                ("Exit code", payload.get("exit_code")),
                ("Result", payload.get("run_result")),
                ("Contract", payload.get("contract_hash")),
                ("Source", payload.get("source_hash")),
                ("Runtime id", payload.get("runtime_id")),
                ("Event head", payload.get("event_head")),
            ]
        ),
        "",
        paint("Output digests", "bold", enabled=enabled),
        *_format_outputs(payload.get("output_digests")),
    ]
    live = payload.get("live_outputs")
    if isinstance(live, list) and live:
        lines.append("")
        lines.append(paint("Live file compare (still not verify)", "bold", enabled=enabled))
        for row in live:
            if not isinstance(row, dict):
                continue
            status = row.get("status")
            mark = paint(str(status), "green" if status == "match" else "red", enabled=enabled)
            lines.append(f"  {row.get('path')}  {mark}")
    return "\n".join(lines) + "\n"


def _format_diff(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    identical = bool(payload.get("identical"))
    lines = [
        _banner(identical, "Receipt field diff (not verify)", enabled=enabled),
        "",
        str(payload.get("note") or ""),
        *kv_block(
            [
                ("Left", payload.get("left")),
                ("Right", payload.get("right")),
                ("Identical", identical),
            ]
        ),
    ]
    changed = payload.get("changed") or []
    if changed:
        lines.append("")
        lines.append(paint("Changed fields", "bold", enabled=enabled))
        for row in changed:
            if not isinstance(row, dict):
                continue
            lines.append(f"  {row.get('field')}")
            lines.append(f"    left:  {_scalar(row.get('left'))}")
            lines.append(f"    right: {_scalar(row.get('right'))}")
    return "\n".join(lines) + "\n"


def _format_isolation(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    lines = [
        _banner(None, "Isolation backends on this host", enabled=enabled),
        "",
        "Default backend is none: RunSpecimen is not an OS sandbox.",
        "",
    ]
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, dict):
                lines.append(paint(str(key), "bold", enabled=enabled))
                lines.extend(kv_block(list(value.items())))
                lines.append("")
            else:
                lines.extend(kv_block([(str(key), value)]))
    return "\n".join(lines).rstrip() + "\n"


def _format_recovery(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    needs = bool(payload.get("needs_recovery"))
    lines = [
        _banner(not needs, "Recovery status", enabled=enabled),
        "",
        *kv_block(
            [
                ("Needs recovery", needs),
                ("Reason", payload.get("recovery_reason") or payload.get("reason") or payload.get("message")),
            ]
        ),
    ]
    if needs:
        lines.extend(
            [
                "",
                "If the process is gone, abandon on a real TTY (type ABANDON), then use a new run_id.",
            ]
        )
    return "\n".join(lines) + "\n"


def _format_abandon(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    lines = [
        _banner(True, "Run abandoned (terminal)", enabled=enabled),
        "",
        *kv_block(
            [
                ("Campaign", payload.get("campaign_id")),
                ("Run", payload.get("run_id")),
                ("Phase", payload.get("phase")),
                ("Result", payload.get("run_result")),
            ]
        ),
        "",
        "This run_id cannot be reused. Author a new contract with a new run_id.",
    ]
    return "\n".join(lines) + "\n"


def _format_bundle(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    lines = [
        _banner(True, "Incident pack written (local files only)", enabled=enabled),
        "",
        *kv_block(
            [
                (key, payload.get(key))
                for key in (
                    "out",
                    "destination",
                    "path",
                    "campaign_id",
                    "run_id",
                    "files",
                    "copied",
                )
                if key in payload
            ]
        ),
    ]
    return "\n".join(lines) + "\n"


def _format_list_keys(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    hmac_ids = payload.get("hmac_key_ids") or []
    ed_ids = payload.get("ed25519_key_ids") or []
    hmac_lines = [f"  {item}" for item in hmac_ids] or ["  (none)"]
    ed_lines = [f"  {item}" for item in ed_ids] or ["  (none)"]
    lines = [
        _banner(True, "Workspace keys", enabled=enabled),
        "",
        *kv_block([("Workspace", payload.get("workspace"))]),
        "",
        paint("HMAC (shared-secret; anyone with the key can forge)", "bold", enabled=enabled),
        *hmac_lines,
        "",
        paint("Ed25519 (optional extra; trust equals key custody)", "bold", enabled=enabled),
        *ed_lines,
    ]
    return "\n".join(lines) + "\n"


def _format_keygen(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    lines = [
        _banner(_strict_ok(payload), f"Key generated ({payload.get('scheme')})", enabled=enabled),
        "",
        *kv_block(
            [
                ("Scheme", payload.get("scheme")),
                ("Key id", payload.get("key_id")),
                ("Algorithm", payload.get("algorithm")),
                ("Private", payload.get("private_key_path") or payload.get("key_path")),
                ("Public", payload.get("public_key_path")),
            ]
        ),
    ]
    if payload.get("message"):
        lines.extend(["", str(payload["message"])])
    return "\n".join(lines) + "\n"


def _format_sign(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    return (
        "\n".join(
            [
                _banner(_strict_ok(payload), f"Certificate authenticated ({payload.get('scheme')})", enabled=enabled),
                "",
                *kv_block(
                    [
                        ("Scheme", payload.get("scheme")),
                        ("Key id", payload.get("key_id")),
                        ("Output", payload.get("signed_output")),
                        ("Certificate", payload.get("certificate_id")),
                        ("Receipt checked", payload.get("receipt_verified")),
                    ]
                ),
            ]
        )
        + "\n"
    )


def _format_verify_signature(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    ok = _strict_ok(payload)
    receipt_error = payload.get("receipt_verification_error")
    title = "Signature / MAC check" if ok else "Signature / MAC check failed"
    lines = [_banner(ok, title, enabled=enabled), ""]
    # Never lead with a positive MAC/schema line when overall ok is false.
    if not ok and receipt_error:
        lines.extend(
            [
                paint("Receipt error", "red", enabled=enabled),
                f"  {escape_for_terminal(str(receipt_error))}",
                "",
            ]
        )
    message = payload.get("message")
    show_message = message
    if not ok and receipt_error:
        show_message = None
    elif not ok and isinstance(message, str) and "mac valid" in message.lower():
        show_message = None
    rows: list[tuple[str, Any]] = [
        ("Scheme", payload.get("scheme")),
        ("Trusted", payload.get("trusted")),
        ("MAC valid", payload.get("mac_valid")),
        ("Signature", payload.get("signature_valid")),
        ("Receipt", payload.get("receipt_valid")),
        ("Canonical", payload.get("canonical_match")),
        ("Key id", payload.get("key_id")),
    ]
    if show_message is not None:
        rows.append(("Message", show_message))
    lines.extend(kv_block(rows))
    if payload.get("note"):
        lines.extend(["", escape_for_terminal(str(payload["note"]))])
    return "\n".join(lines) + "\n"


def _format_export_pub(payload: dict[str, Any], *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    return (
        "\n".join(
            [
                _banner(True, "Public key exported", enabled=enabled),
                "",
                *kv_block(
                    [
                        ("Key id", payload.get("key_id")),
                        ("Path", payload.get("public_key_path")),
                    ]
                ),
            ]
        )
        + "\n"
    )


def _format_generic(payload: Any, *, enabled: bool, context: dict[str, Any]) -> str:
    del context
    lines = [_banner(None, "Result", enabled=enabled), ""]
    lines.extend(_generic_lines(payload, indent=0))
    return "\n".join(lines) + "\n"


def _generic_lines(payload: Any, indent: int) -> list[str]:
    pad = "  " * (indent + 1)
    lines: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{pad}{escape_for_terminal(str(key))}:")
                lines.extend(_generic_lines(value, indent + 1))
            else:
                lines.append(f"{pad}{escape_for_terminal(str(key))}: {_scalar(value)}")
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, (dict, list)):
                lines.extend(_generic_lines(item, indent))
            else:
                lines.append(f"{pad}- {_scalar(item)}")
    else:
        lines.append(f"{pad}{_scalar(payload)}")
    return lines


def emit_result(
    payload: Any,
    *,
    pretty: bool,
    color: str = "auto",
    kind: str,
    context: dict[str, Any] | None = None,
    stream: TextIO | None = None,
    json_kwargs: dict[str, Any] | None = None,
    flush: bool = False,
) -> None:
    """Write either unchanged JSON or the opt-in human view."""
    stream = stream or sys.stdout
    if pretty:
        stream.write(
            format_pretty(
                payload,
                kind=kind,
                context=context,
                color_mode=color,
                stream=stream,
            )
        )
        if flush:
            stream.flush()
        return
    kwargs: dict[str, Any] = {"indent": 2, "sort_keys": True}
    if json_kwargs:
        kwargs = dict(json_kwargs)
        kwargs.setdefault("sort_keys", True)
    text = json.dumps(payload, **kwargs)
    stream.write(text if text.endswith("\n") else text + "\n")
    if flush:
        stream.flush()
