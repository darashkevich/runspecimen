> QA2 correction (27 October 2026): earlier incident summaries are incomplete. See [the full CI census and superseding diagnosis](QA2_CI_CENSUS_2026-10-27.md): 17 iOS failures, three multi-attempt runs; no proven cold-share latency root cause.

# Launch-fault live-writer race — 22 October 2026

Failed evidence: PR78 job 119822067116, Ubuntu 24.04 / Python 3.10,
head f813d365caf2c48de53533aba0d426d8779564e6. The original log is retained
outside the checkout as failed-job-119822067116.log, SHA256
4e3e35e1cef8f4464c2256d261f5bd02409c6d95b33e21e74914184acf7fc9ac.
The target assertion returned 0 instead of EXIT_LEASE (3).

## Root cause and scope

This test drives tests/launch_fault_harness.py. It is an unprivileged real-pipe,
real-process durable-state harness; runspecimen run does not call it.
No shipping workspace-lock or native-holder change is justified by this failure.

After the faulted holder exits, the wrapper observes EOF and rewrites its
identity/proc record. write_durable_record fsyncs a .json.tmp file before its
atomic replace. A new holder previously ran _clear_stale_tmp *before* recovery
and the lease check. It could unlink that live write. The wrapper's replace
then fails, the wrapper exits with error, and the new holder can observe its
absence and admit nonce n2. That is not evidence that a live child bypassed
the shipping lease: the harness itself destroyed the live-child fixture.
The failed test completed in about 0.25 seconds, so the separate 30-second
fixture self-exit does not explain that particular CI failure.

## Correction and regressions

- Recovery, lease refusal and replay refusal now precede stale temporary-file
  cleanup. A rejected launch does not mutate the live wrapper's files.
- A real fork/pipe regression holds the wrapper's EOF identity write exactly
  before replace. The competing nonce must be refused, its pending file must
  remain, the write must complete, and another nonce must still be refused
  while the child remains alive. This assertion fails on the frozen old harness.
- The live fixture now waits for explicit termination rather than declaring
  successful exit after 30 seconds. A separate regression rejects the old
  autonomous exit without sleeping 30 seconds.
- No EXIT_LEASE assertion was weakened, skipped, retried away, or changed to
  accept a second launch. Existing PID-token verification and reap behavior
  remain in use. The barrier test cleans up only its unreaped direct child.

scripts/stress_launch_faults.py runs isolated copies of a selected test in
parallel and records every failed invocation. The dedicated Linux/Python 3.10
workflow retains diagnostic baseline results, then strictly gates the
deterministic launch-fault unittests. The 800-run original-test load and the
writer-boundary load are smoke only: the pre-fix baseline also passed 800/800.
Baseline failure is evidence, not a passing test result; a failed deterministic
unittest fails the job. Artifact upload runs
even on failure. No workflow rerun of the original failed job is required.

Local baseline load on macOS: 400 original-test runs, zero failures. This does
not reproduce the intermittent Linux schedule. Both deterministic regressions
fail against the frozen old harness; the fixed launch suite passes 21 tests.
Exact-head load counts and CI outcomes are in the accompanying task evidence.

Main-based source fix is carried into each draft PR without merging to main.
No release, installed trust/key change, human approval or production run action.
