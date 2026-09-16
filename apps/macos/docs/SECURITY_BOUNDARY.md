# Security boundary — app sandbox vs payload

RunSpecimen’s Mac app is a **native control surface** over the enforcement CLI.
This document states what App Sandbox confines, what it does **not**, and how
human PTY approval stays intact. Never auto-type `APPROVE`. No telemetry.

## Layers

| Layer | What it is | Confined by App Sandbox? |
| --- | --- | --- |
| SwiftUI shell (`RunSpecimen.app`) | Status, evidence, Open panels, Approve UI | **Yes** — App Sandbox + user-selected bookmarks |
| Bundled helper (`Contents/Helpers/runspecimen`) | Same Apache-2.0 CLI engine | **Yes when spawned as child** via `com.apple.security.inherit` |
| User-selected CLI (Open panel bookmark) | External `runspecimen` binary | Access granted by security-scoped bookmark; still basename + version gated |
| **Payload under test** (contract `argv`) | The command the human approved | **No** — not an OS sandbox merely because the UI is sandboxed |

## What the app sandbox confines

- File access from the UI process except through `NSOpenPanel` security-scoped bookmarks (`user-selected.read-write` / `user-selected.executable`).
- Network from the app process per declared entitlements (docs links / optional loopback dashboard).
- Child helper processes that inherit the sandbox when signed with `RunSpecimen.helper.entitlements`.

## What the app sandbox does **not** do

- It does **not** turn the payload command into a macOS App Sandbox / Seatbelt jail.
- It does **not** replace RunSpecimen’s lease, contract hash, TTY gate, or postflight checks.
- It does **not** make hash-chained certificates into asymmetric “digital signatures.”
- It does **not** allow agents/plugins to approve — only a human on a real PTY typing `APPROVE`.

Honest product copy must say: **local evidence / bounded run control**, not “OS sandbox for arbitrary payloads.”

## Human PTY approval (invariant)

1. `ApproveSheet` / `PTYApprovalSession` attach `runspecimen approve` to a real PTY (`openpty` + `posix_spawn`).
2. The engine’s `isatty` gate remains intact.
3. The app **never** auto-detects, coerces, or types `APPROVE`.
4. Send only forwards what the human typed.
5. Cancel stops the PTY without approving.

Static checks live in `SecurityBoundary.swift` and `Scripts/test_security_boundary.sh`.

## MAS packaging implication

Mac App Store builds (`./Scripts/build_app.sh --mas`) **fail closed** without a
frozen Mach-O helper under `Contents/Helpers`. Host-Python `--from-src` launchers
are local/CI only — they are rejected at runtime when `RSDistributionChannel=mas`.

## Reviewer one-liner

> The Mac app is sandboxed. Enforcement and approval are the bundled CLI on a
> human PTY. The payload under test is not claimed to be OS-sandboxed by the UI
> sandbox alone.
