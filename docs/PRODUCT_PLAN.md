# RunSpecimen product plan

RunSpecimen is a temporary working name. The current repository is an alpha
implementation of the local enforcement engine, not a production security
boundary.

## Product promise

For a local unattended research or engineering campaign, execute exactly one
human-approved, bounded step against approved provenance; refuse unsafe or
out-of-order advancement; verify declared outcomes; emit a receipt that can be
checked independently.

## Frozen invariants

1. One execution lease per workspace, regardless of campaign or run ID.
2. Approval requires a human TTY and binds contract plus source hashes with an
   expiry.
3. Launch rechecks approval, provenance, predecessor, outputs, and lease.
4. A run ID cannot be reused after execution starts.
5. A successor requires a valid postflighted predecessor receipt.
6. Every asserted output starts absent, passes its assertion, and is hashed into
   the receipt.
7. Timeout or orchestration failure can never become a certified success.
8. No watcher, scheduler, controller, automatic approval, or parallel worker is
   part of the engine.
9. The engine states plainly that bounded computation is evidence, not proof.

## Milestone 0: alpha engine — implemented

- JSON run contracts and strict validation.
- Deterministic source hashing with fail-closed symlink handling.
- TTY approval, workspace-wide `fcntl` lease, atomic state, bounded captures,
  timeout process-group cleanup, predecessor gating, exact postflight checks,
  hash-chained events, certificates, status, and live verification.
- Adversarial tests for concurrent runs/appends, stale approvals, path escape,
  timeout, provenance drift, receipt/output tampering, and predecessor tampering.

Exit condition: a reproducible local demo reaches a verified receipt and all
tests pass.

## Milestone 1: production-grade provenance

- Bind the resolved executable, interpreter, native libraries, environment
  allowlist, input datasets, and engine build to the contract and receipt.
- Add CPU, memory, process-count, disk, and optional network policy through a
  platform-specific containment adapter.
- Sign receipts with a local hardware-backed or team-managed key and support an
  append-only transparency destination.
- Add crash-recovery commands with explicit, audited human decisions.
- Fuzz contract parsing, state transitions, paths, and interruption points.
- Define migration and compatibility rules for contract and receipt versions.

Exit condition: an external reviewer can reproduce a receipt, detect changes to
all declared runtime inputs, and validate the threat model.

## Milestone 2: free ecosystem adapters

- Cursor Marketplace plugin: skill, commands, lifecycle hooks, and a narrow MCP
  adapter.
- Codex Plugin Directory package: the same contract workflow and narrow local
  adapter.
- Claude Code plugin and Homebrew distribution next.
- Adapters remain free and never contain a generic shell escape hatch.

Exit condition: a new user can install from an agent marketplace and produce a
verified local receipt in under ten minutes.

## Milestone 3: paid Team pilot

- Shared, versioned policies and contract templates.
- Delegated approvals with identity and separation of duties.
- Signed receipt export, retention, incident bundles, and support.
- Five design partners in computational research, ML evaluation, security,
  quant/backtesting, or regulated engineering.

Exit condition: at least three teams pay for evidence sharing or policy control,
not merely command blocking.

## Explicitly postponed

- Generic agent observability.
- A general-purpose shell firewall.
- Hosted remote execution.
- A dashboard without a repeated paid requirement.
- Automatic retry, refill, scheduling, or multi-worker orchestration.

These are crowded categories or conflict with the product's narrow assurance
promise. RunSpecimen should integrate with sandboxes and firewalls instead of
pretending to replace them.
