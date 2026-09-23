"""CLI parsers and handlers for ADR-005 evidence expansion commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from runspecimen.contract import load_contract
from runspecimen.errors import RunSpecimenError


def register_expansion_parsers(sub: Any) -> None:
    # requirements
    p_req = sub.add_parser(
        "requirements",
        help="Validate/run task manifests and emit evidence reports (not verify)",
    )
    req_sub = p_req.add_subparsers(dest="requirements_command", required=True)
    p_req_val = req_sub.add_parser("validate", help="Validate a task manifest")
    p_req_val.add_argument("--manifest", type=Path, required=True)
    p_req_check = req_sub.add_parser(
        "check",
        help="Run configured checks; write evidence report (provider-collected only)",
    )
    _ws(p_req_check)
    p_req_check.add_argument("--contract", type=Path, required=True)
    p_req_check.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Task manifest (defaults to contract.task_manifest.path when bound)",
    )
    p_req_check.add_argument(
        "--write-attestation",
        action="store_true",
        help="Also write a linked evidence_attestation digest document",
    )
    p_req_rep = req_sub.add_parser("report", help="Show stored evidence report + CI summary")
    _ws(p_req_rep)
    p_req_rep.add_argument("--campaign-id", required=True)
    p_req_rep.add_argument("--run-id", required=True)

    # freshness
    p_fr = sub.add_parser(
        "freshness",
        help="Evaluate evidence applicability (separate from verify)",
    )
    fr_sub = p_fr.add_subparsers(dest="freshness_command", required=True)
    p_fr_check = fr_sub.add_parser("check", help="On-demand freshness / applicability")
    _ws(p_fr_check)
    p_fr_check.add_argument("--contract", type=Path, required=True)
    p_fr_check.add_argument("--manifest", type=Path, default=None)

    # config
    p_cfg = sub.add_parser(
        "config",
        help="Inspect/preview/apply/export versioned config bundles (never silent)",
    )
    cfg_sub = p_cfg.add_subparsers(dest="config_command", required=True)
    p_cfg_ins = cfg_sub.add_parser("inspect", help="Same diagnostics surface as doctor+bundle")
    _ws(p_cfg_ins)
    p_cfg_prev = cfg_sub.add_parser("preview", help="Preview applying a config bundle")
    _ws(p_cfg_prev)
    p_cfg_prev.add_argument("--bundle", type=Path, required=True)
    p_cfg_apply = cfg_sub.add_parser("apply", help="Atomically apply a config bundle with backup")
    _ws(p_cfg_apply)
    p_cfg_apply.add_argument("--bundle", type=Path, required=True)
    p_cfg_exp = cfg_sub.add_parser("export", help="Export active bundle (secrets excluded)")
    _ws(p_cfg_exp)
    p_cfg_exp.add_argument("--out", type=Path, required=True)
    p_cfg_rb = cfg_sub.add_parser("rollback", help="Restore active bundle from a backup file")
    _ws(p_cfg_rb)
    p_cfg_rb.add_argument("--backup", type=Path, required=True)

    # decisions
    p_dec = sub.add_parser("decisions", help="Explicit decision provenance registry")
    dec_sub = p_dec.add_subparsers(dest="decisions_command", required=True)
    p_dec_cap = dec_sub.add_parser("capture", help="Capture a decision (explicit only)")
    _ws(p_dec_cap)
    p_dec_cap.add_argument("--id", required=True)
    p_dec_cap.add_argument("--rationale", required=True)
    p_dec_cap.add_argument("--classification", choices=("human", "agent"), required=True)
    p_dec_cap.add_argument("--source-ref", action="append", default=[])
    p_dec_cap.add_argument("--affected-requirement", action="append", default=[])
    p_dec_cap.add_argument("--affected-file", action="append", default=[])
    p_dec_cap.add_argument("--supersedes", default=None)
    p_dec_list = dec_sub.add_parser("list", help="List decisions")
    _ws(p_dec_list)
    p_dec_search = dec_sub.add_parser("search", help="Search decisions")
    _ws(p_dec_search)
    p_dec_search.add_argument("--query", required=True)
    p_dec_show = dec_sub.add_parser("show", help="Show one decision")
    _ws(p_dec_show)
    p_dec_show.add_argument("--id", required=True)
    p_dec_flags = dec_sub.add_parser("review-flags", help="Flag decisions with changed inputs")
    _ws(p_dec_flags)

    # snapshot
    p_snap = sub.add_parser(
        "snapshot",
        help="Local verifiable snapshots (restore defaults to a separate directory)",
    )
    snap_sub = p_snap.add_subparsers(dest="snapshot_command", required=True)
    p_snap_c = snap_sub.add_parser("create", help="Create a local_tar snapshot of source roots")
    _ws(p_snap_c)
    p_snap_c.add_argument("--id", required=True)
    p_snap_c.add_argument("--contract", type=Path, required=True)
    p_snap_p = snap_sub.add_parser("preview-restore", help="Preview restore without writing")
    _ws(p_snap_p)
    p_snap_p.add_argument("--id", required=True)
    p_snap_p.add_argument(
        "--dest",
        type=Path,
        required=True,
        help="Destination directory (use a path outside the workspace)",
    )
    p_snap_r = snap_sub.add_parser("restore", help="Restore archive to a separate directory")
    _ws(p_snap_r)
    p_snap_r.add_argument("--id", required=True)
    p_snap_r.add_argument("--dest", type=Path, required=True)
    p_snap_cmp = snap_sub.add_parser("compare", help="Compare snapshot source hash to workspace")
    _ws(p_snap_cmp)
    p_snap_cmp.add_argument("--id", required=True)

    # usage
    p_usage = sub.add_parser(
        "usage",
        help="Import/summarize external usage (unknown stays unknown; no hard enforcement)",
    )
    usage_sub = p_usage.add_subparsers(dest="usage_command", required=True)
    p_u_imp = usage_sub.add_parser("import", help="Idempotent import from a documented export")
    _ws(p_u_imp)
    p_u_imp.add_argument("--provider", default="local_json")
    p_u_imp.add_argument("--export", type=Path, required=True)
    p_u_sum = usage_sub.add_parser("summarize", help="Summaries by provider/task/campaign/project")
    _ws(p_u_sum)

    # coordination
    p_coord = sub.add_parser(
        "coordination",
        help="Bounded multi-repo readiness (two-repo first slice; no auto-merge)",
    )
    coord_sub = p_coord.add_subparsers(dest="coordination_command", required=True)
    p_c_val = coord_sub.add_parser("validate", help="Validate a coordination plan")
    p_c_val.add_argument("--plan", type=Path, required=True)
    p_c_ready = coord_sub.add_parser("readiness", help="Aggregate readiness from evidence")
    p_c_ready.add_argument("--plan", type=Path, required=True)

    # eval
    p_eval = sub.add_parser(
        "eval",
        help="Workflow regression evaluation (local deterministic suite)",
    )
    eval_sub = p_eval.add_subparsers(dest="eval_command", required=True)
    p_e_run = eval_sub.add_parser("run", help="Run an eval suite in disposable workspaces")
    _ws(p_e_run)
    p_e_run.add_argument("--suite", type=Path, required=True)
    p_e_cmp = eval_sub.add_parser("compare", help="Compare baseline vs candidate eval results")
    p_e_cmp.add_argument("--baseline", type=Path, required=True)
    p_e_cmp.add_argument("--candidate", type=Path, required=True)

    # scenes (ten-scene local demo harness)
    p_scenes = sub.add_parser(
        "scenes",
        help="Run the local ten-scene evidence demo (never types APPROVE)",
    )
    _ws(p_scenes)
    p_scenes.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only materialize fixtures and print human APPROVE instructions",
    )


def _ws(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root",
    )


def handle_expansion(args: argparse.Namespace, workspace: Path) -> int | None:
    """Return exit code if handled, or None to fall through."""
    cmd = args.command
    if cmd == "requirements":
        return _requirements(args, workspace)
    if cmd == "freshness":
        return _freshness(args, workspace)
    if cmd == "config":
        return _config(args, workspace)
    if cmd == "decisions":
        return _decisions(args, workspace)
    if cmd == "snapshot":
        return _snapshot(args, workspace)
    if cmd == "usage":
        return _usage(args, workspace)
    if cmd == "coordination":
        return _coordination(args)
    if cmd == "eval":
        return _eval(args, workspace)
    if cmd == "scenes":
        from runspecimen.scenes import run_scenes

        result = run_scenes(workspace=workspace, prepare_only=bool(args.prepare_only))
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result.get("ok") else 1
    return None


def _requirements(args: argparse.Namespace, workspace: Path) -> int:
    from runspecimen.requirements import (
        AuthorizationError,
        build_evidence_attestation,
        ci_machine_report,
        load_evidence_report,
        load_task_manifest,
        run_requirements,
        write_evidence_attestation,
        write_evidence_report,
        OUTCOME_PASSED,
    )

    if args.requirements_command == "validate":
        manifest = load_task_manifest(args.manifest)
        print(
            json.dumps(
                {
                    "ok": True,
                    "manifest_id": manifest.id,
                    "manifest_hash": manifest.manifest_hash,
                    "requirements": [r.id for r in manifest.requirements],
                    "providers_needed": sorted(
                        {r.check.provider for r in manifest.requirements if r.check}
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.requirements_command == "check":
        contract = load_contract(args.contract)
        if args.manifest is not None:
            manifest = load_task_manifest(args.manifest)
        elif contract.task_manifest is not None:
            from runspecimen.paths import ensure_within

            mpath = ensure_within(
                workspace, Path(contract.task_manifest.path), label="task_manifest.path"
            )
            manifest = load_task_manifest(mpath)
        else:
            raise RunSpecimenError(
                "requirements check requires --manifest or a contract.task_manifest binding"
            )
        try:
            report = run_requirements(
                workspace=workspace, contract=contract, manifest=manifest
            )
        except AuthorizationError as exc:
            out = {
                "ok": False,
                "refused": True,
                "error": str(exc),
                "hint": (
                    "Bind task_manifest on the contract, then run the ordinary "
                    "approve → preflight → run lifecycle on a real TTY. "
                    "Agents must not type APPROVE. Unapproved check commands never execute."
                ),
            }
            print(json.dumps(out, indent=2, sort_keys=True, default=str))
            return 2
        path = write_evidence_report(
            workspace, contract.campaign_id, contract.run_id, report
        )
        att_path = None
        if args.write_attestation:
            att = build_evidence_attestation(report)
            att_path = write_evidence_attestation(
                workspace, contract.campaign_id, contract.run_id, att
            )
        annotated = load_evidence_report(
            workspace, contract.campaign_id, contract.run_id
        )
        out = {
            "ok": annotated.get("aggregate_outcome") == OUTCOME_PASSED
            and annotated.get("final_state_certifiable") is True
            and annotated.get("authenticity") == "receipt_bound",
            "evidence_report": str(path),
            "attestation": str(att_path) if att_path else None,
            "ci": ci_machine_report(annotated),
            "report": annotated,
        }
        print(json.dumps(out, indent=2, sort_keys=True, default=str))
        return 0 if out["ok"] else 1
    if args.requirements_command == "report":
        report = load_evidence_report(workspace, args.campaign_id, args.run_id)
        print(
            json.dumps(
                {"report": report, "ci": ci_machine_report(report)},
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        return 0
    raise RunSpecimenError(f"unknown requirements command: {args.requirements_command}")


def _freshness(args: argparse.Namespace, workspace: Path) -> int:
    from runspecimen.freshness import check_freshness_for_run, write_freshness_report
    from runspecimen.paths import ensure_within
    from runspecimen.requirements import load_task_manifest

    if args.freshness_command != "check":
        raise RunSpecimenError(f"unknown freshness command: {args.freshness_command}")
    contract = load_contract(args.contract)
    manifest = None
    if args.manifest is not None:
        manifest = load_task_manifest(args.manifest)
    elif contract.task_manifest is not None:
        mpath = ensure_within(
            workspace, Path(contract.task_manifest.path), label="task_manifest.path"
        )
        manifest = load_task_manifest(mpath)
    report = check_freshness_for_run(
        workspace=workspace, contract=contract, manifest=manifest
    )
    path = write_freshness_report(
        workspace, contract.campaign_id, contract.run_id, report
    )
    print(
        json.dumps(
            {"freshness_report": str(path), "report": report},
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0 if report.get("applicability") == "applicable" else 1


def _config(args: argparse.Namespace, workspace: Path) -> int:
    from runspecimen.atomic import read_json
    from runspecimen.configsync import (
        apply_bundle,
        export_bundle,
        inspect_environment,
        preview_apply,
        rollback_bundle,
    )

    if args.config_command == "inspect":
        print(json.dumps(inspect_environment(workspace=workspace), indent=2, sort_keys=True))
        return 0
    if args.config_command == "preview":
        bundle = read_json(args.bundle)
        print(json.dumps(preview_apply(workspace, bundle), indent=2, sort_keys=True))
        return 0
    if args.config_command == "apply":
        bundle = read_json(args.bundle)
        print(json.dumps(apply_bundle(workspace, bundle), indent=2, sort_keys=True))
        return 0
    if args.config_command == "export":
        print(json.dumps(export_bundle(workspace, args.out), indent=2, sort_keys=True))
        return 0
    if args.config_command == "rollback":
        print(json.dumps(rollback_bundle(workspace, args.backup), indent=2, sort_keys=True))
        return 0
    raise RunSpecimenError(f"unknown config command: {args.config_command}")


def _decisions(args: argparse.Namespace, workspace: Path) -> int:
    from runspecimen.decisions import (
        capture_decision,
        list_decisions,
        load_decision,
        review_flags,
        search_decisions,
    )

    if args.decisions_command == "capture":
        doc = capture_decision(
            workspace=workspace,
            decision_id=args.id,
            rationale=args.rationale,
            classification=args.classification,
            source_refs=list(args.source_ref),
            affected_requirements=list(args.affected_requirement),
            affected_files=list(args.affected_file),
            supersedes=args.supersedes,
        )
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0
    if args.decisions_command == "list":
        print(json.dumps(list_decisions(workspace), indent=2, sort_keys=True))
        return 0
    if args.decisions_command == "search":
        print(json.dumps(search_decisions(workspace, args.query), indent=2, sort_keys=True))
        return 0
    if args.decisions_command == "show":
        print(json.dumps(load_decision(workspace, args.id), indent=2, sort_keys=True))
        return 0
    if args.decisions_command == "review-flags":
        print(json.dumps(review_flags(workspace), indent=2, sort_keys=True))
        return 0
    raise RunSpecimenError(f"unknown decisions command: {args.decisions_command}")


def _snapshot(args: argparse.Namespace, workspace: Path) -> int:
    from runspecimen.snapshot import (
        compare_snapshot_to_workspace,
        get_snapshot_provider,
        load_snapshot_record,
    )

    provider = get_snapshot_provider("local_tar")
    if args.snapshot_command == "create":
        contract = load_contract(args.contract)
        record = provider.create(
            workspace=workspace,
            snapshot_id=args.id,
            roots=list(contract.source.roots),
            excludes=list(contract.source.excludes),
        )
        print(json.dumps(record, indent=2, sort_keys=True))
        return 0
    record = load_snapshot_record(workspace, args.id)
    if args.snapshot_command == "preview-restore":
        print(
            json.dumps(
                provider.preview_restore(workspace=workspace, record=record, dest=args.dest),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.snapshot_command == "restore":
        print(
            json.dumps(
                provider.restore(workspace=workspace, record=record, dest=args.dest),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.snapshot_command == "compare":
        print(
            json.dumps(
                compare_snapshot_to_workspace(workspace, record),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    raise RunSpecimenError(f"unknown snapshot command: {args.snapshot_command}")


def _usage(args: argparse.Namespace, workspace: Path) -> int:
    from runspecimen.usage import import_usage, summarize_usage

    if args.usage_command == "import":
        print(
            json.dumps(
                import_usage(
                    workspace=workspace,
                    provider_name=args.provider,
                    export_path=args.export,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.usage_command == "summarize":
        print(json.dumps(summarize_usage(workspace), indent=2, sort_keys=True))
        return 0
    raise RunSpecimenError(f"unknown usage command: {args.usage_command}")


def _coordination(args: argparse.Namespace) -> int:
    from runspecimen.coordination import (
        evaluate_readiness,
        load_coordination_plan,
        parse_coordination_plan,
    )
    from runspecimen.artifact import bind_artifact_digest

    plan = load_coordination_plan(args.plan)
    if args.coordination_command == "validate":
        parsed = parse_coordination_plan(plan)
        if "artifact_digest" not in parsed:
            parsed = bind_artifact_digest(parsed)
        print(json.dumps({"ok": True, "plan": parsed}, indent=2, sort_keys=True))
        return 0
    if args.coordination_command == "readiness":
        result = evaluate_readiness(plan)
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        return 0 if result.get("ready") else 1
    raise RunSpecimenError(f"unknown coordination command: {args.coordination_command}")


def _eval(args: argparse.Namespace, workspace: Path) -> int:
    from runspecimen.atomic import read_json
    from runspecimen.evalsuite import (
        compare_eval_results,
        load_eval_suite,
        run_eval_suite,
        write_eval_result,
    )
    from runspecimen.artifact import bind_artifact_digest

    if args.eval_command == "run":
        suite = load_eval_suite(args.suite)
        if "artifact_digest" not in suite:
            suite = bind_artifact_digest(suite)
        result = run_eval_suite(workspace=workspace, suite=suite)
        path = write_eval_result(workspace, result)
        print(
            json.dumps(
                {"result_path": str(path), "result": result},
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        return 0 if result.get("passed_deterministic") else 1
    if args.eval_command == "compare":
        baseline = read_json(args.baseline)
        candidate = read_json(args.candidate)
        print(
            json.dumps(
                compare_eval_results(baseline, candidate),
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        return 0
    raise RunSpecimenError(f"unknown eval command: {args.eval_command}")
