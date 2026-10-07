"""CLI entrypoints for RunSpecimen."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import webbrowser
from pathlib import Path

from runspecimen import DOCS_URLS, PRODUCT_NAME, __version__
from runspecimen.approve import approve_contract
from runspecimen.bundle import write_incident_bundle
from runspecimen.certificate import verify_run_receipt
from runspecimen.contract import load_contract
from runspecimen.errors import RunSpecimenError
from runspecimen.paths import resolve_workspace
from runspecimen.postflight import postflight
from runspecimen.preflight import preflight
from runspecimen.run import run_contract
from runspecimen.status import format_status, status_for
from runspecimen.runtime import runtime_provenance
from runspecimen.lease import Lease
from runspecimen.recovery import abandon_run, check_recovery_status
from runspecimen.atomic import atomic_write_json, read_json
from runspecimen.signing import (
    SigningKey,
    list_signing_keys,
    load_signing_key,
    save_signing_key,
    sign_certificate,
    sign_certificate_file,
    verify_signed_file,
)


_ABOUT_SUMMARY = (
    "Exactly one human-approved, bounded local run at a time, with provenance "
    "binding and a tamper-evident receipt. Core lifecycle: approve → preflight → "
    "run → postflight → verify. Safety model: local TTY APPROVE (primary), optional "
    "Mac-armed remote human confirm via paired companion (not TTY-equivalent), "
    "workspace lease, hash-chained events, and certificates — evidence controls, "
    "not an OS sandbox. Plugins/agents cannot approve. The dashboard is "
    "loopback-only and read-only; it cannot approve or execute."
)


def _add_workspace(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root (all paths must stay inside)",
    )


def _add_contract(p: argparse.ArgumentParser) -> None:
    p.add_argument("--contract", type=Path, required=True, help="Path to contract JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runspecimen",
        description=(
            f"{PRODUCT_NAME}: exactly one approved bounded run with "
            "provenance binding, crash-safe state, mandatory postflight, "
            "and tamper-evident receipts."
        ),
        epilog=(
            "Docs: "
            f"About {DOCS_URLS['about']} · "
            f"User guide {DOCS_URLS['user_guide']} · "
            f"FAQ {DOCS_URLS['faq']} · "
            "or run: runspecimen about"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("about", help="Describe RunSpecimen and print documentation URLs")

    p_demo = sub.add_parser("init-demo", help="Create a fresh unapproved demo workspace")
    p_demo.add_argument("--workspace", type=Path, required=True, help="New directory to create (must not exist)")

    p_approve = sub.add_parser("approve", help="Interactively approve a contract+source binding")
    _add_workspace(p_approve)
    _add_contract(p_approve)

    p_pre = sub.add_parser("preflight", help="Refuse unsafe/stale conditions before run")
    _add_workspace(p_pre)
    _add_contract(p_pre)

    p_run = sub.add_parser("run", help="Reacquire lease, recheck, execute one bounded run")
    _add_workspace(p_run)
    _add_contract(p_run)

    p_post = sub.add_parser("postflight", help="Assert outcomes and issue certificate")
    _add_workspace(p_post)
    _add_contract(p_post)

    p_verify = sub.add_parser(
        "verify",
        help="Verify certificate, state, chain ordering, live outputs, and live provenance",
    )
    _add_workspace(p_verify)
    _add_contract(p_verify)
    p_verify.add_argument("--campaign-id", required=True)
    p_verify.add_argument("--run-id", required=True)

    p_status = sub.add_parser("status", help="Show run state, approval, lease, and chain health")
    _add_workspace(p_status)
    p_status.add_argument("--campaign-id", required=True)
    p_status.add_argument("--run-id", required=True)
    p_status.add_argument("--contract", type=Path, default=None)

    p_validate = sub.add_parser(
        "validate", help="Validate a contract, its paths, and executable provenance"
    )
    _add_workspace(p_validate)
    _add_contract(p_validate)

    p_doctor = sub.add_parser(
        "doctor", help="Check whether this host and workspace are ready"
    )
    _add_workspace(p_doctor)

    sub.add_parser(
        "isolation",
        help="Show opt-in confinement backends on this host (none is the default)",
    )

    p_dashboard = sub.add_parser(
        "dashboard", help="Open a loopback-only read-only lifecycle dashboard"
    )
    _add_workspace(p_dashboard)
    _add_contract(p_dashboard)
    p_dashboard.add_argument("--port", type=int, default=0, help="Loopback port (default: choose one)")
    p_dashboard.add_argument("--open", action="store_true", help="Open the dashboard in the default browser")

    p_companion = sub.add_parser(
        "companion",
        help="Opt-in observe + remote-human-confirm endpoint (plugins cannot approve)",
        description=(
            "Start a fail-closed companion listener for remote observation and optional "
            "Mac-armed remote human confirm (ADR-004). Requires an explicit pairing token. "
            "can_approve stays false; /v1/approve and run/preflight/postflight paths stay "
            "forbidden. Remote confirm needs a prior `remote-confirm arm` on this Mac. "
            "Default bind is loopback (HTTP + pairing token). Non-loopback --allow-lan "
            "requires a private or Tailscale address and TLS (ephemeral self-signed cert "
            "unless --tls-cert/--tls-key are provided). Cleartext remote-confirm is refused "
            "off loopback. No public internet control plane; Tailscale is recommended."
        ),
    )
    _add_workspace(p_companion)
    _add_contract(p_companion)
    p_companion.add_argument(
        "--pairing-token",
        default=None,
        help="Bearer token shared with the iOS app (auto-generated if omitted)",
    )
    p_companion.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p_companion.add_argument("--port", type=int, default=0, help="Bind port (default: choose one)")
    p_companion.add_argument(
        "--allow-lan",
        action="store_true",
        help="Allow private/link-local/Tailscale bind (requires TLS; still refuses public/unspecified)",
    )
    p_companion.add_argument(
        "--tls-cert",
        type=Path,
        default=None,
        help="PEM certificate for non-loopback binds (default: ephemeral self-signed)",
    )
    p_companion.add_argument(
        "--tls-key",
        type=Path,
        default=None,
        help="PEM private key for --tls-cert",
    )
    p_companion.add_argument(
        "--print-token",
        action="store_true",
        help="Print the pairing token once on stdout (needed when auto-generated)",
    )

    p_remote = sub.add_parser(
        "remote-confirm",
        help="Arm/cancel/refuse Mac-side remote human confirm (ADR-004)",
        description=(
            "Create, clear, or refuse a one-shot challenge for paired-companion remote "
            "human confirm. Arming requires an interactive TTY and prints the challenge "
            "only locally. Refuse consumes the pending with a typed reason and does not "
            "write approval. This is not equivalent to local TTY APPROVE. See "
            "docs/ADR-004-remote-human-confirm.md and docs/SPEC_REMOTE_CONFIRM_CARD.md."
        ),
    )
    remote_sub = p_remote.add_subparsers(dest="remote_confirm_command", required=True)
    p_rc_arm = remote_sub.add_parser("arm", help="Arm a pending remote confirm and print the challenge")
    _add_workspace(p_rc_arm)
    _add_contract(p_rc_arm)
    p_rc_arm.add_argument(
        "--ttl-sec",
        type=int,
        default=300,
        help="Challenge lifetime in seconds (30-3600, default 300)",
    )
    p_rc_status = remote_sub.add_parser("status", help="Show whether a remote confirm is pending")
    _add_workspace(p_rc_status)
    _add_contract(p_rc_status)
    p_rc_cancel = remote_sub.add_parser("cancel", help="Cancel a pending remote confirm")
    _add_workspace(p_rc_cancel)
    _add_contract(p_rc_cancel)
    p_rc_refuse = remote_sub.add_parser(
        "refuse",
        help="Consume a pending remote confirm with a typed reason (no approval)",
    )
    _add_workspace(p_rc_refuse)
    _add_contract(p_rc_refuse)
    p_rc_refuse.add_argument(
        "--challenge",
        required=True,
        help="Mac-displayed one-shot challenge (required so a stolen pairing token is not enough)",
    )
    p_rc_refuse.add_argument(
        "--reason",
        required=True,
        help="Why the pending confirm is refused (1-240 characters)",
    )

    p_bundle = sub.add_parser(
        "bundle",
        help="Export a local incident evidence pack (Community; not a Veto vault)",
        description=(
            "Copy run state, events, approval, certificate, verify output, and "
            "refusal extracts into --out. History on disk stays free. Team sharing "
            "Use retain to copy a pack outside the workspace. Never copies "
            "remote_confirm_challenge.local or pairing tokens. See "
            "docs/SPEC_INCIDENT_BUNDLE.md."
        ),
    )
    _add_workspace(p_bundle)
    p_bundle.add_argument("--campaign-id", required=True)
    p_bundle.add_argument("--run-id", required=True)
    p_bundle.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Destination directory for the incident pack",
    )
    p_bundle.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="Optional contract for live verify when the run is postflighted",
    )
    p_bundle.add_argument(
        "--chain",
        action="store_true",
        help="Nest predecessor run packs under predecessors/",
    )

    p_retain = sub.add_parser(
        "retain",
        help="Copy an incident pack to a directory outside the workspace",
        description=(
            "Same evidence pack as bundle, refused when --out is inside the "
            "workspace. Local files only: no upload, no retention service, no account."
        ),
    )
    _add_workspace(p_retain)
    p_retain.add_argument("--campaign-id", required=True)
    p_retain.add_argument("--run-id", required=True)
    p_retain.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Destination directory outside the workspace",
    )
    p_retain.add_argument("--contract", type=Path, default=None)
    p_retain.add_argument("--chain", action="store_true")

    p_digest = sub.add_parser(
        "digest",
        help="Print recorded receipt fields (does not live-verify)",
        description=(
            "Summarize a certificate already on disk. This does not check the "
            "event chain, signatures, or current provenance. Use verify for that. "
            "--live only compares output file bytes to output_digests."
        ),
    )
    _add_workspace(p_digest)
    p_digest.add_argument("--campaign-id", required=True)
    p_digest.add_argument("--run-id", required=True)
    p_digest.add_argument(
        "--live",
        action="store_true",
        help="Also compare current output files to recorded output digests",
    )

    p_diff = sub.add_parser(
        "diff",
        help="Compare two recorded receipts in one workspace",
        description=(
            "Print a field diff of two certificates. Differences are reported "
            "with exit status 0. A missing certificate is an error. This is not verify."
        ),
    )
    _add_workspace(p_diff)
    p_diff.add_argument("--campaign-id", required=True)
    p_diff.add_argument("--run-id", required=True)
    p_diff.add_argument("--against-campaign-id", required=True)
    p_diff.add_argument("--against-run-id", required=True)

    p_abandon = sub.add_parser(
        "abandon",
        help="Abandon a crashed run after TTY confirmation (marks run as failed)",
    )
    _add_workspace(p_abandon)
    p_abandon.add_argument("--campaign-id", required=True)
    p_abandon.add_argument("--run-id", required=True)
    p_abandon.add_argument("--reason", default="", help="Optional reason for abandonment")

    p_recovery_status = sub.add_parser(
        "recovery-status",
        help="Check if a run needs recovery (crashed mid-execution)",
    )
    _add_workspace(p_recovery_status)
    p_recovery_status.add_argument("--campaign-id", required=True)
    p_recovery_status.add_argument("--run-id", required=True)

    p_keygen = sub.add_parser(
        "keygen",
        help="Generate a receipt authentication or signing key",
        description=(
            "Generate a key for receipt authentication. "
            "Default --scheme hmac is a shared-secret MAC (anyone with the key can "
            "forge). --scheme ed25519 requires optional 'runspecimen[ed25519]' and "
            "produces a private/public key pair for offline public-key verification. "
            "Neither scheme proves scientific claims; Ed25519 trust equals key custody."
        ),
    )
    _add_workspace(p_keygen)
    p_keygen.add_argument("--key-id", default=None, help="Optional key ID (auto-generated if omitted)")
    p_keygen.add_argument(
        "--scheme",
        choices=("hmac", "ed25519"),
        default="hmac",
        help="hmac (default, stdlib) or ed25519 (optional PyNaCl extra)",
    )
    p_keygen.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow rotating/replacing an existing Ed25519 key id",
    )

    p_list_keys = sub.add_parser(
        "list-keys",
        help="List available authentication/signing keys in the workspace",
    )
    _add_workspace(p_list_keys)
    p_list_keys.add_argument(
        "--scheme",
        choices=("hmac", "ed25519", "all"),
        default="all",
        help="Filter listed keys (default: all)",
    )

    p_export_pub = sub.add_parser(
        "export-public-key",
        help="Export an Ed25519 public key for offline verification",
        description=(
            "Write the hex-encoded Ed25519 public key for a workspace key id. "
            "Requires the optional ed25519 extra."
        ),
    )
    _add_workspace(p_export_pub)
    p_export_pub.add_argument("--key-id", required=True)
    p_export_pub.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination path inside the workspace for the .pub hex file",
    )

    p_sign = sub.add_parser(
        "sign",
        help="Authenticate or sign a certificate (HMAC MAC or Ed25519)",
        description=(
            "Authenticate (HMAC) or sign (Ed25519) a certificate that matches the "
            "canonical receipt after live provenance checks. "
            "HMAC is shared-secret only. Ed25519 enables offline public-key verify "
            "without sharing the private key (optional dependency)."
        ),
    )
    _add_workspace(p_sign)
    p_sign.add_argument("--key-id", required=True, help="ID of the key to use")
    p_sign.add_argument("--certificate", type=Path, required=True, help="Path to certificate.json")
    p_sign.add_argument("--contract", type=Path, required=True, help="Path to contract.json for live provenance verification")
    p_sign.add_argument("--output", type=Path, default=None, help="Output path (default depends on scheme)")
    p_sign.add_argument(
        "--scheme",
        choices=("hmac", "ed25519"),
        default="hmac",
        help="hmac (default) or ed25519",
    )

    p_verify_sig = sub.add_parser(
        "verify-signature",
        help="Verify an HMAC MAC or Ed25519 signature on a certificate",
        description=(
            "Verify HMAC authentication or an Ed25519 signature. "
            "For Ed25519, pass --public-key for fully offline verify without the "
            "private key (still optionally re-check the live receipt with --contract)."
        ),
    )
    _add_workspace(p_verify_sig)
    p_verify_sig.add_argument("--key-id", default=None, help="Workspace key id (HMAC required; Ed25519 optional if --public-key set)")
    p_verify_sig.add_argument("--signed", type=Path, required=True, help="Path to authenticated/signed certificate file")
    p_verify_sig.add_argument("--contract", type=Path, default=None, help="Contract for live provenance (required for hmac; optional for ed25519 offline)")
    p_verify_sig.add_argument(
        "--scheme",
        choices=("hmac", "ed25519"),
        default="hmac",
        help="hmac (default) or ed25519",
    )
    p_verify_sig.add_argument(
        "--public-key",
        type=Path,
        default=None,
        help="Ed25519 public key file (hex) for offline verify without private key",
    )

    from runspecimen.cli_expansion import register_expansion_parsers

    register_expansion_parsers(sub)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "about":
        print(
            json.dumps(
                {
                    "product": PRODUCT_NAME,
                    "version": __version__,
                    "summary": _ABOUT_SUMMARY,
                    "lifecycle": [
                        "approve",
                        "preflight",
                        "run",
                        "postflight",
                        "verify",
                    ],
                    "docs": dict(DOCS_URLS),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "isolation":
        from runspecimen.isolation import host_capabilities

        print(json.dumps(host_capabilities(), indent=2, sort_keys=True))
        return 0

    # Expansion command groups own --workspace parsing differently for some
    # subcommands (e.g. coordination validate). Handle before requiring workspace.
    from runspecimen.cli_expansion import handle_expansion

    if args.command in {
        "requirements",
        "freshness",
        "config",
        "decisions",
        "snapshot",
        "usage",
        "coordination",
        "eval",
        "scenes",
    }:
        # coordination validate/readiness may omit workspace; resolve when present
        ws = resolve_workspace(getattr(args, "workspace", Path.cwd()))
        try:
            code = handle_expansion(args, ws)
        except RunSpecimenError as exc:
            print(f"{PRODUCT_NAME} error: {exc}", file=sys.stderr)
            return 1
        if code is not None:
            return code

    workspace = resolve_workspace(args.workspace)

    try:
        if args.command == "init-demo":
            from runspecimen.demo import init_demo

            print(json.dumps(init_demo(workspace), indent=2, sort_keys=True))
            return 0
        if args.command == "approve":
            doc = approve_contract(contract_path=args.contract, workspace=workspace)
            print(json.dumps({"ok": True, "approval": doc}, indent=2, sort_keys=True))
            return 0
        if args.command == "preflight":
            result = preflight(contract_path=args.contract, workspace=workspace)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "run":
            result = run_contract(contract_path=args.contract, workspace=workspace)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "postflight":
            cert = postflight(contract_path=args.contract, workspace=workspace)
            print(json.dumps({"ok": True, "certificate": cert}, indent=2, sort_keys=True))
            return 0
        if args.command == "verify":
            contract = load_contract(args.contract)
            if contract.campaign_id != args.campaign_id or contract.run_id != args.run_id:
                raise RunSpecimenError(
                    "campaign-id/run-id flags do not match contract identity"
                )
            result = verify_run_receipt(
                workspace=workspace,
                campaign_id=args.campaign_id,
                run_id=args.run_id,
                contract=contract,
                require_live_provenance=True,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "status":
            if args.contract is not None:
                c = load_contract(args.contract)
                if c.campaign_id != args.campaign_id or c.run_id != args.run_id:
                    raise RunSpecimenError(
                        "campaign-id/run-id flags do not match contract identity"
                    )
            doc = status_for(
                workspace=workspace,
                campaign_id=args.campaign_id,
                run_id=args.run_id,
                contract_path=args.contract,
            )
            print(format_status(doc))
            return 0
        if args.command == "validate":
            contract = load_contract(args.contract)
            from runspecimen.contract import check_contract_paths
            from runspecimen.policy import execution_constraints

            check_contract_paths(contract, workspace)
            isolation, policy = execution_constraints(contract, workspace)
            result = {
                "ok": True,
                "campaign_id": contract.campaign_id,
                "run_id": contract.run_id,
                "contract_hash": contract.contract_hash,
                "runtime": runtime_provenance(contract, workspace),
                "isolation": isolation,
                "policy": policy,
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "doctor":
            from runspecimen.configsync import inspect_environment

            result = inspect_environment(workspace=workspace)
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            return 0 if result.get("ok") else 1
        if args.command == "dashboard":
            if not 0 <= args.port <= 65535:
                raise RunSpecimenError("dashboard port must be between 0 and 65535")
            from runspecimen.dashboard import start_dashboard

            server, url = start_dashboard(
                workspace=workspace, contract_path=args.contract, port=args.port
            )
            print(json.dumps({"ok": True, "url": url, "loopback_only": True}, sort_keys=True), flush=True)
            try:
                if args.open:
                    webbrowser.open(url)
                server.serve_forever()
            finally:
                server.server_close()
            return 0
        if args.command == "remote-confirm":
            from runspecimen.paths import run_state_dir
            from runspecimen.remote_confirm import (
                arm_remote_confirm,
                cancel_remote_confirm,
                load_pending,
                public_pending_view,
                read_local_challenge_for_display,
                refuse_remote_confirm,
            )

            if args.remote_confirm_command == "arm":
                meta = arm_remote_confirm(
                    contract_path=args.contract,
                    workspace=workspace,
                    ttl_sec=int(args.ttl_sec),
                )
                print(json.dumps(meta, indent=2, sort_keys=True))
                return 0
            if args.remote_confirm_command == "cancel":
                print(json.dumps(cancel_remote_confirm(contract_path=args.contract, workspace=workspace), indent=2, sort_keys=True))
                return 0
            if args.remote_confirm_command == "refuse":
                refused = refuse_remote_confirm(
                    contract_path=args.contract,
                    workspace=workspace,
                    challenge=str(args.challenge),
                    reason=str(args.reason),
                )
                print(json.dumps(refused, indent=2, sort_keys=True))
                return 0
            if args.remote_confirm_command == "status":
                contract = load_contract(args.contract)
                state_dir = run_state_dir(workspace, contract.campaign_id, contract.run_id)
                pending = load_pending(state_dir)
                view = public_pending_view(pending)
                local_challenge = read_local_challenge_for_display(state_dir) if view.get("pending") else None
                out = dict(view)
                if local_challenge is not None:
                    # Local CLI status may show the challenge for the Mac operator only.
                    out["local_challenge"] = local_challenge
                    out["local_only_note"] = (
                        "local_challenge is printed for Mac display only; "
                        "companion HTTP never returns this secret."
                    )
                print(json.dumps(out, indent=2, sort_keys=True))
                return 0
            raise RunSpecimenError(f"unknown remote-confirm command: {args.remote_confirm_command}")
        if args.command == "bundle":
            manifest = write_incident_bundle(
                workspace=workspace,
                campaign_id=args.campaign_id,
                run_id=args.run_id,
                out_dir=args.out,
                contract_path=args.contract,
                include_chain=bool(args.chain),
            )
            print(json.dumps(manifest, indent=2, sort_keys=True, default=str))
            return 0
        if args.command == "retain":
            from runspecimen.bundle import retain_incident_bundle

            manifest = retain_incident_bundle(
                workspace=workspace,
                campaign_id=args.campaign_id,
                run_id=args.run_id,
                out_dir=args.out,
                contract_path=args.contract,
                include_chain=bool(args.chain),
            )
            print(json.dumps(manifest, indent=2, sort_keys=True, default=str))
            return 0
        if args.command == "digest":
            from runspecimen.digest import live_output_rows, load_recorded_receipt, summarize_receipt

            cert = load_recorded_receipt(workspace, args.campaign_id, args.run_id)
            summary = summarize_receipt(cert)
            if args.live:
                summary["live_outputs"] = live_output_rows(workspace, cert)
                summary["note"] = (
                    "Recorded certificate fields, plus a byte compare of output_digests "
                    "to current files. This is not runspecimen verify."
                )
            print(json.dumps(summary, indent=2, sort_keys=True, default=str))
            return 0
        if args.command == "diff":
            from runspecimen.digest import diff_summaries, load_recorded_receipt, summarize_receipt

            left = summarize_receipt(load_recorded_receipt(workspace, args.campaign_id, args.run_id))
            right = summarize_receipt(
                load_recorded_receipt(workspace, args.against_campaign_id, args.against_run_id)
            )
            print(json.dumps(diff_summaries(left, right), indent=2, sort_keys=True, default=str))
            return 0
        if args.command == "companion":
            from runspecimen.companion import generate_pairing_token, start_companion
            from runspecimen.companion_attention import notify_attention_requested

            token = args.pairing_token or generate_pairing_token()
            if args.pairing_token is None and not args.print_token:
                raise RunSpecimenError(
                    "companion auto-generated a pairing token; re-run with --print-token "
                    "to display it, or pass --pairing-token explicitly"
                )

            def _on_attention(entry: dict) -> None:
                note = notify_attention_requested(message=str(entry.get("message") or ""))
                print(
                    json.dumps({"event": "attention", **entry, "notification": note}, sort_keys=True),
                    flush=True,
                )

            def _on_open_dashboard() -> None:
                from runspecimen.dashboard import start_dashboard

                dash_server, dash_url = start_dashboard(
                    workspace=workspace, contract_path=args.contract, port=0
                )

                def _serve() -> None:
                    try:
                        webbrowser.open(dash_url)
                        dash_server.serve_forever()
                    finally:
                        dash_server.server_close()

                import threading

                threading.Thread(target=_serve, name="rs-companion-dashboard", daemon=True).start()
                print(
                    json.dumps(
                        {
                            "event": "open-dashboard",
                            "url": dash_url,
                            "loopback_only": True,
                            "mutates_lifecycle": False,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )

            def _on_remote_confirmed(approval: dict) -> None:
                print(
                    json.dumps(
                        {
                            "event": "remote-confirm-settled",
                            "confirm_channel": approval.get("confirm_channel"),
                            "campaign_id": approval.get("campaign_id"),
                            "run_id": approval.get("run_id"),
                            "not_equivalent_to": "local_tty_approve",
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )

            server, url, meta = start_companion(
                workspace=workspace,
                contract_path=args.contract,
                pairing_token=token,
                host=args.host,
                port=args.port,
                allow_lan=bool(args.allow_lan),
                tls_cert=args.tls_cert,
                tls_key=args.tls_key,
                on_attention=_on_attention,
                on_open_dashboard=_on_open_dashboard,
                on_remote_confirmed=_on_remote_confirmed,
            )
            payload = dict(meta)
            if args.print_token:
                payload["pairing_token"] = token
            print(json.dumps(payload, sort_keys=True), flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()
            return 0
        if args.command == "abandon":
            result = abandon_run(
                workspace=workspace,
                campaign_id=args.campaign_id,
                run_id=args.run_id,
                reason=args.reason,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "recovery-status":
            result = check_recovery_status(
                workspace=workspace,
                campaign_id=args.campaign_id,
                run_id=args.run_id,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if not result.get("needs_recovery") else 1
        if args.command == "keygen":
            if getattr(args, "scheme", "hmac") == "ed25519":
                from runspecimen.pubkey import Ed25519KeyPair, save_ed25519_keypair

                pair = Ed25519KeyPair.generate(key_id=args.key_id)
                priv, pub = save_ed25519_keypair(
                    workspace, pair, overwrite=bool(getattr(args, "overwrite", False))
                )
                result = {
                    "ok": True,
                    "scheme": "ed25519",
                    "key_id": pair.key_id,
                    "algorithm": pair.algorithm,
                    "private_key_path": str(priv),
                    "public_key_path": str(pub),
                    "message": (
                        "Ed25519 key pair generated. Keep the private .ed25519 file secret; "
                        "distribute only the .ed25519.pub file for offline verify. "
                        "Trust equals key custody — not absolute non-repudiation."
                    ),
                }
                print(json.dumps(result, indent=2, sort_keys=True))
                return 0
            key = SigningKey.generate(key_id=args.key_id)
            key_path = save_signing_key(workspace, key)
            result = {
                "ok": True,
                "scheme": "hmac",
                "key_id": key.key_id,
                "algorithm": key.algorithm,
                "key_path": str(key_path),
                "message": "HMAC key generated; keep the .key file secure (shared-secret MAC)",
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "list-keys":
            from runspecimen.pubkey import list_ed25519_key_ids

            scheme = getattr(args, "scheme", "all")
            hmac_ids = list_signing_keys(workspace) if scheme in ("hmac", "all") else []
            ed_ids = list_ed25519_key_ids(workspace) if scheme in ("ed25519", "all") else []
            result = {
                "ok": True,
                "workspace": str(workspace),
                "hmac_key_ids": hmac_ids,
                "ed25519_key_ids": ed_ids,
                "key_ids": hmac_ids if scheme != "ed25519" else ed_ids,
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "export-public-key":
            from runspecimen.pubkey import export_ed25519_public_key

            output_path = args.output.resolve()
            try:
                output_path.relative_to(workspace)
            except ValueError:
                print(f"{PRODUCT_NAME} error: --output must be inside the workspace", file=sys.stderr)
                return 1
            path_out = export_ed25519_public_key(workspace, args.key_id, output_path)
            print(json.dumps({"ok": True, "key_id": args.key_id, "public_key_path": str(path_out)}, indent=2, sort_keys=True))
            return 0
        if args.command == "sign":
            from runspecimen.errors import CertificateError
            from runspecimen.certificate import load_certificate
            from runspecimen.paths import run_state_dir
            from runspecimen.hashutil import canonical_json_bytes

            cert_path = args.certificate.resolve()
            try:
                cert_path.relative_to(workspace)
            except ValueError:
                print(f"{PRODUCT_NAME} error: --certificate must be inside the workspace", file=sys.stderr)
                return 1

            cert = read_json(cert_path)
            if not isinstance(cert, dict):
                print(f"{PRODUCT_NAME} error: certificate file must be a JSON object", file=sys.stderr)
                return 1

            campaign_id = cert.get("campaign_id")
            run_id = cert.get("run_id")
            if not campaign_id or not run_id:
                print(f"{PRODUCT_NAME} error: certificate missing campaign_id or run_id", file=sys.stderr)
                return 1

            if not args.contract:
                print(f"{PRODUCT_NAME} error: --contract is required for sign command", file=sys.stderr)
                return 1
            contract = load_contract(args.contract)

            try:
                verify_run_receipt(
                    workspace=workspace,
                    campaign_id=str(campaign_id),
                    run_id=str(run_id),
                    require_live_provenance=True,
                    contract=contract,
                )
            except CertificateError as e:
                print(f"{PRODUCT_NAME} error: receipt verification failed: {e}", file=sys.stderr)
                return 1

            state_dir = run_state_dir(workspace, str(campaign_id), str(run_id))
            canonical_cert = load_certificate(state_dir)
            if canonical_cert is None:
                print(f"{PRODUCT_NAME} error: canonical certificate not found in state directory", file=sys.stderr)
                return 1

            if canonical_json_bytes(cert) != canonical_json_bytes(canonical_cert):
                print(f"{PRODUCT_NAME} error: supplied certificate does not match canonical receipt", file=sys.stderr)
                print(f"  certificate_id supplied: {cert.get('certificate_id')}", file=sys.stderr)
                print(f"  certificate_id canonical: {canonical_cert.get('certificate_id')}", file=sys.stderr)
                return 1

            scheme = getattr(args, "scheme", "hmac")
            output_path = args.output
            if scheme == "ed25519":
                from runspecimen.pubkey import load_ed25519_keypair, sign_certificate_ed25519

                pair = load_ed25519_keypair(workspace, args.key_id)
                if output_path is None:
                    output_path = cert_path.parent / f"{cert_path.stem}.ed25519.json"
                output_path = output_path.resolve()
                try:
                    output_path.relative_to(workspace)
                except ValueError:
                    print(f"{PRODUCT_NAME} error: --output must be inside the workspace", file=sys.stderr)
                    return 1
                signed = sign_certificate_ed25519(canonical_cert, pair)
                atomic_write_json(output_path, signed.to_dict())
                print(json.dumps({
                    "ok": True,
                    "scheme": "ed25519",
                    "certificate": str(cert_path),
                    "signed_output": str(output_path),
                    "key_id": pair.key_id,
                    "algorithm": pair.algorithm,
                    "public_key": pair.public_hex(),
                    "receipt_verified": True,
                    "certificate_id": canonical_cert.get("certificate_id"),
                }, indent=2, sort_keys=True))
                return 0

            key = load_signing_key(workspace, args.key_id)
            if output_path is None:
                output_path = cert_path.parent / f"{cert_path.stem}.signed.json"
            output_path = output_path.resolve()
            try:
                output_path.relative_to(workspace)
            except ValueError:
                print(f"{PRODUCT_NAME} error: --output must be inside the workspace", file=sys.stderr)
                return 1
            signed = sign_certificate(canonical_cert, key)
            atomic_write_json(output_path, signed.to_dict())
            print(json.dumps({
                "ok": True,
                "scheme": "hmac",
                "certificate": str(cert_path),
                "signed_output": str(output_path),
                "key_id": key.key_id,
                "algorithm": key.algorithm,
                "receipt_verified": True,
                "certificate_id": canonical_cert.get("certificate_id"),
            }, indent=2, sort_keys=True))
            return 0
        if args.command == "verify-signature":
            from runspecimen.errors import CertificateError
            from runspecimen.signing import verify_signature, SignedCertificate
            from runspecimen.certificate import load_certificate
            from runspecimen.paths import run_state_dir
            from runspecimen.hashutil import canonical_json_bytes

            signed_path = args.signed.resolve()
            try:
                signed_path.relative_to(workspace)
            except ValueError:
                print(f"{PRODUCT_NAME} error: --signed must be inside the workspace", file=sys.stderr)
                return 1

            scheme = getattr(args, "scheme", "hmac")
            if scheme == "ed25519":
                from runspecimen.pubkey import (
                    Ed25519SignedCertificate,
                    load_ed25519_public_key_file,
                    public_key_path,
                    verify_certificate_ed25519,
                    verify_rejects_hmac_blob,
                )

                if not signed_path.exists():
                    print(json.dumps({
                        "ok": False,
                        "scheme": "ed25519",
                        "message": f"signed file not found: {signed_path}",
                    }, indent=2, sort_keys=True))
                    return 1
                try:
                    data = read_json(signed_path)
                    verify_rejects_hmac_blob(data)
                    signed_cert = Ed25519SignedCertificate.from_dict(data)
                except Exception as e:
                    print(json.dumps({
                        "ok": False,
                        "scheme": "ed25519",
                        "message": f"failed to parse Ed25519 signed file: {e}",
                    }, indent=2, sort_keys=True))
                    return 1

                # Trusted verify requires an external trust anchor — never the
                # attacker-controlled embedded public key alone.
                pub_bytes = None
                if args.public_key is not None:
                    pub_path = args.public_key.resolve()
                    try:
                        pub_path.relative_to(workspace)
                    except ValueError:
                        print(f"{PRODUCT_NAME} error: --public-key must be inside the workspace", file=sys.stderr)
                        return 1
                    pub_bytes = load_ed25519_public_key_file(pub_path)
                elif args.key_id:
                    pub_bytes = load_ed25519_public_key_file(public_key_path(workspace, args.key_id))
                else:
                    print(json.dumps({
                        "ok": False,
                        "scheme": "ed25519",
                        "trusted": False,
                        "signature_consistent": False,
                        "message": (
                            "trusted Ed25519 verify requires --public-key or --key-id "
                            "(embedded receipt public key alone is not a trust anchor)"
                        ),
                    }, indent=2, sort_keys=True))
                    return 1

                ver_result = verify_certificate_ed25519(signed_cert, public_key=pub_bytes)
                result = {
                    "ok": ver_result.ok,
                    "scheme": "ed25519",
                    "trusted": ver_result.trusted,
                    "signature_consistent": ver_result.signature_consistent,
                    "signature_valid": ver_result.signature_valid,
                    "schema_valid": ver_result.schema_valid,
                    "certificate_id_valid": ver_result.certificate_id_valid,
                    "public_key_match": ver_result.public_key_match,
                    "message": ver_result.message,
                    "signed_file": str(signed_path),
                    "key_id": signed_cert.key_id,
                    "algorithm": signed_cert.algorithm,
                    "offline": args.contract is None,
                    "note": (
                        "Trusted Ed25519 verify uses an external public key; "
                        "embedded-key-only consistency is never ok:true. "
                        "Does not prove scientific claims or absolute non-repudiation."
                    ),
                }
                if args.contract is not None and ver_result.ok:
                    contract = load_contract(args.contract)
                    cert = signed_cert.certificate
                    try:
                        verify_run_receipt(
                            workspace=workspace,
                            campaign_id=str(cert["campaign_id"]),
                            run_id=str(cert["run_id"]),
                            require_live_provenance=True,
                            contract=contract,
                        )
                        state_dir = run_state_dir(workspace, str(cert["campaign_id"]), str(cert["run_id"]))
                        canonical = load_certificate(state_dir)
                        if canonical is None or canonical_json_bytes(cert) != canonical_json_bytes(canonical):
                            result["ok"] = False
                            result["receipt_valid"] = False
                            result["message"] = "signature ok but signed certificate does not match canonical receipt"
                        else:
                            result["receipt_valid"] = True
                    except CertificateError as e:
                        result["ok"] = False
                        result["receipt_valid"] = False
                        result["message"] = f"signature ok but live receipt check failed: {e}"
                print(json.dumps(result, indent=2, sort_keys=True))
                return 0 if result["ok"] else 1

            if not args.key_id:
                print(f"{PRODUCT_NAME} error: --key-id is required for --scheme hmac", file=sys.stderr)
                return 1
            if not args.contract:
                print(f"{PRODUCT_NAME} error: --contract is required for verify-signature --scheme hmac", file=sys.stderr)
                return 1
            contract = load_contract(args.contract)
            key = load_signing_key(workspace, args.key_id)

            if not signed_path.exists():
                result = {
                    "ok": False,
                    "scheme": "hmac",
                    "mac_valid": False,
                    "schema_valid": False,
                    "receipt_valid": False,
                    "canonical_match": False,
                    "message": f"signed file not found: {signed_path}",
                }
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1

            try:
                data = read_json(signed_path)
                if isinstance(data, dict) and data.get("algorithm") == "ed25519-v1":
                    print(
                        f"{PRODUCT_NAME} error: refusing to HMAC-verify an Ed25519 signed blob; "
                        f"use --scheme ed25519",
                        file=sys.stderr,
                    )
                    return 1
                signed_cert = SignedCertificate.from_dict(data)
            except Exception as e:
                result = {
                    "ok": False,
                    "scheme": "hmac",
                    "mac_valid": False,
                    "schema_valid": False,
                    "receipt_valid": False,
                    "canonical_match": False,
                    "message": f"failed to parse signed file: {e}",
                }
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1

            ver_result = verify_signature(signed_cert, key)
            result = {
                "ok": False,
                "scheme": "hmac",
                "mac_valid": ver_result.mac_valid,
                "schema_valid": ver_result.schema_valid,
                "certificate_id_valid": ver_result.certificate_id_valid,
                "receipt_valid": False,
                "canonical_match": False,
                "signed_file": str(signed_path),
                "key_id": args.key_id,
                "message": ver_result.message,
            }

            if not ver_result.mac_valid:
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1

            cert = signed_cert.certificate
            campaign_id = cert.get("campaign_id")
            run_id = cert.get("run_id")
            if not campaign_id or not run_id:
                result["message"] = "certificate missing campaign_id or run_id"
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1

            state_dir = run_state_dir(workspace, str(campaign_id), str(run_id))
            canonical_cert = load_certificate(state_dir)
            if canonical_cert is None:
                result["message"] = "canonical certificate not found in state directory"
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1

            if canonical_json_bytes(cert) != canonical_json_bytes(canonical_cert):
                result["message"] = (
                    f"signed certificate does not match canonical receipt; "
                    f"signed_cert_id={cert.get('certificate_id')}, "
                    f"canonical_cert_id={canonical_cert.get('certificate_id')}"
                )
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1

            result["canonical_match"] = True
            try:
                verify_run_receipt(
                    workspace=workspace,
                    campaign_id=str(campaign_id),
                    run_id=str(run_id),
                    require_live_provenance=True,
                    contract=contract,
                )
                result["receipt_valid"] = True
            except CertificateError as e:
                result["receipt_verification_error"] = str(e)
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1

            if ver_result.ok and result["receipt_valid"] and result["canonical_match"]:
                result["certificate_id"] = cert.get("certificate_id")
                result["ok"] = True
                result["message"] = (
                    "MAC valid, certificate matches canonical receipt, live provenance verified"
                )

            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["ok"] else 1
        parser.error(f"unknown command: {args.command}")
        return 2
    except RunSpecimenError as exc:
        print(f"{PRODUCT_NAME} error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"{PRODUCT_NAME} error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"{PRODUCT_NAME}: {args.command} interrupted; inspect status before continuing", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
