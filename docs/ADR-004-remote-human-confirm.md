# ADR-004 — Attested remote human confirm (not TTY-equivalent)

**Status:** Accepted (opt-in companion path; transport / attention / bundle defaults locked 2026-09-18)  
**Date:** 2026-09-18  
**Deciders:** Yahor  
**Related:** `docs/ADR-003-ios-companion-observation.md`, `docs/THREAT_MODEL.md`, loopback dashboard

## Context

ADR-003 shipped observation + attention only and forbade remote `approve` / `run`.
Operators still want a **phone-side human confirm** when they are away from the
Mac keyboard but can see (or be told) a short challenge displayed on the Mac.

That capability must not be confused with:

- local interactive TTY `APPROVE` (primary path; strongest local evidence story)
- agent / Codex / Cursor plugin approval (still forbidden)
- OS sandboxing or App Sandbox confinement claims
- a public internet control plane

## Decision

### Product name and claim language

Call this path **remote human confirm** (receipt field: `confirm_channel =
"remote_human_confirm"`). Do **not** claim it is equivalent to local TTY-only
approval evidence. Receipts and UI copy must state the distinction explicitly.

Honest claim:

> A human who could observe the Mac-displayed one-shot challenge typed that
> challenge plus the word `APPROVE` on a paired companion after the Mac armed a
> pending confirm. This is attested remote human confirm — not local TTY
> APPROVE, not agent approval, and not an OS sandbox.

### Flow (fail-closed)

1. **Mac arms** a pending confirm for one contract (`runspecimen remote-confirm arm`).
   Arming requires an interactive TTY. The one-shot challenge is printed **only**
   to that local TTY (and optionally a mode-0600 local display file for the Mac
   helper). The challenge secret is **never** returned by the companion HTTP API,
   including to a paired phone. Arming also posts a Mac local notification **with
   sound** (Focus/DND may still suppress it; no Focus-bypass claim).
2. Companion **status** (authenticated pairing only) surfaces **presence**:
   `can_remote_confirm=true` while a non-expired, unconsumed pending exists.
   Unauthenticated clients see neither the secret nor pending details beyond
   public health (`can_approve` remains false).
3. **Phone** shows text fields (not a one-tap Approve button). The human must
   type the Mac challenge **and** the word `APPROVE`.
4. Companion accepts `POST /v1/remote-confirm` **only** with a valid pairing
   token, matching challenge, exact `APPROVE` phrase, live pending, and an
   allowed transport (loopback cleartext **or** TLS). Success consumes the
   challenge (single-use), rate-limits failures, and writes the approval with
   remote-confirm attestation metadata.
5. No pending / wrong challenge / reuse / expired / unauthenticated / plugin
   path / cleartext off loopback → **refuse**. No silent remote run of arbitrary
   commands.

### Capability flags (plugin exclusion)

| Flag | Plugins / agents / generic clients | Paired companion with pending |
| --- | --- | --- |
| `can_approve` | **Always false** | **Always false** |
| `can_execute` | Always false | Always false |
| `can_mutate_lifecycle` | Always false | Always false |
| `can_remote_confirm` | Absent / false | **True only while Mac-armed pending exists** |

Lifecycle verb paths containing `approve`, `run`, `preflight`, `postflight`,
`execute`, `pty`, `inject` remain **forbidden** on the companion. Codex and
Cursor plugins must continue to instruct humans to use local TTY `approve` and
must not be given pairing tokens or a remote-confirm automation path.

### Transport / TLS (Accepted defaults)

- Default bind is loopback; pairing bearer over HTTP is OK on loopback.
- `--allow-lan` only for private / link-local / Tailscale CGNAT addresses;
  refuse public and unspecified binds.
- **Non-loopback binds require TLS** before the listener starts: ephemeral
  self-signed cert generated at pair time (or operator `--tls-cert` /
  `--tls-key`). iOS pins the printed SHA-256 fingerprint.
- Pairing bearer + challenge + short TTL + rate limit remain required on every
  remote-confirm attempt.
- **Cleartext remote-confirm off loopback is refused.**
- **Tailscale (or equivalent private mesh) is the recommended path.**
- **No public internet control plane.**
- Full client-certificate mutual TLS remains optional future hardening; the
  Accepted v1 authenticator off loopback is **TLS server cert (pinned) + pairing
  bearer**.

### Attention UX (Accepted default)

- Local macOS banner **with sound** on arm and on `/v1/attention`.
- Document honestly: Focus / DND may suppress delivery; no Focus-bypass claim.
- Silent-only is not the default for armed remote-confirm.

### Bundle IDs

- iOS Observe: `com.darashkevich.runspecimen.observe`
- Mac companion helper: `com.darashkevich.runspecimen.companion`
- Shipping channel: **TestFlight / later** (portal / upload / submit still out of scope)

### Receipt / event fields

Approval documents created via this path include at least:

```json
{
  "confirm_channel": "remote_human_confirm",
  "confirm_evidence": {
    "kind": "mac_armed_challenge_plus_approve_phrase",
    "challenge_id": "<id>",
    "not_equivalent_to": "local_tty_approve",
    "claim": "Remote human confirm of a Mac-armed pending approval; distinct from interactive TTY APPROVE."
  }
}
```

Event log `approval` entries should carry the same `confirm_channel` so verifiers
can distinguish channels without over-reading integrity as sandboxing.

## Consequences

- Observation APIs from ADR-003 remain; remote confirm is **additive opt-in**.
- Local TTY `runspecimen approve` stays the primary path.
- Companion may write lifecycle state **only** by settling a Mac-armed pending
  remote confirm — never by inventing approve/run from the phone alone.
- iOS and Mac helper copy must describe the boundary honestly.
- MAS packaging (`apps/macos` / PR #6) remains untouched by this change set.
- No App Store submit, notarization, or merge-to-main implied by this ADR alone.

## Threat model deltas

| Threat | Mitigation / residual |
| --- | --- |
| Agent calls `/v1/approve` or injects TTY APPROVE | Paths forbidden; plugins lack pairing; `can_approve` stays false |
| Agent arms remote confirm non-interactively | `arm` requires interactive TTY; challenge printed only to that TTY |
| Stolen pairing token without Mac challenge | Cannot confirm without the one-shot challenge; rate-limited guesses |
| Replay of successful confirm | Challenge single-use; pending consumed |
| Phone one-tap phishing UX | UI requires typed challenge + `APPROVE`; no one-tap approve |
| Equating remote confirm with TTY evidence | Receipt `not_equivalent_to` + boundary copy |
| Cleartext LAN remote-confirm / public exposure | TLS required off loopback; bind policy; no public control plane |
| Confused as OS sandbox | Explicit non-goal; capabilities boundary text |

## Explicit non-goals

- Replacing local TTY approve as the primary path
- Agent- or plugin-driven remote confirm
- Remote `run` / `preflight` / `postflight` / arbitrary command execution
- Claiming OS sandboxing, compliance certification, or TTY-equivalent evidence
- Public unauthenticated control plane
- Apple Developer portal records, TestFlight upload, App Store submit
- Focus / DND bypass for attention banners

## Still operator / Apple-portal owned

- App record, provisioning, Development Team, TestFlight upload, App Store submit

## Alternatives considered

| Option | Why rejected |
| --- | --- |
| One-tap Approve on phone | Weak attestation; phishing-friendly; fails Yahor design |
| Send challenge secret to phone over API | Weakens “see Mac challenge” attestation |
| Allow plugins to call remote-confirm | Breaks agent-cannot-approve invariant |
| Full remote run control plane | Out of scope; expands blast radius |
| Cleartext LAN remote-confirm | Rejected; TLS required off loopback |
| Require client-certificate mTLS before any LAN use | Deferred as optional hardening; pinned server TLS + pairing bearer is the Accepted default |
