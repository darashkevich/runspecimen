# Changelog

## Unreleased

These notes describe source on the unpublished candidate. They are not a public release.

- RQ14-01: `python`, `python3`, `python3.X`, and `𝜋thon` in the venv must be a symlink to the base interpreter named by `pyvenv.cfg`, or a byte-for-byte copy of that file. A wrapper script is refused before it runs. The probe uses that base interpreter, not the venv launcher. qafix15 pack.
- RQ14-02: a `.pth` line that names a folder or a zip is followed, including further `.pth` lines, and those locations are scanned for startup hooks. Debian's `sitecustomize` import (such as `apport_python_hook`) is read, not run; a copy on the venv path is refused. The probe uses `-S`, so that import chain does not run. qafix15 pack.
- RQ14-03: `sitecustomize` and `usercustomize` are refused in every form this interpreter can import (source, bytecode, extension, package), not only a `.py` file. qafix15 pack.
- RQ14-04: when system site-packages are turned on, the refusal names the `pyvenv.cfg` path in plain English. qafix15 pack.
- LATEST-01: the installed-wheel check refuses `sitecustomize` and `usercustomize` when they are a folder with `__init__.py`, not only when they are a single `.py` file. That reading happens before any file in the venv runs. qafix14 pack.
- LATEST-02: a launcher that does not match the pinned pip template is refused before it is executed. qafix14 pack.
- SIB-01: on Debian and Ubuntu, the check also reads `dist-packages` directories the venv's `site` would use (`lib/python3/dist-packages`, `lib/pythonX.Y/dist-packages`, `local/lib/pythonX.Y/dist-packages`). Those directories are not treated as the standard library. qafix14 pack.
- SIB-02: an executable `.pth` line in site-packages is refused before the venv's Python can run it. Start the check with the base interpreter and `-I`, not with the venv's `python`. qafix14 pack.
- LATEST-03: two processes writing the first event-log line no longer hit `FileExistsError`. The log file is created while the append lock is held. The two lines are still sequence 1 and sequence 2. qafix14 pack.
- LATEST-04: lock files, `state.json`, and `approval.json` are opened without following a symlink. A symlink is refused. qafix14 pack.
- LATEST-05: the macOS default-TMPDIR shebang check compares the two directories while the temporary venv still exists. qafix14 pack.
- STRUCT-02: an execution snapshot is hashed while its bytes are copied. The holder keeps only a short prefix for the shebang check, instead of a second full copy of the file. A shebang line longer than 4096 bytes with no newline is refused. qafix14 pack.
- CC-01: contract validation refuses C0/C1/DEL/bidi/format characters in argv (and other contract strings); TTY display also escapes them. The bind line stays `Type 'APPROVE' to bind this approval:`. qafix13 pack.
- CC-02: installed-wheel shebang parent compare uses filesystem identity (samefile), so macOS `/var` vs `/private/var` TMPDIR aliases are accepted; a different venv that shares the base Python is still refused. qafix13 pack.
- CC-03: pretty `verify-signature` leads with `receipt_verification_error` when a MAC-valid receipt fails live check, and does not lead with a positive MAC/schema line when `ok` is false. Default JSON is unchanged. qafix13 pack.
- CC-04: launcher body after the shebang must byte-match one of the pinned exact pip console-script templates for `runspecimen.cli:main` (no regex): distlib `SCRIPT_TEMPLATE` (pip 21.2.4 on macOS 3.9.6; pip 24.x on GHA 3.9–3.12); pip 25.1–25.3 PipScriptMaker (`endswith('.exe')` then `[:-4]`); pip 26.0+ PipScriptMaker (`removesuffix('.exe')`, CPython 3.13/3.14 GHA ensurepip; RECORD length ~186 bytes including shebang). qafix13 pack.
- WH-01: verifier refuses unexpected files in the venv `bin/` directory (any `.py` / `.pyc` / `.so` / directory, including a stdlib-shadowing `json.py`). CPython 3.14 `python -m venv` also writes the exact `𝜋thon` symlink (U+1D70B MATHEMATICAL ITALIC SMALL PI + `thon`; gh-119535), which is allowlisted; lookalikes are refused. Provenance probes the real `runspecimen doctor` process for loaded-module origin realpaths. Stdlib-root compares resolve both sides so macOS `/var` vs `/private/var` aliases match. `python -m runspecimen` from an untrusted cwd is not a supported verified path. qafix13 pack.
- WH-02: every terminal-bound string from the contract, workspace, env, or receipts is escaped with the shared sanitizer (`escape_for_terminal`), including approve cwd/outputs, pretty errors, status, doctor, and `confirm_channel_note`. `_require_str` refuses control and bidi characters in contract strings (plain-English error). Refuse at validation and escape on display. qafix13 pack.
- WH-03: after approve, the job is launched with an explicit environment built from the bound `env_allowlist` values plus a documented minimal POSIX/Windows set (`HOME`, `PATH`, `LANG`, locale, `TZ`, `TMPDIR`, `USER`, `LOGNAME`, `TERM`, and Windows `SYSTEMROOT`/`SYSTEMDRIVE`/`WINDIR`/`COMSPEC`/`PATHEXT`). Parent `PYTHONPATH` / `PYTHONHOME` are not inherited. Run refuses if an allowlisted variable's current value differs from the bound value. Behaviour change. qafix13 pack.
- WH-04: `.runspecimen`, campaign, and run directories (and any symlinked component of that control-plane path) are refused. Writes use no-follow semantics where available. qafix13 pack.
- CC-05: verifier refuses any `__pycache__` / `.pyc` under the installed package, `PYTHONPYCACHEPREFIX` / `sys.pycache_prefix`, and sourceless bytecode; probe runs with `-I -B`. HUMAN-ACCEPTANCE installs with `pip install --no-compile` and `PYTHONDONTWRITEBYTECODE=1`. qafix13 pack.
- CC-06: signing copy no longer implies that signing prevents a forged approval or an execution. Signing with a key the agent can't access lets you check afterwards that a receipt is authentic, when a signature is required and checked; it does not stop a program running as you from adding a fake approval or running the job. D1/D2 stay fail-closed. Legacy receipts without a bound approval fail verify (schema 1 still parses). qafix13 pack.
- P3 about JSON: `runspecimen about` summary says plugins/agents cannot approve through the app, and that a program running as you that can edit RunSpecimen's files can still add a fake approval to the record. Default JSON for every other command is unchanged. qafix10 pack.
- P3 USER_GUIDE showcase: the showcase section leads with `scripts/refresh_showcase.py`, matching README. qafix10 pack.
- P3 schema matrix: receipt `schema_version: 2` is current; schema `1` still parses, then fails closed without a bound approval. qafix10 pack.
- P3 honesty: a program running as you that can edit RunSpecimen's files can still add a fake approval to the record. Signing with a key the agent can't access lets you check afterwards that a receipt is authentic, when a signature is required and checked; it does not stop a program running as you from adding a fake approval or running the job. qafix10 pack.
- BH-01/BH-02: `approval.json` is no longer a bearer token. Approve (and remote-confirm settle) append an `approval` event that carries a canonical hash of the approval document, covering every field `approval_is_valid` trusts plus `confirm_channel`, `confirm_evidence`, and `expires_at_unix`. Preflight and run recompute that hash and refuse unless it equals the latest chained approval event; expiry is taken from that event. `verify` is `ok:true` only with a bound approval event or a consistent holder receipt. A bound approval event is a recorded local step, not cryptographic proof of a human. `confirm_channel` is bound into `certificate_id` and is never displayed from an unbound side file. Only `local_tty_approve` and `remote_human_confirm` are accepted. Old receipts without a bound approval never verify silently. Receipt schema is now `2` (schema `1` still parses, then fails closed). The hash chain remains unkeyed: a program running as you that can edit RunSpecimen's files can still add a fake approval to the record. Signing with a key the agent can't access lets you check afterwards that a receipt is authentic, when a signature is required and checked; it does not stop a program running as you from adding a fake approval or running the job. qafix9 pack; honesty wording qafix10.
- BH-03: TTY re-approve while `phase=approved` (or `preflighted`) is a TTL refresh. Each refresh appends a new approval event; the latest governs. Remote confirm cannot refresh. qafix9 pack.
- BH-04: `--pretty run` does not show green OK or "Run completed" when `exit_code != 0`. It prints a yellow/neutral "Process finished with exit code N". Default JSON and CLI exit codes are unchanged. qafix9 pack.
- BH-05: `certificate.json` unknown top-level fields fail verify. qafix9 pack.
- BH-06: README showcase `verify` example leads with `scripts/refresh_showcase.py`. USER_GUIDE matches that order. qafix9 pack; USER_GUIDE qafix10.
- Docs honesty: RunSpecimen stops agents from approving through the app and makes planted or edited approvals show up as broken receipts. A program running as you that can edit RunSpecimen's files can still add a fake approval to the record. Signing with a key the agent can't access lets you check afterwards that a receipt is authentic, when a signature is required and checked; it does not stop a program running as you from adding a fake approval or running the job. qafix9 pack; honesty wording qafix10.
- QA-HOOKS-03: installed-wheel provenance trusts only the Python interpreter and its stdlib. Venv-local metadata is not trust (setuptools RECORD does not hash itself and is writable by the same attacker). The target venv refuses every executable `.pth` import (including leftover `distutils-precedence.pth`), importable sitecustomize/usercustomize outside stdlib, any non-stdlib `sys.meta_path` or `sys.path_hooks` entry, and every `_virtualenv*`. A stdlib finder is identified by its class living in a stdlib module whose realpath is under the interpreter's stdlib dir, not by name. HUMAN-ACCEPTANCE uninstalls setuptools after `python3 -m venv` and before the wheel. qafix8 pack (kept in qafix9).
- QA-HOOKS-01/02: installed-wheel provenance allows a `sys.meta_path` finder only by real class identity (stdlib importer, or `type(finder) is DistutilsMetaFinder` from the `_distutils_hack` module whose realpath is in the venv site-packages and whose bytes match setuptools RECORD). A finder that only claims `__module__ == '_distutils_hack'` is refused. Every `_virtualenv*` artifact is refused; HUMAN-ACCEPTANCE uses stdlib `python3 -m venv`, which creates none, and virtualenv hashes are not pinned. qafix7 pack.
- QA4 pretty CLI: holder-policy `--pretty` hint no longer says "Use the holder". Pretty `verify` states that signature checks are a separate `verify-signature` step with its trust inputs. Pretty formatters treat missing or non-boolean `ok` as failure and never render a success banner. Default JSON, first `RunSpecimen error:` line, N10 text, and exit codes are unchanged. qafix6 pack.
- HUMAN-ACCEPTANCE `rs_ok` now covers N8 (stop before N9 on failure). `rs_neg` requires the expected refusal as a complete line. Automated sheet execution covers N1–N7, N10, and the unknown-field check in bash and zsh; N3 failure still stops later steps. Linux CI installs zsh so those tests run (macOS 3.11 already has zsh).
- Provenance additionally imports remaining `runspecimen.*` modules after the first bind and refuses a non-stdlib `sys.meta_path` finder injected through a startup hook.
- Offline `release_check.py` unittest discovery timeout is 600s (was 300s). Darwin 3.11 with the packed suite plus two in-suite archive rebuilds was hitting the cap.
- Opt-in human CLI: `runspecimen quickstart` and `--pretty` / `--color` (before or after the subcommand). Default stdout is still sorted indented JSON; exit codes, hashes, and the TTY APPROVE gate are unchanged. The bind line remains `Type 'APPROVE' to bind this approval:`. `--pretty` refusals keep `RunSpecimen error: …` and add a next-step hint.
- Holder policies (`local` / `companion` / `dual`) share one typed-phrase refusal across approve, preflight, and postflight. N10 still prints `execution policy local has no typed-phrase fallback`. The TTY APPROVE claim is `on this computer`. Release-check compares a clean-venv install to the wheel RECORD. Linux CI runs Ed25519 tests with PyNaCl.
- `digest` help and the user guide no longer say ordinary `verify` checks HMAC/Ed25519 signatures. `verify` checks receipt integrity, the event chain, and live provenance. `verify-signature` checks those signatures with its required trust inputs. README `sign` / HMAC `verify-signature` examples include `--contract`. Codex install text is the local repository route; there is no public listing.
- Human acceptance creates a brand-new venv every run (`mktemp`, abort if the target exists) and compares installed `runspecimen` bytes to the pinned wheel zip. Version strings are not proof: the 2026-10-06-bump wheel reports the same `0.2.0rc15` and must fail that check. Provenance binds every loaded `runspecimen.*` origin (including `runspecimen.approve`) to the hashed installed member, refuses env-based launcher shebangs instead of guessing a sibling, and rejects sitecustomize and executable `.pth` imports that are not a known-safe exact body. The human sheet is pasteable in zsh and bash without word-splitting `$RS_SANITIZE` or a persisting `set -e`; every mandatory step prints `STEP <id> exit=<n>` and a missing launcher at N3 stops the procedure. Trusted-interpreter assumption is explicit. qafix5 pack.


- `approve` refuses a protected `execution_approval` policy immediately after `load_contract`, before the interactive TTY check, so a piped N10 still prints `execution policy local has no typed-phrase fallback`.
- Installed Secure Enclave admission is fail-closed, not undecided. The Store note in `docs/SUBMISSION.md` follows the 2026-09-28 Connect record (`READY_FOR_SALE` for **0.1.4 (9)**) and was not re-queried on 2026-10-06. `run_integration_complete` and `e2_closed` stay false.
- Exact-run approval checks expiry and the pinned holder id before signing, and an authorize that loses its request keeps the uncertain lease. A holder execute that fails before any child exists keeps that uncertain lease. Root-daemon Secure Enclave creation is unsupported on current Apple guidance. Installed admission stays closed. `run_integration_complete` and `e2_closed` stay false.
- `requirements_check` refuses a digest-valid passed report unless authenticity is receipt-bound and the final state is certifiable. Evidence pointers accept only a basename under `evidence_captures`. Postflight omits an attestation whose digest is not the current capture. The CLI does not claim a hardware human when it cannot collect a device signature. MCP `freshness_check` evaluates without writing `freshness_report.json`.
- Developer ID packaging accepts bundle id `com.darashkevich.runspecimen.holder` and pins that designated requirement when a Developer ID identity is supplied. Ad-hoc `codesign --sign -` is local stage smoke, not the product signature. That bundle id is not `production_verifier_pin()`.
- Usage import holds the workspace lease and refuses to replace a ledger whose digest changed. The dashboard evidence panel records a read-only load error instead of hiding a failed read. Unittest discovery copies the suite so it does not write `__init__.py` into the live tree. Packaged suites (`tests/__init__.py`) are imported from that sandbox copy; the live workspace stays importable for application code. ChatGPT independent re-QA at `6bb64d1`: 644 tests / 6 skip / 0 fail; R-01..R-06 closed. Installed Secure Enclave admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false.
- Release sdist rewrite now pins gzip mtime 0, numeric owner 0/0, empty uname/gname, sorted members, and 0644/0755 modes so archive bytes do not depend on the builder host. The wheel and plugin zip stay content-addressed separately. Installed Secure Enclave admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false.

### Evidence expansion (ADR-005) — review branch, not released

Local-first expansion answering: what was authorized, what ran, which
requirements were checked, what evidence supports results, and whether that
evidence still applies. See `docs/ADR-005-evidence-expansion.md`.

- Task manifests + provider-collected evidence reports (`unittest` / `pytest` /
  `command_status`); never trust agent-written `passed`.
- Freshness/applicability reports (separate from `verify`); stale marks, no
  history rewrite.
- Policy template fields + actionable refusals; NL notes stay visible;
  ambiguous stays advisory.
- Expanded `doctor` / `config inspect|preview|apply|export|rollback` (no silent
  sync).
- Decision registry with MCP/adapter search (no approve).
- Local tar snapshot create/preview/restore-to-separate-dir.
- Usage import/summarize (`local_json`); unknown ≠ zero; idempotent imports.
- Two-repo coordination readiness; workflow eval suite compare.
- `runspecimen scenes` ten-scene local demo (never types APPROVE).
- `freshness show` reads a stored report and does not recompute or write one. The native pane uses that command.
- Session restore keeps the last contract when it is a regular file inside the workspace, and the app stays running after the main window closes.
- Native Workflows cover snapshot, coordination, evaluation, scenes, configuration apply/export/rollback, decision capture, and usage import. Writes require confirmation. The Store build still has no browser dashboard.
- A confirmed workflow is claimed before its dialog dismisses, so cancellation cannot drop that claim, and a second confirm does not run it again. Engine output is read while the process is still running.

## 0.2.0rc15 - not published

Candidate identity for the integrated branch. Not tagged, not uploaded to PyPI, and not a replacement for the published `0.2.0rc14` bytes. Homebrew in this tree still pins the published sdist.

## 0.2.0rc14 - 2026-09-23

GitHub pre-release `v0.2.0-rc.14` and PyPI `0.2.0rc14` (identical bytes, checksum-only, not SLSA-attested). Do not publish draft `v0.2.0-rc.11`. Do not move `v0.2.0-rc.12` or `v0.2.0-rc.13`. Stable `0.2.0` gate remains not met.

### Antigravity CLI + Meta Muse Code adapters

- Add native Antigravity (`agy`) plugin under `plugins/runspecimen/antigravity/`
  (`plugin.json`, `mcp_config.json`, named `PreToolUse` hooks, skill, rules)
  with documented dual path vs enterprise Gemini CLI (`BeforeTool`) and
  `agy plugin import gemini`. Gallery **not** submitted.
- Extend `block_approve_gate.py` with `--format antigravity` and `toolCall`
  payload detection (decision/reason deny dialect).
- Add Meta Muse Code pack under `plugins/runspecimen/muse/` (skill + MCP
  fragment, no approve tool; PreToolUse gate example marked **beta**).
  Marketplace **not** submitted.
- Docs: cloud threads outside TTY trust boundary; one lease per approved run
  under multi-agent/worktrees; do not treat Muse `--yolo` /
  `--disable-approval` as RunSpecimen-compatible; companion `can_approve`
  remains false. Ledger updates in `docs/INTEGRATIONS.md` / `docs/SUBMISSION.md`.

### Independent QA fixes (#31)

- Demo reuse, approver identity, and sdist inspect fixes landed on main before
  this cut.

## 0.2.0rc13 - 2026-09-22

GitHub pre-release `v0.2.0-rc.13` and PyPI `0.2.0rc13` (identical bytes, checksum-only, not SLSA-attested). Do not publish draft `v0.2.0-rc.11`. Do not move `v0.2.0-rc.12`.

- Opt-in isolation backends `sandbox-exec` and `bwrap`. Default `none` does not confine the process. A declared backend that is missing fails closed. The receipt records what was applied and the residual risk. This is not an OS sandbox. The tool is identified by file hash. Validation does not execute it, and a tool replaced after approval is refused.
- Optional workspace-local `policy` file (hash-bound). `approver` records the local OS user. `runspecimen retain` copies an incident pack outside the workspace. No control plane and no uploader.
- Stdlib contract/path mutation tests, vertical templates, an adversarial first-run lease campaign, and a Homebrew formula that installs this sdist. Public tap: [`darashkevich/homebrew-runspecimen`](https://github.com/darashkevich/homebrew-runspecimen).
- `runspecimen digest` and `runspecimen diff` for recorded receipts. They do not replace `verify`.
- Dashboard skip link, contrast, reduced-motion auto-refresh, and isolation copy that matches the contract.

## 0.2.0rc12 - 2026-09-18 (published)

Published on GitHub as `v0.2.0-rc.12` and on PyPI as `0.2.0rc12` (identical bytes, checksum-only). **Do not publish** draft `v0.2.0-rc.11`
(`ecc1709`). See `docs/RELEASE_IDENTITY.md`.

### macOS app

- Fix local launch: the SwiftUI window could size to thousands of points and
  open off-screen (blank view, hidden CLI alert, Full Screen disabled). Clamp
  to the visible display, mark the window Full Screen-capable, keep CLI
  discovery failures on the in-window banner, and skip App Sandbox on local
  `--from-src` builds so the host-Python helper can run. Layout wraps on
  split / 13-inch Macs; iOS Observe uses a readable column and landscape.
  Undersized on-screen frames now grow to the window minimum.
- Store export gate now fail-closes on `codesign --verify --strict` for the
  archived app and nested helper, including a tamper-after-signing negative.
  Local Store `.pkg` export uses `installerSigningCertificate` plus the MAS
  profile **UUID** (the app profile correctly omits the installer cert).
- Fix `AppIcon.appiconset`: catalog filenames are real `icon_*@2x.png` files
  with matching pixel sizes (128@2x is 256px). `verify_app_icon.sh` checks
  Contents.json and a warning-free `actool` compile.
- Mac App Store **0.1.3 (8)** was submitted 2026-09-21 and later rejected. The package recorded as waiting after that rejection is **0.1.4 (9)** (see `apps/macos/asc-kit/STATUS.md`). Do not upload a replacement from this changelog.

### Packaging

- PyPI publish workflow consumes GitHub Release assets as identical bytes
  (no rebuild). This candidate remains checksum-only until SLSA attestations
  exist.

## 0.2.0rc11 - 2026-09-18 (unpublished identity; do not ship this tag)

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
  predecessor chips. Plugins still cannot approve, settle, or refuse through the app.
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
- Keep the dashboard read-only: it cannot approve or execute commands through the app, so the
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
