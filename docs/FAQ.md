# RunSpecimen FAQ

Short answers grounded in the current CLI and product constraints. Product
overview: [ABOUT.md](ABOUT.md). Deeper how-to: [USER_GUIDE.md](USER_GUIDE.md).

## How is this different from ChatGPT / an agent chat?

Chat answers and tool suggestions are not an execution gate. RunSpecimen sits
**beside** the agent: a human TTY approval binds the contract, source tree, and
resolved executable; a workspace lease allows only one mutating lifecycle step
at a time; postflight and verify produce a local receipt. The agent may draft
contracts and run preflight/run/postflight/verify after you approve—it must not
type `APPROVE` for you.

## How is this different from CI?

CI usually runs many jobs, often without interactive human binding of exact
local source + binary hashes, and is oriented to remote pipelines. RunSpecimen
is **local**, **one run at a time** per workspace lease, with mandatory
interactive approval expiry and predecessor gating before the next campaign
step. It does not replace CI; you can still verify receipts in CI if you ship
the workspace evidence with matching host runtime expectations.

## How is this different from a sandbox?

A sandbox limits what a process can reach. RunSpecimen records whether an
approved, exclusive, bounded step happened and whether declared outcomes
passed. It is **not** an OS sandbox.

The default `isolation.backend` is `none`: wall clock, capture size,
path-inside-workspace checks, and process-group kill. No filesystem or network
confinement.

Opt-in `sandbox-exec` (macOS, if `sandbox-exec` is on PATH) and `bwrap` (Linux,
if `bwrap` is on PATH) confine writes to the workspace and deny network unless
the contract sets `isolation.network` to true. A declared backend that is not
installed fails closed. The receipt field `isolation.residual` states what
that profile still allows, including host reads. CPU and memory limits are
not part of either backend.

## Why does approval require a TTY?

Unattended or piped approval would let an agent or script bind a consequential
command without a human at the keyboard. `approve` requires interactive stdin
**and** stdout TTYs and the exact phrase `APPROVE`. Test-only hooks
(`skip_tty_check`) exist for regenerating demos; they are not the production
path.

## Can agents approve runs?

**No.** Codex/Cursor plugins and the narrow adapter
(`about`, `dashboard`, `doctor`, `validate`, `status`, `preflight`, `run`, `postflight`,
`verify`) deliberately exclude `approve`. A human must run
`runspecimen approve --workspace … --contract …` in a real terminal.

## Why does verify fail after I clone the repo?

CLI `verify` rehashes **live** contract bytes, source, outputs, and **runtime**
(resolved interpreter/executable on this machine). Showcase receipts and any
certificate that bound another host’s Python binary will fail until you refresh
on the new host (`python3 scripts/refresh_showcase.py` for the example, or a
full approve → run → postflight path). Also remember: contract hash is raw
file bytes—line endings or whitespace edits change it.

## Can I run two jobs in parallel?

**Not in the same workspace.** One exclusive `fcntl` lease covers the whole
workspace for `approve` / `preflight` / `run` / `postflight`, regardless of
`campaign_id` or `run_id`. Use separate workspaces (separate lease domains) if
you need concurrency. There is no built-in worker pool or scheduler.

## Is the hash chain a signature?

**No.** Events and certificates are SHA-256 hash-chained and locally
recomputable. They detect casual tampering of the evidence set, but a
privileged attacker who can rewrite the whole workspace can fabricate a new
history.

The default `sign` command provides HMAC-SHA256 authentication (a shared-secret
Message Authentication Code), not digital signatures. Anyone with the key
can both verify and forge authenticated certificates. Optional Ed25519 signing
(`pip install 'runspecimen[ed25519]'`, `--scheme ed25519`) enables offline
public-key verification without sharing the private key; trusted success still
requires an externally trusted public key (not a key embedded only in the
receipt). See [ED25519_RECEIPTS.md](ED25519_RECEIPTS.md). Soft keys on disk are
not absolute non-repudiation, and Ed25519 is not an OS sandbox.

## How do I integrate with my research script?

Point `argv` at your interpreter and script (`shell=False`), put code and
material inputs under `source.roots`, declare outputs and postflight
assertions, use a fresh `run_id` per attempt, and chain steps with
`predecessor` when needed. See [USER_GUIDE.md](USER_GUIDE.md#integrating-a-research-script).

## Where is the GitHub repo / what version am I on?

- Repository: https://github.com/darashkevich/runspecimen
- Check installed CLI: `runspecimen --version` (engine package version, e.g.
  `0.2.0rc12`, also the published PyPI pin)

## Is the dashboard safe to leave open?

It listens on **loopback only** (`127.0.0.1`), has no remote service or
telemetry, and is **read-only** (no approve/run APIs). It still exposes local
run evidence to anything that can reach that port on your machine—treat it like
other localhost debug UIs. It **blocks** the foreground shell; background or
detach it so approval and lifecycle commands stay usable. It does not replace
TTY approval. A certificate shown as issued is recorded history only—the
dashboard never marks live verification green; run `runspecimen verify` in a
terminal.

## How do contract and receipt versions work?

Contracts require `"version": 1`. Receipts may omit `schema_version` (legacy v1)
or set `"schema_version": 1`. Unknown versions fail closed. See
[SCHEMA_COMPATIBILITY.md](SCHEMA_COMPATIBILITY.md).

## HMAC vs Ed25519 — what do authenticated receipts prove?

- **HMAC** (`keygen` / `sign` default): shared-secret MAC. Anyone with the key can
  forge. Useful for controlled sharing, not independent third-party trust.
- **Ed25519** (optional `pip install 'runspecimen[ed25519]'`, `--scheme ed25519`):
  offline public-key verification without sharing the private key. Trusted
  success requires an external trust anchor (`--public-key` or workspace
  `--key-id`); a public key embedded only in the receipt proves consistency,
  not trust. Soft-key custody ≠ absolute non-repudiation; not scientific proof;
  not a sandbox. See [ED25519_RECEIPTS.md](ED25519_RECEIPTS.md).
