# ADR-002 — Optional embedded engine helper (stretch)

**Status:** Proposed (scaffold only)  
**Date:** 2026-09-15  
**Related:** [ADR-001](ADR-001-architecture.md), [Helpers/README.md](../Helpers/README.md), [APP_STORE.md](../APP_STORE.md)

## Context

Target A (Mac App Store) risks rejection when the app depends on an optionally
installed PyPI/`runspecimen` CLI (guideline 2.4.5(viii)). Embedding a signed
helper under `Contents/Helpers` is the long-term mitigation.

## Decision (intent)

- Keep the SwiftUI app as a thin shell; do not reimplement leases/approval/hash
  chains in Swift.
- When ready, ship a signed helper that is the enforcement engine (or launches it).
- Approval remains PTY-gated; no auto-`APPROVE`; no telemetry.
- Until the helper ships, Target B (Developer ID + notarization) is the v1 channel.

## Consequences

- Larger notarized artifact; license/runtime packaging work deferred.
- Directory `Helpers/` is reserved; `payload/` is gitignored for local experiments.
- Discovery order documented in Helpers/README.md; not yet wired for bundled path.
