# RunSpecimen

RunSpecimen is a local safety and evidence layer for AI-driven research and engineering commands.

When you let an AI agent run commands on your machine, you want to know exactly what was approved, what ran, and whether it succeeded. RunSpecimen makes sure one human-approved command runs at a time and creates a receipt you can check later.

**Current version:** `0.2.0rc15`  
**GitHub release:** [v0.2.0-rc.15](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.15)  
**PyPI:** `runspecimen==0.2.0rc15`  
**Homebrew:** `brew install darashkevich/runspecimen/runspecimen`

<details>
<summary>Release identity details</summary>

- **Previous release:** [v0.2.0-rc.14](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.14) / PyPI `runspecimen==0.2.0rc14` (identical bytes; checksum-only, not SLSA-attested).
- **Mac App Store:** approved **0.1.4 (9)** freezes engine `0.2.0rc14` and is guarantee (1) only. The local label on this branch is **0.1.5 (13)** and is not an upload.
- Do **not** publish draft `v0.2.0-rc.11` (points at `ecc1709`). Do **not** move `v0.2.0-rc.12`. See [docs/RELEASE_IDENTITY.md](docs/RELEASE_IDENTITY.md).
</details>

## What it does

RunSpecimen ensures exactly **one** approved command runs at a time, with a clear record of what happened:

1. **You approve first** — type `APPROVE` in a terminal to authorize the command, binding the contract, source code, and executable with an expiry
2. **One run at a time** — a workspace lock prevents duplicate or overlapping runs
3. **Check results** — mandatory postflight step verifies outputs before allowing the next command
4. **Keep receipts** — creates a tamper-evident log you can verify later

No background watchers, no recurring jobs, no parallel workers.

<details>
<summary>What's new in 0.2.0rc15</summary>

This release adds evidence-expansion commands for richer verification workflows:

- **`requirements`** — check that declared requirements are met
- **`freshness`** — assess whether evidence still applies to current state
- **`scenes`** — run a local demo walkthrough
- **`config`** — inspect, preview, apply, export, and rollback configuration
- **`usage`** — import and summarize usage data

Also includes opt-in `isolation` backends (`sandbox-exec` on macOS, `bwrap` on Linux), workspace `policy` files, `retain`, `digest`, and `diff`. The default isolation backend is `none`, which does not confine the process. See [docs/USER_GUIDE.md](docs/USER_GUIDE.md).
</details>

<details>
<summary>Technical details: hash chains and state</summary>

- Crash-safe atomic JSON state writes
- Append-only SHA-256 hash-chained event log plus verifiable certificate
- The chain is unkeyed: a program with write access to RunSpecimen's files can fabricate consistent evidence. Signing with a key the agent can't access lets you check afterwards that a receipt is authentic.
</details>

## Requirements

- Python 3.9+
- POSIX (`fcntl` leases)
- Stdlib only (no third-party dependencies)

## Docs

- [About](docs/ABOUT.md) — what RunSpecimen does, lifecycle, safety model, dashboard role
- [User guide](docs/USER_GUIDE.md) — install, lifecycle, contracts, dashboard, plugins, troubleshooting
- [CLI and macOS UX review](docs/ux/CLI_AND_MACOS_REVIEW.md) — presentation findings; `--pretty` is opt-in JSON stays default
- [FAQ](docs/FAQ.md) — vs CI/sandbox/agents, TTY approval, verify-after-clone, parallelism, receipts
- [Product plan](docs/PRODUCT_PLAN.md) — invariants and roadmap
- [Market and distribution](docs/MARKET_AND_DISTRIBUTION.md) — wedge, channels, commercial sequence
- [Integrations](docs/INTEGRATIONS.md) — adapter status ledger + frontier-lab research
- [Marketing pitches](docs/MARKETING_PITCHES.md) — honest one-liners, elevators, CTAs
- [Submission](docs/SUBMISSION.md) — marketplace submission checklist (Cursor/Codex/Claude/Grok)
- [Release identity](docs/RELEASE_IDENTITY.md) — live vs draft vs next tag; checksum-only vs attested
- [Threat model](docs/THREAT_MODEL.md) — trusted boundary and residual risks
- [Schema compatibility](docs/SCHEMA_COMPATIBILITY.md) — contract/receipt versions
- [Ed25519 receipts (optional)](docs/ED25519_RECEIPTS.md) — offline public-key verify
- [Phased roadmap](docs/ROADMAP_PHASED.md) — feature and UX pipeline
- [ADR-003 iOS companion observation](docs/ADR-003-ios-companion-observation.md) — remote observe / attention (Accepted defaults: loopback HTTP OK; LAN TLS + Tailscale preferred)
- [ADR-004 remote human confirm](docs/ADR-004-remote-human-confirm.md) — Mac-armed challenge + phone `APPROVE` (not TTY-equivalent; plugins cannot approve through the app)
- [Incident bundle](docs/SPEC_INCIDENT_BUNDLE.md) — local Community evidence pack (`runspecimen bundle`); not a Veto vault
- [Remote confirm card](docs/SPEC_REMOTE_CONFIRM_CARD.md) — one-card iOS UX, refuse+reason, `confirm_channel` on verify
- [iOS Observe app](apps/ios/README.md) — `com.darashkevich.runspecimen.observe` (TestFlight/later)
- [macOS companion helper](apps/macos-companion/README.md) — `com.darashkevich.runspecimen.companion` (not MAS packaging / PR #6)
- [macOS app](apps/macos/README.md) — native SwiftUI companion (sandbox-first; see `APP_STORE.md`)

## Install

### Homebrew (recommended on macOS)

```bash
brew tap darashkevich/runspecimen
brew install runspecimen
runspecimen --version   # should show 0.2.0rc15
```

Or as a one-liner: `brew install darashkevich/runspecimen/runspecimen`.

Tap: [darashkevich/homebrew-runspecimen](https://github.com/darashkevich/homebrew-runspecimen).

<details>
<summary>Homebrew version troubleshooting</summary>

If `runspecimen --version` shows an older version than expected, check `which -a runspecimen`. An old pip install at `~/.local/bin/runspecimen` often shadows `/opt/homebrew/bin/runspecimen`. Rename the old shim and rehash:

```bash
mv ~/.local/bin/runspecimen ~/.local/bin/runspecimen.bak-shadow
hash -r
runspecimen --version
```

Details in [docs/FAQ.md](docs/FAQ.md#why-does-runspecimen---version-show-an-older-build-than-homebrew).
</details>

### pip or pipx

```bash
pip install runspecimen==0.2.0rc15
# or with pipx for isolated installs:
pipx install runspecimen==0.2.0rc15

runspecimen --version   # should show 0.2.0rc15
```

Pin the version explicitly. pip will not select an RC without `==0.2.0rc15`.

PyPI project: [runspecimen 0.2.0rc15](https://pypi.org/project/runspecimen/0.2.0rc15/)

### From GitHub release

```bash
pip install https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.15/runspecimen-0.2.0rc15-py3-none-any.whl
```

Or from source tarball:

```bash
pip install https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.15/runspecimen-0.2.0rc15.tar.gz
```

Verify checksums: [SHA256SUMS](https://github.com/darashkevich/runspecimen/releases/download/v0.2.0-rc.15/SHA256SUMS)

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

Check the host and contract before approval. After a **pip install**, there is
no repository `examples/` tree in the current directory — create one with
`init-demo` (or clone the repo and use `examples/demo_contract.json`):

```bash
runspecimen init-demo --workspace ./runspecimen-demo
cd runspecimen-demo
runspecimen doctor --workspace .
runspecimen validate --workspace . --contract contract.json
```

From a git checkout you can instead validate the in-tree example:

```bash
runspecimen doctor --workspace .
runspecimen validate --workspace . --contract examples/demo_contract.json
```

## Typical sequence

Prefer `init-demo` after a pip or Homebrew install. `examples/showcase/` exists in a git checkout only; create a workspace with `init-demo` before running commands that name those files. The block below uses the in-tree example path (git clone) or substitute `contract.json` inside an `init-demo` workspace:

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

JSON is the default output. For a copy-paste first run, `runspecimen quickstart`.
For a human table of the same result, pass `--pretty` (exit codes and JSON
defaults stay unchanged): `runspecimen --pretty status --workspace . --campaign-id demo-campaign --run-id run-001`.

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
evidence, and the exact lifecycle commands. It cannot approve or execute a run
through the app.
This keeps the real-TTY approval gate and the CLI enforcement boundary intact
while making the workflow visible in the browser. Docs links open the published
About, User guide, and FAQ on GitHub. CLI shortcut: `runspecimen about`.

RunSpecimen stops agents from approving through the app. Inconsistent edits to
local records can be detected, but a program that can rewrite those files can
fabricate consistent evidence. A program running as you that can edit
RunSpecimen's files can still add a fake approval to the record. Signing
with a key the agent can't access lets you check afterwards that a receipt is
authentic, when a signature is required and checked; it does not stop a
program running as you from adding a fake approval or running the job.

### Showcase receipt

`examples/showcase/` holds a regeneratable postflight receipt with
`outputs/result.json`. Live `verify` binds this machine's interpreter hash, so
lead with a refresh (or treat the committed receipt as host-specific):

```bash
python3 scripts/refresh_showcase.py
runspecimen verify --workspace examples/showcase \
  --contract examples/showcase/contract.json \
  --campaign-id showcase-campaign --run-id run-001
```

`refresh_showcase.py` uses the library test hook `skip_tty_check`; that is not
a production approval. Interactive TTY path: `scripts/demo_rc.sh`.

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

- `approval.json` — bound hashes + expiry (must match the latest chained `approval` event; the file alone is not a token)
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
runspecimen sign --workspace . --key-id <key-id> --certificate path/to/certificate.json --contract path/to/contract.json

# Verify an authenticated certificate
runspecimen verify-signature --workspace . --key-id <key-id> --signed path/to/certificate.signed.json --contract path/to/contract.json
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

## What approval means

When you type `APPROVE`, you're confirming:
- You've reviewed the command, arguments, and working directory
- You accept the source code that will run
- You understand the expiry time (the approval is temporary)

The AI agent can draft contracts and run lifecycle commands, but **only a human can approve**. Plugins for Cursor, Codex, Claude Code, and others deliberately exclude the approve command.

<details>
<summary>Security considerations</summary>

RunSpecimen stops agents from approving through the app. However:

- A program running as you that can edit RunSpecimen's files can still add a fake approval to the record
- Signing with a key the agent can't access lets you check afterwards that a receipt is authentic
- Default receipts use HMAC-SHA256 (shared-secret). Optional Ed25519 (`pip install 'runspecimen[ed25519]'`) enables offline public-key verification. See [docs/ED25519_RECEIPTS.md](docs/ED25519_RECEIPTS.md).
</details>

## Release-candidate limitations

**Not an OS sandbox.** The default isolation backend is `none`, which does not confine the workload. Opt-in `sandbox-exec` (macOS) and `bwrap` (Linux) can restrict filesystem and network access, but they are not a security boundary against a hostile payload. Use a container when you need real isolation.

**Work in progress.** The following features are under development and not complete in this release:
- Secure Enclave integration for hardware-backed signing
- Phone pairing for remote confirmation
- Exact-run integration (the `run_integration_complete` flag is false)

<details>
<summary>Other limitations</summary>

- RunSpecimen does not schedule work and does not prove scientific claims
- The resolved executable or interpreter is automatically hashed; native libraries, environment variables, and input datasets still need to be placed in `source.roots` or otherwise asserted by the workload
- This release is licensed under Apache-2.0
- The CLI remains the enforcement boundary; marketplace integrations are constrained adapters to it (no auto-approve)
</details>

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
