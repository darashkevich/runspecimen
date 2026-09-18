# Spec — Remote confirm one-card UX, refuse+reason, verify `confirm_channel`

**Status:** Specified; companion + CLI implement the v1 slice.  
**Brand:** RunSpecimen Remote Confirm — not “Veto inside RS.”  
**Price:** Free companion. Do not paywall remote confirm.

Related: [ADR-004](ADR-004-remote-human-confirm.md), [ADR-003](ADR-003-ios-companion-observation.md).

## One card (run ontology, not money/audience)

When a Mac-armed pending exists, the iOS observe app shows one card:

| Chip | Source |
| --- | --- |
| Who | Operator + workspace (not Personal/Work agent life) |
| What | `campaign_id` / `run_id` + bound contract hash prefix |
| Expiry | Remaining time until `expires_at_unix` |
| Lease | Held vs free |
| Isolation | Honest `native-unspecified` unless a tested backend is recorded |
| Predecessor | `none` or `campaign/run` |

Copy must state: **not equivalent to local TTY APPROVE**. No one-tap Approve. Plugins `can_approve` stays false. Challenge secret never appears in HTTP JSON.

## Confirm

Human types Mac-displayed challenge **and** the word `APPROVE`. Unchanged from ADR-004.

## Refuse + reason (Amend analog)

Typed refuse consumes the pending **without** writing an approval. A new contract + TTY or re-arm is required to proceed.

- CLI: `runspecimen remote-confirm refuse --reason "..." --challenge "..."`
- Companion: `POST /v1/remote-confirm-refuse` with pairing + **challenge** + `reason` (1–240 chars)
- Event: `remote_confirm_refused` on the hash chain (`reason`, `challenge_id`, `confirm_channel`)
- Challenge still required so a stolen pairing token cannot cancel without the Mac-displayed secret

Not a chatbot. Not App Intents / system confirmation provider (that stays Veto).

## Quiet hours (arm only)

`RUNSPECIMEN_QUIET_HOURS=22-07` (local clock, wrapping midnight) **refuses `remote-confirm arm`**. Never auto-APPROVE. Default unset = no quiet hours.

## `confirm_channel` in verify

`runspecimen verify` / `verify_run_receipt` returns:

```json
{
  "ok": true,
  "confirm_channel": "remote_human_confirm",
  "confirm_channel_note": "Remote human confirm is not equivalent to local TTY APPROVE."
}
```

Channel is read from `approval.json` or the last `approval` event. Omitted only when no approval exists (verify of a postflighted run should normally have one).
