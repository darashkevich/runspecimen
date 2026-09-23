# Contract and receipt schema compatibility

This document defines how RunSpecimen versions JSON contracts and postflight
receipts (`certificate.json`). Unknown versions **fail closed**. HMAC
authentication remains a shared-secret MAC and is not a schema version by itself.

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
- Optional on version 1, accepted by `0.2.0rc14` and rejected by
  published `0.2.0rc12`: `isolation` (`backend` of `none`, `sandbox-exec`, or
  `bwrap`, plus optional `network`) and `policy` (`id`, `path`, `sha256` of a
  workspace-local JSON file). Absent `isolation` means backend `none`.

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
- New receipts may also include `isolation`, `policy`, and `approver`. Each
  key is part of `certificate_id` only when it is present. Historical receipts
  that omit them stay valid. Do not rewrite an issued certificate to add them.

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

## What versioning is not

- Package/`runspecimen --version` (engine release) is independent of contract
  and receipt schema versions.
- HMAC `sign` / `verify-signature` authenticates a certificate blob; it does not
  replace schema validation and does not provide non-repudiation.
- Live `verify` still rehashes contract, source, runtime, and outputs when
  requested; a matching `schema_version` alone never means “green verified.”

## Compatibility matrix (engine ↔ schemas)

| Engine release family | Contracts | Receipts |
| --- | --- | --- |
| 0.2.0-rc.10 and earlier | `version: 1` | Legacy (no `schema_version`) |
| Phase 0+ (this roadmap) | `version: 1` | Legacy **or** `schema_version: 1` |
