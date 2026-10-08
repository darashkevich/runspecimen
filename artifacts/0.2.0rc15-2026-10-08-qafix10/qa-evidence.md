# QA evidence — unpublished 0.2.0rc15 qafix10

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-08-qafix10/`
Engine source: PR #63 head that records this pack (not a self-referencing SHA).
`src/` tree: `f83d15df2394c93f6aa5c4f94508fc7f03a2befd`
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`
Engine/docs commit: `f4a226739217d54d536d7452675924f17db5f427`

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `89e4e3fd8e9012f9b71fe43dc201e95eb9861081e877459846df7d472f49a18a` |
| `runspecimen-0.2.0rc15.tar.gz` | `d2c9239cd1a9b703c3070d5780f99ca7b848c6522fe4f628c75f6603c5be38e6` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged; does not embed the wheel) |
| `release-report.json` | `a9c981fd873f0034292fe4c59276c7cf61557e6f81d9908dc09748f959592652` |

Toolchain: CPython 3.12.3, venv `/tmp/rs-relprep-qafix5` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two rebuilds (`/tmp/rs-qafix10-c` and `/tmp/rs-qafix10-d`) were byte-identical (`cmp`)
for wheel, sdist, plugin zip, `release-report.json`, and `SHA256SUMS`.
Copied into an absent directory (retain_artifacts refuses a non-empty dest).
Prior packs, including qafix9 and earlier, were not overwritten.

This pack folds the four remaining P3 copy fixes (about JSON honesty, USER_GUIDE
showcase order, receipt schema 2 in the compatibility matrix, and the
append-one-event honesty wording). BH-01..06 and QA-HOOKS-01..03 stay closed.
qafix9 remains the approval-binding pack.

## What is trusted now and why venv RECORD is not trusted

Unchanged from qafix8/qafix9. The verifier trusts **only the Python interpreter
and its stdlib**. Venv-local metadata is not trust. See
`artifacts/0.2.0rc15-2026-10-08-qafix9/qa-evidence.md`.

## 1. Full skip list from local `release_check.py`

Command: `/tmp/rs-relprep-qafix5/bin/python scripts/release_check.py --output-dir /tmp/rs-qafix10-c`
Result: **759 tests, skipped=78, 0 failed**, then 4/4 distribution tests, exit 0.
Unittest wall time: **175.486s** (cap 600s). Second rebuild: 759 tests, skipped=78,
173.876s, then 4/4, exit 0. Skip list is unchanged from qafix9.

`src/` changed (about JSON honesty wording), so **wheel `89e4e3fd…` is new**.
Plugin `ea38d5bc…` is unchanged. Sdist rebuilt to `d2c9239c…` after packed
docs/tests/CHANGELOG updates. Test count rose from 752 to 759 because this
pass adds P3 copy pins (`tests/test_qafix10_p3.py` and extra methods).

### Why ~78 here vs ChatGPT's earlier 6

Same as qafix9: this cloud-agent pack run is **Linux** without PyNaCl, CryptoKit,
Darwin verifier, codesign, sandbox-exec, Mach-O fixtures, rsync holder-stage copy,
or bubblewrap in the pack venv. Those tests skip rather than fail. They are
**not** counted as passes.

Skip lines below are the 78 unittest `... skipped` results from the pack log.

### missing optional dependency or OS facility (77)

| Test | Reason |
| --- | --- |
| `test_bwrap_linux.BwrapLinuxIntegrationTests.test_outside_write_is_blocked_and_not_certified` | bwrap is not installed; real confinement spawn skipped |
| `test_bwrap_linux.BwrapLinuxNetworkAndWriteTests.test_network_is_denied_at_runtime` | bwrap is not installed; real confinement spawn skipped |
| `test_bwrap_linux.BwrapLinuxNetworkAndWriteTests.test_workspace_write_still_succeeds_and_is_certified` | bwrap is not installed; real confinement spawn skipped |
| `test_ed25519.TestEd25519CrashSafeRotation.test_sigkill_at_each_fresh_create_phase_leaves_no_half_pair` | PyNaCl not installed |
| `test_ed25519.TestEd25519CrashSafeRotation.test_sigkill_at_each_rotation_phase_recovers_working_pair` | PyNaCl not installed |
| `Forged receipt: attacker embeds their own key — must not be ok/trusted.` | PyNaCl not installed; pip install 'runspecimen[ed25519]' |
| `test_ed25519.TestEd25519Crypto.test_forged_receipt_fails_against_victim_trust_anchor` | PyNaCl not installed; pip install 'runspecimen[ed25519]' |
| `test_ed25519.TestEd25519Crypto.test_hmac_blob_rejected_by_ed25519_path` | PyNaCl not installed; pip install 'runspecimen[ed25519]' |
| `test_ed25519.TestEd25519Crypto.test_sign_verify_roundtrip_and_wrong_key` | PyNaCl not installed; pip install 'runspecimen[ed25519]' |
| `test_ed25519.TestEd25519Crypto.test_tamper_fails` | PyNaCl not installed; pip install 'runspecimen[ed25519]' |
| `test_ed25519.TestEd25519JournalPathTrust.test_foreign_key_journal_and_sidecar_names_are_rejected` | PyNaCl not installed |
| `Forged fresh_priv_installed must not delete an already-complete live pair.` | PyNaCl not installed |
| `test_ed25519.TestEd25519JournalPathTrust.test_forged_journal_does_not_touch_outside_victim` | PyNaCl not installed |
| `test_ed25519.TestEd25519JournalPathTrust.test_malformed_journal_is_discarded_without_deleting_live_keys` | PyNaCl not installed |
| `test_ed25519.TestEd25519JournalPathTrust.test_relative_traversal_sidecar_is_rejected` | PyNaCl not installed |
| `test_ed25519.TestEd25519JournalPathTrust.test_symlink_sidecar_journal_is_rejected` | PyNaCl not installed |
| `test_ed25519.TestEd25519KeyDirConcurrency.test_cross_process_concurrent_creates_of_distinct_keys` | PyNaCl not installed |
| `test_ed25519.TestEd25519KeyDirConcurrency.test_cross_process_rotation_and_load_stay_consistent` | PyNaCl not installed |
| `test_ed25519.TestEd25519KeyDirConcurrency.test_nonblocking_lock_rejects_second_process` | PyNaCl not installed |
| `test_ed25519.TestEd25519Persistence.test_export_public_key_does_not_read_private_seed` | PyNaCl not installed |
| `Private must not be removed if installing the new public path fails.` | PyNaCl not installed |
| `If public staging fails, the previous private+public pair must still load.` | PyNaCl not installed |
| `If new private install fails after new public is in place, restore old pair.` | PyNaCl not installed |
| `test_ed25519.TestEd25519Persistence.test_private_key_created_with_0600_not_chmod_after` | PyNaCl not installed |
| `test_ed25519.TestEd25519Persistence.test_public_key_file_load_refuses_symlink` | PyNaCl not installed |
| `test_ed25519.TestEd25519Persistence.test_refuse_overwrite_without_flag` | PyNaCl not installed |
| `test_ed25519.TestEd25519Persistence.test_refuse_symlink_private_key_on_load` | PyNaCl not installed |
| `test_ed25519.TestEd25519Persistence.test_refuse_symlink_private_key_path_on_save` | PyNaCl not installed |
| `test_ed25519.TestEd25519Persistence.test_refuse_symlink_public_key_on_load` | PyNaCl not installed |
| `test_ed25519.TestEd25519Persistence.test_rotate_overwrite_replaces_pair` | PyNaCl not installed |
| `test_ed25519.TestEd25519Persistence.test_save_load_and_list` | PyNaCl not installed |
| `TOCTOU: path must be opened O_NOFOLLOW; fd fstat must reject link swaps.` | PyNaCl not installed |
| `CryptoKit can verify a signature. That signature is not a Secure Enclave.` | CryptoKit verifier compiler is absent |
| `test_isolated_native_enrollment.IsolatedEnrollmentTests.test_local_companion_and_dual_isolated_execute` | CryptoKit signer compiler is absent |
| `test_native_bridge_policies.LabeledBridgePolicyTests.test_cancel_revoke_replay_rotation_binding_restart_and_concurrency` | CryptoKit signer compiler is absent |
| `test_native_bridge_policies.LabeledBridgePolicyTests.test_concurrent_consume_of_one_nonce_fails_closed` | CryptoKit signer compiler is absent |
| `test_native_bridge_policies.LabeledBridgePolicyTests.test_local_companion_and_dual_execute_and_are_not_hardware` | CryptoKit signer compiler is absent |
| `test_phases.SeatbeltIntegrationTests.test_write_outside_workspace_fails` | sandbox-exec is not installed |
| `test_production_boundary.CleanPackageTests.test_extracted_artifact_is_the_holder_verifier_without_repo_fallback` | codesign and the Darwin verifier are macOS-only |
| `test_production_boundary.HumanNativeSignerTests.test_injected_signer_cancel_revoke_rotate_restart_downgrade_and_race` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanNativeSignerTests.test_injected_signer_enrolls_pairs_and_executes` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanNativeSignerTests.test_installed_protection_refuses_the_injected_signer_when_the_pin_matches` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_adapter_cancel_revoke_rotate_restart_downgrade_and_race` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_adapter_enrolls_pairs_and_executes_for_local_companion_and_dual` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_concurrent_consume_of_a_custody_signature` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_exact_run_companion_and_dual_require_the_phone_key` | P-256 verification uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_exact_run_expiry_and_generation_do_not_reach_the_lease` | P-256 verification uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_exact_run_signature_authorizes_one_nonce_and_refuses_software` | P-256 verification uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_exact_run_uncertain_lease_is_not_released_or_replayed` | P-256 verification uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_injected_signer_cancel_revoke_rotate_restart_downgrade_and_race` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_injected_signer_enrolls_pairs_and_executes` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_installed_protection_refuses_the_adapter_origin_string` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_installed_protection_refuses_the_injected_signer_when_the_pin_matches` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_local_ipc_enrollment_reloads_and_runs` | P-256 verification uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_observe_transport_challenge_bytes_match` | phone peer comparison uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_observe_transport_software_double_is_refused_when_the_pin_matches` | phone peer comparison uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_observe_transport_wrong_key_is_refused` | phone peer comparison uses the Darwin verifier |
| `The mock replaces the OS call. It does not call SecureEnclave.P256.Signing.PrivateKey.` | phone peer comparison uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_phone_ipc_rejects_wrong_key_and_installed_software_double` | P-256 verification uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_phone_peer_comparison_enrolls_companion` | phone peer comparison uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_phone_receipt_refuses_revoked_keys_and_fingerprint_mismatch` | P-256 verification uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_phone_receipt_rejects_forged_flags_wrong_key_replay_and_stale` | P-256 verification uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_published_mailbox_signature_is_verified_and_consumed` | P-256 verification uses the Darwin verifier |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_session_custody_signs_after_holder_reload` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_software_signer_is_not_the_native_adapter` | CryptoKit signer compiler is absent |
| `test_production_boundary.HumanOperatedNativeAdapterTests.test_user_invoked_enrollment_cancel_rotation_and_revocation` | CryptoKit signer compiler is absent |
| `test_production_boundary.ProductionBoundaryTests.test_adhoc_repository_verifier_does_not_meet_the_confirmed_pin` | codesign identity is macOS-only |
| `test_production_boundary.ProductionBoundaryTests.test_injected_boundary_exercises_local_companion_and_dual` | CryptoKit signer compiler is absent |
| `test_production_boundary.ProductionBoundaryTests.test_injected_control_flow_cancel_revoke_rotate_restart_downgrade_and_race` | CryptoKit signer compiler is absent |
| `test_production_boundary.ProductionBoundaryTests.test_installed_protection_refuses_a_software_key_when_the_pin_matches` | CryptoKit signer compiler is absent |
| `test_production_boundary.ProductionBoundaryTests.test_replay_stays_refused_on_the_boundary_path` | CryptoKit signer compiler is absent |
| `test_release_ledger.HolderStageTests.test_compiled_package_relocates_runtime_without_a_developer_interpreter` | rsync is absent; holder stage was not copied and install assertions were not weakened |
| `test_release_ledger.HolderStageTests.test_compiled_stage_is_adhoc_signed_and_not_installed` | rsync is absent; holder stage was not copied and install assertions were not weakened |
| `test_release_ledger.HolderStageTests.test_detached_interpreter_is_not_executed` | rsync is absent; holder stage was not copied and install assertions were not weakened |
| `test_release_ledger.HolderStageTests.test_fixture_lifecycle_stays_in_a_temp_root` | rsync is absent; holder stage was not copied and install assertions were not weakened |
| `test_release_ledger.HolderStageTests.test_relocatable_executable_path_closure_is_copied` | relocatable Mach-O fixture is macOS-only |
| `test_release_ledger.HolderStageTests.test_stage_embeds_an_interpreter_and_refuses_install` | rsync is absent; holder stage was not copied and install assertions were not weakened |

### previously outside discovery scope (1)

| Test | Reason |
| --- | --- |
| `test_p1_evidence_blockers.P1EvidenceBlockersTests.test_p1_pytest_nonzero_returncode_not_passed` | pytest not installed; returncode branch covered synthetically |

### other (0)

| Test | Reason |
| --- | --- |


## 2. Darwin 3.11 unittest timings

Local pack unittest discover: **175.486s** vs 600s cap (second rebuild 173.876s).
Report Darwin 3.11 timings from the unittest line `Ran N tests in X s` in the
CI logs, **not** the GitHub Actions job wall clock. CI `Ran … in X s` numbers
for **both macOS 3.11 jobs** (push + PR) are recorded in the PR #63 body /
final report after the pack-commit CI is terminal. They are not guessed here.
Packed `release_check.py` timeout is 600s; the `release-check` job is
`timeout-minutes: 20`.

## 3. The four P3s (this pack)

Independent re-QA of `4b35ac7` was SHIP-CANDIDATE: BH-01..06 and
QA-HOOKS-01..03 closed. These four P3s were the remaining open copy items.

| P3 | Change | Outcome |
| --- | --- | --- |
| about JSON | `runspecimen about` summary now says plugins/agents cannot approve **through the app**, plus the fake-approval honesty sentence. Default JSON for every other command stays byte-exact vs qafix4 / 5565000 (N10 and unknown-field included). | `test_about_default_json_uses_through_the_app_honesty` ok; `test_default_json_matches_qafix4_5565000_for_covered_commands` ok |
| USER_GUIDE showcase | Showcase section leads with `scripts/refresh_showcase.py`, matching README. | `test_user_guide_showcase_leads_with_refresh_script` ok |
| schema matrix | `docs/SCHEMA_COMPATIBILITY.md` compatibility matrix lists receipt `schema_version: 2` as current; schema 1 still parses then fails closed without a bound approval. | `test_compatibility_matrix_lists_receipt_schema_2` ok |
| honesty | Replaced “rewrite the whole record / entire event log” with: a program running as you that can edit RunSpecimen's files can still add a fake approval to the record. To protect against that, sign receipts with a key the agent can't access. | `test_qafix10_p3` honesty pins ok |

N10 `execution policy local has no typed-phrase fallback` and the unknown-field
refusal stay byte-exact vs qafix4.

## 4. Exact list of changed user-facing copy lines

Honesty sentence used consistently (sentence-case may follow a colon):
`A program running as you that can edit RunSpecimen's files can still add a fake approval to the record. To protect against that, sign receipts with a key the agent can't access.`

| File | Old → new |
| --- | --- |
| `src/runspecimen/cli.py` `_ABOUT_SUMMARY` | `Plugins/agents cannot approve.` → `Plugins/agents cannot approve through the app.` plus the honesty sentence. Dashboard clause `it cannot approve or execute.` → `it cannot approve or execute through the app.` |
| `src/runspecimen/present.py` planted-approval hint | `A program that rewrites the whole record still needs a signature from a key the agent cannot access.` → honesty sentence |
| `src/runspecimen/present.py` unbound-receipt hint | `For protection against a program that rewrites the whole record, sign receipts with a key the agent cannot access.` → honesty sentence |
| `README.md` dashboard honesty | `; for protection against a program that rewrites the whole record, …` → period + honesty sentence |
| `docs/FAQ.md` “Can agents approve?” | same rewrite as README |
| `docs/FAQ.md` “Is the hash chain a signature?” | `a same-user process that rewrites the entire event log consistently can still forge a receipt. Only a signing key the agent can't read … closes that.` → honesty sentence + the same `verify-signature` / holder close |
| `docs/THREAT_MODEL.md` trusted-boundary honesty | same rewrite as README |
| `docs/THREAT_MODEL.md` receipt authentication | `A same-user process that rewrites the whole log can still forge a receipt.` → honesty sentence |
| `docs/ABOUT.md` dashboard | `sign receipts with a key the agent can't access if you need protection against a full record rewrite.` → honesty sentence |
| `docs/USER_GUIDE.md` what-it-is | `for protection against a program that rewrites the whole record, …` → honesty sentence |
| `docs/USER_GUIDE.md` Showcase refresh | verify-first block → `python3 scripts/refresh_showcase.py` then `runspecimen verify …` (README order) |
| `docs/SCHEMA_COMPATIBILITY.md` matrix | added row: `0.2.0rc15 approval binding` / `schema_version: 2` (current). Schema `1` and legacy still parse, then fail closed without a bound approval. |
| `CHANGELOG.md` Unreleased | four P3 bullets; BH-01/docs-honesty lines use the new sentence; historical `Plugins still cannot approve, settle, or refuse.` → `… through the app`; historical dashboard `it cannot approve or execute commands` → `… through the app` |
| `docs/RELEASE_CANDIDATE_REPORT.md` | pack path `qafix9` → `qafix10` (no archive hashes) |

## 5. Controls whose outcomes did not change (BH / QA-HOOKS)

Approval binding, pretty-run nonzero, unknown certificate fields, leftover
setuptools pth, file+RECORD tamper, and clean sheet venv outcomes are unchanged
from qafix9. Holder-policy N10 matrix matches qafix4.

`test_holder_policy_allow_refuse_matrix_matches_qafix4` **ok**.
`test_default_json_matches_qafix4_5565000_for_covered_commands` **ok** (about
removed from that byte-exact set; covered by the dedicated about test).

## 6. Guardrail checks

| Gate | State |
| --- | --- |
| `run_integration_complete` | false (source + tests; not flipped) |
| `e2_closed` | false (source + tests; not flipped) |
| D1 installed admission | fail-closed |
| D2 `production_verifier_pin()` | unchanged; holder id is not that pin |
| APPROVE phrase | not typed |
| `--human-invoked` | not used |
| merge / publish / retag / notarize / real-machine install | not done |
| entitlement changes | none |
| older packs | not overwritten (qafix9 and earlier stay on disk) |
| `apps/` / `packaging/` | not touched |
| `src/` | changed (about JSON honesty); wheel hash moved |

## QA4 named tests (pretty / sheet)

Same named tests **ok** as qafix9 (`test_pretty_*`, HUMAN-ACCEPTANCE bash/zsh
sheet, `rs_neg` complete line). Zsh sheet job: **every GitHub Actions
`release-check` matrix cell**.
