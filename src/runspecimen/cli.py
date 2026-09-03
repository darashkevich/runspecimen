"""CLI entrypoints for RunSpecimen."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

from runspecimen import PRODUCT_NAME, __version__
from runspecimen.approve import approve_contract
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
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace = resolve_workspace(args.workspace)

    try:
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

            check_contract_paths(contract, workspace)
            result = {
                "ok": True,
                "campaign_id": contract.campaign_id,
                "run_id": contract.run_id,
                "contract_hash": contract.contract_hash,
                "runtime": runtime_provenance(contract, workspace),
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "doctor":
            workspace_writable = os.access(str(workspace), os.W_OK)
            lease = Lease.for_workspace(workspace, holder="doctor") if workspace.is_dir() else None
            lease_held = lease.is_locked_by_other() if lease is not None else False
            lease_meta = lease.read_meta() if lease is not None and lease_held else None
            result = {
                "ok": workspace.is_dir() and workspace_writable,
                "platform": platform.platform(),
                "python": platform.python_version(),
                "workspace": str(workspace),
                "workspace_writable": workspace_writable,
                "workspace_lease_held": lease_held,
                "active_lease": lease_meta.to_dict() if lease_meta else None,
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["ok"] else 1
        parser.error(f"unknown command: {args.command}")
        return 2
    except RunSpecimenError as exc:
        print(f"{PRODUCT_NAME} error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        print(f"{PRODUCT_NAME}: interrupted; no approval was recorded", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
