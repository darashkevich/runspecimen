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
passed. It is **not** an OS sandbox: no CPU/memory/network/filesystem
containment beyond wall clock, capture size, path-inside-workspace checks, and
process-group kill on timeout. Use a container or stronger isolation for
untrusted payloads.

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
history. External signing / transparency is on the roadmap, not in this RC.

## How do I integrate with my research script?

Point `argv` at your interpreter and script (`shell=False`), put code and
material inputs under `source.roots`, declare outputs and postflight
assertions, use a fresh `run_id` per attempt, and chain steps with
`predecessor` when needed. See [USER_GUIDE.md](USER_GUIDE.md#integrating-a-research-script).

## Where is the GitHub repo / what version am I on?

- Repository: https://github.com/darashkevich/runspecimen
- Check installed CLI: `runspecimen --version` (engine package version, e.g.
  `0.2.0rc4`)

## Is the dashboard safe to leave open?

It listens on **loopback only** (`127.0.0.1`), has no remote service or
telemetry, and is **read-only** (no approve/run APIs). It still exposes local
run evidence to anything that can reach that port on your machine—treat it like
other localhost debug UIs. It **blocks** the foreground shell; background or
detach it so approval and lifecycle commands stay usable. It does not replace
TTY approval.
