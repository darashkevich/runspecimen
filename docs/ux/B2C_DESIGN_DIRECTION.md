# RunSpecimen B2C design direction

A presentation-only brief for the **macOS app** (primary consumer surface)
and the standalone product page under `web/product-demo/`. It does not change
approval, hashing, leases, certificates, admission, sandbox, signing, or CLI
JSON/exit codes.

Grounding: the CLI/macOS review in draft PR #60 stayed developer-facing. This
document is a deliberate shift toward everyday people who want peace of mind,
not a denser instrument for scientists and power users.

Packed `CHANGELOG.md` is left untouched so the unpublished rc15 sdist digest
stays put. This brief is the record of the presentation change.

---

## 1. Target persona

**Name we design for:** Maya, 34. She is not a developer.

She uses a Mac the way most people do: Mail, Notes, Photos, a browser, and
lately an AI assistant that can edit files and run tasks for her. She is
comfortable clicking through a clear app. She is **not** comfortable with
terminals, JSON, SHA-256, or words like *contract*, *postflight*, and *lease*.

**Job to be done:** “An assistant is about to do something that matters on my
Mac. I want to see what it may do, say yes myself, and later prove it did only
that — without becoming a security engineer.”

**Emotional job:** feel looked-after, not tested. Calm confidence. No shame
for not knowing the jargon.

**What success feels like**

- First launch explains itself in three short beats.
- The next action is obvious. Everything else is quieter.
- After a run she can answer, in one glance: *all good* or *something changed*.
- If she is curious, a “Show details” disclosure still has the full evidence.

**What we refuse to pretend**

- We do not sandbox the operating system.
- We do not prove her work is scientifically true.
- We do not approve on her behalf, and we never invoke Touch ID / Face ID
  as a substitute for typing `APPROVE`.
- Receipts are a local, checkable history — not a court-grade signature.

Those limits stay honest. They move into plain language and, where they are
engineering caveats, into a details disclosure rather than the first headline.

---

## 2. Brand voice

Speak like a thoughtful consumer Mac app: **Warm. Clear. Specific. Unhurried.**

Think the tone of a well-written Notes, Find My, or banking-receipt screen —
not a lab console, not a marketing landing page that shouts.

### Do

- Short sentences. Everyday verbs: *review, allow, run, check, keep*.
- Address the person: “You approve. Then you get a receipt.”
- Name the feeling of the state: “All good.” “Something changed.” “Still
  waiting on you.”
- Reassure without hype: “This stays on your Mac.” “Nothing is sent
  automatically.”
- Keep one exact ritual: the person types **APPROVE** themselves.

### Don’t

- Lead with enforcement vocabulary (*TTY*, *PTY*, *argv*, *digest*, *HMAC*).
- Use ALL-CAPS section labels as the primary hierarchy (`EVIDENCE`,
  `HONEST NON-GOALS`).
- Make honesty sound like a warning sticker on every panel. One calm
  “What this does not do” is enough; repeat the rest under Details.
- Joke about the user being non-technical.
- Imply the app approved, signed, or “secured the machine” for them.

### Exact ritual we never paraphrase away

The engine bind line remains:

```
Type 'APPROVE' to bind this approval:
```

Surround it with friendlier framing. Do not rewrite, auto-complete, or
submit it.

---

## 3. Plain-English glossary

Show the everyday phrase first. Keep the exact term in a **Details**
disclosure, tooltip, or “Technical name” caption — never delete it.

| Everyday (lead with this) | Exact term (details) | One-line meaning |
| --- | --- | --- |
| Run plan | contract | The bounded list of what may run, which files count, and what must be true afterward. |
| This project / this run | campaign / run id | Names that identify *which* plan and *which* attempt. |
| The command | argv | The exact program and arguments that will execute. |
| Fingerprint | SHA-256 digest / hash | A unique checksum of a file or plan. If the file changes, the fingerprint changes. |
| Get ready | preflight | Last check that the approval is still valid and nothing drifted. |
| Start the run | run | Execute the approved command once. |
| Check the results | postflight | Compare what happened with what the plan required. |
| Receipt | certificate | The local, checkable record of the approved run. |
| History | event chain | The ordered, fingerprint-linked log of steps. |
| This folder is busy | lease | Only one of these runs may use the workspace at a time. |
| Plan or files changed | source / contract drift | Something you approved is no longer what is on disk. |
| Approval expired | stale / TTL | The yes is too old; you need to approve again. |
| Engine | CLI / runspecimen binary | The local program that actually enforces the rules. |
| Advanced tools | workflows | Extra evidence commands. They never type APPROVE. |

---

## 4. Visual language

The macOS app should feel like **paper, a seal, and a receipt** — not a
terminal grid. The product page shares the same tokens so the two surfaces
read as one product.

### Color

Light is the primary consumer appearance. Dark follows the system, with the
same roles (never a neon-on-black “ops” skin).

| Role | Light | Dark | Use |
| --- | --- | --- | --- |
| Paper | `#F4F0E8` | `#161412` | Window background |
| Card | `#FFFCF7` | `#221F1A` | Panels, sheets |
| Ink | `#1C1814` | `#F3EEE6` | Titles, body |
| Soft ink | `#5C564F` | `#C4BBA8` | Secondary copy |
| Teal (brand) | `#1F6F68` | `#7DCEB0` | Primary buttons, current step |
| Sage (success) | `#2E8B57` | `#8FCB9B` | All-good states |
| Amber (wait) | `#C9891A` | `#E0A45A` | Needs you / still running |
| Coral (problem) | `#C94C4C` | `#F0A196` | Something changed / failed |
| Hairline | ink at 10% | ink at 16% | Card edges |

**Accent, not alarm.** Teal is the brand; sage is the result. Do not paint
the whole chrome signal-green. Do not use monospaced capsules as status
pills — use rounded, word-shaped labels.

### Typography

- **UI:** SF Pro / system sans. Rounded *display* for the product name and
  result headlines only.
- **Body:** 13–15 pt, comfortable line height, max readable column ~40em.
- **Mono:** fingerprints, paths, and JSON **inside Details only**.
- **No tracked all-caps** as the primary section title. Use Title Case or
  sentence case (`Your receipt`, not `EVIDENCE`).

### Spacing and shape

- Window padding 20–28 pt; card padding 16–20 pt; stack spacing 12–16 pt.
- Corner radius 12–16 pt on cards; 10 pt on buttons; pills fully rounded.
- One primary button per region. Secondary actions are quieter text or
  bordered buttons.
- Generous empty space. If a panel needs a scrollbar of hashes, those hashes
  belong in Details.

### Iconography

SF Symbols, outlined, medium weight. Metaphor:

- Seal / check-seal for “all good”
- Doc with badge for the run plan
- Keyboard for “you type APPROVE”
- Clock for running
- Exclamation-triangle only for *something changed* (not for idle empty)

Do not use a blinking radar LED as the brand mark. A small teal seal is
enough.

### State recipes

Every consequential screen uses the same four result treatments.

| State | Hero | Color | Body pattern |
| --- | --- | --- | --- |
| Empty | “Nothing has run yet” | Soft ink | One sentence + one next action |
| Success | “All good” | Sage | What was allowed, that it matched, how to see the receipt |
| Warning | “Still waiting on you” / “Running now” | Amber | What happens next; no fake progress that looks like a receipt |
| Error | “Something changed” / “Didn’t finish” | Coral | What we noticed, that nothing was auto-approved, Details for the exact reason |

Progressive disclosure pattern (mandatory):

1. Everyday headline.
2. One-paragraph meaning.
3. `Show details` — fingerprints, paths, exact terms, JSON.

Hide complexity. **Never remove evidence.**

---

## 5. Core consumer flows

The engine lifecycle is unchanged: validate → approve → preflight → run →
postflight → verify. The app **narrates** that as a shorter story.

### 5.1 First-run onboarding

**Goal:** in under a minute, Maya knows she is the one who says yes, and
that she will get a receipt.

Three beats, not a feature tour:

1. **Review the plan** — see what may run, in plain language.
2. **You type APPROVE** — the app will not type it; an assistant cannot.
3. **Keep the receipt** — later you can tell if anything changed.

Primary CTA:

- Mac App Store: open the bundled sample (existing reviewer demo — same
  action, calmer label).
- Local builds: choose the engine, then a folder. Keep the exact
  `Select runspecimen CLI` control where tests require it; surround it with
  “this is the engine that enforces the rules.”

Footer honesty: “Stays on this Mac. No account. No telemetry.” Engineering
pins (`0.2.0rc14` vs unpublished engines) live under Details, not the
hero.

### 5.2 Review and approve

**Goal:** she understands the bound command before she types APPROVE.

Layout:

- Headline: “Review and approve”
- Card: the command, the folder, the project/run names in everyday labels
- Body: “Typing APPROVE means you allow this plan. Assistants cannot do
  this for you.”
- The live engine prompt stays visible (that is the bind surface).
- Input placeholder and send path **unchanged in spirit**: the person types;
  Send transmits only what they typed; the source comment
  `Deliberately do not auto-detect or coerce APPROVE` stays.

Details disclosure: full fingerprints, paths, TTL as “this yes expires in
…”, isolation residual as “this is not a cage for the program.”

### 5.3 Running

**Goal:** she is not abandoned, and she does not mistake a spinner for a
receipt.

- Headline: “Running now”
- Subcopy: “The approved command is in progress. We’ll check the results
  when it finishes.”
- Quiet progress. No live log that could be confused with the receipt.
- Next action disabled except Cancel-equivalents already offered by the
  engine/UI.

### 5.4 All good / something changed

**Goal:** a binary, human verdict, then evidence.

**All good** when results were checked and the history is intact:

- “All good”
- “This run matches what you allowed.”
- Button: “Show receipt details”

**Something changed** when fingerprints, history, or declared outputs do
not match — or the run failed:

- “Something changed” or “Didn’t finish as planned”
- One sentence on what that means (files moved, approval expired, the
  command failed).
- Details: the engine’s exact fields (contract hash, source hash, chain
  note, exit code).

Never show a raw JSON blob as the first thing on this screen.

### 5.5 History / receipts

**Goal:** a calm inspector, not a dump.

- Lead with the verdict and the receipt id (short, copyable).
- Rows in everyday labels: Receipt id, History, Plan fingerprint, Files
  fingerprint, Program fingerprint.
- JSON, expansion readouts, and workflow tools sit behind Details /
  Advanced tools.

Advanced tools (snapshots, evaluations, carried approval) are **not** part
of the consumer path. Keep them; retitle the sheet so it does not compete
with Review and approve.

---

## 6. Before / after copy

### First launch

| Before | After |
| --- | --- |
| Native control surface for the CLI enforcement engine. Approval stays interactive on a real TTY. Evidence inspection is read-only. | You review a short plan, you type APPROVE yourself, and you get a receipt of what ran. It stays on this Mac. |
| One human-approved bounded run. Local evidence. No telemetry. | You approve what may run. Then you get a receipt you can keep. |
| HONEST NON-GOALS — Not an OS sandbox · Not a scheduler · Not compliance theater · Receipts are local hash chains, not digital signatures | What this does not do — It does not lock the rest of your Mac. It does not prove your work is true. It does not schedule jobs. The receipt is a checkable history, not a bank-style signature. |
| Select a contract / Open Contract JSON | Choose a run plan / Open a run plan |
| Contracts declare argv, caps, provenance roots, and postflight assertions. | A run plan says what may run, which files count, and what must be true when it finishes. |
| CLI SETUP REQUIRED | The engine needs a moment — plus the existing diagnostic message in Details. |
| Published pin runspecimen==0.2.0rc14. This build's engine is unpublished 0.2.0rc15. | Stays on this Mac · No account · No telemetry *(version pins under Details)* |

### Review and approve

| Before | After |
| --- | --- |
| Human approval / TTY required | Review and approve / You type this yourself |
| This sheet attaches runspecimen approve to a real PTY so the engine’s interactive gate still holds. | This window is the real approval step. Assistants cannot type APPROVE for you, and this app will not type it either. |
| Bound command | What will run |
| Type APPROVE to bind — nothing is sent automatically | *(placeholder kept — tests and screenshots rely on it)* |
| Invariant: agents and plugins cannot approve. Only a human on this PTY. | Only you can approve. Type APPROVE when you have read the plan. |
| PTY live. Read the prompt carefully, then type APPROVE yourself. | Waiting on you. When the prompt appears, type APPROVE yourself. |

### Running and next step

| Before | After |
| --- | --- |
| LIFECYCLE / Postflighted | This run / Results checked |
| Approve · Preflight · Run · Postflight · Verify | You approve · Get ready · It runs · Check results · Receipt |
| Campaign / Run / Lease / Chain / Argv | Project / This run / Folder / History / Command |
| Doctor OK · Python 3.x | Engine is ready *(Python version under Details)* |
| Evidence inspection is read-only. Approve / run / postflight stay explicit human actions through the bundled engine. | Looking does not approve or start anything. You choose the next step. |
| *(no next-step banner)* | Next: Check the results — Make sure the run did what you allowed. |

### Receipt / result

| Before | After |
| --- | --- |
| EVIDENCE / Receipt inspector | Your receipt |
| Local hash-chained certificate — not an asymmetric digital signature. | This receipt is a checkable history on this Mac, not a bank-style signature. |
| NO RECEIPT YET | Nothing has run yet |
| Certificate ID / Event head / Contract hash / Source hash / Runtime ID / Postflight | Receipt id / History pointer / Plan fingerprint / Files fingerprint / Program fingerprint / Results check |
| Chain OK / Chain invalid | History looks intact / History does not match |
| Status JSON (always visible) | Show technical details — full JSON, fingerprints, engine notes |
| Copied Certificate ID | Copied Certificate ID *(keep the `Copied` prefix)* |

### Actions and menus

| Before (engine name, still the command) | After (visible label) |
| --- | --- |
| Validate | Check the plan |
| Approve… | Review & approve |
| Preflight | Get ready |
| Run | Start the run |
| Postflight | Check results |
| Verify | Get the receipt |
| Dashboard | Open the timeline |
| Workflows… | Advanced tools… |
| Run this bounded command? | Start this run? |
| Executes one lease-bounded run via the selected CLI. Approval must already be in place. The app will not type APPROVE for you. | This starts the task you already approved. The app will not type APPROVE for you. |
| Run postflight checks? | Check the results now? |
| Runs postflight assertions against the recorded run evidence. This does not re-execute the payload. | This checks that the run did what you allowed. It does not run the task again. |

Menu items that tests grep for stay exact (`Select runspecimen CLI…`,
privacy URL, Close Settings / Close About identifiers).

---

## 7. What stays technical on purpose

Leave these exact, reachable, and unglamorized:

- The bind line `Type 'APPROVE' to bind this approval:`
- Full fingerprints, paths, campaign/run ids, exit codes, JSON
- Isolation residual / “not a sandbox” in Details
- Engine version, source (Bundled Helpers), and setup diagnostics
- Carried-approval / native-bridge status text (advanced tools)
- Default CLI JSON and exit codes
- Fail-closed Store engine discovery copy that tests assert
  (`fail closed`, `does not select a host CLI`)

The consumer layer **translates**. It does not delete the lab notebook.

---

## 8. Prototype scope (this change)

Highest-value presentation work, in order:

1. This document.
2. macOS theme, empty/onboarding, next-step banner, result heroes, approve
   framing, receipt progressive disclosure, calmer action bar.
3. Align `web/product-demo/` color, type, and copy with the same persona.
4. HTML previews of key screens in `docs/ux/previews/` (Linux agents cannot
   render SwiftUI).

Out of scope here: CLI `--pretty` (PR #60), security, admission, helpers,
versions, notarization, auto-approve, invoking biometrics.
