# Reviewer demo + App Review notes

**Status:** paste-ready. Sample workspace zip attachment in Connect is **pending** if showcase is not embedded in the build.

## Review notes (paste)

> RunSpecimen is a local safety/evidence control surface for one human-approved
> bounded run at a time. The Mac app is a sandboxed SwiftUI shell. Enforcement is
> the **bundled** `Contents/Helpers/runspecimen` CLI (Apache-2.0, frozen Mach-O —
> no host Python). Approval requires an interactive PTY and the human typing
> APPROVE — the app never auto-approves and has no agent API. App Sandbox
> confines the UI (+ inherit helper); it does **not** claim to OS-sandbox the
> payload under test. Certificates are hash-chained receipts, not asymmetric
> digital signatures. The optional dashboard is loopback-only and read-only.
> No telemetry. Workspace paths use NSOpenPanel security-scoped bookmarks.

## Demo path (5 steps)

1. Launch RunSpecimen — Source should read **Bundled Helpers** (frozen engine).
2. Choose workspace → attach `examples/showcase` (or the Review notes sample zip).
3. Refresh status / inspect certificate (read-only).
4. Open **Approve…** — type `APPROVE` yourself on the PTY (**do not automate**).
5. Quit — confirm the loopback dashboard child is gone (Activity Monitor / no stray port).

## Contact for Review

| Field | Value | Status |
| --- | --- | --- |
| Demo account | N/A — no accounts | Ready |
| Contact | Yahor (ASC Account Holder) | **Pending** phone/email in Connect |
| Notes attachment | showcase zip | **Pending** if needed |

## Automated evidence (not a substitute for Review)

Local positive e2e (never types APPROVE):

```bash
cd apps/macos
./Scripts/archive_mas.sh
./Scripts/test_mas_sandbox_e2e.sh
```

Covers workspace bookmark, dashboard cleanup, and PTY gate wait on the sandboxed app + bundled helper.
