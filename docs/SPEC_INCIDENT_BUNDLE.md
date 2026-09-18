# Spec — RunSpecimen incident bundle and campaign-chain export

**Status:** Specified; local CLI `runspecimen bundle` is Community (free).  
**Not:** a Veto 7-day receipt vault. History on disk stays visible.  
**Paid later (Team):** shared retention, identity-attributed review, off-laptop store — not hiding local files.

## Job

Reconstruct one failed or ambiguous night as a pack a stranger can verify offline:

- refused second worker / out-of-order launch
- stale approval
- provenance drift
- abandon
- postflight success or failure

Willingness-to-pay metric: **time to reconstruct an incident**, not decisions per week.

## CLI

```bash
runspecimen bundle \
  --workspace . \
  --campaign-id <id> \
  --run-id <id> \
  --out /tmp/rs-incident \
  [--contract path/to/contract.json] \
  [--chain]
```

`--chain` walks `predecessor` links and nests prior run packs under `predecessors/`.

## Bundle layout

```
manifest.json          # campaign_id, run_id, schema_version, created_at, files[], confirm_channel
state.json             # copy
events.jsonl           # copy (includes refusal events)
approval.json          # copy if present
certificate.json       # copy if present
verify.json            # output of verify_run_receipt when the run is postflighted
refusals.json          # first-class extract of remote_confirm_refused / launch-refusal events
predecessors/...       # only with --chain
```

Never copy `remote_confirm_challenge.local` or pairing tokens.

## `manifest.json`

```json
{
  "product": "RunSpecimen",
  "kind": "incident_bundle",
  "schema_version": 1,
  "campaign_id": "camp",
  "run_id": "run-a",
  "confirm_channel": "local_tty_approve",
  "not_a_compliance_product": true,
  "files": ["state.json", "events.jsonl"]
}
```

`confirm_channel` is copied from approval or the last `approval` event (`local_tty_approve` | `remote_human_confirm` | omitted). Verify output must surface the same field so TTY vs phone confirm is honest.

## Campaign chain

If the contract (or state) names a predecessor, `--chain` includes that run’s bundle. A verifier can answer “was step 3 eligible?” without a dashboard.

## What Team pays for (not in Community CLI)

- Shared policy packs and SoD second human (Milestone 3)
- Retention beyond a laptop
- Support / incident review with design partners

Do not market this pack as a compliance certification.
