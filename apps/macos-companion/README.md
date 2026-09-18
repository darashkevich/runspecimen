# RunSpecimen macOS companion helper

Thin SwiftPM module + UI that **previews** the opt-in CLI and provides a **local
challenge display** surface for ADR-004 remote human confirm.

**Bundle ID:** `com.darashkevich.runspecimen.companion`  
**Shipping channel:** TestFlight / later (no App Store submit / notarize in this change set)

```text
runspecimen companion --workspace … --contract … [--allow-lan --host …] --print-token
runspecimen remote-confirm arm --workspace … --contract …
```

## Invariants

- Does **not** inject TTY `APPROVE`.
- Does **not** give plugins an approve path (`can_approve` stays false).
- Challenge secret is Mac-local only (TTY / paste field / mode-0600 local file).
- Non-loopback companion binds require TLS (Python CLI); Tailscale recommended.
- Attention default: local banner **with sound** (CLI `osascript` + helper
  UserNotifications). Focus/DND may suppress delivery — no Focus-bypass claim.
- Enforcement lives in `src/runspecimen/companion.py` and `remote_confirm.py`.
- See `docs/ADR-004-remote-human-confirm.md` (and ADR-003 for observation).

## Build

```bash
cd apps/macos-companion
swift test
swift run runspecimen-companion-ui
```

This tree is independent of `apps/macos` (MAS packaging / PR #6) so it can merge from `main` without disturbing that branch.
