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

RunSpecimen records evidence. The default isolation backend is `none`: it does
**not** sandbox the payload from the OS.

- Interactive TTY approval (agents cannot approve through the app; planted or edited approvals become broken receipts)
- Workspace execution lease (one mutating lifecycle step at a time)
- Hash-chained append-only event log
- Verifiable local certificates after successful postflight
- Opt-in `sandbox-exec` or `bwrap` when the contract names them and the tool is installed. A missing tool fails closed. Neither backend is an OS sandbox. `0.2.0rc14` accepts the `isolation` field. Published `0.2.0rc12` does not.

Wall timeout, process-group cleanup, and path-inside-workspace checks are
orchestration controls. They confine a hostile program only when a receipt
shows an enforced isolation backend, and only to the degree `isolation.residual` states.

## Dashboard

`runspecimen dashboard` opens a **loopback-only, read-only** guide for one
contract. It shows phase, evidence, and copyable CLI commands. It cannot
approve or execute a run through the app. Approval stays a terminal action; the CLI remains
the enforcement boundary. The hash chain is unkeyed: a program running as you
that can edit RunSpecimen's files can still add a fake approval to the record.
Signing with a key the agent can't access lets you check afterwards that a
receipt is authentic, when a signature is required and checked; it does not
stop a program running as you from adding a fake approval or running the job.

## Learn more

- [User guide](USER_GUIDE.md) — install, contracts, lifecycle, plugins
- [FAQ](FAQ.md) — vs CI / sandboxes / agents, TTY approval, verify-after-clone

Installed CLI shortcut: `runspecimen about`.
