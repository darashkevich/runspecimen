# RunSpecimen release-candidate report (PRs #5 / #6 / #7)

**Date:** 2026-09-16  
**Authoring branch:** `cursor/ed25519-pubkey-receipts`  
**Package identity on this PR:** **`0.2.0rc10`** / plugin **`0.2.0-rc.10`**  
**Baseline already published:** [v0.2.0-rc.9](https://github.com/darashkevich/runspecimen/releases/tag/v0.2.0-rc.9) / PyPI `runspecimen==0.2.0rc9`  
**Hard stops honored:** no merge, no PyPI publish, no website deploy, no notarization, no marketplace submit, no retag of rc9.

**READY FOR CODEX QA: yes** (after CI green on this tip — includes forged `fresh_priv_installed` complete-pair wipe fix)

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
- **Journal path-trust hardening (CVE-class):** recovery no longer trusts absolute `priv_tmp`/`pub_tmp`/`priv_bak`/`pub_bak` strings from a writable journal for `unlink`/`os.replace`.
- **Forged fresh-create journal wipe (CVE-class):** recovery no longer treats filename/`key_id` match alone as proof of an in-progress fresh create; a complete live pair is preserved when `fresh_priv_installed` provenance is insufficient.

### Not in this Python RC

- macOS `.app`, Apple signing, notarization, Mac App Store (PR #6 only).
- Website production deploy / marketplace listings / PyPI publish.

---

## 1b. CVE-class finding: rotation journal path trust (fixed)

**Finding:** `_recover_one_rotation_journal` previously took `priv_tmp` / `pub_tmp` / `priv_bak` / `pub_bak` as absolute paths from the rotation journal (a file an attacker who can write the keys directory can forge) and passed them to `unlink` / `os.replace`. A forged journal could therefore delete or replace files **outside** the keys directory when the next key operation triggered recovery.

**Fix (fail-closed):**

1. Validate journal `key_id` against the journal filename (`.<key_id>.ed25519.rotate.journal`).
2. Accept sidecar fields only when the **basename** matches the narrow rotation sidecar pattern for that key; reconstruct the path as `keys_dir / basename` (never use the journal’s absolute parent for I/O).
3. Reject symlink sidecars (`is_symlink` / no-follow posture).
4. On invalid journals: discard **only** the journal; do **not** delete live key finals; do **not** touch foreign paths.
5. Regression coverage in `tests.test_ed25519.TestEd25519JournalPathTrust` (outside-victim, malformed, symlink sidecar, foreign-key / basename mismatch, traversal).

**Evidence:** see §2 and `TestEd25519JournalPathTrust.test_forged_journal_does_not_touch_outside_victim`.

---

## 1c. CVE-class finding: forged `fresh_priv_installed` wipes complete pair (fixed this tip)

**Finding:** Matching journal filename/`key_id` is **not** proof of a genuine fresh-create transaction. An attacker who can write `.runspecimen/keys/` could plant:

```json
{"version":1,"key_id":"forged","phase":"fresh_priv_installed","priv_tmp":null,"pub_tmp":null,"priv_bak":null,"pub_bak":null}
```

Recovery previously treated `fresh_priv_installed` as an incomplete fresh create and unlinked both live finals — wiping a complete working keypair (`rolled_back_fresh_incomplete`).

**Fix (fail-closed):**

1. For `fresh_priv_installed`, if both `*.ed25519` and `*.ed25519.pub` finals are already present, discard the journal **without** deleting finals (`discarded_untrusted_journal:fresh_priv_installed_complete_pair_preserved`).
2. Incomplete fresh creates (public final missing after private install — the real SIGKILL window) still roll back correctly.
3. Regression: `TestEd25519JournalPathTrust.test_forged_fresh_priv_installed_journal_does_not_wipe_complete_pair`.

**Evidence:** exact QA repro now preserves the pair; prior path-trust / outside-victim / symlink / foreign-key tests remain green.

---

## 2. Crash-safe rotation + concurrency (evidence)

### Design

- Journal file: `.runspecimen/keys/.<key_id>.ed25519.rotate.journal` (fsynced phase commits).
- Phases: `intent` → `staged` → `pub_backed` → `pub_installed` → `priv_backed` → `priv_installed` → `complete` (fresh create also journals `fresh_priv_installed`).
- On next `save` / `load` / `list` / `export`: hold `keys.op.lock`, recover journals/orphaned sidecars.
- Pre-`priv_installed`: roll back to previous working pair. At/after `priv_installed` (including `complete`): keep new pair and clean leftovers.
- Recovery path-trust: basename-only reconstruction under keys dir; `key_id`↔filename match; symlink sidecars rejected.

### Tests (independent re-validation 2026-09-16, post forged-fresh wipe fix)

| Evidence | Result |
| --- | --- |
| `PYTHONPATH=src python3 -m unittest discover -s tests` | **226 OK** (2 skipped) |
| `PYTHONPATH=src python3 -m unittest tests.test_ed25519 -v` | includes JournalPathTrust |
| Outside-victim forged journal | victim file **untouched**; live keys intact; journal discarded |
| Forged `fresh_priv_installed` + complete live pair | pair **preserved**; journal discarded (`complete_pair_preserved`) |
| Malformed / wrong-type journals | discarded; live keys intact |
| Symlink sidecar in journal | discarded as untrusted; target untouched |
| Foreign-key journal (`key_id` mismatch / other-key basename) | discarded; both keys intact |
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

Local rebuild (not published): `/tmp/runspecimen-release-check-rc10-20260916120713`  
Interpreter: `.tools/python` 3.11.10 (offline builds require setuptools≥77 in **non-user** site-packages; see release_check gate fix).

| Artifact | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc10-py3-none-any.whl` | `c9e538f61ea358e22d0407594022c99e18e0bde47a7b07c45a1de3363e0cab1e` |
| `runspecimen-0.2.0rc10.tar.gz` | `f207a246bde4507bf3e4389f49f067c46b07d2c321e12045694361c0882287a4` |
| `runspecimen-plugin-0.2.0-rc.10.zip` | `50b0f2a98b92f8d3d08c9c790adf65412fadba8c433eb4bc434f318a30178d55` |
| `release-report.json` | a9d0ab0ad798a531825b3a33532a797d0273f4f39aa530bcd9e8d388dca608a9 |

Local artifacts path: `/tmp/runspecimen-release-check-rc10-20260916120713` (not published).

| Install check | Result |
| --- | --- |
| Fresh wheel install | `runspecimen 0.2.0rc10` |
| Fresh sdist install | `runspecimen 0.2.0rc10` |
| Upgrade `0.2.0rc9` → local rc10 wheel | before `rc9`, after `rc10` |
| `release_check.py` (`.tools/python`) | **passed** (`release-report.json` ok) |
| Live PyPI / GitHub `v0.2.0-rc.10` | **absent** (do not publish in this session) |

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
| README / CHANGELOG / FAQ / USER_GUIDE / ED25519_RECEIPTS / SUBMISSION | Aligned to **0.2.0rc10**; README + USER_GUIDE + SUBMISSION honest that PyPI/GitHub assets appear only after publish (SUBMISSION no longer marks rc10 as live); CHANGELOG + ED25519 docs note journal path-trust fix |
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
| Journal path-trust CVE-class fix + outside-victim regression | Done |
| Forged `fresh_priv_installed` complete-pair wipe fix + regression | Done |
| Distinct `0.2.0rc10` identity | Done |
| Fresh + rc9→rc10 artifact checks | Done (local) |
| Dashboard a11y (unnamed links fixed) + desktop/mobile keyboard/visual | Done |
| Docs honest about unpublished rc10; SOURCE candidate; no deploy | Done |
| CI green on push | Required after push of this update |
| Merge / publish / notarize / marketplace | **Not done** (hard stop) |

### READY FOR CODEX QA: **yes**

Independent Codex QA can review PR #7 tip after CI is green. Do not merge or publish from QA alone.

### Post-clearance release plan (Python / GitHub / site only — after “Codex QA cleared + approve release”)

Do **not** execute until Yahor explicitly clears. Exact steps then:

1. Merge PR #7 (includes #5). Keep PR #6 macOS separate; no notarization / marketplace claim.
2. From a clean checkout of the merged tip, re-run `scripts/release_check.py --output-dir /tmp/runspecimen-release-check-rc10` and retain:
   - `runspecimen-0.2.0rc10-py3-none-any.whl`
   - `runspecimen-0.2.0rc10.tar.gz`
   - `runspecimen-plugin-0.2.0-rc.10.zip`
   - `SHA256SUMS` / `release-report.json`
3. GitHub Release `v0.2.0-rc.10` attaching the three artifacts + checksums (do not retag/move rc9).
4. PyPI: `twine upload` the rc10 wheel + sdist only (`runspecimen==0.2.0rc10`).
5. Website: deploy `astro-portfolio` RunSpecimen SOURCE only on a separate explicit ask after tag/PyPI alignment.
6. Verify: `pip install runspecimen==0.2.0rc10` → `runspecimen --version` shows `0.2.0rc10`; GitHub release assets 200; PyPI page lists rc10.
