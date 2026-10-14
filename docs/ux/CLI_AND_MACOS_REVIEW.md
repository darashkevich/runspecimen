# RunSpecimen UX/UI review (CLI + macOS)

Grounded in the shipped surface on `main` (`0.2.0rc14`): Python CLI in
`src/runspecimen/cli.py`, TTY approval in `src/runspecimen/approve.py`,
refusals across `preflight.py` / `run.py` / `postflight.py` / `certificate.py`,
the loopback dashboard in `src/runspecimen/dashboard.py`, and the SwiftUI app
under `apps/macos/`. This is a presentation review. It does not propose
changes to approval, hashing, leases, certificates, or release gates.

## What users actually experience today

**CLI is the enforcement boundary.** The happy path is still
`approve → preflight → run → postflight → verify`. Every one of those commands
prints a **sorted, indented JSON document** on success. Failures print a single
stderr line `RunSpecimen error: {message}` and exit 1.

**macOS is a thin shell.** `apps/macos/README.md` states it does not reimplement
leases, approval, or verify. Approve attaches `runspecimen approve` to a real
PTY (`ApproveSheet.swift`) and never types `APPROVE`. Evidence inspection is
read-only.

**The dashboard is already the best human UI.** It answers “what happened?”,
“is it safe to continue?”, and labels phases in English
(`dashboard.py` `_PHASE_LABELS`, `_happened_summary`, `_continue_verdict`).
The CLI does not reuse that language. `status` is documented as the diagnosis
command and still dumps the full JSON document (`status.format_status`).

## First-time user (pip / Homebrew, no git tree)

1. `runspecimen` with no command → argparse usage plus
   `the following arguments are required: command` (exit 2). No quick start.
2. `runspecimen --help` lists **20+ subcommands** with one-line blurbs. Core
   lifecycle sits next to `companion`, `keygen`, `bundle`, `remote-confirm`.
   No copy-pasteable example block (until this prototype).
3. README / user guide tell them to `init-demo`, then `doctor`, `validate`,
   then type `APPROVE`. `init-demo` itself prints JSON
   `{ok, workspace, contract, approved, executed}` with **no next commands**.
4. `approve` draws a dense TTY dump: Python `repr()` of argv/lists, raw byte
   sizes (`65536B`), unlabeled 64-character hashes, `runtime#`, `ttl_sec`.
   The bind line is `Type 'APPROVE' to bind this approval:` — clear enough, but
   “bind” is jargon and the screen is hard to scan.
5. After approval they get the full approval JSON. Next step is not stated.
6. `preflight` / `run` / `postflight` / `verify` each dump more JSON. The
   certificate is a nested object. There is no table of output digests.
7. If they skip approve: `RunSpecimen error: no approval present; run approve first`
   — true, but it does not show the command line to run.
8. If they run without a TTY: `approval requires an interactive TTY on stdin and stdout (refuse unattended / piped approval)` — correct and fail-closed,
   opaque if they pasted the command into an agent chat.

## Repeat user

Friction is different: they know the lifecycle, but every diagnosis is a JSON
blob. `status` includes nested `state` + `approval` + lease metadata.
`digest` / `diff` exist and are honest that they are not `verify`, yet they
still print JSON only. Re-approving after TTL/source drift requires decoding
`approval expired (stale)` or `changed provenance: source hash drift`.
`run already in phase='completed'; refuse re-entry` does not say “use a new
run_id”. Declared outputs left on disk:
`asserted output already exists (refuse overwrite): …` — no “move the file or
change run_id”.

`--campaign-id` and `--run-id` are required on `verify` even when `--contract`
already contains them. That is an identity check, not a bug; the missing-flag
error is argparse’s generic “required” text rather than “these must match the
contract”.

## macOS app (presentation only)

**Strengths**

- Brand empty state, honest non-goals, CLI version gate, accessibility labels
  (`BrandEmptyState.swift`, `ApproveSheet.swift`).
- Store path: “Open Reviewer Demo”. Non-store: Select CLI + Open Workspace.
- Evidence inspector already shows certificate id, hashes, chain, copy-JSON
  (`EvidenceInspectorView.swift`) — closer to a receipt than the CLI default.
- Lifecycle rail + action chips with keyboard shortcuts (`ActionBar.swift`).
- Approve sheet states the invariant in plain language and never auto-sends
  `APPROVE`. MAS e2e (`MasSandboxE2E.swift`) waits for the exact bind prompt
  `Type 'APPROVE' to bind this approval:` and asserts the harness did not type
  it.

**Friction**

- First launch is three pickers (CLI, workspace, contract) with little “you are
  here / next step” copy. The dashboard’s continue-verdict is not mirrored.
- Approve sheet is a **raw PTY transcript**, so CLI prompt density lands in the
  GUI. Structured contract fields in the header (argv only) are incomplete
  compared to the hashes the human is binding.
- Action chips are equally weighted. Approve is amber; Run is styled
  `destructive` but painted with the signal color — not an obvious next step.
- Lifecycle rail labels include Verify, but the index mapping stops at
  postflight (`StatusLifecycleView.LifecycleRail`).
- Evidence still appends a raw “Status JSON” dump under the friendly rows.
- Non-store footer is a pip one-liner; PATH-shadowing (documented in FAQ) is
  easy to hit and the app only shows a version-mismatch banner after the fact.

This PR does **not** change Swift (cannot be smoke-tested here; MAS e2e is a
release path). CLI prompt/help/`--pretty` improvements will show through the
PTY sheet without touching the app binary.

## Prioritized improvements

### P0 — high impact, low risk (prototyped here)

| ID | Improvement | Rationale (observed) | Constraint |
| --- | --- | --- | --- |
| P0.1 | Opt-in `--pretty` / `--color` human view | Every success path is JSON. User guide even says there is no `status --brief`. Repeat users and first-timers cannot read a receipt. | JSON + exit codes stay the default. `--pretty` is opt-in (flag before or after the command). |
| P0.2 | `runspecimen --help` + `quickstart` with copy-paste examples | Bare invocation and `--help` do not teach the lifecycle. Marketplace installs die without a 10-minute path (`docs/NEXT_CHANGES.md` item 5). | Additive command + help epilog. No change to required-command exit 2. |
| P0.3 | Scannable approve prompt (keep bind line) | Prompt uses `repr()` lists and raw hashes. Last line is a MAS e2e contract. | Presentation only. Last line remains `Type 'APPROVE' to bind this approval:`. Phrase, TTY gate, hashes, and documents unchanged. |
| P0.4 | Pretty receipts / status / digest | Certificates and `status` dump nested JSON. Dashboard already has the right words. | `--pretty` only. Default `format_status` JSON unchanged. |
| P0.5 | Pretty refusal hints | Messages are accurate but not actionable (`no approval present`, `expired (stale)`, `refuse re-entry`). | Default stderr first line stays `RunSpecimen error: {exc}`. Hints only with `--pretty`. |

### P1 — worth doing next (not all prototyped)

| ID | Improvement | Rationale |
| --- | --- | --- |
| P1.1 | Reuse dashboard copy on CLI `status --pretty` (what happened / safe to continue) | Partially prototyped: phase labels + next sentence. Full trust-ladder duplication can wait. |
| P1.2 | Friendlier argparse errors for missing `--campaign-id` on verify | Still generic argparse. Exit code 2 must stay. |
| P1.3 | macOS “next step” banner on `StatusLifecycleView` | App already has the data; it does not say “now postflight”. Needs a macOS smoke. |
| P1.4 | Parse approve PTY into structured rows in `ApproveSheet` | Keep transcript for audit; add a decoded contract card. Must not type APPROVE. |
| P1.5 | `init-demo` pretty next-step block | Prototyped under `--pretty`. Default JSON unchanged. |
| P1.6 | Group `--help` subcommands (lifecycle / evidence / keys / companion) | Long flat list. Custom argparse formatter; easy to get wrong. |
| P1.7 | Default stderr hints (without `--pretty`) | Would change the **text** of default errors. Tests mostly `assertIn` substrings, but downstream scrapers might not. Left opt-in. |

### P2 — polish

| ID | Improvement | Rationale |
| --- | --- | --- |
| P2.1 | Color on `--pretty` | Prototyped (`auto` / `always` / `never`, `NO_COLOR`). Never applied to JSON. |
| P2.2 | Highlight the single next action chip on macOS | ActionBar treats steps as equal. |
| P2.3 | Tab completion / man page | Agents and humans both benefit; not required for the gate. |
| P2.4 | Progress on long `run` | Currently silent then JSON. Must not look like a live log that could be spoofed as a receipt. |
| P2.5 | Truncated hashes in the prompt | **Rejected for default.** Full SHA-256 is what the human is binding. Pretty views still print full hashes. |
| P2.6 | Auto-fill verify ids from the contract | Tempting, but explicit identity is part of the product. Keep required flags; improve the error (P1.2). |

## What this PR prototypes

Additive only. Security, crypto, admission, entitlements, versions, and CI
release gates are untouched.

- `runspecimen quickstart` — always human, copy-paste lifecycle.
- Global + per-command `--pretty` and `--color`.
- Human formatters in `src/runspecimen/present.py` for lifecycle, doctor,
  status, digest, diff, receipts, keys, refusals.
- Clearer approve **prompt body**; MAS bind line preserved.
- `--help` epilog with examples; missing-command text points at `quickstart`
  (still exit 2).
- User guide / FAQ notes that JSON remains default.

## Explicit non-goals (honored)

- No change to TTY / phrase / remote-confirm semantics.
- No change to certificate schema, hashing, or verify checks.
- No change to default JSON keys, indent, `sort_keys`, or exit codes.
- No macOS signing / sandbox / helper / version gate edits.
- Dashboard remains loopback, read-only, unable to approve.
