# RunSpecimen phased roadmap (Cursor session)

Durable plan derived from `CURSOR_ROADMAP_UX_BRIEF.md`, compared against
**v0.2.0-rc.9** (`main` @ PyPI/GitHub pre-release). Do not merge, publish,
deploy, or submit marketplace listings without an explicit later release
decision. Preserve the dirty checkout at `/Users/yahor/Documents/Codex/2026-08-24/how-x20`.

## rc9 reality vs plan (do not re-implement)

| Opportunity | rc9 status |
| --- | --- |
| Crash recovery (`abandon`, `recovery-status`) | Shipped; abandoned IDs permanently terminal |
| HMAC shared-secret receipt authentication | Shipped; docs correctly deny non-repudiation |
| Runtime provenance (`runtime` / `runtime_id`) | Shipped; libs best-effort / platform-limited |
| `init-demo`, `scripts/demo_rc.sh`, showcase receipt | Shipped |
| Contract `version` field | Present; only `1` accepted; no migration doc/golden tests |
| Receipt `schema_version` | **Missing** before this roadmap’s Phase 0 |
| Asymmetric Ed25519 / offline pubkey verify | Not started (HMAC only) |
| Containment (CPU/mem/proc/disk/net) | Not started; threat model outs it |
| Fuzz / golden old-receipt suite | Partial adversarial tests only |
| Dashboard world-class IA | Functional read-only UI; first viewport still education-heavy |
| Claude Code / Homebrew | Explicitly next after core QA |
| Team evidence / cloud / remote approval | Explicitly gated; never remote execution API |

## Frozen invariants (every phase)

One workspace lease; human real-TTY approval with provenance + expiry; launch
rechecks; non-reusable started run IDs; certified predecessor gating; absent
asserted outputs at preflight; postflight-required success; no
watcher/scheduler/parallel workers; CLI is the enforcement boundary; dashboard
remains loopback-only, contract-bound, same-origin, read-only (no POST
approve/run). Agents never type or pipe `APPROVE` / `ABANDON`.

---

## Phase 0 — Schema compatibility + dashboard IA foundation *(this PR)*

**Scope**

- Document and enforce contract/receipt schema versioning with fail-closed
  unknown versions and migration rules.
- Emit `schema_version: 1` on new certificates; treat missing field as legacy v1.
- Golden old-receipt test (showcase / fixture) still verifies.
- Redesign local dashboard first viewport to answer: *What is this run? What
  happened? Is it safe to continue? What do I do next?* Move About behind
  progressive disclosure. Keep trust ladder honest (recorded ≠ live verified).

**Dependencies:** none beyond rc9.

**Acceptance**

- Unknown contract/receipt versions refuse with a migration-oriented error.
- Legacy certificates without `schema_version` still verify when otherwise valid.
- New certificates include `schema_version` bound into `certificate_id`.
- Dashboard security regressions (no POST, loopback Host/Origin checks) still pass.
- Unit + dashboard tests + `scripts/release_check.py` pass.

**Release gate:** reviewable PR only; no version publish.

---

## Phase 1 — Receipt portability (asymmetric trust)

**Scope:** Optional Ed25519 sign/verify without breaking stdlib-only Community
engine (optional dependency or documented extra); key lifecycle/rotation; honest
terminology; bind material input datasets + engine build into provenance where
feasible. Preserve HMAC as shared-secret authentication.

**Platform limits:** Soft keys on disk until hardware-backed story exists.

**Acceptance:** Offline pubkey verify of a receipt; forged HMAC cannot satisfy
Ed25519 path; packaging still installs stdlib-only by default.

**Blocked on:** Yahor decision if optional dependency vs vendored pure-Python.

---

## Phase 2 — Containment (accurately scoped)

**Scope:** Documented threat-model update + narrow macOS/Linux limits (CPU,
memory, process count, disk; optional network). Record applied limits on the
receipt; fail closed when declared limits cannot be applied. Never claim a
general OS sandbox.

**Acceptance:** Contract-declared limit overrun → non-success; receipt shows
what was applied; unsupported platforms labeled.

---

## Phase 3 — Resilience and compatibility depth

**Scope:** Fuzz contract parsing, state transitions, paths, interruption;
expand golden historical receipts; clear migration errors. Preserve terminality,
lease exclusivity, predecessor gating, mandatory postflight.

**Acceptance:** Fuzz corpus in CI; each supported schema has at least one golden
fixture.

---

## Phase 4 — Activation and distribution polish

**Scope:** Adversarial first-run campaign (<10 minutes to verified receipt);
vertical templates (research / ML-eval / backtest / fuzz); GitHub showcase
narrative; narrow Cursor/Codex adapter polish (no shell escape, no approval
tool). Claude Code + Homebrew as **separate** slices after core QA. Avoid
duplicate marketplace submissions while Cursor review is pending.

**Acceptance:** Clean-machine path documented and smoke-tested; adapter tests
forbid generic shell + approve.

---

## Phase 5 — Team evidence (validation-gated)

**Scope (prototype only until buyers validate):** shared versioned
policies/templates; portable incident/evidence bundles; identity-attributed
*human* approvals; opt-in export/retention; ingest-only evidence service design.

**Never:** remote execution API, browser approval API, SSO/RBAC/fleet/compliance
claims without design-partner evidence.

**Release gate:** stop and ask Yahor before productionizing pricing or hosting.

---

## Phase 6 — World-class UX completion pass

**Scope:** Contract-review density, digest/diff comparisons, a11y (WCAG 2.2 AA),
keyboard/screen-reader/contrast/zoom/narrow/reduced-motion, empty/long/stale
states, coherent CLI + docs + product-site copy. Website changes are a
**separate** PR against `darashkevich/darashkevich.com` after product approval.

**Acceptance:** Automated + recorded manual a11y checks; security regressions
unchanged.

---

## Status legend for reports

- **Shipped** — in tree and tested
- **Prototype-only** — UI or design docs without production claims
- **Blocked** — needs Yahor, platform support, or customer validation
