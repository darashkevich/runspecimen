# Contract and receipt schema compatibility

This document defines how RunSpecimen versions JSON contracts and postflight
receipts (`certificate.json`). Unknown versions **fail closed**. HMAC
authentication remains a shared-secret MAC and is not a schema version by itself.

Evidence-layer sidecar documents (task manifests, evidence reports, freshness
reports, config bundles, decisions, snapshots, usage ledgers, coordination
plans, eval suites/results) use `schema_kind` + `schema_version` +
`artifact_digest` as defined in `docs/ADR-005-evidence-expansion.md`. Unsupported
kinds/versions fail closed. They do not replace `verify`.

## Contract versions

| `version` | Status | Notes |
| --- | --- | --- |
| `1` | Current | Only supported contract schema. Required field. |

- Missing `version` → validation error (not assumed).
- Any integer other than a supported version → `ContractError` naming the
  unsupported value and pointing here.
- Forward compatibility: new optional fields may be added under the same
  version only when older engines that reject unknown fields are no longer
  required. Until then, unknown top-level or nested fields fail closed.
- Optional on version 1, accepted by `0.2.0rc13` and rejected by
  published `0.2.0rc12`: `isolation` (`backend` of `none`, `sandbox-exec`, or
  `bwrap`, plus optional `network`) and `policy` (`id`, `path`, `sha256` of a
  workspace-local JSON file). Absent `isolation` means backend `none`.
- Policy files remain `version: 1` with **additive optional** template fields
  (`protected_paths`, `expected_outputs`, `required_verification`,
  `ops_requiring_distinct_run`, `required_predecessor_evidence`, `template_id`,
  `template_version`, `nl_constraint_notes`). Unknown policy keys still fail
  closed. Engines that do not list a field reject policies that use it.

## Receipt schema versions (`certificate.json`)

| `schema_version` | Status | Notes |
| --- | --- | --- |
| absent | Legacy v1 | Treated as `1`. Golden / pre-Phase-0 receipts. |
| `1` | Current | Written on every newly issued certificate. |

- `schema_version`, when present, must be a JSON integer in the supported set.
- Unsupported or non-integer values → `CertificateError` with a migration hint.
- When `schema_version` is present on a certificate, it is included in the
  `certificate_id` hash material. Legacy certificates omit it from both the
  document and the hash material.
- New receipts may also include `isolation`, `policy`, `approver`, and optional
  `evidence_attestation`. Each key is part of `certificate_id` only when it is
  present. Historical receipts that omit them stay valid. Do not rewrite an
  issued certificate to add them.
- `evidence_attestation` (when present) binds an evidence-report digest. It
  authenticates linked evidence bytes; it does not rewrite check outcomes or
  imply current applicability. Live `verify` semantics are unchanged.

### Issuance rules

New certificates always set `"schema_version": 1` and bind that value into
`certificate_id`. Verification accepts legacy certificates without the field.

### Migration rules

1. **Verify old receipts:** keep the workspace, outputs, and contract bytes that
   match the certificate; use a RunSpecimen build that lists the receipt’s
   schema in the supported set (legacy absent ≡ 1).
2. **Cannot “upgrade” an issued receipt:** do not rewrite `certificate.json` to
   add fields that change `certificate_id`. Issue a new run if you need a new
   schema.
3. **Future versions:** a new `schema_version` requires an explicit engine bump,
   golden fixtures, and a changelog entry. Engines that do not understand the
   version must refuse verification rather than skip fields.
4. **Evidence sidecars:** preserve historical evidence/freshness reports; mark
   applicability stale rather than rewriting outcomes. Requirement edits and
   source/runtime/policy changes invalidate applicability (`runspecimen freshness`).

## What versioning is not

- Package/`runspecimen --version` (engine release) is independent of contract
  and receipt schema versions.
- HMAC `sign` / `verify-signature` authenticates a certificate blob; it does not
  replace schema validation and does not provide non-repudiation.
- Live `verify` still rehashes contract, source, runtime, and outputs when
  requested; a matching `schema_version` alone never means “green verified.”
- `requirements`, `freshness`, `digest`, and `diff` are separate from `verify`.

## Compatibility matrix (engine ↔ schemas)

| Engine release family | Contracts | Receipts |
| --- | --- | --- |
| 0.2.0-rc.10 and earlier | `version: 1` | Legacy (no `schema_version`) |
| Phase 0+ (this roadmap) | `version: 1` | Legacy **or** `schema_version: 1` |
| Evidence expansion (ADR-005) | `version: 1` + sidecar kinds | Receipt optional `evidence_attestation` |
