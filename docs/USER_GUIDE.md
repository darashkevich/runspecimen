# RunSpecimen user guide

Practical how-to for the local CLI. This guide matches the installed
`runspecimen` commands and current release-candidate limits
(`0.2.0rc5` at time of writing). For a short product overview see
[ABOUT.md](ABOUT.md); for product intent see
[PRODUCT_PLAN.md](PRODUCT_PLAN.md); for short Q&A see [FAQ.md](FAQ.md).

## What it is / what it is not

**It is** a local safety and evidence layer for consequential agent-driven
commands: one human-approved, bounded run at a time; crash-safe state;
mandatory postflight before a successor; tamper-evident hash-chained receipts.

**It is not:**

- An OS sandbox. Wall timeout, process-group cleanup, and path containment are
  orchestration controls, not a security boundary against a hostile payload.
- A job scheduler. No cron, watchers, fan-out, or parallel workers in one
  workspace lease domain.
- A cryptographic signature service. Receipts are locally hash-chained, not
  signed by an external key or transparency log.
- Proof that a scientific or engineering claim is true. A green postflight
  means the approved contract ran under recorded provenance and assertions
  passed.

Approval always requires an interactive TTY. Agents and adapters must not
enter `APPROVE` for you.

## Install

Requirements: Python 3.9+, POSIX (`fcntl` leases), stdlib only.

From a clone of https://github.com/darashkevich/runspecimen:

```bash
# Preferred: regular local install (avoids editable-install import edge cases)
sh scripts/bootstrap_dev.sh

# Or manually
python3 -m pip install --upgrade 'setuptools>=77' wheel
python3 -m pip install --no-build-isolation .

# Version check
runspecimen --version
command -v runspecimen
```

`bootstrap_dev.sh` deliberately does **not** use `pip install -e`. Some Python
builds ignore the editable `.pth`, leaving a console script that cannot import
`runspecimen`. After source edits, re-run the install.

Optional: create a fresh demo workspace that does not touch an existing tree:

```bash
runspecimen init-demo --workspace ./runspecimen-demo
```

Host and contract checks before approval:

```bash
runspecimen doctor --workspace .
runspecimen validate --workspace . --contract examples/demo_contract.json
```

## Core lifecycle

Exactly one step at a time. Do not run lifecycle commands concurrently in the
same workspace.

```bash
# 1) Human TTY approval (binds contract + source + resolved executable hashes)
runspecimen approve --workspace . --contract examples/demo_contract.json
# When prompted, type APPROVE exactly

# 2) Optional explicit preflight (run also rechecks under lease)
runspecimen preflight --workspace . --contract examples/demo_contract.json

# 3) Execute one bounded run
runspecimen run --workspace . --contract examples/demo_contract.json

# 4) Assert outcomes and issue certificate (required before a successor)
runspecimen postflight --workspace . --contract examples/demo_contract.json

# 5) Verify receipts against live contract, source, runtime, and outputs
runspecimen verify --workspace . --contract examples/demo_contract.json \
  --campaign-id demo-campaign --run-id run-001

# Read-only diagnosis (does not take the execution lease)
runspecimen status --workspace . --campaign-id demo-campaign --run-id run-001
# Optional: also bind a contract path for identity / argv display
runspecimen status --workspace . --campaign-id demo-campaign --run-id run-001 \
  --contract examples/demo_contract.json
```

Interactive demo that exercises drift refusal and second-launch refusal:

```bash
sh scripts/demo_rc.sh
```

### CLI map

| Command | Role | Takes workspace lease? |
| --- | --- | --- |
| `about` | Product summary + documentation URLs | No |
| `init-demo` | Create a new unapproved demo directory | N/A (new path) |
| `doctor` | Host/workspace readiness JSON (includes docs URLs) | No (probes only) |
| `validate` | Contract paths + runtime provenance | No |
| `approve` | TTY bind of contract/source/runtime | Yes |
| `preflight` | Refuse unsafe/stale conditions | Yes |
| `run` | Recheck + execute one bounded run | Yes |
| `postflight` | Assert outcomes + write certificate | Yes |
| `verify` | Rehash live evidence; require campaign/run IDs | No |
| `status` | Phase, approval, lease, chain health (JSON) | No |
| `dashboard` | Loopback read-only UI with About + docs links (blocking) | No |

Global flag: `runspecimen --version`.

There is no `status --brief` flag. `status` prints a single JSON document.

## Contracts

Start from `examples/demo_contract.json`. Minimal surface (version 1):

| Field | Role |
| --- | --- |
| `campaign_id` / `run_id` | Identity; run ID cannot be reused after execution starts |
| `argv` | Argument vector; always executed with `shell=False` |
| `cwd` | Working directory inside the workspace |
| `source.roots` / `excludes` | Deterministic source hashing / provenance |
| `outputs.required` | Must be absent at preflight; present at postflight when required |
| `caps.*` | Wall timeout + bounded stdout/stderr capture |
| `approval.ttl_sec` | Approval expiry bound into the approval document |
| `predecessor` | Gate on a prior run’s postflight / failure, or `null` |
| `postflight.*` | Exit code, output existence/SHA, JSON field equality, source unchanged |

Hard tool maxima (refuse out-of-range contracts):

- Wall timeout: 1 … 86400 seconds
- Capture sizes: 1 … 50 MiB each for stdout/stderr
- Approval TTL: 1 … 7 days

### Hashing caveats (raw bytes)

- **Contract hash** is SHA-256 of the contract file’s **raw bytes**, not a
  canonicalized JSON object. Reformatting, reordering keys, or changing
  whitespace changes the hash even when the parsed command is identical.
- **Source hash** walks `source.roots` (fail-closed on unexcluded symlinks),
  hashes each file’s bytes, then digests a canonical manifest.
- **Runtime** resolves `argv[0]` the same way launch will, hashes that
  executable, and binds `runtime_id`. Native libraries, env vars, and datasets
  are **not** auto-fingerprinted—put material inputs in `source.roots` or assert
  them in postflight.
- Every path used in an output existence, SHA-256, or JSON assertion must be
  absent before launch and is hashed into the receipt after it passes.

Default source excludes always include `.runspecimen`, VCS dirs, `__pycache__`,
`*.pyc`, `.DS_Store`, and `.tools`, plus your contract `excludes`.

## Campaigns, predecessors, postflight, verify, certificates

**Campaign / run.** State lives under:

```text
{workspace}/.runspecimen/runs/{campaign_id}/{run_id}/
```

Files: `approval.json`, `state.json`, `events.jsonl` (+ append lock),
bounded `stdout.capture` / `stderr.capture`, and `certificate.json` after a
successful postflight. Workspace-wide lease:
`{workspace}/.runspecimen/execution.lock`.

**Predecessor.** A non-null `predecessor` must name a prior run and currently
requires both `require_postflight: true` and `refuse_if_failed: true`. Preflight
and run refuse if the predecessor is missing, failed/timed out, not
postflighted, or its receipt fails verification.

**Postflight.** Rechecks approval, contract/source/runtime hashes, exit code,
required outputs, optional `output_sha256` and `json_equals`, and optionally
`source_unchanged`. On success it appends chain events and writes
`certificate.json`. Timeout or orchestration failure cannot become a certified
success. A successor must not start until this completes.

**Verify.** CLI `verify` always rehashes live contract, source, runtime, and
outputs (`require_live_provenance=True`). `--campaign-id` and `--run-id` must
match the contract identity. Success prints JSON including certificate details.

**Certificate.** Locally verifiable receipt: bound hashes, output digests,
event head, runtime, and a `certificate_id` derived from that body. Not an
external signature.

## Doctor, validate, status

```bash
runspecimen doctor --workspace .
# { ok, platform, python, workspace, workspace_writable,
#   workspace_lease_held, active_lease }

runspecimen validate --workspace . --contract path/to/contract.json
# { ok, campaign_id, run_id, contract_hash, runtime }

runspecimen status --workspace . --campaign-id … --run-id …
# Full JSON: phase, state, approval, certificate summary, event_chain_ok,
# lease_meta, optional contract info
```

`doctor` exits non-zero when the workspace is missing or not writable.
`status` never takes the execution lease; use it while diagnosing a stuck run.

## Dashboard

```bash
runspecimen dashboard --workspace . --contract path/to/contract.json --open
# Optional: --port N  (0 = OS-chosen; must be 0..65535)
```

- Binds **only** to `127.0.0.1` (loopback).
- **Read-only**: shows phase, approval/lease/receipt evidence, and exact
  lifecycle commands. It cannot approve or execute.
- **Blocks** in the foreground (`serve_forever`). Background it (`&`), detach
  it, or use another terminal if you still need the shell for `approve` /
  lifecycle commands. Agents must not wait on it in the main turn.
- Startup prints JSON like `{"ok": true, "url": "http://127.0.0.1:…/", "loopback_only": true}`.

## Plugins (Cursor / Codex)

Package root: `plugins/runspecimen`. The plugin is an **adapter**; the CLI on
`PATH` remains the enforcement boundary.

Install:

- **Codex:** install the `runspecimen` plugin from the Codex plugin listing
  (skill under `skills/runspecimen/`). Confirm `runspecimen` is on `PATH` in
  the environment Codex uses.
- **Cursor (local):** symlink `plugins/runspecimen` to
  `~/.cursor/plugins/local/runspecimen`, reload Cursor, confirm skill/rule in
  Customize.

Adapter limits (`plugins/runspecimen/scripts/runspecimen_adapter.py`):

- Allowed: `about`, `dashboard`, `doctor`, `validate`, `status`, `preflight`, `run`,
  `postflight`, `verify`
- **Not allowed:** `approve` (and anything else). A human must run
  `runspecimen approve …` in a real terminal.

## Showcase refresh (host-bound)

`examples/showcase/` holds a regeneratable postflight receipt. Verify:

```bash
runspecimen verify --workspace examples/showcase \
  --contract examples/showcase/contract.json \
  --campaign-id showcase-campaign --run-id run-001
```

Refresh without a TTY (library test hook `skip_tty_check` — **not** for
production approvals):

```bash
python3 scripts/refresh_showcase.py
```

Live verify binds this machine’s resolved interpreter hash. After cloning onto
another host, re-run `refresh_showcase.py` (or an interactive approve/run path)
before expecting verify to pass. Historical pre-`runtime` certificates from
earlier RCs are not verifiable on current builds.

## Integrating a research script

1. Put the script and material inputs under `source.roots`.
2. Set `argv` to the interpreter/binary plus script path (no shell string).
3. Declare required outputs and postflight assertions (`exit_code`,
   `json_equals`, optional `output_sha256`, `source_unchanged`).
4. Choose a fresh `run_id` for each execution attempt.
5. Chain campaigns with `predecessor` when a later step must only run after a
   certified prior receipt.
6. Keep human TTY `approve` in the terminal; let agents run
   validate → preflight → run → postflight → verify after you approve.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `workspace execution lease unavailable` | Another lifecycle command holds `.runspecimen/execution.lock`. `doctor` / `status` show `workspace_lease_held` / `lease_meta`. Wait for the holder to finish, or inspect whether a crashed process left confusion (status can report running with no active lease). |
| Stuck in `running` | Inspect `status` and captures under the run dir. There is no automated recover/abandon command yet; do not reuse the same `run_id`. |
| `approval requires an interactive TTY` | Run `approve` in a real terminal (stdin and stdout must be TTYs). Do not pipe `APPROVE`. |
| Approval expired / hash mismatch | Re-approve after fixing contract or source drift. Contract hash is raw bytes. |
| Runtime / executable mismatch | Interpreter or binary path changed since approval (common after clone or PATH change). Re-approve on this host. |
| Verify fails after clone | Showcase and any receipt with live runtime binding are host-specific. Refresh on the new host; ensure outputs and contract bytes match the certificate. |
| Predecessor refused | Prior run not postflighted, failed/timed out, or receipt invalid. Fix predecessor first. |
| Second `run` refused | Expected: a run ID cannot be reused after execution starts. New contract + new `run_id`. |
| Outputs already exist at preflight | Delete or move asserted output paths before launch (they must start absent). |
| Untrusted payload | Use a container or OS sandbox; RunSpecimen does not isolate the process. |

## Related docs

- [ABOUT.md](ABOUT.md)
- [FAQ.md](FAQ.md)
- [PRODUCT_PLAN.md](PRODUCT_PLAN.md)
- [THREAT_MODEL.md](THREAT_MODEL.md)
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)
- [SECURITY.md](../SECURITY.md)
