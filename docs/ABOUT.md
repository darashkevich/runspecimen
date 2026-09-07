# About RunSpecimen

RunSpecimen is a local safety and evidence layer for consequential
agent-driven research and engineering commands. It enforces **exactly one**
human-approved, bounded run at a time in a workspace, then records a
tamper-evident receipt of what happened.

## Core lifecycle

1. **Approve** — a human types `APPROVE` on a real TTY, binding contract,
   source, and resolved executable hashes with an expiry.
2. **Preflight** — recheck approval freshness, provenance, outputs, and the
   workspace lease before launch.
3. **Run** — execute the exact declared argument vector once, within wall and
   capture bounds.
4. **Postflight** — assert outcomes and issue a certificate (required before a
   successor run).
5. **Verify** — rehash live contract, source, runtime, outputs, and the event
   chain against the receipt.

## Safety model

RunSpecimen records evidence; it does **not** sandbox the payload from the OS.

- Interactive TTY approval (agents must not type `APPROVE`)
- Workspace execution lease (one mutating lifecycle step at a time)
- Hash-chained append-only event log
- Verifiable local certificates after successful postflight

Wall timeout, process-group cleanup, and path-inside-workspace checks are
orchestration controls, not isolation against a hostile program.

## Dashboard

`runspecimen dashboard` opens a **loopback-only, read-only** guide for one
contract. It shows phase, evidence, and copyable CLI commands. It cannot
approve or execute a run. Approval stays a terminal action; the CLI remains
the enforcement boundary.

## Learn more

- [User guide](USER_GUIDE.md) — install, contracts, lifecycle, plugins
- [FAQ](FAQ.md) — vs CI / sandboxes / agents, TTY approval, verify-after-clone

Installed CLI shortcut: `runspecimen about`.
