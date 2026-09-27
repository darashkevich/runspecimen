# Deterministic fast path

RunSpecimen does not ship a generative-model runtime. The only provider
dispatch on the evidence-expansion surface is `eval` (`EvalProvider.run_task`).
The fast path is an **opt-in exact-match** step that runs *after* suite/config
validation and workspace safety checks, and *before* that provider is invoked.

It exists so a configured acknowledgement can complete a **text-completion**
task without calling that task's eval provider. It does **not** make CPU, disk,
or application work zero. It does **not** approve a run, settle remote confirm,
or skip contract and requirement checks.

## What can be skipped on a hit

Only a task that sets `capability` to `text_completion`, and only when its
provider is not `local_deterministic`. A hit skips `EvalProvider.run_task` for
that task. The recorded outcome is `text_completed`, which is not a passed
requirement check and is not conclusive eval evidence.

`local_deterministic` tasks, fixture/contract/check tasks, and any task without
`capability: text_completion` always take the existing provider path.

## What still runs

- JSON schema validation of the suite or `fastpath_config`
- artifact digest verification on the original serialized suite
- workspace resolution
- live pending-confirmation / structured-action / `requires_human` checks
- contract and requirement evaluation for every non-text-completion task
- eval result writing, digests, dashboard counters, and CLI JSON

## Configuration

Disabled unless you opt in. Sample rules below are examples, not defaults.

```json
{
  "schema_kind": "fastpath_config",
  "schema_version": 1,
  "enabled": true,
  "rules": [
    {
      "id": "gratitude",
      "exact": ["thanks", "thank you", "thx", "ty", "cheers"],
      "outcome": {"type": "respond", "text": "You're welcome."}
    },
    {
      "id": "acknowledgement",
      "exact": ["ok", "okay", "got it", "understood"],
      "outcome": {"type": "no_response"}
    }
  ]
}
```

Embed the same `enabled` / `rules` object as `fastpath` on an `eval_suite`, or
pass a sidecar to:

```bash
runspecimen eval complete --workspace . --config path/to/fastpath.json --input "Thank you!"
```

### Normalization (exact after this)

1. trim; 2. Unicode casefold; 3. collapse internal whitespace to one space;
4. remove a trailing run of `.` and `!` only; 5. trim again.

`?`, commas, emoji, and extra words stay. `"thank you?"` is not `"thank you"`.
Normalization is one pass and is not idempotent: `"ok! !"` becomes `"ok!"`, and
a second pass would become `"ok"`. Saved and digest-bound configs keep the
author's original strings. The compiled lookup is not written back into the
document, and a user-supplied `index` is rejected.

### Matching

After normalization, the whole string must equal one configured variant.
Conflicts that normalize to the same value across rule IDs fail at load time.

### Outcomes

- `respond` — return the configured text. Not a model result.
- `no_response` — `ok: true` with `text: null`. Not a provider failure.

## Safety

The fast path declines, and the existing provider path runs, when:

- the task does not declare `capability: text_completion`
- the provider is `local_deterministic`
- `requires_human` is true, whatever the judgment
- the text normalizes to `approve`
- the task carries structured action/tool/confirm fields
- the workspace has a **live** remote-confirm pending file

Consumed or expired pending records do not disable routing. Unreadable or
malformed pending state stays conservative and does. A present `consumed`
value that is not a boolean, or an `expires_at_unix` value that is not a
number, is malformed and blocks routing before the record can be treated as
inactive. Generic `"ok"` rules must not swallow a confirmation or a
requirement check.

## Observability

Hits record `route=fastpath`, `provider_called=false`, and known-zero inference
tokens. `model_calls_avoided` is 1 only when the skipped task's judgment is
`model`. Standalone `eval complete` has no model fallback, so that counter
stays 0. `provider_dispatches_avoided` counts a skipped suite provider.
`deterministic_completions` counts hits. Estimated token or energy savings are
not invented.

Misses and safety declines keep a stable `reason` (`no_match`,
`unsafe_requires_human`, `unsafe_pending_confirmation`, and the other decline
reasons). Provider-supplied token and cost measurements are copied when
present. A missing measurement stays unknown (`null`), not zero.

The loopback dashboard shows these counters from the latest eval result and
refreshes them with status.

## Streaming

Eval and `eval complete` are request/response JSON. There is no model token
stream to keep compatible.

## V2 (not implemented)

Local classifiers, semantic routing, localization packs, and environmental
accounting stay out of this version.
