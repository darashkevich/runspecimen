# RunSpecimen

RunSpecimen is a local safety and evidence layer for consequential agent-driven
research and engineering commands. This repository contains the `0.2.0rc2`
release candidate.

## Core promise

Exactly **one** approved, bounded run at a time, with:

1. **Approved provenance** — interactive TTY approval binds contract, source, and resolved executable hashes with expiry
2. **Crash-safe state** — atomic JSON state writes
3. **Mandatory postflight** — successor runs refuse an unpostflighted / failed predecessor
4. **Tamper-evident receipts** — append-only SHA-256 hash-chained event log + verifiable certificate

No watchers, no recurring scheduler, no parallel workers.

## Requirements

- Python 3.9+
- POSIX (`fcntl` leases)
- Stdlib only (no third-party dependencies)

## Install

```bash
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
```

### Showcase receipt (rc2)

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

## Release-candidate limitations

- Receipts are locally hash-chained, not yet signed by an external key or
  transparency service. A privileged attacker who can rewrite the complete
  workspace can fabricate a new history.
- The executed payload is not sandboxed and CPU, memory, network, filesystem,
  and child-process limits are not yet enforced. The current hard bounds are one
  workspace run, wall-clock duration, and captured output size.
- The resolved executable or interpreter is automatically hashed. Native
  libraries, environment variables, and input datasets still need to be placed
  in `source.roots` or otherwise asserted by the workload.
- This release is licensed under Apache-2.0. The CLI remains the enforcement
  boundary; Codex and Cursor integrations are constrained adapters to it.

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
See [the threat model](docs/THREAT_MODEL.md), [release checklist](docs/RELEASE_CHECKLIST.md),
and [security policy](SECURITY.md) before using RunSpecimen for sensitive work.
