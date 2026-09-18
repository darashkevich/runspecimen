# Changelog

## Unreleased

### macOS app

- Fix local launch: the SwiftUI window could size to thousands of points and
  open off-screen (blank view, hidden CLI alert, Full Screen disabled). Clamp
  to the visible display, mark the window Full Screen-capable, keep CLI
  discovery failures on the in-window banner, and skip App Sandbox on local
  `--from-src` builds so the host-Python helper can run. Layout wraps on
  split / 13-inch Macs; iOS Observe uses a readable column and landscape.
- Store export gate now fail-closes on `codesign --verify --strict` for the
  archived app and nested helper, including a tamper-after-signing negative.
- Fix `AppIcon.appiconset`: catalog filenames are real `icon_*@2x.png` files
  with matching pixel sizes (128@2x is 256px). `verify_app_icon.sh` checks
  Contents.json and a warning-free `actool` compile.
- PyPI publish workflow consumes GitHub Release assets as identical bytes
  (no rebuild). rc11 remains checksum-only until SLSA attestations exist.

## 0.2.0rc11 - 2026-09-18

### Brand

- Replace the padlock glyph with the 6-fold hexaflake mark (plugin logos,
  Codex `interface.logo` / `composerIcon`, iOS Observe, macOS AppIcon).

### Incident bundle and remote-confirm refuse

- Add Community CLI `runspecimen bundle` for a local incident evidence pack
  (state, events, approval, certificate, verify output, refusal extract,
  optional predecessor chain). History on disk stays visible. Not a Veto
  7-day vault; Team later pays for off-laptop retention, not hiding local files.
- Remote human confirm can be **refused with a typed reason**
  (`runspecimen remote-confirm refuse` / `POST /v1/remote-confirm-refuse`).
  Challenge still required; pending is consumed without writing approval.
- `runspecimen verify` surfaces `confirm_channel` (`local_tty_approve` vs
  `remote_human_confirm`) so phone confirm is not claimed TTY-equivalent.
- Quiet hours (`RUNSPECIMEN_QUIET_HOURS=HH-HH`) block **arm only** — never
  auto-APPROVE. Companion iOS card shows who/what/expiry/lease/isolation/
  predecessor chips. Plugins still cannot approve, settle, or refuse.
- Docs: `docs/SPEC_INCIDENT_BUNDLE.md`, `docs/SPEC_REMOTE_CONFIRM_CARD.md`.
  RS price book stays Community / Pro / Team — not Veto SKUs.

### Gemini, JetBrains, and Windsurf adapters

- Add Gemini CLI extension manifest (`gemini-extension.json`), `GEMINI.md`,
  TOML slash commands, and `BeforeTool` approve-gate wiring via
  `hooks/hooks.json` (Gemini-only) plus shared
  `block_approve_gate.py --format gemini`. Claude/Junie/Grok keep
  `hooks/claude-hooks.json` (`PreToolUse`) so Claude's hook schema is not
  broken by `BeforeTool` keys.
- Add Junie native marketplace (`.junie-extension/marketplace.json`),
  `extension.json`, guidelines, MCP mirror, JetBrains install docs, tested
  `ide_actions.py`, and a minimal IntelliJ Tools-menu scaffold with **no**
  in-IDE Approve action.
- Add Windsurf Cascade skill/rule pack under `plugins/runspecimen/windsurf/`.
- Extend `docs/INTEGRATIONS.md` / `docs/SUBMISSION.md` ledger for all three.
- Tests cover Gemini gate dialect, IDE action allow-list, and new manifests.
- QA: split Claude/Gemini hook files; deny `ide_actions.py approve` and
  approve-named MCP tool ids in the shared gate.

### Claude Code and Grok Build adapters

- Extend `plugins/runspecimen` with Claude Code manifest (`.claude-plugin/`),
  slash commands, PreToolUse approve-gate hook, and a local stdio MCP server
  that never exposes `approve` / remote-confirm settle.
- Cover Grok Build via Claude Code compatibility plus `plugins/runspecimen/grok/`
  install notes and optional `AGENTS.md`.
- Add repo marketplace catalog `.claude-plugin/marketplace.json` and central
  ledger/research brief `docs/INTEGRATIONS.md` (next targets: Gemini, JetBrains,
  Windsurf).
- Tests: `tests/test_plugins.py` for manifests, adapter allow-list, approve-gate,
  and MCP tool exclusion.

## 0.2.0rc10 - 2026-09-15

### Optional Ed25519 public-key receipts (Phase 1)

- Add optional extras `runspecimen[ed25519]` / `runspecimen[signing]` (PyNaCl)
  with `keygen` / `sign` / `verify-signature --scheme ed25519`,
  `export-public-key`, and offline public-key verification without the private
  key. Default install stays stdlib-only. See `docs/ED25519_RECEIPTS.md`.
- QA hardenings: release-check permits only vetted optional `Requires-Dist`
  markers; private keys use 0600 exclusive no-follow creates; public-key export
  never reads the private seed; trusted verify requires an external trust
  anchor (embedded-key-only consistency is never `ok: true`).
- Key rotation (`overwrite`) is crash-safe and all-or-nothing: durable journal +
  exclusive temps/backups at each transition; a killed process automatically
  rolls back to the previous working pair (or finishes cleanup after both new
  finals are installed) on the next open/use. SIGKILL fault-injection covers
  every rotation and fresh-create transition (including `complete`). Concurrent
  key create/list/rotate/load ops are excluded via `fcntl` `keys.op.lock`.
  Key reads use `O_NOFOLLOW` + `fstat` on the opened fd.
- **Security:** rotation recovery validates `key_id` against the journal
  filename and only `unlink`/`os.replace`s narrowly named, non-symlink children
  of the keys directory (basename reconstructed under the keys dir). Forged
  journals with absolute foreign paths, `..` traversal, symlink sidecars, or
  foreign-key sidecar names are discarded without deleting live keys or
  touching files outside the keys directory. A forged `fresh_priv_installed`
  journal never wipes an already-complete live keypair — incomplete fresh-create
  rollback requires a missing final (real SIGKILL half-pair window).
- `scripts/release_check.py` refuses packaging when setuptools≥77 is only in
  the user site: offline builds set `PYTHONNOUSERSITE=1` and previously could
  silently emit `UNKNOWN-0.0.0` sdists.

### Product direction

- Refine the phased roadmap toward verifiable execution: prioritize optional
  Ed25519 offline public-key receipts; prefer tested isolation integrations over
  inventing an OS sandbox; keep the core engine free of schedulers; refuse
  universal “scientifically proven” claims (`docs/ROADMAP_PHASED.md`,
  `docs/THREAT_MODEL.md`).

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
- Name documentation links for assistive tech (including links inside closed
  `<details>`); keep a always-visible footer docs nav on desktop and mobile.

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
