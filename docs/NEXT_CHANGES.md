# Next changes — RunSpecimen

Status legend for each section:

- `<!-- APPROVE: yes | no | defer | edit -->` — Yahor marks decision
- **Source:** `LOCAL DRAFT` = authored locally after ChatGPT call **failed** (429 credit_balance_exhausted). **Not from GPT.** Replace or annotate when a real Completions reply lands (see `docs/CHATGPT_TANDEM.md`).

Priority order below is a local judgment call aligned with `docs/PRODUCT_PLAN.md` M1 and differentiation vs generic CLI wrappers.

---

## 1. Runtime provenance bind (executable + interpreter + libs + env allowlist)

<!-- APPROVE: IMPLEMENTED -->

**Status:** ✅ IMPLEMENTED in rc9

**Source:** LOCAL DRAFT (not from GPT)

**Why (differentiation):** Receipts that only hash contract/source roots still look like "ran a script." Binding the resolved binary, interpreter, native libs, and declared env allowlist into the contract/receipt is the trust story wrappers lack.

**Effort:** M

**Implementation:**
- Contract now supports optional `runtime` field with `env_allowlist`, `interpreter`, and `capture_libs`
- `runtime.py` extended to capture interpreter via shebang detection or explicit path
- Environment variables from allowlist are captured and hashed into `env_hash`
- Optional library hashing via `ldd` when `capture_libs: true`
- All provenance fields included in `runtime_id` computation
- Mismatch detection reports specific changes (executable, interpreter, env, libraries)

**Risks:** Platform drift (macOS vs Linux path resolution); false fails on brew/pyenv upgrades; oversized fingerprints.

**Acceptance:** ✅ External reviewer can change one declared runtime input (e.g. interpreter path or env var) and `verify` fails with a clear provenance mismatch.

---

## 2. Crash-recovery commands with audited human decisions

<!-- APPROVE: IMPLEMENTED -->

**Status:** ✅ IMPLEMENTED in rc9

**Source:** LOCAL DRAFT (not from GPT)

**Why:** One-run-at-a-time + lease is worthless if a crashed agent leaves ambiguous state that a second agent "clears." Explicit recover/abandon with hash-chained decision events is agent-safety, not sugar.

**Effort:** M

**Implementation:**
- New `recovery.py` module with `is_recoverable()`, `abandon_run()`, `check_recovery_status()`
- CLI commands: `runspecimen abandon --workspace --campaign-id --run-id` and `runspecimen recovery-status`
- TTY-gated confirmation with `ABANDON` phrase
- `recovery_abandon` event recorded in hash-chained log
- State updated to `phase="abandoned"` with `recovery_decision` audit trail
- Status command shows `needs_recovery` flag and reason

**Risks:** Wrong recovery can orphan leases or resurrect run IDs; UX pressure to auto-heal (must stay human-gated).

**Acceptance:** ✅ Kill mid-run; `status` shows recoverable; only a TTY-approved abandon advances; event log records the decision; run ID still non-reusable after start.

---

## 3. Signed receipts (local key) + offline verify story

<!-- APPROVE: IMPLEMENTED -->

**Status:** ✅ IMPLEMENTED in rc9

**Source:** LOCAL DRAFT (not from GPT)

**Why:** Hash-chained events are integrity inside a workspace; signatures make receipts travel to a skeptic. This is the wedge vs "another CLI that prints JSON."

**Effort:** M (hardware-backed / team key later)

**Implementation:**
- New `signing.py` module with `SigningKey`, `SignedCertificate` classes
- HMAC-SHA256 signing (MVP; Ed25519/RSA via optional deps for production)
- Key storage in `.runspecimen/keys/` with chmod 0600
- CLI commands: `keygen`, `list-keys`, `sign`, `verify-signature`
- Canonical JSON serialization for deterministic signatures
- Signature includes `key_id` and `algorithm` for versioning

**Risks:** Key UX (lost keys, soft keys on disk); overclaiming "proof"; version skew of signature scheme.

**Acceptance:** ✅ `sign` + `verify-signature --key-id` round-trip on a clean receipt; tampered receipt fails; docs state what signature does **not** prove.

---

## 4. Containment adapter (CPU / mem / proc / disk; optional net deny)

<!-- APPROVE:  -->

**Source:** LOCAL DRAFT (not from GPT)

**Why:** Threat model today explicitly outs containment. Even a thin platform adapter (cgroups / `sandbox-exec` / job objects) plus honest "best-effort" labeling closes the "you only wrap subprocess" critique.

**Effort:** L (start S: document + macOS/Linux MVP limits)

**Risks:** False security theater; portability; workload breakage; expanding trust boundary accidentally.

**Acceptance:** Contract declares limits; overrun fails closed (non-success); receipt records applied limits; README/threat model updated with residual risks.

---

## 5. `demo_rc` TTY path that sells the product in <10 minutes

<!-- APPROVE:  -->

**Source:** LOCAL DRAFT (not from GPT)

**Why:** Marketplace installs die without a visceral approve → lease → receipt → verify loop. Differentiation is felt in the TTY ceremony, not the README alone.

**Effort:** S–M

**Risks:** Demo becomes too cute / non-adversarial; drifts from real CLI.

**Acceptance:** Fresh clone (or marketplace install) produces a verified receipt via documented TTY steps in under ten minutes on a clean machine.

---

## 6. Host-bound showcase refresh (public GitHub narrative)

<!-- APPROVE:  -->

**Source:** LOCAL DRAFT (not from GPT)

**Why:** Public repo @ d7da6a3 needs a host-bound story: "this workspace, this lease, this certificate" — not feature laundry lists. Positions RunSpecimen as evidence infrastructure.

**Effort:** S

**Risks:** Marketing tone overclaims security boundary.

**Acceptance:** README first screen + one showcase run match PRODUCT_PLAN promise language; link to threat model; no dashboard/scheduler promises.

---

## 7. Marketplace adapter polish (narrow MCP, no shell escape hatch)

<!-- APPROVE:  -->

**Source:** LOCAL DRAFT (not from GPT)

**Why:** Distribution is M2, but polishing the Cursor/Codex surface so agents *must* go through approve/lease keeps the product from being used as a thin `run_terminal` proxy.

**Effort:** M

**Risks:** Agent platforms reject narrow tools; users demand `shell` escape.

**Acceptance:** Plugin/skill path cannot manufacture approval; only CLI TTY approval works; adapter tests assert no generic shell tool.

---

## 8. Contract/receipt versioning + migration rules (pre-M1 freeze)

<!-- APPROVE:  -->

**Source:** LOCAL DRAFT (not from GPT)

**Why:** Before provenance/signing land, freeze schema versioning so early adopters don't invalidate every receipt. Quietly critical for "checkable later."

**Effort:** S

**Risks:** Over-engineering; delaying M1 features.

**Acceptance:** Docs define version field, compatibility matrix, and fail-closed behavior on unknown versions; one golden old receipt still verifies or fails with a migration message.

---

## Explicitly not next (keep postponed)

Per `PRODUCT_PLAN.md`: generic observability, shell firewall, hosted remote exec, auto-retry/schedule/multi-worker, dashboard without paid need.

---

## Retry when quota restored

1. Add credits in [platform.openai.com billing](https://platform.openai.com/settings/organization/billing/) or generate a fresh Composio connection locally. Never commit short-lived connection URLs or credentials.
2. Re-run Completions with the same brief (logged in `docs/CHATGPT_TANDEM.md`).
3. Append GPT's real reply to the chatlog; convert matching sections above from `LOCAL DRAFT` → `FROM GPT` (or add GPT-only items). Mark `<!-- APPROVE: -->` for Yahor.
