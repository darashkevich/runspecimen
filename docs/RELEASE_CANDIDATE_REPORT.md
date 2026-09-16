# RunSpecimen release-candidate report (PRs #5 / #6 / #7)

**Date:** 2026-09-16  
**Authoring branch:** `cursor/ed25519-pubkey-receipts`  
**Package identity on this PR:** **`0.2.0rc10`** / plugin **`0.2.0-rc.10`**  
**Baseline already published:** [v0.2.0-rc.9](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.9) / PyPI `runspecimen==0.2.0rc9`  
**Hard stops honored:** no merge, no PyPI publish, no website deploy, no notarization, no marketplace submit, no retag of rc9.

**READY FOR CODEX QA: yes** (after CI green on this tip)

This report is the decision packet for the next Python RC after rc9. PR #6 (macOS) remains a separate workstream.

| PR | Title | Role |
| --- | --- | --- |
| [#5](https://github.com/darashkevich/runspecimen/pull/5) | Phase 0: schema compatibility + dashboard IA | Included in #7 stack |
| [#6](https://github.com/darashkevich/runspecimen/pull/6) | Native macOS RunSpecimen app | **Out of scope for this RC** |
| [#7](https://github.com/darashkevich/runspecimen/pull/7) | Harden optional Ed25519 receipts + rc10 | Python package candidate |

---

## 1. Features in THIS RC vs future

### Ships in Python `0.2.0rc10` (PR #7, includes #5)

- Schema compatibility fail-closed; new certs emit `schema_version: 1`.
- Loopback dashboard IA: run identity / outcomes / continue safety / next CLI step; receipt ≠ live-verified.
- Optional `runspecimen[ed25519|signing]` → PyNaCl; default install dependency-free.
- Trust model: embedded-key-only consistency never `ok: true`.
- Key I/O: `0600` exclusive `O_EXCL|O_NOFOLLOW`; export never opens private seed; reads `O_NOFOLLOW`+`fstat`.
- **Crash-safe key rotation:** durable journal + temps/backups; SIGKILL at every transition recovers automatically on next open/use; all-or-nothing (never lose both pairs).
- **Key-dir exclusion:** `.runspecimen/keys.op.lock` (`fcntl`) serializes create/list/rotate/load.

### Not in this Python RC

- macOS `.app`, Apple signing, notarization, Mac App Store (PR #6 only).
- Website production deploy / marketplace listings / PyPI publish.

---

## 2. Crash-safe rotation + concurrency (evidence)

### Design

- Journal file: `.runspecimen/keys/.<key_id>.ed25519.rotate.journal` (fsynced phase commits).
- Phases: `intent` → `staged` → `pub_backed` → `pub_installed` → `priv_backed` → `priv_installed` → `complete` (fresh create also journals `fresh_priv_installed`).
- On next `save` / `load` / `list` / `export`: hold `keys.op.lock`, recover journals/orphaned sidecars.
- Pre-`priv_installed`: roll back to previous working pair. At/after `priv_installed` (including `complete`): keep new pair and clean leftovers.

### Tests (independent re-validation 2026-09-16)

| Evidence | Result |
| --- | --- |
| `PYTHONPATH=src python3 -m unittest discover -s tests` | **220 OK** (2 skipped) |
| `PYTHONPATH=src python3 -m unittest tests.test_ed25519 -v` | **28 OK** |
| SIGKILL at `intent`,`staged`,`pub_backed`,`pub_installed`,`priv_backed` | recovers **previous** pair |
| SIGKILL at `priv_installed`,`complete` | keeps **new** pair; cleans sidecars |
| SIGKILL at fresh `intent`,`staged`,`fresh_priv_installed` | no half-pair left |
| SIGKILL at fresh `complete` | pair remains loadable |
| Cross-process rotator∥loader | consistent loadable pair |
| Cross-process concurrent creates (`raceA`/`raceB`) | both keys loadable |
| Non-blocking second process lock | `SigningError` … busy |

---

## 3. Version identity + artifact validation

| Surface | Value |
| --- | --- |
| `pyproject.toml` / `__version__` | `0.2.0rc10` |
| Codex/Cursor plugin manifests + marketplace.json | `0.2.0-rc.10` |
| `scripts/release_check.py` EXPECTED_* | matches above |

Local rebuild (not published): `/tmp/runspecimen-release-check-rc10`  
Interpreter: `.tools/python` 3.11.10 (offline builds require setuptools≥77 in **non-user** site-packages; see release_check gate fix).

| Artifact | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc10-py3-none-any.whl` | `fcac250e60dc1327946ab6f62d8527cd4be72026d7cd34eba283f40619fc877c` |
| `runspecimen-0.2.0rc10.tar.gz` | `631334a9ccef12af23b07ea43a3ecfdaede8d29f0c813b105ed7d705a072635a` |
| `runspecimen-plugin-0.2.0-rc.10.zip` | `50b0f2a98b92f8d3d08c9c790adf65412fadba8c433eb4bc434f318a30178d55` |

| Install check | Result |
| --- | --- |
| Fresh wheel install | `runspecimen 0.2.0rc10` |
| Fresh sdist install | `runspecimen 0.2.0rc10` |
| Upgrade `0.2.0rc9` → local rc10 wheel | before `rc9`, after `rc10` |
| `release_check.py` (`.tools/python`) | **passed** (`release-report.json` ok) |
| Live PyPI / GitHub `v0.2.0-rc.10` | **absent** (confirmed 404 / release not found) |

rc9 was **not** republished or retagged.

### Release-check hardening in this tip

`ensure_build_backend()` now probes setuptools under the same `PYTHONNOUSERSITE=1` offline env used for packaging, so a user-site-only setuptools≥77 cannot silently produce `UNKNOWN-0.0.0` sdists.

---

## 4. Dashboard accessibility

**Fixes:** `aria-label` on About-docs links (names available even when `<details>` is closed); always-visible footer docs nav; docs nav kept on mobile.

| Evidence path | Notes |
| --- | --- |
| `/tmp/runspecimen-dashboard-a11y/desktop.png` | 1280×800 visual |
| `/tmp/runspecimen-dashboard-a11y/mobile.png` | 390×844 visual |
| `/tmp/runspecimen-dashboard-a11y/desktop-keyboard.png` | focus/keyboard smoke |
| `/tmp/runspecimen-dashboard-a11y/mobile-keyboard.png` | focus/keyboard smoke |
| `/tmp/runspecimen-dashboard-a11y/rc_notes.json` | structured checks |

**Checks (2026-09-16 refresh):** lang=en; H1 present; **unnamed interactive controls = 0**; cannot-approve copy; receipt vs LIVE VERIFICATION / not-checked; keyboard focus reaches named links/buttons on desktop and mobile (13 tab stops each).

---

## 5. Docs / website SOURCE

| Surface | Status |
| --- | --- |
| README / CHANGELOG / FAQ / USER_GUIDE / ED25519_RECEIPTS / SUBMISSION | Aligned to **0.2.0rc10**; README + USER_GUIDE + SUBMISSION honest that PyPI/GitHub assets appear only after publish (SUBMISSION no longer marks rc10 as live) |
| Website SOURCE `astro-portfolio/sites/runspecimen/public` | Candidate wording for rc10 present in working tree; last-published assets still rc9; **not deployed**; **not committed** in astro-portfolio (separate repo decision) |
| PR #6 macOS | Explicitly out of release scope |

---

## 6. macOS (PR #6) — Yahor-only prerequisites

Apple signing / notarization remain **Yahor-only** and are **not** part of Python rc10:

1. Apple Developer Program + Developer ID Application certificate  
2. Notary credentials  
3. `apps/macos/Config/signing.env` (gitignored)  
4. `check_signing_identity.sh` → `build_app.sh` → `sign_and_notarize.sh`  
5. Separate decision for Developer ID vs Mac App Store  

**This report does not sign, notarize, or submit.**

---

## 7. Remaining blockers needing Yahor

External decisions only (engineering release blockers for Codex QA are cleared on this tip after CI):

1. **Merge policy:** merge #7 (includes #5) vs merge #5 then #7; keep #6 separate.  
2. **Publish:** GitHub Release `v0.2.0-rc.10` + PyPI `0.2.0rc10` only on explicit yes (do not touch rc9).  
3. **Website deploy** after SOURCE/tag alignment — separate ask. Optionally commit SOURCE updates in `astro-portfolio`.  
4. **Marketplace submits** — separate ask.  
5. **Apple signing / notarization** for PR #6 — Yahor-only, separate track.  
6. Soft-key custody remains the Ed25519 trust root (product limitation, not a bug).

### Decision checklist

**Python:** [ ] A1 merge #7 + publish rc10 after approval · [ ] A2 merge #5 then #7 · [ ] A3 leave open · [ ] A4 rework  

**macOS:** [ ] B1 keep #6 open (recommended with this RC) · [ ] B2 ad-hoc only · [ ] B3 you notarize separately · [ ] B4 defer  

**Website:** [ ] C1 SOURCE only until asked (local candidate; not deployed) · [ ] C2 deploy later  

**Default recommendation:** **A1 + B1 + C1** after Codex QA sign-off.

---

## 8. Codex QA readiness

| Gate | Status |
| --- | --- |
| Crash-safe rotation + SIGKILL fault tests (every transition) | Done |
| Key-dir / concurrent exclusion + tests | Done |
| Distinct `0.2.0rc10` identity | Done |
| Fresh + rc9→rc10 artifact checks | Done (local) |
| Dashboard a11y (unnamed links fixed) + desktop/mobile keyboard/visual | Done |
| Docs honest about unpublished rc10; SOURCE candidate; no deploy | Done |
| CI green on push | Required after push of this update |
| Merge / publish / notarize / marketplace | **Not done** (hard stop) |

### READY FOR CODEX QA: **yes**

Independent Codex QA can review PR #7 tip after CI is green. Do not merge or publish from QA alone.
