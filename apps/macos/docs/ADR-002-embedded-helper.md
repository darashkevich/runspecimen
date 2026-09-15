# ADR-002 — Optional embedded engine helper (stretch)

**Status:** Accepted for wiring; helper binary packaging deferred  
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
- `build_app.sh` always materializes `Contents/Helpers/` (real binary when
  `Helpers/payload/runspecimen` is staged; otherwise README placeholder).
- Helper entitlements: `Entitlements/RunSpecimen.helper.entitlements` (inherit).
- Approval remains PTY-gated; no auto-`APPROVE`; no telemetry.
- Until a frozen helper ships and Developer ID certs exist, Target B
  (Developer ID + notarization) remains the v1 channel with user-selected CLI.

## Consequences

- Larger notarized artifact once packaging lands; license/runtime work still open.
- `Helpers/payload/` stays gitignored for local experiments.
- App Settings surfaces CLI **Source** so operators can confirm bundled vs PATH.
- Exact packaging steps live in `Scripts/stage_helper.sh` and Helpers/README.md.
