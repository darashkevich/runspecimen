---
name: runspecimen
description: Use when a consequential local command should be explicitly approved, bounded to one workspace execution, provenance-checked, postflighted, and issued a tamper-evident receipt. Also use for RunSpecimen contract authoring, status, diagnosis, or receipt verification.
---

# RunSpecimen

Use the installed `runspecimen` CLI as the enforcement boundary. Never imitate
an approval, call internal test helpers, pipe approval input, or weaken a
contract to make a refusal disappear.

## Workflow

1. Run `runspecimen doctor --workspace <workspace>`.
2. Read the intended command, source roots, outputs, bounds, assertions, and
   predecessor. Create or edit a version-1 JSON contract only when the user has
   asked for it.
3. Run `runspecimen validate --workspace <workspace> --contract <contract>`.
4. Show the user the exact command, outputs, timeout, and major limitations.
5. Ask the user to run `runspecimen approve ...` in a real terminal. Pause until
   they confirm it completed; an agent must not enter `APPROVE` for them.
6. Run `preflight`, then `run`, then `postflight` sequentially. Stop at the first
   refusal or failure and preserve the evidence.
7. Run `verify` with the exact campaign and run IDs. Report the certificate ID.

Use `status` for read-only diagnosis. Never run lifecycle steps concurrently,
reuse a terminal run ID, overwrite asserted outputs, or continue past a missing
or failed postflight. RunSpecimen is not an OS sandbox; recommend a container or
stronger isolation for untrusted payloads.
