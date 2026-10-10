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
same CLI and cannot approve through the app.

RunSpecimen stops agents from approving through the app and makes planted or
edited approvals show up as broken receipts. A program running as you that can
edit RunSpecimen's files can still add a fake approval to the record. Signing
with a key the agent can't access lets you check afterwards that a receipt is
authentic, when a signature is required and checked; it does not stop a program
running as you from adding a fake approval or running the job. D1/D2 stay
fail-closed; E2 is not closed.

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
  The chain is unkeyed. An `approval` event must carry a canonical hash of
  `approval.json`; preflight, run, and verify refuse a planted or edited file.
  A program running as you that can edit RunSpecimen's files can still add a
  fake approval to the record. Signing with a key the agent can't access lets
  you check afterwards that a receipt is authentic, when a signature is
  required and checked; it does not stop a program running as you from adding
  a fake approval or running the job. D1/D2 stay fail-closed; E2 is not closed.
- **HMAC-SHA256** (optional) — shared-secret MAC; verifiers who hold the key can
  also forge; useful for controlled sharing, not independent third-party trust.
- **Ed25519** (optional extra, shipped) — offline public-key verification without
  sharing the private key; still depends on key custody and does not prove
  scientific truth. See `docs/ED25519_RECEIPTS.md`.

## Installed-wheel check

The check that compares an installed copy to the pinned wheel trusts only the
base Python interpreter and that interpreter's own standard library. It does
not trust files inside the virtual environment.

Before anything in that environment runs, the check asks the base interpreter
which directories Python's site startup would use. That list covers Debian
and Ubuntu `dist-packages` directories, paths named by `pyvenv.cfg`, every
folder or zip a `.pth` line would add (followed again when those folders
have their own `.pth` lines), and the user site when this environment would
actually turn the user site on. A normal venv leaves the user site off. A
path that does not exist is not scanned and is not counted. The check does
not stop after a fixed number of directories and leave the rest unread. If
there are more existing directories than it can safely read, it refuses in
plain English and does not run the environment. The
check then reads those locations for startup hooks: a `.pth` file with an
`import` line, `sitecustomize` or `usercustomize` in every form Python can
import (source, bytecode, an extension, or a package), a module that the
base interpreter's own `sitecustomize` would import (on Debian, that is
`apport_python_hook`), and bytecode that does not belong. A `.pth` file that
is not UTF-8 text, or that contains a null byte, is refused, and the report
is still the usual JSON. A `.pth` file or zip that cannot be read is refused
the same way. A `.pth` line that names a file or folder which exists, but
cannot be fully read, is refused. That includes a permission error, a
symlink loop, something that is not a regular file or a directory, and a
file that is not a readable zip. A repeated `home` or `executable` in
`pyvenv.cfg` is refused; this check does not guess which copy to keep.
`python`,
`python3`, `python3.X`, and `𝜋thon` must be a symlink to the base interpreter
named by `pyvenv.cfg`, or a byte-for-byte copy of that file. Following too
many links is a refusal with that reason. `pyvenv.cfg`
must name the real file that was started (`home` plus the interpreter's file
name, and `executable` when it is present), so a venv created through a
symlink is accepted when that file is the Python running the check. A
mismatch names `pyvenv.cfg` and is not described as extra startup code. The
file must not turn on system site-packages. When that switch is on, the
message names the `pyvenv.cfg` file. Any of those findings stops the check
immediately. The acceptance sheet records an absolute `python3` program,
asks that program for its real path with `-I -S`, and starts this check the
same way. A shell function or alias named `python3` stops the sheet. The
check also refuses when it was itself started by a virtual environment's
Python. It does not run the venv's `python`.

A path counts as the standard library only when it is inside the base
interpreter's real library directories, is not a site-packages or
dist-packages directory, and is not inside the virtual environment. Sharing a
parent folder with the standard library is not enough.

Only after that reading is clean does the check run the launcher body on the
base interpreter with site startup turned off (`-I -S`), and look at where
the loaded modules came from. The venv's Python is not executed, so site
hooks and Debian's `sitecustomize` import chain do not run.

## Residual risks

The wall-clock timeout kills the launched process group, but detached or hostile
process behavior is outside the security boundary. Native libraries, environment
variables, input services, and datasets are not automatically fingerprinted.
Place material local inputs in `source.roots`. When the payload is not trusted,
name `sandbox-exec` or `bwrap` in the contract and read the receipt field
`isolation.residual` before treating the run as confined. `backend: none` is
not that control.
