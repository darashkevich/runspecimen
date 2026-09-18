# Threat model

## Protected properties

RunSpecimen is designed to prevent accidental or agent-driven double launch,
stale approval reuse, source/contract/executable drift, output overwrite, and
continuation past an uncertified predecessor. It records bounded output captures,
atomic lifecycle state, a hash-chained event log, and a checkable receipt.

The product promise is **run assurance / verifiable execution** of one
human-approved bounded step — not a general OS sandbox, job scheduler, or
proof that a scientific or engineering claim is true.

## Trusted boundary

The human invoking the TTY approval, the local operating-system account, the
RunSpecimen installation, Python runtime, workspace filesystem, and workload are
trusted. The Codex and Cursor adapters do not expand this boundary; they call the
same CLI and cannot manufacture an approval.

A native macOS (or other) companion UI that shells to the CLI does not move the
enforcement boundary into the UI process. App Sandbox entitlements on a companion
app confine that UI process’s file/network access story; they do **not**, by
themselves, prove that:

- an externally launched `runspecimen` from Terminal is confined, or
- the workload subprocess started by `runspecimen run` is confined.

Those child-process boundaries must be tested and documented before any
“sandboxed execution” claim.

## Explicitly out of scope

- Inventing a general-purpose OS sandbox inside the Community engine
- Treating resource-limit wrappers alone as an OS-sandbox claim
- Cron, watchers, fan-out workers, or parallel execution inside one lease domain
- Remote scheduling, distributed consensus, or exactly-once effects outside the workspace
- Agent/plugin remote approve / run / preflight / postflight (see ADR-003 / ADR-004).
  Optional Mac-armed **remote human confirm** is a distinct, weaker evidence channel
  than local TTY `APPROVE` and must not be over-claimed.
- Protection from root, kernel, hypervisor, or full-workspace rewrite attacks
- Proof that a scientific or engineering claim is true
- Equating HMAC shared-secret authentication with digital signatures or absolute
  non-repudiation

## Isolation direction (future, opt-in)

Planned work prefers **tested platform integrations** (for example hardened
containers or native OS isolation backends) with:

- capability discovery,
- preflight refusal when a declared policy cannot be enforced,
- receipt fields recording backend, version, and effective settings,
- an explicit residual-risk / escape write-up.

Until such a backend is selected, tested, and documented, execution remains
**unsandboxed** aside from orchestration controls (lease, wall clock, capture
bounds, process-group timeout).

## Receipt authentication vs signatures

- **Hash-chained events + certificate_id** — integrity of recorded local evidence.
- **HMAC-SHA256** (optional) — shared-secret MAC; verifiers who hold the key can
  also forge; useful for controlled sharing, not independent third-party trust.
- **Ed25519** (planned optional extra) — offline public-key verification without
  sharing the private key; still depends on key-custody and does not prove
  scientific truth.

## Residual risks

The wall-clock timeout kills the launched process group, but detached or hostile
process behavior is outside the security boundary. Native libraries, environment
variables, input services, and datasets are not automatically fingerprinted.
Place material local inputs in `source.roots`; use a container or OS sandbox when
the payload or its dependencies are not trusted — and treat that as a separate
control until RunSpecimen records an enforced isolation backend on the receipt.
