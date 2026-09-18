# ADR-003 — iOS companion for remote observation (not remote approval)

**Status:** Accepted (product defaults locked 2026-09-18; Apple portal / TestFlight upload still operator-owned)  
**Date:** 2026-09-17  
**Deciders:** Yahor  
**Related:** `docs/THREAT_MODEL.md`, loopback dashboard (`src/runspecimen/dashboard.py`), macOS ADR-001 (PR #6 / `apps/macos`)

## Context

Operators want phone-side awareness of RunSpecimen lifecycle state while away from the Mac keyboard. Wording like “remotely control” can be read as remote `approve` / `run` / `postflight`. That reading **violates** product invariants:

- Local-only CLI enforcement; no product telemetry / phone-home by default
- Human approval is real-TTY `APPROVE` on the Mac; **agents/plugins must never approve**
- Loopback dashboard is read-only and cannot approve/execute
- Remote control must **not** be misrepresented as OS sandboxing
- HMAC / Ed25519 claims stay honest (shared-secret ≠ non-repudiation; signatures ≠ scientific truth)

## Decision

### v1 product shape

Ship a companion as **remote observation + optional attention request**, with intentional Mac-side human confirmation for any lifecycle mutation.

| Capability | v1 remote (iOS) | Mac-side |
| --- | --- | --- |
| Read phase / lease / receipt summaries | Yes (authenticated) | Source of truth via CLI / `.runspecimen/` |
| Refresh status | Yes (non-mutating) | Serves snapshot |
| Request attention (notify Mac operator) | Optional | Local notification / banner **with sound** (default) |
| Open loopback dashboard on Mac | Optional narrow command | Local-only side effect |
| `approve` / `run` / `preflight` / `postflight` / inject `APPROVE` via plugins | **Forbidden** (`can_approve` always false) | TTY / native PTY only |
| Mac-armed **remote human confirm** (challenge + `APPROVE` on paired phone) | Allowed only per **ADR-004** when Mac armed a pending | Challenge shown locally on Mac |
| Unattended remote execute | **Forbidden** | N/A |

### Pairing & transport (Accepted defaults)

1. **Default off.** Companion listener does not start unless the operator opts in.
2. **Fail-closed bind.** Default bind is loopback. LAN / Tailscale bind requires `--allow-lan` and refuses public/unspecified addresses.
3. **Loopback:** pairing bearer over cleartext HTTP is OK.
4. **Non-loopback:** TLS is **required** before the listener starts (ephemeral self-signed cert generated at pair time, or operator-supplied `--tls-cert` / `--tls-key`). Phone pins the printed SHA-256 fingerprint. Pairing bearer remains the client authenticator (full client-certificate mTLS is optional future hardening, not required for this default).
5. **Remote-confirm** additionally refuses cleartext off loopback even if a misconfigured cleartext socket exists.
6. **Recommended path:** Tailscale (or equivalent private mesh) + TLS. **No public internet control plane.**
7. **Pairing model:** out-of-band transfer of URL + pairing secret (+ TLS fingerprint when HTTPS). iOS stores secrets in Keychain / app defaults for the observe client.
8. **iCloud / public relay:** deferred. Not in v1.

### Attention UX (Accepted default)

- Mac posts a **local notification banner with sound** when the phone requests attention and when a remote confirm is armed.
- Honest limit: **Focus / Do Not Disturb may suppress banners and sounds**; RunSpecimen does **not** claim Focus bypass.
- Silent-only is **not** the product default for armed remote-confirm on the Mac helper / CLI path.

### Bundle IDs / shipping channel (Accepted convention; portal still open)

| Surface | Bundle ID |
| --- | --- |
| iOS Observe | `com.darashkevich.runspecimen.observe` |
| Mac companion helper | `com.darashkevich.runspecimen.companion` |

Shipping channel for the iOS binary: **TestFlight / later**. No App Store submit, ASC upload, or notarization is implied by accepting this ADR. Apple Developer portal app records and provisioning remain operator-owned.

### API surface (companion endpoint)

Allowed (read / non-mutating):

- `GET /v1/health`
- `GET /v1/capabilities` — `can_approve=false` always; `can_remote_confirm` only when Mac-armed pending exists
- `GET /v1/status` — status snapshot (same family as CLI `status` / dashboard JSON)
- `POST /v1/attention` — request Mac-side human attention (no lifecycle change)
- `POST /v1/open-dashboard` — optional; only triggers local dashboard open on Mac

Explicitly rejected without ADR-004 settle semantics (405 / 403):

- any path containing `approve`, `run`, `preflight`, `postflight`, `execute`, `pty`, `inject`
- agent/plugin-driven approval

Optional additive path (see **ADR-004**):

- `POST /v1/remote-confirm` — paired companion only; settles a **Mac-armed** pending
  challenge when the human types challenge + `APPROVE`. Not TTY-equivalent.
- Status/capabilities may set `can_remote_confirm=true` only while that pending exists;
  `can_approve` remains **false** forever for plugins.

### Threat model deltas

| Threat | Mitigation / residual |
| --- | --- |
| Remote attacker forges journal via companion | Companion writes approval **only** via ADR-004 settle of a Mac-armed pending; otherwise never writes lifecycle. Journal trust remains local hash-chain (+ optional HMAC/Ed25519). |
| Stolen pairing secret | Attacker can read status and request attention until revoked. Without the Mac-displayed challenge, remote confirm fails. Rotate by stopping companion and re-pairing. |
| LAN MITM without TLS | Non-loopback binds require TLS + fingerprint pin; cleartext remote-confirm off loopback is refused. Residual: hostile LAN can still observe cleartext loopback if somehow reachable. |
| Phishing “approve on phone” UX | No one-tap approve; typed challenge + APPROVE; copy states not TTY-equivalent. |
| Confused deputy / plugin calling companion | `can_approve` always false; `/v1/approve` forbidden; plugins must not receive pairing tokens or automate remote-confirm. |
| Misread as sandbox | Capabilities + About copy: evidence/observation layer, not OS confinement. |

## Consequences

- Scaffold lives under `apps/ios/` (SwiftUI observe client) and `apps/macos-companion/` (optional Mac helper UI). Enforcement stays in the Python CLI companion module (`src/runspecimen/companion.py`), fail-closed and opt-in.
- Does **not** disturb MAS packaging on `cursor/macos-native-app` (PR #6). Integration into the native Mac app is a later merge once that work lands.
- No App Store submit in this ADR. No marketplace claims. Unattended remote approval remains forbidden; Mac-armed remote human confirm is ADR-004.

## Alternatives considered

| Option | Why rejected for v1 |
| --- | --- |
| Remote approve/run API with strong auth | Breaks TTY-human invariant; agents could be wired to it; needs Yahor sign-off + new ADR |
| Public internet control plane (default) | Expands attack surface; conflicts with local-only default |
| Cleartext LAN remote-confirm | Rejected; TLS required off loopback |
| iOS app shells SSH and types APPROVE | Still remote approval; forbidden |
| Reuse loopback dashboard from phone via tunnel without pairing | Host header / loopback checks intentionally block this; bypassing them would weaken dashboard guarantees |
| Focus-bypass “critical alert” attention | Overreach for v1; document Focus limits honestly instead |

## Still operator / Apple-portal owned

- Creating the App Store Connect / Developer portal app records
- Provisioning profiles, Development Team signing, TestFlight upload
- App Store submit (explicitly out of scope)

## Explicit non-goals (v1)

- Agent- or plugin-driven approval from iOS
- Claiming OS sandboxing, compliance certification, or Ed25519-as-legal-signature
- Equating remote human confirm with local TTY APPROVE (see ADR-004 claim language)
- Product telemetry / phone-home
- Public unauthenticated control plane
- Merging into Mac App Store binary in this change set

Remote `run` / `preflight` / `postflight` remain forbidden. Narrow Mac-armed remote
human confirm is specified in `docs/ADR-004-remote-human-confirm.md`.
