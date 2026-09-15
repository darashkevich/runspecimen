# Changelog

## Unreleased

### Schema compatibility

- Document contract and receipt schema versioning in
  `docs/SCHEMA_COMPATIBILITY.md` with fail-closed unknown versions and
  migration rules.
- New certificates emit `schema_version: 1` bound into `certificate_id`.
  Legacy certificates without the field remain valid as v1.
- Add phased roadmap at `docs/ROADMAP_PHASED.md`.

### Dashboard UX (prototype)

- Redesign the local dashboard first viewport to answer: what run, what
  happened, whether it is safe to continue, and what to do next.
- Move About behind progressive disclosure; add an evidence trust ladder that
  never presents a certificate as live-verified.
- Keep the dashboard loopback-only and read-only (no approve/run APIs).

## 0.2.0rc9 - 2026-09-13

### Security Hardening

- **Abandoned runs are permanently terminal**: Abandoned run IDs cannot be
  re-approved, preflighted, or executed. Predecessors with `refuse_if_failed`
  now reject abandoned predecessors.

- **Recovery status checks active leases**: `needs_recovery` is only true when
  `phase=running` AND no active workspace lease exists. Prevents abandoning
  runs that are still executing.

- **Key storage hardening**: Key IDs are validated against a strict safe-ID
  grammar. Path traversal attacks are blocked. Keys cannot be overwritten
  without explicit rotation.

- **Certificate validation before signing**: Sign command validates certificate
  schema and recomputes `certificate_id` before signing. Rejects malformed or
  tampered certificates.

- **HMAC terminology corrected**: Documentation and CLI now accurately describe
  HMAC-SHA256 as shared-secret authentication (not digital signatures). Anyone
  with the key can both create and verify MACs.

- **Interpreter provenance is truthful**: Configured interpreters must resolve
  to executables and are fingerprinted. Missing or non-executable interpreters
  cause hard failures. Library capture uses the interpreter (not the script).

- **Environment values not persisted**: Raw environment variable values are
  never stored in artifacts. Only variable names and domain-separated hashes
  are recorded.

- **Portable path identity**: Added helper for macOS /var vs /private/var
  symlink aliasing in path comparisons.

### Bug Fixes

- Fixed macOS path-alias test failures using `os.path.realpath` comparisons.
- Library capture explicitly reports unsupported platforms (non-Linux).

## 0.2.0rc8 - 2026-09-10

- Package the RunSpecimen logo in source and plugin archives and reference it
  from the Cursor plugin and marketplace manifests.
- Extend the release gate so missing plugin branding fails before publication.

## 0.2.0rc7 - 2026-09-08

- Made the installed-dashboard release smoke deterministic on macOS runners by hosting and probing the loopback server in one process.

## 0.2.0rc6 - 2026-09-08

- Replaced the release-gate dashboard startup log dependency with direct loopback HTTP readiness verification for reliable macOS checks.

## 0.2.0rc5 - 2026-09-08

- Make the offline release gate wait for dashboard startup without relying on
  platform-specific pipe readiness notifications.

## 0.2.0rc4 - 2026-09-07

- Harden lifecycle supervision so inherited output pipes, timeouts, and
  interruption all leave bounded captures and a terminal recorded state.
- Bind approvals and receipts to the exact parsed contract bytes, reject unsafe
  source-root symlinks, and recheck expiry at launch.
- Make the local dashboard honest about recorded evidence versus live receipt
  verification; reject cross-origin access, contract drift, and write requests.
- Add a dashboard About panel plus User guide / FAQ links, `docs/ABOUT.md`, and
  a `runspecimen about` command (docs URLs also appear in `doctor` and `--help`).
- Add a fresh `init-demo` onboarding command and a clean-install release gate
  for source archives, wheels, the dashboard, and the plugin package.

## 0.2.0rc3 - 2026-09-04

- Add a contract-scoped, loopback-only local dashboard that renders phase,
  evidence, and the exact lifecycle commands for Codex and Cursor users.
- Keep the dashboard read-only: it cannot approve or execute commands, so the
  real-TTY approval and CLI enforcement boundaries remain intact.
- Teach the Codex and Cursor adapters to launch the dashboard on request.

## 0.2.0rc2 - 2026-09-03

- Execute the exact absolute executable whose digest was approved, including
  correct resolution of relative `PATH` entries against the contract working directory.
- Reject unknown and duplicate contract fields so misspelled safety controls fail closed.
- Add a native Cursor plugin manifest, marketplace metadata, packaged rule, and local-test docs.
- Expand release checks to keep the Python, Codex, and Cursor package versions aligned.

## 0.2.0rc1 - 2026-09-01

- Bind approvals and receipts to the resolved executable SHA-256.
- Remove stale lease-owner metadata and make status report only active holders.
- Add `doctor` and `validate` readiness commands.
- Add Codex plugin and Cursor rule adapters that preserve the TTY approval gate.
- Add threat model, security policy, CI, release checks, and clean-install smoke tests.
- Declare Apache-2.0 licensing and Python 3.9+ support.

## 0.1.0 - 2026-08-24

- Initial bounded-run engine with TTY approval, workspace lease, atomic state,
  predecessor gating, postflight assertions, and tamper-evident receipts.
