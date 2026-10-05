# RunSpecimen — close quality gaps for the integrated RC (no invented product decisions)

You are implementing QA follow-up on **PR #39**. Independent QA already ran. Do not redesign the product. Do not guess blocked decisions. Do not merge, publish, retag, upload to PyPI, TestFlight, or submit to Apple. Do not type `APPROVE`. Do not trigger Touch ID / Face ID. Do not install or overwrite `/Applications/RunSpecimen.app` or a live holder daemon.

## Trees (do not confuse them)

| Tree | Ref | Role |
| --- | --- | --- |
| PR **base** | `origin/cursor/evidence-expansion-coherence` @ `d54c803c9b6dfe82cb91f55c5a21923c822041d9` | ADR-005 evidence expansion + Mac 0.1.5 (12) workflows. Engine still labeled `0.2.0rc14`. |
| PR **head** (work here) | `origin/cursor/integrated-release-candidate` (PR #39; last reviewed `fa8664338faa1dc137ade9f30e73d9ffffa6a752`) | Holder, single-use signatures, phone receipt, uncertain leases, package hashes, unpublished `0.2.0rc15`. |

Start from the **current PR #39 HEAD**, not the base. Re-read `docs/SECURE_ENCLAVE_ADMISSION.md`, `docs/HOLDER_NATIVE_BRIDGE.md`, `docs/CANDIDATE_MANIFEST.md`, `CHANGELOG.md` Unreleased, and `artifacts/RUNSPECIMEN-INDEPENDENT-QA.md` before editing.

Preserve: one lease / one approved run; agents never approve; dashboard loopback read-only; `verify` semantics unchanged; published `0.2.0rc14` bytes must not be replaced; Store package **0.1.4 (9)** identity stays distinct.

---

## BLOCKED — NEED USER DECISION (do not guess, do not implement a chosen architecture)

Stop and ask Yahor if work would require picking one of these. Present options and consequences only.

### D1 — Replacement for third-party root-daemon + Secure Enclave / Touch ID
Apple (TN3137 + DTS) marks Secure Enclave / data-protection keychain / biometry from a third-party `launchd` / `SMAppService.daemon` as **unsupported**. In-tree `unattendedAssessment()` already records `finding: "unsupported"`.

Options (do not pick):
1. Keep installed admission **fail-closed** (matches current tree; E2 stays open).
2. Move key creation to a **per-user Aqua app/agent** (TN3137-legal; not a root daemon; does not give Developer ID guarantee (2); same-user process can still mint its own key).
3. Something else Yahor names (not invented here).

Do **not** store a Secure Enclave `dataRepresentation` in the system keychain to imitate daemon custody. Do **not** add a privileged helper, network relay, or `com.apple.security.network.server` without explicit approval.

### D2 — Bundle id `com.darashkevich.runspecimen.holder`
Already in `apps/holder/Resources/Info.plist` and LaunchDaemon names. Docs call it **unconfirmed**; it is not D1 and is not in `production_verifier_pin()`.

Options (do not pick):
1. Accept this bundle id as the Developer ID holder identity (then pin designated requirement; stop ad-hoc `codesign --sign -` for that product).
2. Reject / rename before any notarized or installed identity is treated as canonical.

Also still blocked on Yahor (do not automate): real Touch ID / Face ID press; carry-a-package Observe → Mac; send `docs/APPLE_DTS_HOLDER_QUESTION.md`; promote prototype beyond “not an execution gate.”

---

## Ordered work

### P0 — honesty / identity (do these first)

1. **Keep installed admission fail-closed until D1.** Confirm `run_integration_complete` / `e2_closed` stay false in holder responses and docs. Do not describe a software P-256 key, pin match, or App Store signature as same-user agent bypass prevention.

2. **Do not collide with published rc14.** Head must remain unpublished `0.2.0rc15` (or later unpublished identity). Never rewrite GitHub/PyPI `0.2.0rc14` bytes. Do not upload Mac **0.1.5** while Store **0.1.4 (9)** is the submission on file.

3. **`run.py` `_human_for` must not claim hardware without signatures.** Today it sets `"hardware": True` with no `signatures` field, then holder consume fails with “cryptographic device signatures are missing.” Set `hardware` honestly (`False` unless a verified device signature is attached) and fail fast with one operator-facing message when the CLI path cannot collect exact-run / device signatures. Add a regression test.

### P1 — evidence-chain and authorization bugs (exist on base **and** still on head unless proven fixed)

4. **`policy.enforce_required_verification` `requirements_check` is too weak.** `src/runspecimen/policy.py` accepts `aggregate_outcome == "passed"` only. It does not require `authenticity == "receipt_bound"` or `final_state_certifiable is True`. Test `test_p2_required_verification_refuses_verify_without_evidence` only covers a **missing** report, and always pairs `requirements_check` with `freshness_applicable`.
   - Fix: require receipt-bound authenticity + certifiable final state (or refuse).
   - Test: policy with **only** `required_verification: ["requirements_check"]` plus a digest-valid forged `aggregate_outcome: "passed"` report must fail `verify`.

5. **MCP/adapter `freshness_check` is not read-only.** `plugins/runspecimen/README.md` calls it read-only. `runspecimen_mcp.py` / `runspecimen_adapter.py` / antigravity copy invoke `runspecimen freshness check`, which **writes** `freshness_report.json` (`cli_expansion.py`). Dashboard `check_freshness_for_run` is compute-only — keep that distinction.
   - Fix: MCP should call `freshness show` (or a non-writing evaluate) **or** rename/document the tool as mutating. Prefer a read-only MCP tool. Apply the same change to every MCP copy.
   - Test: MCP/adapter path must not create `freshness_report.json` if documented read-only.

6. **Postflight attestation vs current evidence pointer.** `postflight.py` binds any digest-valid `evidence_attestation.json` into the certificate without requiring `evidence_report_digest` == current capture pointer digest.
   - Fix: load current evidence via `load_evidence_report`; refuse or omit attestation on mismatch.
   - Test: stale attestation + newer capture must not bind the stale digest.

7. **Evidence pointer path confinement.** `load_evidence_report` joins `capture_path` onto the captures dir with no `ensure_within` / basename-only / no-`..` rule. Pointer digest can be rebound by a same-user writer.
   - Fix: accept only a basename under `evidence_captures/`; reject `..`, absolute paths, symlinks.
   - Test: pointer with `../` capture_path fails closed.

8. **Holder execute pre-spawn failure vs uncertain lease.** `execution_holder.py` writes `lease.json` `{"held": False, "child": "spawn-failed"}` on some OSError paths. Swift exact-run tests keep an **uncertain** lease on execute failure. Checklist language says execute failure keeps uncertain lease.
   - Fix: make Python holder match the documented uncertain-lease rule **or** document spawn-failed-as-release as intentional and update the checklist/tests. Do not silently diverge.
   - Test: Python integration mirroring Swift `testExecuteFailureKeepsTheUncertainLease` if the product rule is “keep uncertain.”

9. **CLI `run` + installed holder: missing signatures.** `_resolve_installed_holder` does not prompt; `_human_for` has no signatures → `_verify_device_signatures` refuses. Either wire the approved exact-run IPC (without claiming E2 closed) or fail before implying a hardware human.
   - Do not call `consumeForExecution` / `consumeEnrolled` from a run entry point unless Yahor has already authorized that as an execution gate (last QA said: not an execution gate).

### P2 — safe, in-scope cleanups (after P1)

10. **Scenes demo manifest mismatch.** `scenes.py` `_seed_mini_workspace` `pass_manifest`: provider `unittest` but `required_evidence: ["junit"]` and description says pytest. Align evidence keys with `UnittestProvider` artifacts (or change provider). Scene 1 only tests unapproved refusal today.

11. **Mac `CLIService.run` truncation.** On the evidence-expansion base, `failed = timedOut || cancelled` only; truncated stdout can still parse as success. On later tips, capture-failure axes exist — keep **service-level** tests that `runLifecycle` / `version()` fail on `timedOut`, `cancelled`, `streamReadError`, `cleanupFailed`, and truncation if that is still success-mapped.

12. **`run.py` hardware label** (if not fully closed in task 3): never set `"hardware": True` without a verified device signature.

13. **Package hash tables.** Sync `docs/CANDIDATE_MANIFEST.md` with the ledger hashes at the exact tip. One canonical table. Do not put tip hashes only in evidence notes.

14. **Docs drift on this PR’s base (still in the merge).**
    - `docs/USER_GUIDE.md` presents ADR-005 commands as matching installed `0.2.0rc14`. `docs/FAQ.md` correctly says published rc14 **lacks** them. Fix USER_GUIDE / README so published pin vs this branch/rc15 is unambiguous.
    - `apps/macos/RELEASE_CHECKLIST.md` still says successor **0.1.5 (10)**; STATUS has **(12)** and later local labels. Fix the successor line. Link `apps/macos/docs/SECURITY_BOUNDARY.md` (the `docs/SECURITY_BOUNDARY.md` path is broken).
    - `apps/macos/asc-kit/README.md` still says successor 0.1.5 (10).

15. **`requirements check` CLI `ok`.** `cli_expansion.py` sets `ok` true only when `authenticity == "receipt_bound"`, which is false until postflight. Split JSON into `checks_passed` vs `receipt_bound` and document exit codes. Do not weaken the authenticity field.

16. **`HolderStageTests` / rsync.** Linux worktree failed `HolderStageTests` with `rsync: command not found`. Skip with an explicit reason when `rsync`/`swiftc` absent, or require them only on macOS CI. Do not weaken the stage-not-installed assertions.

### Remaining features clearly in-scope for PR #39 (after P0–P2; still no D1/D2)

17. Keep single-use device/exact-run nonces (`spent.json`); missing/corrupt spent beside durable identity stays **lost**, not fresh.
18. Keep phone receipt: ignore caller `verified`; bind holder receipt; do not treat a mailbox flag as enrollment.
19. Keep uncertain-lease behavior after cancel / unseen fork / crash, consistent across Python holder and Swift coordinator.
20. Human-only harnesses stay skipped in automation (`testSecureEnclaveHumanHarnessIsNotRunByAutomation`).
21. Store vs holder: Store app stays guarantee (1); holder is a separate Developer ID product; no `network.server` in Store.

Do **not** do drive-by refactors, MCP approve tools, silent doctor sync, history rewrite, or privileged-helper/relay work.

---

## Acceptance criteria

- [ ] Working tree is PR #39 head (or a follow-up commit on `cursor/integrated-release-candidate`), not the evidence-expansion base alone.
- [ ] D1 and D2 are untouched except for clearer “blocked / unconfirmed” wording.
- [ ] Tasks 3–8 have tests that fail on the old behavior and pass on the new.
- [ ] `python3 -m unittest discover -s tests -v` : 0 failures. Record skip reasons (PyNaCl, bwrap, sandbox-exec, Darwin P-256, rsync/swiftc).
- [ ] `python3 scripts/release_check.py` on a host with `setuptools>=77` in site-packages (`PYTHONNOUSERSITE=1` safe). Engine version is **not** published rc14.
- [ ] Plugin/MCP: no `approve` / settle tool; freshness MCP matches documented read vs write.
- [ ] `verify` on `examples/showcase` still works; expansion commands remain **not** `verify`.
- [ ] macOS (when available): `swift test --package-path apps/macos` and holder Swift tests 0 failures; Store scheme does not link test-only hooks.
- [ ] Docs: published rc14 vs unpublished rc15 vs Store 0.1.4 (9) vs local Mac candidates are not conflated.
- [ ] No merge / publish / Apple submit / live daemon install.

## Verify commands

```bash
git rev-parse HEAD
git merge-base --is-ancestor d54c803c9b6dfe82cb91f55c5a21923c822041d9 HEAD && echo "base is ancestor OK"

PYTHONPATH=src python3 -m unittest discover -s tests -v
# Expect 0 failures. Paste skip list.

# Targeted regressions (add the new test names you introduce):
PYTHONPATH=src python3 -m unittest \
  tests.test_p2_p3_qa_fixes \
  tests.test_p1_evidence_blockers \
  tests.test_plugins \
  tests.test_evidence_expansion \
  tests.test_freshness_show -v

python3 scripts/release_check.py --output-dir /tmp/rs-rc-gate

# macOS only
swift test --package-path apps/macos
# holder package tests if present; do not register SMAppService

# Never
# runspecimen approve …   (human TTY only)
# codesign/install into /Applications
```

Return: exact tip SHA, test counts, file-level evidence per task, what remains unproven (human biometrics, DTS, D1/D2).
