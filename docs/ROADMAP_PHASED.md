# RunSpecimen phased roadmap (Cursor session)

Durable plan from `CURSOR_ROADMAP_UX_BRIEF.md`, refined by
`CURSOR_PRODUCT_DIRECTION_FOLLOWUP.md`. Compared against **v0.2.0-rc.10**.

Do **not** merge, publish, deploy, or submit marketplace listings without an
explicit later release decision. Preserve the dirty checkout at
`/Users/yahor/Documents/Codex/2026-08-24/how-x20`.

## Product direction (approved refinement)

Keep the core promise: **run assurance** — one exact human-approved run,
provenance, exclusive workspace lease, mandatory postflight, and an
independently checkable receipt. Evolve toward **verifiable execution**, not a
general sandbox, scheduler, or science-verifier platform.

| Direction | Decision |
| --- | --- |
| Public-key receipts | **Prioritize** optional Ed25519 + offline pubkey verify (Phase 1) |
| Isolation | **Opt-in tested integrations** (containers / native OS backends), not an invented OS sandbox (Phase 2) |
| Scheduler | **Do not** add cron/watchers/fan-out/parallel workers to the core engine |
| Scientific truth | **Do not** claim arbitrary scientific/engineering truth; narrow adapters only if a buyer asks |

HMAC remains shared-secret authentication. Never equate HMAC to digital
signatures or promise absolute non-repudiation. Soft keys on disk do not equal
hardware-backed identity.

### Active PR coordination

| PR | Role | Note |
| --- | --- | --- |
| [#5](https://github.com/darashkevich/runspecimen/pull/5) | Phase 0 — schema + dashboard IA | Preserve; do not overwrite. CI green ≠ production-ready. |
| [#6](https://github.com/darashkevich/runspecimen/pull/6) | Native macOS companion | Separate workstream. App Sandbox on the **UI process** does **not** by itself prove the externally launched CLI or its **payload** is confined. |

## rc9 reality vs plan (do not re-implement)

| Opportunity | Status |
| --- | --- |
| Crash recovery | Shipped (rc9) |
| HMAC shared-secret auth | Shipped (rc9); not a digital signature |
| Runtime provenance | Shipped (rc9); platform limits remain |
| `init-demo`, `demo_rc.sh`, showcase | Shipped |
| Contract `version` + receipt `schema_version` | Phase 0 (PR #5) |
| Dashboard four-question IA | Phase 0 prototype (PR #5) |
| Ed25519 offline pubkey receipts | **Next** (Phase 1) |
| Tested isolation integrations | Phase 2 (design → narrow slice) |
| Fuzz / golden depth | Phase 3 |
| Activation / adapters | Phase 4 |
| Team evidence | Phase 5 (validation-gated) |
| UX a11y completion + site | Phase 6 |

## Frozen invariants (every phase)

One workspace lease; human real-TTY approval with provenance + expiry; launch
rechecks; non-reusable started run IDs; certified predecessor gating; absent
asserted outputs at preflight; postflight-required success; **no**
watcher/scheduler/parallel workers in the engine; CLI is the enforcement
boundary; dashboard remains loopback-only, contract-bound, same-origin,
read-only (no POST approve/run). Agents never type or pipe `APPROVE` / `ABANDON`.

---

## Phase 0 — Schema compatibility + dashboard IA *(PR #5)*

**Status:** Implemented on `cursor/schema-compat-dashboard-ia`; open for review.

**Acceptance:** Unknown versions fail closed; legacy receipts verify; new certs
emit `schema_version: 1`; dashboard trust ladder never implies live verify;
security regressions pass.

**Release gate:** Reviewable only. Outstanding local `release_check` /
dashboard manual smoke must be green before any merge *recommendation* — and
merge still requires Yahor's later decision.

---

## Phase 1 — Public-key signed receipts (Ed25519) *(next PR: `cursor/ed25519-pubkey-receipts`)*

**Priority:** Highest after Phase 0.

**Status:** Implementation in progress on branch `cursor/ed25519-pubkey-receipts`
(stacked on Phase 0 direction commit). Optional PyNaCl extra; offline pubkey
verify; HMAC path preserved.

**Scope**

- Optional dependency (prefer well-maintained crypto lib, e.g. PyNaCl) so the
  default Community install stays **stdlib-only**.
- Ed25519 keygen, private-key sign, **offline public-key verify** without the
  secret.
- Canonical JSON serialization shared with HMAC path; key ID, rotation, export
  of public keys; separate on-disk layout from HMAC secrets.
- Tamper, wrong-key, missing-extra, and scheme-mismatch tests.
- Precise docs: identity ≈ key custody; not absolute non-repudiation; HMAC
  unchanged and clearly labeled.

**Dependencies:** Phase 0 schema rules preferred (stack on #5 or merge #5 first).

**Acceptance**

- `pip install runspecimen` (no extras) still works; Ed25519 commands fail with
  an actionable install hint when the extra is absent.
- `pip install 'runspecimen[ed25519]'` enables sign + offline pubkey verify.
- Forged HMAC MAC cannot satisfy the Ed25519 verify path.
- Wrong public key / tampered body fails closed.

**Release gate:** Unit + adversarial tests; release_check with and without
extra; docs/FAQ honesty pass. No PyPI publish without Yahor.

**Blocked on:** None for optional-dependency choice (direction approved:
optional dep over handwritten crypto). Hardware-backed keys remain later.

---

## Phase 2 — Isolation via tested integrations *(not an invented sandbox)*

**Scope**

- Opt-in backends (e.g. hardened containers, platform-supported OS isolation)
  with **capability discovery**, preflight **refusal** if declared policy cannot
  be enforced, and receipt fields for backend/version/effective settings.
- Document threat model, escape paths, and residual risks.
- Resource-limit wrappers alone must **not** be marketed as an OS sandbox.
- Native/unsandboxed execution stays honestly labeled.

**macOS app (PR #6) boundary**

- Sandbox entitlements on the SwiftUI UI process ≠ confinement of an externally
  selected `runspecimen` CLI launched from Terminal, and ≠ confinement of the
  workload subprocess the CLI starts.
- Before any “sandboxed execution” marketing: test and document the actual
  child-process / payload boundary (inherit vs external launch).

**Acceptance:** Declared isolation unmet → fail closed; receipt records what
was applied; unsupported hosts labeled; threat model updated.

**Hypothesis only (not core):** customer-validated opt-in coordinator that
schedules only exact, still-fresh human-approved contracts, preserves
predecessor/lease checks, and uses distinct lease domains — never auto-approval
or run-ID resurrection. Record demand; do not implement in-engine now.

---

## Phase 3 — Resilience and compatibility depth

Fuzz contract parsing, state transitions, paths, interruption; expand golden
historical receipts; clear migration errors. Preserve terminality and lease
exclusivity.

---

## Phase 4 — Activation and distribution polish

Adversarial first-run campaign; vertical templates; GitHub showcase; narrow
Cursor/Codex adapters (no shell escape, no approval tool). Claude Code +
Homebrew as separate slices. Avoid duplicate marketplace submissions while
Cursor review is pending. Coordinate messaging with PR #6 (Developer ID first;
MAS stretch).

---

## Phase 5 — Team evidence (validation-gated)

Prototype shared policies, incident bundles, identity-attributed *human*
approvals, opt-in export — only after design-partner validation. Never remote
execution or browser approval APIs.

---

## Phase 6 — UX completion + site honesty

a11y/WCAG, digest/diff, coherent CLI/docs/site copy **after** capabilities ship
and are independently validated. No production marketing upgrades for unshipped
claims. Website PRs against `darashkevich/darashkevich.com` only after product
approval.

### Domain-specific proof adapters (optional, buyer-driven)

Explore only when a buyer asks for a **particular** checkable claim. Distinguish:

1. Evidence that approved steps executed  
2. Assertion outcomes  
3. Independently checked proof objects  
4. Empirical interpretation  

No universal green “proven true” badge.

---

## Production-readiness gate (not inferred from green CI)

A **specific release candidate** may be nominated for Codex/Yahor production QA
only after **all** of:

1. Unit + adversarial tests  
2. Clean-install / `scripts/release_check.py`  
3. macOS + Linux checks as applicable  
4. Dashboard accessibility / manual smoke  
5. Security-boundary review (CLI + dashboard + any app shell)  
6. Artifact verification (checksums / signatures as declared)  
7. Truthful docs and site copy matching shipped behavior  

Until then: **not production-ready**.

## Status legend

- **Shipped** — in tree and tested  
- **Prototype-only** — UI/design without production claims  
- **Design hypothesis** — recorded, not scheduled into the engine  
- **Blocked** — needs Yahor, platform support, or customer validation  
