# QA follow-up evidence — tip after 69ab2b9 (this pass)

Unprivileged source/tests only. **Green CI is not production sign-off.** The
installed root daemon and `/Applications/RunSpecimen*.app` were **not**
modified. `/Applications/RunSpecimen.app` mtime stayed `2026-09-26 13:56:03`.

## Defects addressed in source (this pass)

1. Root execute `Popen` now drops uid/gid and clears supplementary groups via
   `preexec_fn` (`_preexec_drop`) after mapping the console/originating user.
2. Execute refuses caller `interpreter` / `interpreter_args`; launch is the
   consumed binding `launch_argv` only; post-consume launch mutation fails.
3. Device verifier remains labeled `device-hmac-not-hardware`. Challenges include
   exact `authorized` bytes (payload digest, launch_argv, bounds, mutation
   digest). Bootstrap is enroll/pair only.
4. Consume/execute run under one durable `_transaction()` flock with lease
   `launch_started` / at-most-once recovery and strict schema.
5. Lease releases only after process-group descendants are absent; drain is
   wall-deadline bounded.
6. Framing uses absolute monotonic read/write deadlines.
7. Protected runtime chain in `holder_runtime.py` + HolderDaemon `main.swift`
   (source only). Live repair request:
   `evidence/2026-09-30-69ab2b9-live-repair-authorization-request.md`.

## Tests

`tests.test_execution_holder` + `tests.test_holder_protocol`: 46 OK, 0 skip.
Every class states these tests do **not** prove installed protection. No test
points at the live root socket.

## Development GUI (existing app only)

App: `/private/tmp/rs-local-qa-91081f5/DerivedData/Build/Products/Release/RunSpecimen.app`
(Apple Development, Team UN6KF8636A). Main executable SHA-256
`cfb41bcc731c0beac57c96dbc712b9a7f0d9409cb8328df6aba9504ffb04c605` (source
`91081f5`; this GUI binary does not contain the holder). Shared container
backed up to `/private/tmp/rs-qa-69ab2b9-container-backup-*`, QA pid quit only,
container restored. Opened About (Escape closed), Reviewer Demo, Workflows
sheet (Escape), Lifecycle Validate. Compare / diff / retain were **not**
re-finished in this pass (SwiftUI AX sparse). Prior finished receipt evidence
on `91081f5` remains on file. No APPROVE. No biometrics. Holder.app not
modified.

## Remaining human / privileged gates

- Live protected-runtime repair (separate Yahor authorization).
- Real Touch ID / Face ID / `--human-invoked` Mac+iPhone pairing/local/companion/dual/run/replay.
- Notarize / merge / publish / Apple submit.
