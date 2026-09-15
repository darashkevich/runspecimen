# RunSpecimen release-candidate report (PRs #5 / #6 / #7)

**Date:** 2026-09-15  
**Authoring branch:** `cursor/ed25519-pubkey-receipts` @ `b7202b8`  
**Baseline already published:** [v0.2.0-rc.9](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.9) / PyPI `runspecimen==0.2.0rc9`  
**Hard stops honored:** no merge, no PyPI publish, no website deploy, no notarization, no marketplace submit.

This report is the single decision packet for what (if anything) should become the **next** release candidate after rc9. All three PRs are **OPEN** and **MERGEABLE** with green CI as of authoring; none are in `main`.

| PR | Title | Tip (approx.) | Role |
| --- | --- | --- | --- |
| [#5](https://github.com/darashkevich/runspecimen/pull/5) | Phase 0: schema compatibility + dashboard IA foundation | `606cee3` (also first commit of #7 stack) | Python package: schema + dashboard UX |
| [#6](https://github.com/darashkevich/runspecimen/pull/6) | Native macOS RunSpecimen app | `7fa2e7c` on `cursor/macos-native-app` | Separate macOS `.app` workstream |
| [#7](https://github.com/darashkevich/runspecimen/pull/7) | Harden optional Ed25519 receipts after Codex QA | `b7202b8` | Python package: optional Ed25519 + QA hardenings (includes #5 commits) |

**Stack note:** PR #7’s branch already contains PR #5’s commits (schema + dashboard IA). Merging #7 alone would land Phase 0 + Phase 1 Ed25519. PR #6 is a parallel branch and is **not** included in #7.

---

## 1. Exact features proposed for THIS release vs future work

### Proposed for the next Python package RC (recommended label: **0.2.0rc10**)

Ship from **PR #7** (which already includes **PR #5**):

**From PR #5 — Phase 0**

- Contract / receipt schema compatibility (`docs/SCHEMA_COMPATIBILITY.md`): unknown versions fail closed; new certificates emit `schema_version: 1` bound into `certificate_id`; legacy receipts without the field remain valid as v1.
- Loopback dashboard first-viewport IA: what run / what happened / safe to continue / next step; trust ladder that never treats a certificate as live-verified; About behind progressive disclosure; still read-only (no approve/run APIs).

**From PR #7 — Phase 1 + QA**

- Optional extras `runspecimen[ed25519]` / `runspecimen[signing]` → PyNaCl; default install stays dependency-free.
- CLI: `keygen` / `sign` / `verify-signature --scheme ed25519`, `export-public-key`.
- Trust model: embedded-key-only consistency ≠ trusted success; `ok: true` requires external trust anchor (`--public-key` or workspace `--key-id`).
- Packaging: `release_check` allows only vetted optional `Requires-Dist` markers.
- Key I/O: private keys `0600` from exclusive `O_EXCL|O_NOFOLLOW` create; export never opens private seed.
- **Rotation recoverable / all-or-nothing:** stage temps + fsync; never remove live private before new public install; rollback keeps previous pair loadable on in-process failure.
- **TOCTOU closed on key reads:** `O_NOFOLLOW` open + `fstat` on the opened fd (private and public).

**Not in the Python wheel/sdist (even if #7 merges):** macOS `.app`, notarization, App Store listing.

### Proposed as a **separate** optional macOS artifact (only if Yahor opts in) — PR #6

- SwiftUI companion under `apps/macos/` that shells to the real `runspecimen` CLI (does not reimplement enforcement).
- App Sandbox + security-scoped bookmarks for workspace / CLI; PTY-backed approve sheet that never auto-types `APPROVE`.
- Local ad-hoc `RunSpecimen.app` build path works without Apple certs; **Developer ID + notarization** is the recommended v1 distribution (Target B). Mac App Store (Target A) is architecture-ready but deferred until embedded-helper / review-risk mitigation.

### Explicitly **future** (not this RC)

| Item | Why deferred |
| --- | --- |
| OS sandbox / process containment of the **payload** | Product non-goal; Phase 2 is opt-in tested isolation integrations |
| Mac App Store submission | Needs review-risk mitigation / embedded signed helper (ADR-002) |
| Automatic crash recovery of orphaned `.bak` / `.rotating` key sidecars | In-process rollback works; durable crash mid-rename still needs operator restore (documented risk) |
| Schedulers / watchers / parallel workers | Frozen invariant — out of core |
| Absolute non-repudiation / transparency log | Soft keys + no log product |
| Website production deploy / marketplace listings | Separate approval |
| Bumping past rc9 on PyPI | Requires Yahor publish decision |

---

## 2. Dashboard approval flow + accessibility

**Surface:** loopback `runspecimen dashboard` (PR #5 / included in #7).  
**Enforcement:** approval remains human TTY (`runspecimen approve`); dashboard cannot approve or execute.

### Receipt vs live-verified run (product language)

| Concept | Meaning in UI / docs |
| --- | --- |
| **Receipt issued** | Certificate file exists on disk (recorded history). Dashboard may show “issued”. |
| **Live verification** | CLI re-check of current files / provenance / optional signature under a trust anchor. Dashboard ladder shows **NOT-CHECKED** and never marks this green. |
| **Trusted Ed25519 success** | Separate from dashboard: `verify-signature --scheme ed25519` with `--public-key` / `--key-id`. |

Verified copy on the live dashboard (2026-09-15, local `PYTHONPATH=src`):

- “This page inspects evidence; it cannot approve or execute.”
- “approve in a real terminal — never via this dashboard.”
- Trust ladder: `RECEIPT ISSUED` vs `LIVE VERIFICATION / NOT-CHECKED` (“Dashboard never marks this green; use CLI verify”).
- Lifecycle step labeled **Verify receipt** (CLI copy), not an in-page verify action.

### Manual / automated visual evidence

| Viewport | Evidence |
| --- | --- |
| Desktop 1280×800 | `/tmp/runspecimen-dashboard-a11y/desktop.png` |
| Mobile 390×844 | `/tmp/runspecimen-dashboard-a11y/mobile.png` |
| Structured notes | `/tmp/runspecimen-dashboard-a11y/rc_notes.json` (2026-09-15 refresh) |
| Earlier automated report | `/tmp/runspecimen-dashboard-a11y/report.json` (8/9 checks; “unnamed controls” false positive on About/FAQ links that have visible text elsewhere) |

**Method:** Playwright Chromium (Agent browser not required for this pass).  
**Result:** desktop + mobile screenshots refreshed; `lang=en`; H1 present; no POST forms; cannot-approve language present; receipt vs live-verify distinction present.

**Residual a11y note:** footer/doc icon links without accessible names remain a polish item (not a ship blocker for “no approve affordance” / trust-ladder honesty).

---

## 3. macOS app — sandbox boundary + Yahor-only steps (PR #6)

### What the sandbox actually confines

- The **UI process** (`RunSpecimen.app`) is designed for App Sandbox: user-selected workspace and CLI via `NSOpenPanel` + security-scoped bookmarks; optional network client for opening docs links; optional loopback server entitlement only if launching dashboard from the app.
- Approval uses a real PTY attached to `runspecimen approve` (or Terminal handoff); the app must not inject `APPROVE`.

### What is **not** claimed

- App Sandbox on the companion does **not** mean the externally launched CLI, host Python, or the **payload command** are OS-sandboxed.
- Bundled/frozen helper paths improve distribution; they still do not turn RunSpecimen into a general OS sandbox product.
- ADR-001 / APP_STORE.md / ROADMAP state this boundary explicitly.

### Signing / notarization steps that still require Yahor

1. Apple Developer Program membership + **Developer ID Application** certificate.  
2. Notary credentials (App Store Connect API key or app-specific password).  
3. Fill gitignored `apps/macos/Config/signing.env` from the example.  
4. `./Scripts/check_signing_identity.sh` → expect `Developer ID Application: …`.  
5. `./Scripts/build_app.sh` then `./Scripts/sign_and_notarize.sh sign` (Hardened Runtime `--options runtime`) and notarize/staple per `NOTARIZATION.md` / `RELEASE_CHECKLIST.md`.  
6. Separate later decision for Mac App Store (Target A) vs Developer ID-only (Target B recommended first).

**This report does not run notarization.**

---

## 4. Artifacts — rebuild and validate

### Python package (PR #7 tree @ `b7202b8`)

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests` | **215 OK** (2 skipped) |
| `python3 -m unittest tests.test_ed25519 -v` | **23 OK** (incl. failed rotation, interruption, symlink/TOCTOU) |
| `python scripts/release_check.py --output-dir /tmp/runspecimen-release-check-pr7` (venv + `setuptools>=77` + PyNaCl) | **passed** |

Artifacts under `/tmp/runspecimen-release-check-pr7` (version still **0.2.0rc9** until a deliberate version bump):

| File | SHA-256 (local rebuild) |
| --- | --- |
| `runspecimen-0.2.0rc9-py3-none-any.whl` | `f28fce7fb9a46dde7856c0a3b16226e9dfa696035d5e30f38814766e52e5f66e` |
| `runspecimen-0.2.0rc9.tar.gz` | `0667f133f296fd9f2ce03643b55145b015fdcbddb1355737cc31a8ba91017a83` |
| `runspecimen-plugin-0.2.0-rc.9.zip` | `3ba9d490a432c986f3c706ca9b4b4b76adc097c4ade5470af0c41aa0ff3df487` |

Wheel METADATA: no hard deps; only optional `Requires-Dist: pynacl>=1.5.0; extra == "ed25519|signing"`.

**Install / upgrade behavior (proposed rc10, after version bump):**

- Fresh: `pip install runspecimen==0.2.0rc10` (stdlib).  
- Ed25519: `pip install 'runspecimen[ed25519]==0.2.0rc10'`.  
- Upgrade from rc9: normal pip upgrade; HMAC keys unchanged; new Ed25519 files only appear after `keygen --scheme ed25519`. Schema: new certs gain `schema_version: 1`; old certs still verify.

### macOS app (PR #6)

- CI job `macos-app` green on the PR.  
- Local ad-hoc build documented; Developer ID artifacts **not** produced in this report.

---

## 5. Docs / product-page reconciliation

| Surface | Status vs proposed scope |
| --- | --- |
| Repo `README.md` / `CHANGELOG.md` (Unreleased) | Describes schema, dashboard IA, Ed25519 + rotation/TOCTOU hardenings on #7 branch |
| `docs/ED25519_RECEIPTS.md` | Trust model + rotation/TOCTOU notes updated |
| `docs/SCHEMA_COMPATIBILITY.md`, `docs/ROADMAP_PHASED.md`, FAQ/USER_GUIDE (PR #5) | Aligned with Phase 0 |
| `apps/macos/*` docs (PR #6) | Honest sandbox / notarization posture |
| Website SOURCE `astro-portfolio/sites/runspecimen/public` | Already pins **rc9**, states not a sandbox, Ed25519 needs external trust anchor, dashboard cannot approve. **No macOS app claim.** No deploy performed. |

**Before publishing rc10:** bump version strings on the website SOURCE (and release links) to match the chosen tag; keep “not a sandbox” / receipt-vs-verify language; still do not deploy without a separate ask.

---

## 6. Unresolved blockers + production decision for Yahor

### Unresolved / residual risks (non-blocking for “merge recommendation,” blocking for “publish” until acknowledged)

1. **Version still says 0.2.0rc9** on the #7 branch until an explicit bump commit.  
2. **Ed25519 crash mid-rotation:** process kill after live keys moved to `.bak-*` but before finals restored can require manual restore of sidecar files (in-process failures roll back).  
3. **Soft-key custody** remains the trust root for Ed25519.  
4. **macOS notarization / MAS** require Yahor’s Apple credentials and a separate ship decision.  
5. **PR merge order:** prefer merging #7 (lands #5+#7) *or* merge #5 then #7; keep #6 independent. Do not merge #6 into the Python RC by accident.  
6. Website / PyPI / GitHub Release assets must be updated together if publishing.

### Precise decisions needed from Yahor

Check exactly one package path and optional macOS path:

**Python package**

- [ ] **A1 — Merge #7 only** (includes #5), bump to `0.2.0rc10`, run release_check, publish PyPI + GitHub Release **after** you explicitly approve publish.  
- [ ] **A2 — Merge #5 and #7 separately**, then same bump/publish gate.  
- [ ] **A3 — Do not merge yet**; leave PRs open for more review.  
- [ ] **A4 — Reject / rework** (name the blocker).

**macOS app**

- [ ] **B1 — Keep #6 open**; no `.app` in this RC.  
- [ ] **B2 — Build ad-hoc `.app` for internal smoke only** (no notarize).  
- [ ] **B3 — You will run Developer ID sign + notarize** (Target B) as a **separate** artifact from the Python RC.  
- [ ] **B4 — Do not pursue macOS distribution in this cycle.**

**Website**

- [ ] **C1 — Update SOURCE only** when rc10 tag exists; **do not deploy** until asked.  
- [ ] **C2 — Deploy updated marketing site** in a later explicit request.

**Default recommendation from this report:** **A1 + B1 + C1** — land Python rc10 from #7 (schema + dashboard + Ed25519 hardenings); leave macOS as a parallel track; update website SOURCE only after the tag exists; publish/deploy/notarize only on a later explicit yes.

---

## Appendix — PR #7 validation snapshot (post TOCTOU/rotation fix)

- Commit: `b7202b8` — *Make Ed25519 key rotation recoverable and close key-read TOCTOU.*  
- Tip matches `origin/cursor/ed25519-pubkey-receipts`.  
- Left alone: `cursor/macos-native-app`, unrelated stashes, untracked local `apps/` checkout debris, website deploy.  
- CI: re-triggered on push; prior #7 head was fully green across Ubuntu 3.9–3.14 + macOS release-check.
