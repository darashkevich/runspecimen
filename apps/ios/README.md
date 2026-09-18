# RunSpecimen Observe (iOS)

SwiftUI companion for **remote observation** and optional **Mac-armed remote human confirm**.

**Bundle ID:** `com.darashkevich.runspecimen.observe`  
**Shipping channel:** TestFlight / later (no App Store submit in this change set)

## Safety boundary

- `can_approve` stays **false**. Plugins/agents cannot approve through this app.
- Local TTY `APPROVE` on the Mac remains the primary path.
- Optional remote human confirm (ADR-004): only when the Mac has armed a pending
  challenge; the human must **type** the Mac-displayed challenge **and** `APPROVE`
  (no one-tap button). This is **not** equivalent to local TTY APPROVE evidence.
- Typed **refuse + reason** consumes the pending without writing approval
  (`POST /v1/remote-confirm-refuse`). Re-arm or use Mac TTY to proceed.
- Pairing talks to `runspecimen companion` (opt-in, fail-closed).
- Loopback may use `http://127.0.0.1`. Non-loopback requires **HTTPS + TLS
  fingerprint** from the Mac printout. Tailscale is recommended. No public
  internet control plane.

See `docs/ADR-003-ios-companion-observation.md` and `docs/ADR-004-remote-human-confirm.md`.

## Generate & open

```bash
cd apps/ios
xcodegen generate
open RunSpecimenObserve.xcodeproj
```

Requires Xcode 16+ and an iOS 17+ simulator or device. Set your Development Team in Signing
(Apple Developer portal / provisioning is operator-owned).

## Pairing + remote confirm

On the Mac:

```bash
# Loopback (simulator / same Mac):
runspecimen companion \
  --workspace /path/to/ws \
  --contract /path/to/contract.json \
  --print-token

# LAN / Tailscale (TLS auto-enabled):
runspecimen companion \
  --workspace /path/to/ws \
  --contract /path/to/contract.json \
  --allow-lan --host 100.x.y.z \
  --print-token
# Paste url + pairing_token + tls_fingerprint_sha256 into the app.

# In a real TTY on the Mac (prints challenge locally; Mac banner+sound):
runspecimen remote-confirm arm \
  --workspace /path/to/ws \
  --contract /path/to/contract.json
```

Enter the printed URL + token (+ fingerprint for HTTPS) in the app. When a pending
confirm exists, the app shows one card (who/what/expiry/lease/isolation/predecessor).
Type the Mac challenge and `APPROVE` to settle, or the same challenge plus a reason
to refuse. There is no one-tap Approve. The client refuses to stay paired if
capabilities claim plugin-style `can_approve` / `can_execute`.

## Brand

App icon and mark are copied from the marketing brand pack (`sites/runspecimen/public/brand`).

## Non-goals

No App Store submit in this change set. No remote run/preflight/postflight. No
marketplace claims. No public internet control plane.
