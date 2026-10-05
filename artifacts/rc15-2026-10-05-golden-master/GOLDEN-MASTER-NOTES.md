# Engineering golden-master notes (evidence+approval slice)

Not a production biometric sign-off. Not a Store, PyPI, or notarized publish.

## SHAs

| Field | Value |
| --- | --- |
| START_SHA | `6bb64d1c6ee6798b102023652255d15830e51178` |
| Package-tree SHA | `5f35cfcf401107648d61b84e29da5a2e8b45f708` (NEW-01 + `test_new01_*` + CHANGELOG Unreleased + FAQ identity sentence) |
| Final tip SHA | `9b6a80edccc5e4ee7601ac86b9ef56eb23930def` |
| PR base | `cursor/evidence-expansion-coherence` @ `d54c803c9b6dfe82cb91f55c5a21923c822041d9` |
| Pack | `artifacts/rc15-2026-10-05-golden-master/` |

Canonical hashes: `docs/CANDIDATE_MANIFEST.md` (one table). Do not treat this file as a second source of truth.

`git diff --stat 5f35cfcf401107648d61b84e29da5a2e8b45f708..HEAD` after the pack-recording commit touches only non-sdist paths (`docs/CANDIDATE_MANIFEST.md`, `docs/BRANCH_HYGIENE.md`, this pack). `tar tzf` of the sdist has CHANGELOG, FAQ, `tests/test_new01_unittest_packaged_suite.py`, and does not contain `CANDIDATE_MANIFEST.md`, `BRANCH_HYGIENE.md`, or `SECURE_ENCLAVE_ADMISSION.md`.

## Honesty / identity

| Check | Result | Evidence |
| --- | --- | --- |
| `hardware` not claimed without verified device signatures | Pass | `src/runspecimen/run.py:135-168` refuses installed-holder CLI before consume; does not set hardware true. `tests/test_holder_socket_isolation.py` `test_named_policy_hardware_true_fails_closed` |
| Unpublished rc15+, no rc14 collision | Pass | `src/runspecimen/__init__.py:6`, `pyproject.toml:7`, `scripts/release_check.py:31` are `0.2.0rc15`. PyPI JSON latest `0.2.0rc14`; GitHub Releases have no `v0.2.0-rc.15`. Published rc14 bytes unchanged |
| `run_integration_complete` false | Pass | `docs/CANDIDATE_MANIFEST.md` Status / Executor guarantees; `docs/SECURE_ENCLAVE_ADMISSION.md:3,42`; CHANGELOG Unreleased |
| `e2_closed` false | Pass | same rows; D1 locked |
| Installed admission fail-closed | Pass | `docs/SECURE_ENCLAVE_ADMISSION.md:3,69`; `docs/HOLDER_NATIVE_BRIDGE.md:28` |
| Holder id accepted, Developer ID DR pinned | Pass | D2 2026-10-05. `docs/SECURE_ENCLAVE_ADMISSION.md:42`; `apps/holder/Resources/Info.plist:11-12` `com.darashkevich.runspecimen.holder`; `apps/holder/Scripts/build_install_holder.sh:206-223` |
| Manifest hashes match the package tree | Pass | table in `docs/CANDIDATE_MANIFEST.md`; wheel `809431ea6683a7779e13eb3cd024c7bea4ce87dc90a483c9b8aa9892fac78dae`, sdist `b2db7b78cb742ab8934368d634f46e1fde02ba4cb5c1950b2986bd3e9b080cb9`, plugin `d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6` (plugin unchanged from prior canonical table) |

## Disposition (ChatGPT re-QA at `6bb64d1`)

ChatGPT did not find F02–F09 identifiers in its records. Old IDs below are mapped only where the defect is unambiguous.

| ChatGPT ID | Status | Old ID | Evidence at tip |
| --- | --- | --- | --- |
| R-01 | CLOSED | F02 (`requirements_check`) | `src/runspecimen/policy.py:341-360`; `tests/test_p2_p3_qa_fixes.py:222` `test_requirements_check_refuses_digest_valid_forged_pass` |
| R-02 | CLOSED | F09 (`capture_path` confinement) | `src/runspecimen/requirements.py:1395-1411` `_confined_evidence_capture`; `tests/test_p1_evidence_blockers.py:589` |
| R-03 | CLOSED | F08 (stale attestation vs current pointer) | `src/runspecimen/postflight.py:206-224`; `tests/test_p1_evidence_blockers.py:627` and `:652` |
| R-04 | CLOSED | unmapped (not in F02–F09) | subprocess isolation `src/runspecimen/requirements.py:632-640,767+`; `tests/test_p1_evidence_blockers.py:364`. NEW-01 was the leftover |
| R-05 | CLOSED | unmapped (not in F02–F09) | `src/runspecimen/requirements.py:293,394`; `tests/test_p1_evidence_blockers.py:434,491` |
| R-06 | CLOSED | F05 / F07 (hardware honesty; CLI installed-holder without signatures) | `src/runspecimen/run.py:135-168` |
| NEW-01 | FIXED this pass | none (new) | `src/runspecimen/requirements.py:697-749`; `tests/test_new01_unittest_packaged_suite.py` |

## Phase 2.6 prior-P1 sweep (tip)

| Item | Status | Evidence |
| --- | --- | --- |
| MCP `freshness_check` read-only (F03) | CLOSED | `plugins/runspecimen/scripts/runspecimen_mcp.py:258-267` and adapter `:66-77` invoke `freshness evaluate`. `tests/test_plugins.py:461` `test_freshness_check_evaluates_without_writing` asserts no `freshness_report.json` |
| Scenes `pass_manifest` unittest vs artifacts | CLOSED | `src/runspecimen/scenes.py:97-113`: `provider: unittest`, `required_evidence: ["unittest_stream_sha256"]`, matches `UnittestProvider.artifacts` |
| Mac `CLIService` truncation | CLOSED | `apps/macos/Tests/RunSpecimenAppTests/CLIServiceCaptureFailureTests.swift`: truncated, timedOut, cancelled, streamReadError, cleanupFailed must not map to success |
| Lease spawn-failed vs uncertain (F06) | CLOSED | Python `src/runspecimen/execution_holder.py:2761-2782` keeps `child: uncertain` when no child exists; `tests/test_execution_holder.py:1741` `test_execute_failure_before_spawn_keeps_the_uncertain_lease` mirrors Swift `testExecuteFailureKeepsTheUncertainLease` |

No sweep item required a code fix on this pass.

## NEW-01

Bug: runner inserted live `workspace` after sandbox `top_level`, so `sys.path[0]` was the live tree. A `tests/__init__.py` suite imported live `tests`; discovery returned `outcome: error`, 0 tests, `module incorrectly imported from …/tests. Expected …/sandbox/tests`.

Fix: insert workspace first, then sandbox `top_level`, plus a `find_spec` check that the suite package origin is under `top_level`. Subprocess isolation, `_copy_unittest_suite`, symlink skip, timeout, expected-failure, and no-live-tree-write remain.

Worktree proof: tests copied onto START_SHA `6bb64d1` at `/tmp/rs-new01-start` (old `requirements.py`).

START_SHA (a)(b):

```
test_new01_packaged_suite_discovers_and_passes ... FAIL
test_new01_nested_package_imports_helpers ... FAIL
AssertionError: 'error' != 'passed'
collection_errors: ["'test_ok' module incorrectly imported from '/tmp/runspecimen-uzwyowhw/tests'. Expected '/tmp/rs-unittest-wjg320zt/sandbox/tests'. Is this module globally installed?"]
collection_errors: ["'test_nested' module incorrectly imported from '/tmp/runspecimen-iinmx8nl/tests/unit'. Expected '/tmp/rs-unittest-8yedad3j/sandbox/tests/unit'. …"]
Ran 2 tests in 0.111s
FAILED (failures=2)
```

After fix (same tests on package tree `5f35cfc`):

```
test_new01_packaged_suite_discovers_and_passes ... ok
test_new01_nested_package_imports_helpers ... ok
Ran 2 tests in 0.101s
OK
```

Full `test_new01_*` module: 6 tests, 0 fail (packaged, nested, app import, live tree packaged, live tree unpackaged, expected failure not passed).

## Tests

| Gate | Result |
| --- | --- |
| `PYTHONPATH=src python3 -m unittest discover -s tests -v` | Ran 650, 0 fail, 0 error, skipped=78. Interpreter CPython 3.12.3 |
| `tests.test_new01_unittest_packaged_suite` | 6 ran, 0 fail |
| `tests.test_p1_evidence_blockers tests.test_p2_p3_qa_fixes tests.test_plugins` | 65 ran, 0 fail, skipped=1 (pytest not installed; returncode branch covered synthetically) |
| `PYTHONNOUSERSITE=1 python3 scripts/release_check.py --output-dir /tmp/rs-gm-gate` | passed (`setuptools` 84.0.0 in `/usr/local`; smoke venv required `python3.12-venv` on this host). Copies in this pack directory |
| Swift `swift test --package-path apps/macos` | not run (no toolchain) |
| Holder Swift tests | not run (no toolchain). Never registered SMAppService, never installed |

Skip reasons on this Linux host (78): PyNaCl (29), CryptoKit signer compiler absent (21), Darwin P-256 verifier (9), Darwin phone peer (5), rsync absent (5), bwrap (3), CryptoKit verifier compiler (1), pytest (1), sandbox-exec (1), codesign/Darwin verifier macOS-only (1), codesign identity macOS-only (1), relocatable Mach-O macOS-only (1). ChatGPT’s 644/6 skip/0 fail at `6bb64d1` was Py 3.11.10 with more optional deps. This gate added 6 `test_new01_*` tests (644+6=650). CI on GitHub is a separate matrix.

## CI

Pushed to `cursor/integrated-release-candidate`. Expect 9 check names × push+PR. Status recorded on the PR after this tip is green. CI green is not biometric or holder threat-model proof.

## Human / authority residuals (unchecked)

- [ ] H1: real Touch ID / Face ID press on hardware (Yahor)
- [ ] H2: live holder daemon install / SMAppService registration on a real Mac (Yahor)
- [ ] H3: send `docs/APPLE_DTS_HOLDER_QUESTION.md` to Apple DTS (Yahor)
- [ ] H4: Developer ID signing + notarization of the holder (Yahor)
- [ ] H5: PyPI publish of the engine rc / any retag (Yahor)
- [ ] H6: App Store / TestFlight upload of Mac or iOS builds (Yahor)
- [ ] H7: merge PR #39 (Yahor, after independent retest)

E2 remains open by decision D1. `run_integration_complete` and `e2_closed` are false. This is an engineering golden master of the evidence+approval slice, not a production biometric sign-off and not a Store submission.
