# ADR-002 — Optional embedded engine helper (stretch)

**Status:** Accepted — package-tree staging implemented; frozen interpreter deferred  
**Date:** 2026-09-15  
**Related:** [ADR-001](ADR-001-architecture.md), [Helpers/README.md](../Helpers/README.md), [APP_STORE.md](../APP_STORE.md)

## Context

Target A (Mac App Store) risks rejection when the app depends on an optionally
installed PyPI/`runspecimen` CLI (guideline 2.4.5(viii)). Embedding a signed
helper under `Contents/Helpers` is the long-term mitigation.

## Decision

- Keep the SwiftUI app as a thin shell; do not reimplement leases/approval/hash
  chains in Swift.
- Ship discovery order now: Open-panel bookmark → bundled Helpers → PATH probe.
- Prefer `Scripts/stage_helper.sh --from-src`: copy the Apache-2.0 stdlib-only
  `src/runspecimen` tree plus a host-Python launcher. Zero third-party Python
  deps (`pyproject.toml` `dependencies = []`) keeps redistribution legally clear
  without freezing CPython in this iteration.
- `build_app.sh` materializes `Contents/Helpers/` (launcher + `lib/` + NOTICE when
  staged; otherwise README placeholder).
- Helper entitlements: `Entitlements/RunSpecimen.helper.entitlements` (inherit).
- Approval remains PTY-gated; no auto-`APPROVE`; no telemetry.
- PyInstaller (or equivalent) freeze remains optional for MAS self-containment
  when Developer ID certs exist; until then Target B uses user-selected CLI or
  the host-Python package-tree helper for local testing.
- `Scripts/freeze_helper.sh` is gated behind `RS_FREEZE_HELPER=1` / `--enable` and
  exits 0 when PyInstaller is missing so CI stays green.

## Consequences

- `--from-src` helpers require Python 3.9+ on PATH at runtime (honest limitation
  until a freeze lands).
- Larger notarized artifact once a freeze lands; CPython NOTICE attribution still
  required for that path.
- `Helpers/payload/` stays gitignored for local experiments.
- App Settings / Engine menu surfaces CLI **Source** and “Prefer Bundled Helper”
  so operators can confirm bundled vs bookmark vs PATH.
- PATH probes are session-only (not auto-bookmarked) so Prefer Bundled / Clear
  Bookmark cannot race with a silently re-saved Open-panel override.
- Exact packaging steps live in `Scripts/stage_helper.sh`, `Scripts/freeze_helper.sh`,
  and Helpers/README.md.
