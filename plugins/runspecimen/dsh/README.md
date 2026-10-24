# RunSpecimen for DeepSeek Harness

A DSH plugin bundle that exposes RunSpecimen's observe/bound/run/verify surface
to the agent — and keeps the human approval gate human.

RunSpecimen guards consequential local commands with approval, bounds, provenance
and receipts. The value comes from where the approval happens, so this plugin
reproduces the same boundary the bundled MCP adapter already enforces:

| Command | Exposed to the agent? |
| --- | --- |
| `about`, `doctor`, `validate`, `status` | yes |
| `preflight`, `run`, `postflight`, `verify` | yes |
| `dashboard`, `decisions search`, `requirements report`, `freshness evaluate` | yes |
| `approve` | **no** — refused, with the command a human must run |
| `remote-confirm` | **no** — refused |
| `abandon` | **no** — refused |

The three refusals are registered as real tools that return an explanatory
failure rather than being merely absent, so a model that infers the CLI surface
gets a typed reason instead of an unknown-tool error it might retry.

## What the agent sees

16 tools: the 12 drivable actions above, `runspecimen_dashboard_stop`, and
`runspecimen_approve` / `runspecimen_remote_confirm` / `runspecimen_abandon`,
which are registered but always refuse.

Each drivable tool runs exactly one `runspecimen` CLI invocation and returns:

```json
{ "ok": true, "exitCode": 0, "truncated": false, "output": "<combined stdout+stderr>" }
```

Read-only actions are declared concurrency-safe, so several can run in one
batch: `about`, `doctor`, `validate`, `status`, `decisions_search`,
`requirements_report` and `freshness_check`. `validate` belongs there because it
reads a contract and probes provenance without writing run state. `preflight`,
`run`, `postflight`, `verify` and `dashboard` are exclusive.

A policy section is added to the system prompt stating that the agent cannot
approve, that the three refusal tools are present and always refuse (so their
presence is not a way through), that a human must type APPROVE at a real terminal, that
`preflight`→`run`→`postflight`→`verify` is the required order, that a refusal
before approval is the product working rather than an error to route around, and
that a passing receipt does not prove a claim is true.

## Requirements

- DeepSeek Harness 0.2.0-rc.2 or a compatible release.
- Node 22+.
- The `runspecimen` CLI on `PATH`, or an absolute path in the plugin config.
- The `dsh` CLI on your `PATH` for the install commands below. In the desktop app
  it lives at
  `/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh`;
  symlink it somewhere on `PATH`, or call it by absolute path.

## Which profile

`add` targets one named profile. `dsh plugin --profile <name> add …` installs into
that profile only. In the desktop app your daily profile is usually `web`
(`$DSH_HOME/profiles/web`); the scratch profile used to verify this plugin is not
your daily profile. Check what is installed with:

```sh
dsh --profile web --dump-config | grep -A 4 'id: runspecimen'
```

## Install

```sh
# From this directory, into the profile you actually use:
dsh plugin --profile web add /absolute/path/to/runspecimen-dsh-plugin
```

`add` links the package, enables it as a bundle, and applies its patch on the
next composition. To confirm the row composed:

```sh
dsh --profile web --dump-config | grep -A 4 'id: runspecimen'
```

Expected:

```yaml
- id: runspecimen
  name: runspecimen-dsh-plugin
  config:
    command: runspecimen
    timeoutMs: 600000
    maxOutputBytes: 64000
```

## Configure

Override the row from your profile's `cordis.patch.yml`. A patch replaces the
targeted row's whole `config`, so restate every field you want to keep:

```yaml
- id: runspecimen
  config:
    command: /opt/homebrew/bin/runspecimen
    cwd: /Users/me/work
    timeoutMs: 900000
    maxOutputBytes: 128000
```

To turn the tools off without uninstalling:

```yaml
- id: runspecimen
  disabled: true
```

| Field | Default | Meaning |
| --- | --- | --- |
| `command` | `runspecimen` | Executable name or absolute path. |
| `cwd` | the Host's working directory | Child working directory. |
| `timeoutMs` | `600000` | Wall-clock budget per call; the child is terminated on expiry. |
| `maxOutputBytes` | `64000` | Captured stdout+stderr budget; truncation is marked in the text. |
| `graceMs` | `2000` | SIGTERM→SIGKILL grace before a call is reported terminated. |

`runspecimen_dashboard` starts the loopback dashboard as a detached background
process and returns its URL and pid. It serves until stopped or until the configured
`timeoutMs` lifetime expires (default 600000 ms / ten minutes from launch).
Stop it earlier with `runspecimen_dashboard_stop` (`pid` optional; omitting it stops
every dashboard this plugin started).

Every call inherits the caller's cancellation signal, so aborting a turn kills a
running child instead of leaving a `run` executing behind the user's back.

## Layout

```
lib/index.js      plugin: tools, policy section, config schema
lib/cli.js        argv construction and bounded child execution
lib/refusal.js    the human-gate refusals and their reasons
cordis.patch.yml  the bundle patch layer (one `insert`)
test/             behavior tests, run with `node --test test/`
```

`cordis.patch.yml` follows the bundle convention: exactly one
`insert:` list adding the `runspecimen` row, `disabled` left to the consumer.

## Verification

### Executed

- `node --test test/` — **37 tests, all passing** (see the table below). They
  cover argv mapping for every action, workspace-relative path resolution,
  refusal of the three human-gate actions, byte-accurate truncation, bounded
  memory under a 32 MiB stream, a retained stderr tail after stdout overflow,
  real process death after timeout/cancellation (including a spawned
  descendant), rejection of a zero budget, and the dashboard's background
  lifetime plus `stopDashboard`.
- Thirteen new production-code regressions cover surviving descendants, unknown-PID
  stop refusal, cross-instance dashboard isolation, disposal, failed startup,
  pre-aborted dispatch, true stderr tails, small budgets and UTF-8 boundaries.
  Frozen 0.2.0 reproduces the surviving-descendant, arbitrary-PID stop and late
  stderr defects; partial/cancelled baseline test runs are not counted as passes.
- Activation in a real DeepSeek Harness Host 0.2.0-rc.2: a scratch profile is
  scaffolded, the package installed with `dsh plugin add`, and the profile
  booted. A rejected tool definition aborts activation and prints
  `1 entry did not activate`, so a clean boot is meaningful.
- User-level `cordis.patch.yml` precedence over the bundle defaults, verified
  through `--dump-config`.

| Defect | Regression test |
| --- | --- |
| Termination did not establish process death | `timeout terminates a stubborn child before reporting`, `caller cancellation terminates a stubborn child…`, `cancellation also terminates a spawned descendant` |
| Output limit did not bound memory | `captured memory stays bounded while a huge stream is drained` |
| Late stderr lost after stdout overflow | `a late stderr error survives stdout consuming the budget` |
| Truncation could report complete | `truncated is true whenever a truncation notice is present` |
| Zero timeout removed the budget | `Config rejects a zero or negative execution budget`, `timeoutMs and maxOutputBytes reject non-positive values` |
| Dashboard could not return its URL | `dashboard starts in the background, reports a URL, and stops on request` |
| Relative contract resolved elsewhere | `relative contract resolves against the workspace, not the process cwd` |
| `validate` exclusivity mismatch | `validate is declared concurrency-safe; run and dashboard are not` |

### Not verified, and not claimed

- A model actually selecting and calling these tools in a chat turn. Tool
  registration and schema acceptance are proven; a visible model call is not.
- An end-to-end human-approved lifecycle, live Mac/iPhone companion interaction,
  or real receipts.
- Windows: execution is explicitly unsupported and refused before spawning.
- Repeated install/uninstall and hot-reload lifecycle; clean install from the
  public registry.

## Fixes in 0.2.0

Version 0.1.0 shipped with two P1 defects found in independent QA and reproduced
here before fixing:

- **Process termination is now proven, not assumed.** The child runs in its own
  process group; cancellation and timeout send SIGTERM, wait `graceMs`, escalate
  to SIGKILL, and resolve only after the process is actually gone. Descendants
  die with the group. Caller abort is reported as `cancelled:true`; budget expiry as `timedOut:true`, with
  a `termination` reason rather than as a bare signal exit.
- **Memory is bounded while draining.** Per-stream byte-budgeted accumulators
  discard overflow instead of buffering it, stderr keeps a guaranteed tail, and
  `truncated` is tracked from bytes seen versus bytes retained rather than by
  comparing two different strings.
- `dashboard` now requires `contract` (the CLI does), starts detached, returns
  the URL and pid, and has a matching `runspecimen_dashboard_stop`.
- Relative `contract`/`manifest` paths resolve against the resolved workspace,
  and a relative `workspace` resolves against the session cwd.
- `timeoutMs`/`maxOutputBytes`/`graceMs` reject zero and negatives in both the
  loader schema and programmatic `apply`.
- Docs: `validate` is documented as concurrency-safe, the refusal tools are
  described as present-but-refusing, and the license is corrected to Apache-2.0.

## Design notes

**Why refuse instead of omit.** Omitting `approve` entirely would leave a model
that knows RunSpecimen looking for a way to approve. A registered refusal that
names the human command teaches the boundary in one step.

**Why the CLI and not the MCP server.** The plugin could have spoken MCP to
`runspecimen_mcp.py`. Driving the CLI directly keeps one less process and one
less protocol in the path, and the CLI is the interface RunSpecimen documents as
primary. The argv translation is deliberately the same as the adapter's, so both
surfaces stay in step; `test/cli.test.js` asserts that allowlist matches.

**Why `additionalProperties: false` on results.** The harness value-schema DSL
requires it to be explicit, and these results are fixed records. A sibling
`required` list is not part of that DSL — declaring one is a registration-time
error, which is how the first boot failed.

## License

Apache-2.0, matching RunSpecimen. This plugin is an independent adapter, not part
of the RunSpecimen distribution; the shared license does not imply endorsement.

## 0.2.1 release-blocker follow-up

This version retains the 16-tool 0.2.0 surface, including background dashboards.
It additionally verifies that the entire owned POSIX group disappears before
returning cancellation; a cooperative parent cannot cancel escalation for a
stubborn descendant. Cleanup escalates after `graceMs` and has an additional
five-second confirmation deadline. A failure to confirm cleanup throws an error
rather than reporting successful termination. A pre-aborted request starts no
process. Windows execution fails before spawning; no Windows cleanup is claimed.
Processes that deliberately create another session/group are not confined.

Dashboard managers are scoped to one plugin instance. A stop request may signal
only a live dashboard registered by that instance; arbitrary PIDs and another
profile's dashboards are refused. Disposal stops the instance's dashboards. A
startup failure, cancellation or missing loopback URL stops the process and is
not reported as a running server. Dashboard lifetime is bounded by `timeoutMs`
(up to one hour); stop it explicitly sooner when finished. The returned URL must
be an observed HTTP loopback URL.

Retained stdout and stderr together do not exceed `maxOutputBytes`; the notice
is additional. Stdout retains a prefix and stderr retains an actual tail. Small
budgets also honor the combined bound. UTF-8 cuts omit incomplete characters.

Config and programmatic apply require integer budgets: timeout 1–3600000 ms,
output 1–4194304 bytes, grace 1–10000 ms. Tests exercise source, not mocked copies
of the cleanup/path/output logic. Preserve the separate limits below when
reporting verification; automated fixtures are not a human-approved run or a
physical companion test.

## Unpublished QA continuation — 22 October 2026

Dashboard startup timeout is a distinct `timedOut` outcome; caller abort is
`cancelled`. Both paths wait for cleanup before returning through the registered
tool. Successful starts report both flags as false.

If cleanup cannot be confirmed, the dashboard remains registered with an
unresolved cleanup error. A later `runspecimen_dashboard_stop` performs a fresh
TERM/KILL and death-check attempt, rather than awaiting the failed attempt again.
An entry is removed only after death is confirmed. Concurrent retries share one
attempt. Retries request cleanup over the original supervisor IPC connection. If it is
unavailable and the group is still present, retry fails closed and retains the unresolved state for manual
inspection; it does not turn a numeric PID into new authority. Once group death
is observed, the stale entry can be cleared without signaling anything.

## Tested Cordis compatibility

The Cordis peer range is `^4.0.5` (4.0.5 through 4.x; excludes 5.x). The lockfile resolves 4.0.5, used for this QA round. This replaces the unbounded wildcard because later major host versions have not been qualified. Registration, execution, cancellation and dashboard cleanup tests run with the locked dependency graph; the range does not claim testing of every future 4.x release.

### Process-group signal ownership (ICQA-02)

Each command runs under a small Node supervisor that stays alive as the POSIX
process-group leader after the command exits. Command exit status travels over a
private IPC channel; the supervisor keeps the group identity pinned through
TERM/grace/KILL cleanup. The owned dashboard PID therefore identifies the
supervisor, not necessarily the CLI process. A process-list snapshot only
classifies leftover children; it never grants signal authority. Group KILL is
sent only by the executing supervisor to its own group. The parent never sends
a destructive group signal, including initial cleanup, escalation or retries.
A cleanup acknowledgement and group-death observation are required. Unexpected loss of
the supervisor returns `cleanupFailed`/unconfirmed cleanup and keeps a dashboard
entry unresolved, rather than signaling the same numeric group again. The
supervisor kills its own still-owned group if its parent IPC connection closes.
Node child exit fields and numeric PID probes never confer signal authority. Escaped
sessions/process groups are still outside this process-group cleanup boundary.
