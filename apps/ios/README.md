# RunSpecimen Observe (iOS)

SwiftUI companion for **remote observation** and optional **Mac-armed remote human confirm**.

## Safety boundary

- `can_approve` stays **false**. Plugins/agents cannot approve through this app.
- Local TTY `APPROVE` on the Mac remains the primary path.
- Optional remote human confirm (ADR-004): only when the Mac has armed a pending
  challenge; the human must **type** the Mac-displayed challenge **and** `APPROVE`
  (no one-tap button). This is **not** equivalent to local TTY APPROVE evidence.
- Pairing talks to `runspecimen companion` (opt-in, fail-closed).

See `docs/ADR-003-ios-companion-observation.md` and `docs/ADR-004-remote-human-confirm.md`.

## Generate & open

```bash
cd apps/ios
xcodegen generate
open RunSpecimenObserve.xcodeproj
```

Requires Xcode 16+ and an iOS 17+ simulator or device. Set your Development Team in Signing.

## Pairing + remote confirm

On the Mac:

```bash
runspecimen companion \
  --workspace /path/to/ws \
  --contract /path/to/contract.json \
  --allow-lan --host 100.x.y.z \
  --print-token

# In a real TTY on the Mac (prints challenge locally only):
runspecimen remote-confirm arm \
  --workspace /path/to/ws \
  --contract /path/to/contract.json
```

Enter the printed URL + token in the app. When a pending confirm exists, type the
Mac challenge and `APPROVE`. The client refuses to stay paired if capabilities claim
plugin-style `can_approve` / `can_execute`.

## Brand

App icon and mark are copied from the marketing brand pack (`sites/runspecimen/public/brand`).

## Non-goals

No App Store submit in this change set. No remote run/preflight/postflight. No
marketplace claims. No public internet control plane (mTLS required before untrusted networks).
