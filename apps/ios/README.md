# RunSpecimen Observe (iOS)

SwiftUI companion for **remote observation** of a Mac-side RunSpecimen workspace.

## Safety boundary

- This app **cannot approve or execute**.
- Pairing talks to `runspecimen companion` (opt-in, fail-closed). See `docs/ADR-003-ios-companion-observation.md`.
- Attention / open-dashboard requests still require a human on the Mac for any lifecycle step.

## Generate & open

```bash
cd apps/ios
xcodegen generate
open RunSpecimenObserve.xcodeproj
```

Requires Xcode 16+ / 27 and an iOS 17+ simulator or device. Set your Development Team in Signing.

## Pairing

On the Mac (private or Tailscale IP):

```bash
runspecimen companion \
  --workspace /path/to/ws \
  --contract /path/to/contract.json \
  --allow-lan --host 100.x.y.z \
  --print-token
```

Enter the printed URL + token in the app. The client refuses to stay paired if capabilities claim `can_approve` / `can_execute`.

## Brand

App icon and mark are copied from the marketing brand pack (`sites/runspecimen/public/brand`).

## Non-goals

No App Store submit in this scaffold. No remote approve/run API. No marketplace claims.
