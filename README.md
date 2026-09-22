# RunSpecimen

RunSpecimen is a local safety and evidence layer for consequential agent-driven
research and engineering commands.

**Current package version (this branch):** `0.2.0rc13`  
**Release:** [v0.2.0-rc.13](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.13) / PyPI `runspecimen==0.2.0rc13` (identical bytes; checksum-only, not SLSA-attested).  
Do **not** publish draft `v0.2.0-rc.11` (points at `ecc1709`). Do **not** move `v0.2.0-rc.12`. See [docs/RELEASE_IDENTITY.md](docs/RELEASE_IDENTITY.md).

## Core promise

Exactly **one** approved, bounded run at a time, with:

1. **Approved provenance** — interactive TTY approval binds contract, source, and resolved executable hashes with expiry
2. **Crash-safe state** — atomic JSON state writes
3. **Mandatory postflight** — successor runs refuse an unpostflighted / failed predecessor
4. **Tamper-evident receipts** — append-only SHA-256 hash-chained event log + verifiable certificate

No watchers, no recurring scheduler, no parallel workers.

`0.2.0rc13` includes opt-in `isolation` (`none` by default), a workspace `policy` file, `retain`, `digest`, and `diff`. See [docs/USER_GUIDE.md](docs/USER_GUIDE.md). `none` does not confine the process. `sandbox-exec` and `bwrap` are not an OS sandbox. Published `0.2.0rc12` rejects `isolation` and `policy`.

## Requirements

- Python 3.9+
- POSIX (`fcntl` leases)
- Stdlib only (no third-party dependencies)

## Docs

- [About](docs/ABOUT.md) — what RunSpecimen does, lifecycle, safety model, dashboard role
- [User guide](docs/USER_GUIDE.md) — install, lifecycle, contracts, dashboard, plugins, troubleshooting
- [FAQ](docs/FAQ.md) — vs CI/sandbox/agents, TTY approval, verify-after-clone, parallelism, receipts
- [Product plan](docs/PRODUCT_PLAN.md) — invariants and roadmap
- [Market and distribution](docs/MARKET_AND_DISTRIBUTION.md) — wedge, channels, commercial sequence
- [Integrations](docs/INTEGRATIONS.md) — adapter status ledger + frontier-lab research
- [Marketing pitches](docs/MARKETING_PITCHES.md) — honest one-liners, elevators, CTAs
- [Grok tandem](docs/GROK_TANDEM.md) — external xAI Grok review log (Composio `GROK_*`)
- [Submission](docs/SUBMISSION.md) — marketplace submission checklist (Cursor/Codex/Claude/Grok)
- [Release identity](docs/RELEASE_IDENTITY.md) — live vs draft vs next tag; checksum-only vs attested
- [Threat model](docs/THREAT_MODEL.md) — trusted boundary and residual risks
- [Schema compatibility](docs/SCHEMA_COMPATIBILITY.md) — contract/receipt versions
- [Ed25519 receipts (optional)](docs/ED25519_RECEIPTS.md) — offline public-key verify
- [Phased roadmap](docs/ROADMAP_PHASED.md) — feature and UX pipeline
- [ADR-003 iOS companion observation](docs/ADR-003-ios-companion-observation.md) — remote observe / attention (Accepted defaults: loopback HTTP OK; LAN TLS + Tailscale preferred)
- [ADR-004 remote human confirm](docs/ADR-004-remote-human-confirm.md) — Mac-armed challenge + phone `APPROVE` (not TTY-equivalent; plugins cannot approve)
- [Incident bundle](docs/SPEC_INCIDENT_BUNDLE.md) — local Community evidence pack (`runspecimen bundle`); not a Veto vault
- [Remote confirm card](docs/SPEC_REMOTE_CONFIRM_CARD.md) — one-card iOS UX, refuse+reason, `confirm_channel` on verify
- [iOS Observe app](apps/ios/README.md) — `com.darashkevich.runspecimen.observe` (TestFlight/later)
- [macOS companion helper](apps/macos-companion/README.md) — `com.darashkevich.runspecimen.companion` (not MAS packaging / PR #6)
- [macOS app](apps/macos/README.md) — native SwiftUI companion (sandbox-first; see `APP_STORE.md`)

## Install

### From PyPI

```bash
python3 -m pip install runspecimen==0.2.0rc13
runspecimen --version
```

Pin the version. pip will not select an RC without `==0.2.0rc13`. The rc11 draft tag must stay unpublished.

PyPI project: [runspecimen 0.2.0rc13](https://pypi.org/project/runspecimen/0.2.0rc13/)

### From GitHub release

```bash
python3 -m pip install https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.13/runspecimen-0.2.0rc13-py3-none-any.whl
```

Or from source tarball:

```bash
python3 -m pip install https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.13/runspecimen-0.2.0rc13.tar.gz
```

Verify checksums: [SHA256SUMS](https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.13/SHA256SUMS)

### From local clone

```bash
git clone https://github.com/darashkevich/runspecimen
cd runspecimen
python3 -m pip install .
```

For development, prefer the bootstrap. It pins `setuptools>=77` and performs
a regular local install; this avoids an editable-install edge case in some
Python builds where the command is created but cannot import the package:

```bash
sh scripts/bootstrap_dev.sh
```

Or manually: `python3 -m pip install --upgrade 'setuptools>=77' wheel` then
`python3 -m pip install --no-build-isolation .`. Stock setuptools before 77
rejects the project metadata used by `scripts/release_check.py`. Re-run the
install after source edits.

Check the host and contract before approval:

```bash
runspecimen doctor --workspace .
runspecimen validate --workspace . --contract examples/demo_contract.json
```

Create a fresh, unapproved demo workspace without modifying an existing
directory:

```bash
runspecimen init-demo --workspace ./runspecimen-demo
```

## Typical sequence

```bash
# 1) Bind approval on a real TTY (refuses pipes/CI without a TTY)
runspecimen approve --workspace . --contract examples/demo_contract.json

# 2) Optional explicit preflight
runspecimen preflight --workspace . --contract examples/demo_contract.json

# 3) Execute one bounded run (reacquires lease + rechecks under lease)
runspecimen run --workspace . --contract examples/demo_contract.json

# 4) Assert outcomes and issue certificate (required before a successor)
runspecimen postflight --workspace . --contract examples/demo_contract.json

# 5) Verify receipts (requires contract; rehashes live contract+source+runtime)
runspecimen verify --workspace . --contract examples/demo_contract.json \
  --campaign-id demo-campaign --run-id run-001
runspecimen status --workspace . --campaign-id demo-campaign --run-id run-001

# Optional: local incident pack (Community). Never a 7-day Veto vault.
runspecimen bundle --workspace . --campaign-id demo-campaign --run-id run-001 \
  --out /tmp/rs-incident --contract examples/demo_contract.json
```

## Local dashboard for agent-host users

Open a contract-scoped dashboard from a terminal, or ask the installed
RunSpecimen integration (Codex / Cursor / Claude Code / Grok Build / Gemini CLI /
Junie / Windsurf) to do so:

```bash
runspecimen dashboard --workspace . --contract examples/demo_contract.json --open
```

`dashboard` blocks in the foreground while it serves HTTP. Background it
(`&`), detach it, or use a separate terminal if you still need the shell for
`approve` / lifecycle commands (agents should not wait on it in the main turn).

It binds only to `127.0.0.1`, has no remote service or telemetry, and is
read-only: it shows an About overview, the current phase, approval/lease/receipt
evidence, and the exact lifecycle commands. It cannot approve or execute a run.
This keeps the real-TTY approval gate and the CLI enforcement boundary intact
while making the workflow visible in the browser. Docs links open the published
About, User guide, and FAQ on GitHub. CLI shortcut: `runspecimen about`.

### Showcase receipt

`examples/showcase/` holds a regeneratable postflight receipt with
`outputs/result.json`. Verify it with:

```bash
runspecimen verify --workspace examples/showcase \
  --contract examples/showcase/contract.json \
  --campaign-id showcase-campaign --run-id run-001
```

Refresh without a TTY (uses the library test hook `skip_tty_check`; not for
production approvals): `python3 scripts/refresh_showcase.py`. Interactive TTY
path: `scripts/demo_rc.sh`.

Any local `/.runspecimen/runs/demo-campaign/run-001` left from earlier RCs is
**historical / pre-`runtime` certificate** and is **not** verifiable on rc2.

## Contract surface (v1)

See `examples/demo_contract.json`. Important fields:

| Field | Role |
| --- | --- |
| `argv` | Executed as an argument vector (`shell=False` always) |
| `source.roots` / `excludes` | Deterministic source hashing / provenance |
| `outputs.required` | Must be absent at preflight; present at postflight when required |
| `caps.*` | Wall timeout + bounded stdout/stderr capture (hard tool maxima apply) |
| `approval.ttl_sec` | Approval expiry bound into the approval document |
| `predecessor` | Gate on prior run postflight / failure |
| `postflight.*` | Exit code, output existence/SHA, JSON field equality, source unchanged |

Every path involved in an output existence, SHA-256, or JSON assertion must be
absent before launch and is hashed into the receipt after it passes.

## State layout

Per run under `{workspace}/.runspecimen/runs/{campaign_id}/{run_id}/`:

- `approval.json` — bound hashes + expiry
- `state.json` — atomic phase document
- `events.jsonl` — hash-chained append-only log (`events.append.lock` serializes appends)
- `stdout.capture` / `stderr.capture` — bounded captures
- `certificate.json` — postflight receipt

Workspace-wide execution lease: `{workspace}/.runspecimen/execution.lock` (held by
approve/preflight/run/postflight; status is read-only).

## New in rc9: Missing features implemented

### Crash recovery with audited human decisions

When a run crashes mid-execution, use the new recovery commands:

```bash
# Check if a run needs recovery
runspecimen recovery-status --workspace . --campaign-id demo --run-id run-001

# Abandon a crashed run (TTY confirmation required)
runspecimen abandon --workspace . --campaign-id demo --run-id run-001
```

### Authenticated receipts (shared-secret)

Authenticate certificates with local HMAC keys for tamper detection:

```bash
# Generate an authentication key
runspecimen keygen --workspace .

# List available keys
runspecimen list-keys --workspace .

# Authenticate a certificate (creates .signed.json with MAC)
runspecimen sign --workspace . --key-id <key-id> --certificate path/to/certificate.json

# Verify an authenticated certificate
runspecimen verify-signature --workspace . --key-id <key-id> --signed path/to/certificate.signed.json
```

**Shared-secret limitation**: HMAC-SHA256 uses the same key for authentication
and verification. Anyone with the key can forge certificates. For independent
third-party verification without sharing secrets, use asymmetric cryptography.

### Extended runtime provenance

Contracts now support a `runtime` field for enhanced provenance binding:

```json
{
  "runtime": {
    "env_allowlist": ["PATH", "HOME", "PYTHONPATH"],
    "interpreter": "/usr/bin/python3",
    "capture_libs": true
  }
}
```

This binds environment variables, interpreter, and optionally linked libraries
into the certificate's `runtime_id`.

## Release-candidate limitations

- Default authenticated receipts use HMAC-SHA256 shared-secret MACs. Anyone with
  the key can forge certificates. Optional Ed25519 offline public-key
  verification is available via `pip install 'runspecimen[ed25519]'` (see
  `docs/ED25519_RECEIPTS.md`). Trusted Ed25519 verify requires an external
  public-key trust anchor; a key embedded only in the receipt is never enough
  for `ok: true`. Soft keys on disk are not absolute non-repudiation.
- Default `isolation.backend` is `none`: the workload is not confined. Published
  `0.2.0rc13` accepts opt-in `sandbox-exec` and `bwrap` when the contract names
  them and the tool is installed; a missing tool fails closed. Those backends
  can confine writes to the workspace and deny network. They are not an OS
  sandbox. `bwrap` was argument-tested (argv wrapping). It was not executed on
  macOS. A real Linux execution test may land separately. CPU, memory, and
  child-process limits are not part of either backend. Published `0.2.0rc12`
  rejects the `isolation` field. Optional Ed25519 is not an OS sandbox. A
  companion app’s UI sandbox (if any) does not imply payload confinement.

- RunSpecimen does not schedule work and does not prove scientific claims.
- The resolved executable or interpreter is automatically hashed. Native
  libraries, environment variables, and input datasets still need to be placed
  in `source.roots` or otherwise asserted by the workload.
- This release is licensed under Apache-2.0. The CLI remains the enforcement
  boundary; Codex, Cursor, Claude Code, Grok Build, Gemini CLI, Junie, and
  Windsurf integrations are
  constrained adapters to it (no auto-approve).

## Non-goals

- **Not an OS sandbox.** Process groups, wall clocks, and path containment are orchestration controls, not a security boundary against a hostile payload.
- **Finite computation is not proof.** A green postflight and a valid certificate mean the approved contract ran under recorded provenance and assertions passed — not that the scientific/engineering claim is true.
- **Not a job scheduler.** No cron, no watchers, no fan-out workers, no multi-run parallelism inside one lease domain.
- **Not a remote execution fabric.** Local workspace only.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

For the complete release-candidate gate, run `python3 scripts/release_check.py`.
Day-to-day usage: [about](docs/ABOUT.md), [user guide](docs/USER_GUIDE.md), and [FAQ](docs/FAQ.md).
Before sensitive work: [threat model](docs/THREAT_MODEL.md),
[release checklist](docs/RELEASE_CHECKLIST.md), and [security policy](SECURITY.md).
