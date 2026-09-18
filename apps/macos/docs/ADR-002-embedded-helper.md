# ADR-002 — Embedded engine helper (MAS-first)

**Status:** Accepted — MAS path requires frozen Mach-O helper (`build_app.sh --mas`,
fail closed); `--from-src` host-Python remains local/CI only  
**Date:** 2026-09-16  
**Related:** [ADR-001](ADR-001-architecture.md), [Helpers/README.md](../Helpers/README.md),
[APP_STORE.md](../APP_STORE.md), [SECURITY_BOUNDARY.md](SECURITY_BOUNDARY.md),
[RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md)

## Context

Mac App Store guideline **2.4.5(viii)** risks rejection when the app depends on
optionally installed Python/PyPI tools. Embedding a self-contained helper under
`Contents/Helpers` is required for the primary Store submission path.

## Decision

- Keep the SwiftUI app as a thin shell; do not reimplement leases/approval/hash
  chains in Swift.
- **Primary Store packaging:** `./Scripts/build_app.sh --mas`
  - `Entitlements/RunSpecimen.mas.entitlements`
  - `RSDistributionChannel=mas` in Info.plist
  - PyInstaller onefile freeze into `Contents/Helpers/runspecimen` (**required**)
  - Fail closed if freeze fails or helper is a host-Python shell launcher
  - No `Contents/Helpers/lib/` package tree in MAS builds
- **Local/CI convenience:** `stage_helper.sh --from-src` (host Python 3.9+) remains
  supported for Prefer Bundled Helper smoke without PyInstaller.
- Discovery: bookmark → bundled Helpers → PATH (PATH disabled on MAS channel).
- Approval remains PTY-gated; no auto-`APPROVE`; no telemetry.
- App Sandbox confines UI (+ inherit helper). Payload under test is **not**
  claimed to be OS-sandboxed by the UI sandbox alone.

## Consequences

- Store builds need PyInstaller on the packaging machine and Apple Distribution
  + full Xcode for Archive/upload (operator-only on cert-less agent Macs).
- Frozen artifacts need CPython / PyInstaller NOTICE attribution.
- `Helpers/payload/` stays gitignored.
- Runtime MAS builds reject host-Python launchers even if somehow staged.
