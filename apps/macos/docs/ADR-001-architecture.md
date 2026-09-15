# ADR-001 — RunSpecimen macOS app architecture (v1)

**Status:** Accepted  
**Date:** 2026-09-15  
**Deciders:** RunSpecimen maintainers / native app workstream

## Context

RunSpecimen’s enforcement boundary is the Python CLI (`runspecimen` on PyPI / this repo).
Hard invariants include interactive TTY approval (`APPROVE`), exclusive workspace lease,
local-only operation (no telemetry), and a read-only loopback dashboard.

We need a native macOS companion with world-class UX that does **not** reimplement the
security boundary in Swift, and that remains viable for Apple distribution (Mac App Store
and/or Developer ID notarization).

## Decision

1. **Thin native shell + CLI engine.** The app discovers / invokes the installed
   `runspecimen` binary and observes `.runspecimen/` state. It does not rewrite lease,
   approval, hashing, or certificate logic in Swift for v1.
2. **Sandbox-first design.** Code paths assume App Sandbox + security-scoped bookmarks
   for workspace folders and for the CLI executable (via `NSOpenPanel`). PATH auto-discovery
   is a convenience only when the sandbox does not apply (debug / non-MAS builds).
3. **Approval stays TTY-gated.** Approve uses a first-party sheet backed by a real PTY
   attached to `runspecimen approve`, or hands off to Terminal.app. The app never injects
   `APPROVE` unattended and never exposes a plugin/agent approval API.
4. **Dual distribution targets.**
   - **Target A — Mac App Store:** sandboxed entitlements, user-selected CLI + workspace,
     Privacy Manifest, no private APIs.
   - **Target B — Developer ID notarized:** same codebase; hardened runtime; may ship
     sooner if Store review rejects external-Python / user-selected engine dependency.
5. **Honest product surfaces.** Non-goals (not a sandbox, scheduler, compliance product,
   or asymmetric signature system) appear on empty states and About. Receipts are labeled
   as local hash-chained certificates / symmetric MAC if ever shown — never “digital signatures.”

## Consequences

- Store compliance is first-class (see `APP_STORE.md`), but **v1 recommended ship channel
  is Developer ID** until either (a) the engine is embedded as a signed helper, or
  (b) App Review accepts the user-selected CLI model with clear notes.
- Embedding a full Python+engine helper is deferred (large, license/signing complexity).
- Dashboard remains read-only; the app may launch `runspecimen dashboard --open` but must
  not add approve/run controls inside any web view.

## Alternatives considered

| Option | Why rejected for v1 |
| --- | --- |
| Electron / WKWebView wrapper of dashboard | Fails “real native functionality” and feels like a thin web wrapper (guideline 4.2). |
| Reimplement engine in Swift | High risk of diverging from the trusted CLI boundary. |
| Auto-approve / skip TTY | Violates product and threat-model invariants. |
| Unrestricted PATH shell-out in MAS sandbox | Blocked by sandbox; also weakens review story. |
