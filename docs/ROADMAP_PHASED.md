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
| Ed25519 offline pubkey receipts | Shipped optional extra (see `docs/ED25519_RECEIPTS.md`) |
| Tested isolation integrations | In this working tree, unreleased (`none` / `sandbox-exec` / `bwrap`) |
| Fuzz / golden depth | In this working tree (`tests/test_fuzz_contracts.py`) |
| Activation / adapters | Adapters shipped in-repo; Homebrew formula pins published rc12 |
| Local evidence slice | In this working tree (policy file, local OS user, `retain`). No paid control plane |
| UX a11y + digest/diff + site copy | In this working tree. Public site no longer lists a price book. Proof adapters stay buyer-driven |

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

## Phase 2 — Isolation via tested integrations *(0.2.0rc13)*

In `0.2.0rc13`. Published `0.2.0rc12` rejects the field.

- Optional contract `isolation.backend`: `none` (default), `sandbox-exec` (when the binary is on PATH), `bwrap` (when the binary is on PATH).
- A declared backend that is missing fails closed at approve, preflight, and run.
- `none` does not wrap argv. The receipt says the workload is not confined.
- `sandbox-exec` is seatbelt write confinement to the workspace, with network denied unless `isolation.network` is true. It is not an OS sandbox.
- `bwrap` bind-mounts the workspace read-write over a read-only host root, and unshares the network unless `isolation.network` is true.
- `runspecimen isolation` and `doctor` report which backends exist. They do not claim one is in effect.
- Receipt field `isolation` (backend, enforced, network, tool, claim, residual) is bound into `certificate_id` when present. Historical receipts that omit it still verify.

The macOS app sandbox still does not confine a CLI started in Terminal, and it does not confine the workload except through the contract backend above.

Not in the engine: a scheduler, watcher, or coordinator. Resource limits are not an isolation backend.

---

## Phase 3 — Resilience and compatibility depth *(in tree, unreleased)*

- `tests/test_fuzz_contracts.py` mutates contracts and paths with stdlib `random` and requires fail-closed errors. No new required dependency.
- Terminal phases still refuse re-entry.
- Interruption during a run is covered by `tests/test_timeout_run.py` (`run_result=interrupted`).
- Optional receipt fields change `certificate_id`. The showcase certificate stays a legacy receipt without those fields.
- Migration text for `isolation`, `policy`, and `approver` is in `docs/SCHEMA_COMPATIBILITY.md`.

---

## Phase 4 — Activation and distribution polish *(partial, in tree)*

Done in this tree, without new marketplace submissions:

- `examples/templates/` for a research step, an ML eval step, and a security check that names a shared policy.
- `examples/campaigns/adversarial-first-run/` shows a second worker refused by the workspace lease.
- `packaging/homebrew/runspecimen.rb` installs the `v0.2.0-rc.13` sdist. A tap repository is not created here.

Still outside this change: Cursor, Claude, Gemini, Junie, and OpenAI submissions already filed. Do not file them again. Windsurf, VS Code, and Amazon Q stay unsubmitted. GitHub showcase was already published with rc12.

---

## Phase 5 — Local evidence slice *(in tree, unreleased; no control plane)*

The paid Team pilot, SSO, billing, and design-partner gate are not in this
tree. The local mechanics are:

- Optional contract `policy` names a JSON file inside the workspace. Its SHA-256 is part of the contract hash. Ceilings, `argv0_allow`, and `require_isolation_backend` are enforced before approval.
- The approval document and receipt record `approver` as the local OS user (`kind: local_os_user`). That is the account that settled the TTY or remote-confirm on this Mac, not an SSO identity.
- `runspecimen retain --out <dir>` copies the incident pack and refuses a destination inside the workspace. Nothing is uploaded.

Not built: browser approval, one-tap Approve, a public retention service, remote execution, or a paid control plane.

---

## Phase 6 — UX completion + site honesty *(0.2.0rc13)*

- `runspecimen digest` and `runspecimen diff` compare recorded receipts. They are not `verify`. `digest --live` reports output-byte drift only.
- Dashboard: skip link, main landmark, stronger focus outlines, muted text darkened for contrast, auto-refresh starts off when the user prefers reduced motion, and the page states the contract's isolation backend without applying it.
- The public page `sites/runspecimen/public/index.html` (in the portfolio repo) no longer lists Pro/Team prices. It installs `0.2.0rc13` and says opt-in confinement is not an OS sandbox. Published `0.2.0rc12` does not include these commands.
- No production claim that opt-in confinement is an OS sandbox.

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
