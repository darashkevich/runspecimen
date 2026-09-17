# RunSpecimen macOS companion helper

Thin SwiftPM module + UI that **previews** the opt-in CLI:

```text
runspecimen companion --workspace … --contract … [--allow-lan --host …] --print-token
```

## Invariants

- Does **not** implement approve/run/preflight/postflight.
- Does **not** inject TTY `APPROVE`.
- Enforcement lives in `src/runspecimen/companion.py` (fail-closed).
- See `docs/ADR-003-ios-companion-observation.md`.

## Build

```bash
cd apps/macos-companion
swift test
swift run runspecimen-companion-ui
```

This tree is independent of `apps/macos` (MAS packaging / PR #6) so it can merge from `main` without disturbing that branch.
