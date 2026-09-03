"""JSON contract schema and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runspecimen.errors import ContractError
from runspecimen.hashutil import hash_contract_file
from runspecimen.paths import ensure_within, resolve_workspace

# Hard caps enforced by the tool (unsafe if contract exceeds these).
MAX_WALL_TIMEOUT_SEC = 24 * 60 * 60
MAX_CAPTURE_BYTES = 50 * 1024 * 1024
MAX_APPROVAL_TTL_SEC = 7 * 24 * 60 * 60
MIN_WALL_TIMEOUT_SEC = 1
MIN_CAPTURE_BYTES = 1
MIN_APPROVAL_TTL_SEC = 1

_HEX_CHARS = set("0123456789abcdefABCDEF")


def _reject_unknown(obj: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise ContractError(f"{label} contains unknown field(s): {', '.join(unknown)}")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON field: {key!r}")
        result[key] = value
    return result


def _require_dict(obj: Any, label: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ContractError(f"{label} must be an object")
    return obj


def _require_str(obj: Any, label: str) -> str:
    if not isinstance(obj, str) or not obj:
        raise ContractError(f"{label} must be a non-empty string")
    return obj


def _require_int(obj: Any, label: str) -> int:
    if isinstance(obj, bool) or not isinstance(obj, int):
        raise ContractError(f"{label} must be an integer")
    return obj


def _require_bool(obj: Any, label: str) -> bool:
    if not isinstance(obj, bool):
        raise ContractError(f"{label} must be a JSON boolean (true/false), not {type(obj).__name__}")
    return obj


def _require_list(obj: Any, label: str) -> list[Any]:
    if not isinstance(obj, list):
        raise ContractError(f"{label} must be an array")
    return obj


def _require_sha256_hex(obj: Any, label: str) -> str:
    if not isinstance(obj, str) or len(obj) != 64:
        raise ContractError(f"{label} must be a 64-character SHA-256 hex digest")
    if any(c not in _HEX_CHARS for c in obj):
        raise ContractError(f"{label} must be hexadecimal")
    return obj.lower()


@dataclass(frozen=True)
class SourceSpec:
    roots: tuple[str, ...]
    excludes: tuple[str, ...]


@dataclass(frozen=True)
class CapsSpec:
    wall_timeout_sec: int
    stdout_max_bytes: int
    stderr_max_bytes: int


@dataclass(frozen=True)
class ApprovalSpec:
    ttl_sec: int


@dataclass(frozen=True)
class PredecessorSpec:
    campaign_id: str
    run_id: str
    require_postflight: bool = True
    refuse_if_failed: bool = True


@dataclass(frozen=True)
class JsonEqualsAssert:
    path: str
    field: str
    equals: Any


@dataclass(frozen=True)
class PostflightSpec:
    exit_code: int
    require_outputs: bool
    output_sha256: dict[str, str]
    json_equals: tuple[JsonEqualsAssert, ...]
    source_unchanged: bool


@dataclass(frozen=True)
class Contract:
    version: int
    campaign_id: str
    run_id: str
    argv: tuple[str, ...]
    cwd: str
    source: SourceSpec
    outputs_required: tuple[str, ...]
    caps: CapsSpec
    approval: ApprovalSpec
    predecessor: PredecessorSpec | None
    postflight: PostflightSpec
    path: Path
    contract_hash: str
    raw: dict[str, Any] = field(repr=False)

    @property
    def id_pair(self) -> tuple[str, str]:
        return self.campaign_id, self.run_id

    @property
    def asserted_output_paths(self) -> tuple[str, ...]:
        """Every file whose contents or existence influence postflight."""
        paths = set(self.outputs_required)
        paths.update(self.postflight.output_sha256)
        paths.update(assertion.path for assertion in self.postflight.json_equals)
        return tuple(sorted(paths))


def validate_caps(caps: CapsSpec) -> None:
    if not (MIN_WALL_TIMEOUT_SEC <= caps.wall_timeout_sec <= MAX_WALL_TIMEOUT_SEC):
        raise ContractError(
            f"unsafe wall_timeout_sec={caps.wall_timeout_sec} "
            f"(allowed {MIN_WALL_TIMEOUT_SEC}..{MAX_WALL_TIMEOUT_SEC})"
        )
    if not (MIN_CAPTURE_BYTES <= caps.stdout_max_bytes <= MAX_CAPTURE_BYTES):
        raise ContractError(
            f"unsafe stdout_max_bytes={caps.stdout_max_bytes} "
            f"(allowed {MIN_CAPTURE_BYTES}..{MAX_CAPTURE_BYTES})"
        )
    if not (MIN_CAPTURE_BYTES <= caps.stderr_max_bytes <= MAX_CAPTURE_BYTES):
        raise ContractError(
            f"unsafe stderr_max_bytes={caps.stderr_max_bytes} "
            f"(allowed {MIN_CAPTURE_BYTES}..{MAX_CAPTURE_BYTES})"
        )


def parse_contract(data: dict[str, Any], *, path: Path) -> Contract:
    data = _require_dict(data, "contract")
    _reject_unknown(
        data,
        {
            "version",
            "campaign_id",
            "run_id",
            "argv",
            "cwd",
            "source",
            "outputs",
            "caps",
            "approval",
            "predecessor",
            "postflight",
        },
        "contract",
    )
    version = _require_int(data.get("version"), "version")
    if version != 1:
        raise ContractError(f"unsupported contract version: {version}")

    campaign_id = _require_str(data.get("campaign_id"), "campaign_id")
    run_id = _require_str(data.get("run_id"), "run_id")

    argv_raw = _require_list(data.get("argv"), "argv")
    if not argv_raw:
        raise ContractError("argv must be a non-empty array")
    argv: list[str] = []
    for i, item in enumerate(argv_raw):
        if not isinstance(item, str) or item == "":
            raise ContractError(f"argv[{i}] must be a non-empty string")
        argv.append(item)

    cwd = data.get("cwd", ".")
    if not isinstance(cwd, str):
        raise ContractError("cwd must be a string")

    source_obj = _require_dict(data.get("source"), "source")
    _reject_unknown(source_obj, {"roots", "excludes"}, "source")
    roots_raw = _require_list(source_obj.get("roots"), "source.roots")
    if not roots_raw:
        raise ContractError("source.roots must be non-empty")
    roots = tuple(_require_str(r, f"source.roots[{i}]") for i, r in enumerate(roots_raw))
    excludes_raw = source_obj.get("excludes", [])
    excludes_list = _require_list(excludes_raw, "source.excludes")
    excludes = tuple(
        _require_str(x, f"source.excludes[{i}]") for i, x in enumerate(excludes_list)
    )

    outputs_obj = _require_dict(data.get("outputs"), "outputs")
    _reject_unknown(outputs_obj, {"required"}, "outputs")
    req_raw = _require_list(outputs_obj.get("required"), "outputs.required")
    outputs_required = tuple(
        _require_str(x, f"outputs.required[{i}]") for i, x in enumerate(req_raw)
    )

    caps_obj = _require_dict(data.get("caps"), "caps")
    _reject_unknown(
        caps_obj,
        {"wall_timeout_sec", "stdout_max_bytes", "stderr_max_bytes"},
        "caps",
    )
    caps = CapsSpec(
        wall_timeout_sec=_require_int(caps_obj.get("wall_timeout_sec"), "caps.wall_timeout_sec"),
        stdout_max_bytes=_require_int(caps_obj.get("stdout_max_bytes"), "caps.stdout_max_bytes"),
        stderr_max_bytes=_require_int(caps_obj.get("stderr_max_bytes"), "caps.stderr_max_bytes"),
    )
    validate_caps(caps)

    approval_obj = _require_dict(data.get("approval"), "approval")
    _reject_unknown(approval_obj, {"ttl_sec"}, "approval")
    ttl = _require_int(approval_obj.get("ttl_sec"), "approval.ttl_sec")
    if not (MIN_APPROVAL_TTL_SEC <= ttl <= MAX_APPROVAL_TTL_SEC):
        raise ContractError(
            f"unsafe approval.ttl_sec={ttl} "
            f"(allowed {MIN_APPROVAL_TTL_SEC}..{MAX_APPROVAL_TTL_SEC})"
        )
    approval = ApprovalSpec(ttl_sec=ttl)

    pred_raw = data.get("predecessor")
    predecessor: PredecessorSpec | None
    if pred_raw is None:
        predecessor = None
    else:
        pred = _require_dict(pred_raw, "predecessor")
        _reject_unknown(
            pred,
            {"campaign_id", "run_id", "require_postflight", "refuse_if_failed"},
            "predecessor",
        )
        if "require_postflight" in pred:
            require_postflight = _require_bool(pred.get("require_postflight"), "predecessor.require_postflight")
        else:
            require_postflight = True
        if "refuse_if_failed" in pred:
            refuse_if_failed = _require_bool(pred.get("refuse_if_failed"), "predecessor.refuse_if_failed")
        else:
            refuse_if_failed = True
        predecessor = PredecessorSpec(
            campaign_id=_require_str(
                pred.get("campaign_id", campaign_id), "predecessor.campaign_id"
            ),
            run_id=_require_str(pred.get("run_id"), "predecessor.run_id"),
            require_postflight=require_postflight,
            refuse_if_failed=refuse_if_failed,
        )
        if not predecessor.require_postflight or not predecessor.refuse_if_failed:
            raise ContractError(
                "predecessor.require_postflight and predecessor.refuse_if_failed "
                "must both be true (v1 mandatory-gating promise)"
            )

    pf_obj = _require_dict(data.get("postflight"), "postflight")
    _reject_unknown(
        pf_obj,
        {"exit_code", "require_outputs", "output_sha256", "json_equals", "source_unchanged"},
        "postflight",
    )
    exit_code = _require_int(pf_obj.get("exit_code"), "postflight.exit_code")
    if "require_outputs" in pf_obj:
        require_outputs = _require_bool(pf_obj.get("require_outputs"), "postflight.require_outputs")
    else:
        require_outputs = True
    sha_obj = pf_obj.get("output_sha256", {})
    sha_dict = _require_dict(sha_obj, "postflight.output_sha256")
    output_sha256: dict[str, str] = {}
    for k, v in sha_dict.items():
        if not isinstance(k, str) or not k:
            raise ContractError("postflight.output_sha256 keys must be non-empty paths")
        output_sha256[k] = _require_sha256_hex(v, f"postflight.output_sha256[{k!r}]")
    je_raw = pf_obj.get("json_equals", [])
    je_list = _require_list(je_raw, "postflight.json_equals")
    json_equals: list[JsonEqualsAssert] = []
    for i, item in enumerate(je_list):
        item_d = _require_dict(item, f"postflight.json_equals[{i}]")
        _reject_unknown(
            item_d,
            {"path", "field", "equals"},
            f"postflight.json_equals[{i}]",
        )
        json_equals.append(
            JsonEqualsAssert(
                path=_require_str(item_d.get("path"), f"postflight.json_equals[{i}].path"),
                field=_require_str(item_d.get("field"), f"postflight.json_equals[{i}].field"),
                equals=item_d.get("equals"),
            )
        )
    # v1 provenance promise: source_unchanged must be present and true.
    source_unchanged = _require_bool(pf_obj.get("source_unchanged"), "postflight.source_unchanged")
    if source_unchanged is not True:
        raise ContractError(
            "postflight.source_unchanged must be true (v1 exact-provenance promise)"
        )
    postflight = PostflightSpec(
        exit_code=exit_code,
        require_outputs=require_outputs,
        output_sha256=output_sha256,
        json_equals=tuple(json_equals),
        source_unchanged=source_unchanged,
    )

    contract_hash = hash_contract_file(path)
    return Contract(
        version=version,
        campaign_id=campaign_id,
        run_id=run_id,
        argv=tuple(argv),
        cwd=cwd,
        source=SourceSpec(roots=roots, excludes=excludes),
        outputs_required=outputs_required,
        caps=caps,
        approval=approval,
        predecessor=predecessor,
        postflight=postflight,
        path=path.resolve(),
        contract_hash=contract_hash,
        raw=data,
    )


def load_contract(path: Path) -> Contract:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise ContractError(f"contract not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh, object_pairs_hook=_object_without_duplicates)
    except ContractError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ContractError(f"invalid contract JSON: {exc}") from exc
    return parse_contract(data, path=path)


def check_contract_paths(contract: Contract, workspace: Path) -> None:
    """Ensure cwd, source roots, and output paths stay inside workspace."""
    workspace = resolve_workspace(workspace)
    ensure_within(workspace, Path(contract.cwd), label="cwd")
    for root in contract.source.roots:
        ensure_within(workspace, Path(root), label=f"source root {root!r}")
    for out in contract.outputs_required:
        ensure_within(workspace, Path(out), label=f"output {out!r}")
    for out in contract.postflight.output_sha256:
        ensure_within(workspace, Path(out), label=f"output_sha256 path {out!r}")
    for assertion in contract.postflight.json_equals:
        ensure_within(workspace, Path(assertion.path), label=f"json_equals path {assertion.path!r}")
