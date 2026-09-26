# ADR-005: Evidence expansion (requirements → eval)

**Status:** Accepted for implementation on branch `cursor/evidence-expansion-coherence`  
**Date:** 2026-09-23  
**Product question:** What was authorized, what actually ran, which requirements were checked, what evidence supports the results, and does that evidence still apply?

## Context

RunSpecimen already provides one-approved-run execution, provenance, policy binding,
hash-chained events, certificates, crash abandon, HMAC/Ed25519 receipts, a
read-only dashboard, and host adapters that never approve. The next slice must
answer requirement/evidence/freshness questions **without** weakening those
trust boundaries or silently changing `verify`.

Published pin: `0.2.0rc14`. Contract `version: 1` and receipt `schema_version: 1`
remain current. This ADR extends the tree with **sidecar schemas** and optional
contract/policy fields that fail closed on unknown versions.

## Trust boundaries (non-negotiable)

1. Agents never approve, manufacture approval records, settle remote confirm, or
   bypass refusals. MCP/plugin tools stay approval-free.
2. One workspace lease; one-approved-run execution semantics unchanged.
3. Dashboard remains loopback read-only (no approve/run POST).
4. Not an OS sandbox. Distinguish prevented ops, post-hoc detections, and
   unobservable ops. Unchanged final digest ≠ “never temporarily modified.”
5. Preserve `verify` guarantees. New views/commands are separate.
6. New evidence is integrity-covered only when its digest is bound through a
   supported receipt field or a linked attestation document.
7. Separate in data model and UI: (a) receipt authenticity, (b) check/requirement
   outcome, (c) evidence applicability to current state.
8. v1 contracts keep `postflight.source_unchanged: true`. Mutation contracts are
   out of scope (separate future design with before/after provenance).

## Reuse

| Existing | Role in this expansion |
| --- | --- |
| `contract.py` / `schema.py` | Optional refs; version fail-closed |
| `policy.py` | Extended additive policy/template fields |
| `hashutil.hash_source` / `runtime.py` | Freshness fingerprints |
| `certificate.py` | Optional `evidence_attestation` when present |
| `recovery.py` | Crash abandon stays; snapshot restore is separate |
| `dashboard.py` | Read-only panels for requirements/freshness/etc. |
| `cli.py` doctor | Expanded diagnostics; no silent sync |
| MCP `runspecimen_mcp.py` | Add search/read tools only (no approve) |

## Schema story (single coherent model)

All new artifacts share:

- `schema_kind` (stable string)
- `schema_version` (integer; unsupported → fail closed)
- Canonical JSON material → `artifact_digest` (SHA-256), excluding the digest
  field itself

| Kind | Purpose | Bound how |
| --- | --- | --- |
| `task_manifest` | Versioned requirements + check mappings | Optional contract `task_manifest` `{id,path,sha256}` |
| `evidence_report` | Provider-collected check results | Digests of evidence artifacts; optional receipt `evidence_attestation` |
| `freshness_report` | What changed; applicability | References prior report digests; never rewrites outcomes |
| `policy` (v1 additive) | Templates: protected paths, required verification, … | Existing contract `policy` hash bind |
| `config_bundle` | Inspect/preview/apply env config | Explicit apply only; backups |
| `decision` | Human/agent-classified rationale registry | Content-addressed; search only |
| `snapshot_record` | Verifiable workspace snapshot metadata | Optional contract `snapshot` ref |
| `usage_event` / ledger | Imported usage attribution | Idempotent import keys |
| `coordination_plan` | Multi-repo readiness | Per-workspace approval preserved |
| `eval_suite` / `eval_result` | Workflow regression | Fixture/config version binding |

### Compatibility

- Existing contracts/receipts without new fields verify unchanged.
- Contracts that **include** new optional fields require an engine that lists
  those fields (this branch+). Older engines reject unknown fields (fail closed).
- Receipt optional `evidence_attestation` participates in `certificate_id` **only
  when present** (same pattern as `policy` / `isolation` / `approver`).
- Do not rewrite issued certificates. Issue a new run for new bindings.
- Policy version stays `1` with **additive optional** keys; unknown keys still
  fail closed. Document migration in `SCHEMA_COMPATIBILITY.md`.

### Outcome honesty

- Never accept an agent-written `passed` field as proof.
- Missing / malformed / conflicting / skipped / collection-error → not success.
- Filename match is not coverage.
- Passing configured checks ≠ universal correctness.
- Historical authentic failed checks stay failed; freshness marks **stale**, not
  rewritten.

## Modules

1. **Core:** auth/exec/provenance/assertions/receipts (unchanged semantics)
2. **Evidence:** `requirements.py`, `freshness.py`, providers under
   `runspecimen/providers/`
3. **Policy UX:** extend `policy.py`; refusal helper
4. **Config:** `configsync.py` + doctor expansion
5. **Decisions:** `decisions.py`
6. **Recovery snapshots:** `snapshot.py` (local tar provider; evaluate before inventing)
7. **Usage:** `usage.py`
8. **Coordination:** `coordination.py`
9. **Eval:** `evalsuite.py`
10. **Adapters/CLI/dashboard:** wire commands; read-only UI; MCP search

## Verification plan

- Unit/adversarial tests for each module’s honesty rules
- Compatibility: golden showcase receipt + existing contract suite
- Tamper detection on manifests/policies/reports/evidence
- Ten-scene local demo script (non-destructive; never types APPROVE)
- `python -m unittest` / project CI gates

## Explicit non-goals

Auto-deploy, auto-merge, blanket multi-repo approval, spend hard-enforcement,
scraping undocumented Cursor DBs, OS-sandbox claims, silent doctor sync,
rewriting history, harvesting private chats.
