# RunSpecimen independent QA

**Reviewer:** Cursor Cloud Agent (read-only product QA; no feature implementation).  
**Date:** 2026-10-05.  
**Owner paste target:** `artifacts/CURSOR-MEGA-PROMPT.md` (prompt-only copy).

## Scope (read this first)

PR **#39** is **not** the same git ref as branch `cursor/evidence-expansion-coherence`.

| Label | Ref | SHA reviewed | What it is |
| --- | --- | --- | --- |
| **A — this checkout (PR base)** | `cursor/evidence-expansion-coherence` | `d54c803c9b6dfe82cb91f55c5a21923c822041d9` | ADR-005 evidence expansion + Mac native workflows / 0.1.5 (12). Engine still `__version__ = "0.2.0rc14"`. |
| **B — PR #39 head** | `cursor/integrated-release-candidate` | `fa8664338faa1dc137ade9f30e73d9ffffa6a752` | Holder process, single-use signatures, phone review, uncertain leases, package hashes, unpublished `0.2.0rc15`. Base of the PR is **A**. |

Holder / Secure Enclave / bundle-id work **does not exist on A**. Findings for those are from a disposable worktree of **B** (`/tmp/rs-pr39-head`). Do not treat a green suite on A as a sign-off of B.

Published PyPI/GitHub identity remains **`0.2.0rc14`**. Store submission on file remains **0.1.4 (9)**. Neither is this branch’s extra engine surface.

---

### 1. Executive summary

This checkout (A) is a coherent ADR-005 slice: unapproved `requirements check` is refused, agent `passed` is ignored, captures are pointer+immutable files, freshness is not `verify`, plugins still omit approve. Prior P1/P2 on A were closed in `58564c1` / `85d6564` and stay closed under unittest.

Remaining holes on A are real: policy `requirements_check` accepts a self-digested `passed` report without receipt binding; MCP `freshness_check` writes state while docs say read-only; postflight can bind a stale attestation; evidence pointer paths are not confined; this tree still wears the **published rc14** version while shipping unpublished commands.

PR #39 head (B) is a large holder/biometric candidate, not production-ready. Installed admission is fail-closed; E2 is explicitly open; Apple documents root-daemon Secure Enclave as unsupported. Two product choices are blocked on Yahor (D1 architecture, D2 holder bundle id). Do not invent those.

Python tests on A: **377 passed, 1 error (env), 33 skipped**. Swift/iOS/macOS were **not** run here (no `swift`). B worktree: **562 passed, 3 failed, 75 skipped** (rsync/reproducibility/Linux). GitHub Actions on B tip: **18/18 green**. Independent QA does not equal production or biometric sign-off.

---

### 2. Findings table

Severity: **P0** ship-blocker / identity or trust lie. **P1** security/integrity or operator-facing authorization bug with code evidence. **P2** clear defect or docs/contract skew. **P3** cleanup / missing test / low risk. Categories: `bug` | `cleanup` | `feature` | `decision`.

| ID | Sev | Cat | Location | Evidence | Suggested fix direction |
| --- | --- | --- | --- | --- | --- |
| **D1** | P0 | decision | `docs/SECURE_ENCLAVE_ADMISSION.md` (B); `apps/holder/.../DaemonKeyFeasibility` | In-tree: root `launchd` / SMAppService Secure Enclave creation is **unsupported** (TN3137 + DTS). `unattendedAssessment()` → `finding: "unsupported"`. Hardware callsite count 0. | **NEED USER.** Options: (1) keep installed admission fail-closed; (2) per-user Aqua creator (not a root daemon; not guarantee (2); same-user can still mint a key); (3) Yahor-named alternative. Do not store SE `dataRepresentation` in the system keychain. |
| **D2** | P0 | decision | `apps/holder/Resources/Info.plist` CFBundleIdentifier; `docs/SECURE_ENCLAVE_ADMISSION.md` §Identities | Bundle id `com.darashkevich.runspecimen.holder` is used in plist, LaunchDaemon, `/Library/Application Support/...`. Docs: **unconfirmed**, not D1, not in `production_verifier_pin()`. Staging uses ad-hoc `codesign --sign -`. | **NEED USER.** Accept this id (then pin designated requirement) or rename before treating it as canonical. |
| **F01** | P0 | feature | B: `execution_holder.py`, `native_bridge.py`, `docs/HOLDER_NATIVE_BRIDGE.md` | Responses set `run_integration_complete: False`, `e2_closed: False`. CHANGELOG: installed admission stays closed. | Keep labels. Do not close E2 without D1 + human/device evidence. Marketing must not claim holder = Secure Enclave. |
| **F02** | P1 | bug | A+B: `src/runspecimen/policy.py` `enforce_required_verification` (`requirements_check`) | Only checks `aggregate_outcome == "passed"`. No `authenticity == "receipt_bound"`, no `final_state_certifiable`. `test_p2_required_verification_refuses_verify_without_evidence` uses **both** steps and a **missing** report. | Require receipt-bound + certifiable (or refuse). Add test: **only** `requirements_check` + forged passed report. |
| **F03** | P1 | bug | A+B: `plugins/runspecimen/README.md`; `scripts/runspecimen_mcp.py` `freshness_check`; `cli_expansion.py` `_freshness` | README: “read-only … `freshness_check`”. MCP runs `runspecimen freshness check`, which **writes** `freshness_report.json`. `check_freshness_for_run` (dashboard) does **not** write. | Make MCP `freshness show` / evaluate-only, or document mutating. Same for adapter + antigravity copy. Test that a read-only tool does not create the file. |
| **F04** | P1 | bug | A: `src/runspecimen/__init__.py` `__version__ = "0.2.0rc14"` vs unpublished expansion | This branch adds `requirements`/`freshness`/… while still claiming the **published** package identity. FAQ correctly says published rc14 lacks expansion; USER_GUIDE presents those commands as installed rc14. B already moved to `0.2.0rc15`. | Never republish rc14 bytes. Keep unpublished identity on the integrated tip. Fix USER_GUIDE/README pin language on any tree that still says rc14. |
| **F05** | P1 | bug | B: `src/runspecimen/run.py` `_human_for` | Returns `"hardware": True` with **no** `signatures`. Holder then refuses “cryptographic device signatures are missing.” Misleading before the real fail-closed. | Set `hardware` false unless a verified signature is attached; one operator-facing refusal. Regression test. |
| **F06** | P1 | bug | B: `execution_holder.py` execute ~2761–2765 | Pre-spawn failure writes `lease.json` `held: False`, `child: "spawn-failed"`. Swift exact-run tests keep an **uncertain** lease on execute failure. Checklist says execute failure keeps uncertain lease. | Reconcile Python with Swift/docs. If product rule is uncertain, do not release; add Python test. |
| **F07** | P1 | feature | B: `run.py` `_resolve_installed_holder` | Docstring: does not prompt. Installed policy has no typed-phrase fallback. CLI cannot collect exact-run signatures here. | Fail fast with a single message, or wire the already-approved exact-run IPC **without** declaring E2 closed or calling consume as an execution gate unless Yahor authorized that. |
| **F08** | P2 | bug | A+B: `src/runspecimen/postflight.py` `_postflight_under_lease` | Loads `evidence_attestation.json` if digest-valid; embeds in certificate; no check vs current evidence pointer/capture digest. Broad `except` swallows errors → silent omit. | Bind only if attestation digest matches `load_evidence_report`. Test stale attestation + new capture. |
| **F09** | P2 | bug | A+B: `requirements.py` `load_evidence_report` | `captures_dir / str(doc.get("capture_path"))` with no basename/`ensure_within`. Writer who rebinds pointer digest can traverse. | Basename-only under `evidence_captures/`; reject `..`, abs paths, symlinks. |
| **F10** | P2 | bug | A: `scenes.py` `_seed_mini_workspace` `pass_manifest` | `provider: "unittest"` but `required_evidence: ["junit"]` and description “Passing pytest check”. Unittest artifacts are not `junit` → `_requirement_outcome` would not pass after a real approved check. Scene 1 only tests unapproved refusal. | Align `required_evidence` with unittest artifacts or use pytest+junit. |
| **F11** | P2 | bug | A: `CLIService.swift` `run` ~399 | `failed = output.timedOut \|\| output.cancelled`. Truncation is appended to stderr but **not** failure. 8 MiB cap. Later PR comments added stream-read/cleanup axes on B — still need **service-level** tests. | Treat truncation / stream-read / cleanup as failure for JSON and plain-text; inject `ProcessResult` at `CLIService`. |
| **F12** | P2 | cleanup | A: `docs/USER_GUIDE.md` §Requirements vs `docs/FAQ.md` “Which build is public” | USER_GUIDE: “matches … `0.2.0rc14`” then documents expansion CLIs. FAQ: published rc14 **does not** include them. Operators who `pip install runspecimen==0.2.0rc14` will not have those commands. | Split “published pin” vs “this branch / rc15”. |
| **F13** | P2 | cleanup | A: `apps/macos/RELEASE_CHECKLIST.md` L10; `asc-kit/README.md` L13 | Still “Successor source here is **0.1.5 (10)**”. STATUS / NATIVE_FEATURE_COVERAGE / CHANGELOG: candidate **0.1.5 (12)** from `c400f2d`. Checklist links `docs/SECURITY_BOUNDARY.md` (missing); real file is `apps/macos/docs/SECURITY_BOUNDARY.md`. | Update successor identity; fix the link. |
| **F14** | P2 | bug | B: `docs/CANDIDATE_MANIFEST.md` vs ledger `2026-10-02-codex-release-ledger.md` | Manifest wheel hash lagged ledger seal hashes at `fa86643`. | One canonical hash table at the exact tip. Hashes outside packed sdist files. |
| **F15** | P2 | bug | B: `tests/test_release_ledger.py` `HolderStageTests` | Failed in Linux worktree: `build_install_holder.sh: rsync: command not found`. | Skip with reason when `rsync`/`swiftc` absent; keep assertions on macOS. |
| **F16** | P2 | feature | A: `cli_expansion.py` requirements `check` `ok` | `ok` requires `authenticity == "receipt_bound"` immediately after check, which is false until postflight. Honest but looks like check failure (exit 1) when checks passed. | Split `checks_passed` vs `receipt_bound`. Document exit codes. Do not weaken authenticity. |
| **F17** | P2 | feature | B: `execution_holder.py` `submit_device_signature` under `installed_protection` | After valid P-256, raises `production_enrollment_refusal()`. Installed daemon cannot enroll phone/Mac keys via that socket path. | Document; do not add a new enrollment architecture (D1). |
| **F18** | P2 | decision | B: `docs/APPLE_DTS_HOLDER_QUESTION.md` | Status **not sent**. Asks whether embedded `SMAppService.daemon` violates App Store 2.4.5(v). | **NEED USER** whether to send. Not a code task. |
| **F19** | P3 | cleanup | A: `snapshot.py` `_assert_safe_restore_dest` | Defined; callers use `_restore_dest_refusal_reason` directly. | Delete wrapper or use it from restore/preview. |
| **F20** | P3 | bug | A: `dashboard.py` `_evidence_panel` | Bare `except: pass` → load failures look like “no evidence / unknown applicability.” | Surface a read-only error field. |
| **F21** | P3 | cleanup | A: `MANIFEST.in` | No `docs/ADR-005-evidence-expansion.md` / `NATIVE_FEATURE_COVERAGE.md`. Duplicate `logo.png` include. | Add expansion docs if they should ship in sdist; drop duplicate include. |
| **F22** | P3 | cleanup | A: `plugins/.../runspecimen_mcp.py` and `antigravity/scripts/runspecimen_mcp.py` | Near-duplicate servers; F03 can be fixed in one copy only. | Thin re-export. |
| **F23** | P3 | bug | A: `requirements.py` `UnittestProvider.run` | May `write_text` `__init__.py` into `start_dir`; unlink is best-effort. Can trip `source_changed_during_checks`. | Don’t write into live source roots (temp copy). |
| **F24** | P3 | bug | A: `usage.py` `import_usage` | Read-modify-write without workspace lease; concurrent imports can drop events. | Lease or CAS on ledger digest. |
| **F25** | P3 | cleanup | A: `PytestProvider.run` `node_ids` | Appended as extra argv after `-q`, not as pytest nodeid selectors. Fail-closed on bad CLI, but config is misleading. | Document or implement real nodeid selection. |
| **F26** | P3 | feature | A: `decisions.py` `capture_decision` | No lease/approval/campaign bind (ADR allows explicit capture). Agents with a shell can append. | Document ungated, or optional bind to an approved run. Not an approve bypass. |
| **F27** | P3 | feature | B: many Darwin-only P-256 / exact-run tests | Skipped off-macOS (`P-256 verification uses the Darwin verifier`). Linux CI is not the holder proof. | Keep a macOS job; don’t skip-weaken Darwin tests. |
| **F28** | P3 | cleanup | A env | `test_wheel_and_sdist_digests_repeat` **ERROR**: `setuptools` 68.1.2 in this interpreter; gate wants `>=77` in site-packages (`PYTHONNOUSERSITE=1`). Not a product logic bug. | Use bootstrap/venv for `release_check.py`. |

Already **closed** on A (do not reopen without new evidence): unapproved command_status write (`test_p1_requirements_check_refuses_unapproved_command_write`); rewritten report not `ci.ok`; freshness without authenticity not applicable; coordination missing producer digest; config secret strip; snapshot parent restore refuse; MCP no `approve` tool; source change during checks; `freshness show` does not write. Mac `WorkflowConfirmationGate` claim-before-dismiss and `BoundedProcessCapture` drain have unit tests on A.

---

### 3. Cursor mega-prompt

Copy `artifacts/CURSOR-MEGA-PROMPT.md` verbatim (it is the prompt with no preamble). Summary of that prompt:

Work on **PR #39 HEAD** (`cursor/integrated-release-candidate`), not the evidence-expansion base. Close P0 honesty (`hardware` flag, rc14 identity, E2 labels), then P1 bugs F02–F07/F08–F09, then P2 cleanups, then in-scope holder features that are already designed. **Do not implement D1 or D2.** Verify with unittest + `release_check.py` + Swift when available.

---

## Test results

### A — `d54c803` (this environment)

Command: `PYTHONPATH=src python3 -m unittest discover -s tests -v`  
Host: Linux x86_64, Python 3.12.3, `setuptools==68.1.2`, no PyNaCl, no bwrap, no sandbox-exec, no `swift`.

| Result | Count |
| --- | --- |
| Ran | 378 |
| Passed | 377 |
| Errors | **1** — `test_release_archive_reproducibility.ReleaseArchiveReproducibilityTests.test_wheel_and_sdist_digests_repeat` (`setuptools>=77` required; env, F28) |
| Failed | 0 |
| Skipped | **33** |

Notable skips:

- **Ed25519 / PyNaCl** (~29): `PyNaCl not installed` / `pip install 'runspecimen[ed25519]'`.
- **bwrap** (3): `bwrap is not installed` (`test_bwrap_linux`).
- **sandbox-exec** (1): `sandbox-exec is not installed` (`test_phases.SeatbeltIntegrationTests`).

`python3 scripts/release_check.py` was **not** fully re-run: it would fail the same setuptools gate. GitHub **CI on this branch is green** (ubuntu + macos-app at `d54c803` push `36242764687`).

Swift / Xcode / iOS Observe / macOS app tests: **not run** (no `swift` / `xcodebuild`). Static review only: confirmation gate and pipe drain look consistent with tests under `apps/macos/Tests/RunSpecimenCoreTests/`.

### B — `fa86643` worktree (subagent; this VM)

Focused holder modules: 209 passed, 42 skipped, **2 failed** (`HolderStageTests`, missing `rsync`).  
Full discover: **562 passed, 75 skipped, 3 failed** (HolderStage + `test_wheel_and_sdist_digests_repeat`).  
GitHub Actions PR #39: **18/18 pass** (duplicate push/PR matrices).  
Swift holder / `apps/macos` tests: **not run here**. Prior Codex QA on older tips reported 70–94 Swift tests; do not treat those counts as this SHA.

---

## Remaining work inventory (not invented)

### On A (`CHANGELOG.md` Unreleased, ADR-005, NATIVE_FEATURE_COVERAGE)

Shipped on this branch vs published rc14: task manifests, provider evidence, freshness, config inspect/preview/apply/export/rollback, decisions, snapshots, usage, coordination, eval, `scenes`, native Workflows with confirmation, session restore, `freshness show`.  

Still CLI-only on the Mac candidate: `requirements check`, `freshness check`, digest, diff, retain. Store builds still omit browser dashboard / `network.server`. Native UI never types `APPROVE`.

ADR-005 non-goals remain: auto-deploy, auto-merge, spend hard-enforcement, scraping Cursor DBs, OS-sandbox claims, silent doctor sync, rewriting history.

No `TODO`/`FIXME`/`XXX` in-tree.

Docs/product still open from `NEXT_CHANGES.md` (not PR #39 scope unless Yahor says so): demo_rc TTY <10 min; host-bound showcase refresh; marketplace adapter polish. Isolation backends already in rc14.

Mac checklist: do not upload 0.1.5 while 0.1.4 (9) is WAITING_FOR_REVIEW.

### On B (PR #39 Unreleased / ledgers / HOLDER_NATIVE_BRIDGE)

Open by **docs themselves**: E2 not closed; biometric execution not on `runspecimen run`; human Touch ID / Face ID / carry-a-package; DTS unsent; whole-directory spent-history loss unsolved by design; Store XPC not feasible; `run_integration_complete` false; package hashes must be re-sealed per tip; H1/H2/H3 human gates.

In-scope to finish **without** D1/D2: F02–F16, hash table sync, MCP freshness honesty, uncertain-lease consistency, skip hygiene for rsync/swiftc.

---

## Classification for the owner

| Bucket | IDs |
| --- | --- |
| **(A) Safe cleanups** | F13, F19, F21, F22, F25; duplicate MCP; broken SECURITY_BOUNDARY link |
| **(B) Clear bugs (repro or strong code evidence)** | F02, F03, F05, F06, F08, F09, F10, F11, F15, F16, F20, F23, F24; F28 is environment |
| **(C) Remaining features (in-scope for PR #39, not new product)** | F01, F07, F14, F17, F27; exact-run/phone/spent already designed; E2 stays open |
| **(D) NEED USER** | **D1**, **D2**, **F18** (send DTS?). Also: whether CLI `run` may ever call consume as an execution gate; whether to promote biometrics beyond prototype |

---

## What this QA did not do

- No Touch ID / Face ID / System Settings daemon approval.
- No Store archive, notarization, or `/Applications` install.
- No typing `APPROVE`.
- No merge/publish.
- No iOS simulator ObserveSchemaTests.
- Did not treat GitHub Actions green as holder threat-model proof.
