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
trusted. The Codex, Cursor, Claude Code, and Grok Build adapters do not expand
this boundary; they call the
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

## Isolation (opt-in)

The default backend is `none`. RunSpecimen does not wrap the approved argv and
does not confine writes or network. The receipt says so.

Opt-in backends, only when the contract names them and the tool is on `PATH`:

| Backend | What it enforces | What it does not enforce |
| --- | --- | --- |
| `sandbox-exec` | Seatbelt profile: deny by default, allow the process to run and read the host, allow writes only under the workspace, deny network unless `isolation.network` is true | A complete OS sandbox. Mach lookup and host reads stay allowed so the approved program can start. Profile escape and a hostile approved payload remain. |
| `bwrap` | Read-only host root, read-write bind of the workspace, network unshared unless `isolation.network` is true | A complete OS sandbox. The approved program keeps the authority of that mount. |

A declared backend that is not installed fails closed before launch. Validate, approve, and preflight identify that tool by hashing the file. They do not execute it. If the file path or bytes change after approval, launch is refused and no receipt can say the backend was enforced. Resource
limits (wall clock, capture bytes) are not an isolation backend. The macOS app
sandbox on the GUI process does not confine a CLI the user runs in Terminal,
and it does not replace the contract backend.

## Receipt authentication vs signatures

- **Hash-chained events + certificate_id** — integrity of recorded local evidence.
- **HMAC-SHA256** (optional) — shared-secret MAC; verifiers who hold the key can
  also forge; useful for controlled sharing, not independent third-party trust.
- **Ed25519** (optional extra, shipped) — offline public-key verification without
  sharing the private key; still depends on key custody and does not prove
  scientific truth. See `docs/ED25519_RECEIPTS.md`.

## Residual risks

The wall-clock timeout kills the launched process group, but detached or hostile
process behavior is outside the security boundary. Native libraries, environment
variables, input services, and datasets are not automatically fingerprinted.
Place material local inputs in `source.roots`. When the payload is not trusted,
name `sandbox-exec` or `bwrap` in the contract and read the receipt field
`isolation.residual` before treating the run as confined. `backend: none` is
not that control.
