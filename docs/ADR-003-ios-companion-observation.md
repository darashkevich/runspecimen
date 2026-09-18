# ADR-003 — iOS companion for remote observation (not remote approval)

**Status:** Proposed (scaffold landed; pairing transport decision open)  
**Date:** 2026-09-17  
**Deciders:** Yahor (required sign-off before any mutating remote API)  
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
| Request attention (notify Mac operator) | Optional | Local notification / banner only |
| Open loopback dashboard on Mac | Optional narrow command | Local-only side effect |
| `approve` / `run` / `preflight` / `postflight` / inject `APPROVE` via plugins | **Forbidden** (`can_approve` always false) | TTY / native PTY only |
| Mac-armed **remote human confirm** (challenge + `APPROVE` on paired phone) | Allowed only per **ADR-004** when Mac armed a pending | Challenge shown locally on Mac |
| Unattended remote execute | **Forbidden** | N/A |

### Pairing & transport (v1 recommendation)

1. **Default off.** Companion listener does not start unless the operator opts in.
2. **Fail-closed bind.** Default bind is loopback. LAN / Tailscale bind requires an explicit flag and refuses public/unspecified addresses unless a future ADR adds authenticated internet exposure.
3. **Pairing model (recommended for v1):** local-network QR (or short code) that transfers a **pairing secret** + Mac endpoint URL over an out-of-band channel the human can see. iOS stores the secret in Keychain; requests use a short-lived HMAC (or bearer derived from the secret). Prefer Tailscale/LAN over any public internet control plane.
4. **iCloud / public relay:** deferred. Not in v1. Would need a separate ADR covering authn, key custody, and residual remote-attacker risk.
5. **Trust:** the phone is an untrusted observer by default. With ADR-004, a paired
   phone may settle a **Mac-armed** pending confirm only by typing the Mac-local
   challenge + `APPROVE`. A compromised phone still cannot invent approve/run without
   that Mac-side challenge. Plugins never get `can_approve`.

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

Optional additive path (Yahor go-ahead; see **ADR-004**):

- `POST /v1/remote-confirm` — paired companion only; settles a **Mac-armed** pending
  challenge when the human types challenge + `APPROVE`. Not TTY-equivalent.
- Status/capabilities may set `can_remote_confirm=true` only while that pending exists;
  `can_approve` remains **false** forever for plugins.

### Threat model deltas

| Threat | Mitigation / residual |
| --- | --- |
| Remote attacker forges journal via companion | Companion writes approval **only** via ADR-004 settle of a Mac-armed pending; otherwise never writes lifecycle. Journal trust remains local hash-chain (+ optional HMAC/Ed25519). |
| Stolen pairing secret | Attacker can read status and request attention until revoked. Without the Mac-displayed challenge, remote confirm fails. Rotate by stopping companion and re-pairing. |
| LAN MITM without TLS | v1 may use HTTP on trusted LAN/Tailscale with bearer auth; treat as cleartext-equivalent if the network is hostile. **mTLS required before untrusted networks** (ADR-004). |
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
| iOS app shells SSH and types APPROVE | Still remote approval; forbidden |
| Reuse loopback dashboard from phone via tunnel without pairing | Host header / loopback checks intentionally block this; bypassing them would weaken dashboard guarantees |

## Yahor decisions needed

1. **Transport:** LAN-only vs Tailscale-preferred vs defer any non-loopback bind until mutual TLS exists?
2. **Attention channel:** local macOS notification only, or also sound / Focus bypass?
3. **When (if ever)** authenticated remote human confirm — **accepted in ADR-004** as
   Mac-armed challenge + phone-typed APPROVE; still never for agents/plugins.
4. **Brand / App Store:** companion bundle id and whether it ships as a separate free utility after Mac app channel stabilizes.

## Explicit non-goals (v1 observation scaffold)

- Agent- or plugin-driven approval from iOS
- Claiming OS sandboxing, compliance certification, or Ed25519-as-legal-signature
- Equating remote human confirm with local TTY APPROVE (see ADR-004 claim language)
- Product telemetry / phone-home
- Public unauthenticated control plane
- Merging into Mac App Store binary in this change set

Remote `run` / `preflight` / `postflight` remain forbidden. Narrow Mac-armed remote
human confirm is specified in `docs/ADR-004-remote-human-confirm.md`.
