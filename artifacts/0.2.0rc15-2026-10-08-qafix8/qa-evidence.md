# QA evidence — unpublished 0.2.0rc15 qafix8

This file is not packed into the sdist (`artifacts/` is excluded).
It is not a production sign-off. It does not authorize a merge, tag,
notarization, install, or upload. Version stays unpublished `0.2.0rc15`.

Pack: `artifacts/0.2.0rc15-2026-10-08-qafix8/`
Engine source: PR #63 head that records this pack (not a self-referencing SHA).
`src/` tree: `3b20ad6b179baab582ec97285dd7899f09f11574`
Base lineage: `8015b6d8017e5566f7558cc916dc0ee470c653ad`
Engine/docs commit: `46111309f46af37bf8e840f7099836d0c70981c8`

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `68d5a98b5bc26b0afe14982bf77c39212707629a1f3befed327e34bd53021951` |
| `runspecimen-0.2.0rc15.tar.gz` | `29347132909012cb8aab4be0f21653702e2e1ec5c9acd9bf014bc100f82afced` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` (unchanged; does not embed the wheel) |
| `release-report.json` | `f46852fe024e1e532d0b83e3639edf936f6b981e367a82868dbe4d12bf3b1185` |

Toolchain: CPython 3.12.3, venv `/tmp/rs-relprep-qafix5` (setuptools 84.0.0, wheel 0.48.0).
`SOURCE_DATE_EPOCH` 1577836800 as in `scripts/release_check.py`.
Two rebuilds (`/tmp/rs-qafix8-a` and `/tmp/rs-qafix8-b`) were byte-identical (`cmp`)
for wheel, sdist, plugin zip, `release-report.json`, and `SHA256SUMS`.
Copied into an absent directory (retain_artifacts refuses a non-empty dest).
Prior packs, including qafix7 and earlier, were not overwritten.

## What is trusted now and why venv RECORD is not trusted

The verifier trusts **only the Python interpreter and its stdlib**. It does
not claim to resist someone replacing Python itself. Venv-local metadata is
not trust: setuptools RECORD does not hash itself (`RECORD,,`) and is writable
by the same attacker who can replace `_distutils_hack/__init__.py` and rewrite
the matching RECORD line. That is QA-HOOKS-03. The previous DistutilsMetaFinder
RECORD allowlist and `_virtualenv` pins are gone.

A stdlib finder is identified by its **class living in a stdlib module whose
realpath is under the interpreter's stdlib dir**, not by name. Frozen and
built-in modules count as the interpreter.

In the **target venv** the verifier REJECTS:

- any `.pth` file with an executable (`import`) line, whatever its name or
  owner (including setuptools' `distutils-precedence.pth`)
- any sitecustomize or usercustomize that is importable from the venv
  (venv-prefix sitecustomize is extra startup; distro/stdlib sitecustomize
  under the interpreter is trusted interpreter, not venv extra)
- any non-stdlib `sys.meta_path` or `sys.path_hooks` entry present after startup
- any `_virtualenv*`

Rejection message (plain English): `This environment runs extra startup code we
can't vouch for (file: …). Create a fresh one by following the acceptance sheet.`

### Acceptance-sheet setup lines (exact)

After creating the venv and before installing the wheel:

```
python3 -m venv "$VENV"
rs_ok N1-venv $?
```

```
"$PY" -m pip uninstall -y setuptools
rs_ok N1-setuptools $?
```

That removes `distutils-precedence.pth` and the `_distutils_hack` shim.
Python 3.12+ venvs do not ship setuptools; the uninstall is then a no-op and
still prints `STEP N1-setuptools exit=0`. HUMAN-ACCEPTANCE markdown-block
execution (bash and zsh) includes those lines.

## 1. Full skip list from local `release_check.py`

Command: `/tmp/rs-relprep-qafix5/bin/python scripts/release_check.py --output-dir /tmp/rs-qafix8-a`
Result: **738 tests, skipped=78, 0 failed**, then 4/4 distribution tests, exit 0.
Unittest wall time: **158.991s** (cap 600s). Second rebuild: 738 tests, skipped=78,
160.586s, then 4/4, exit 0. Skip list is unchanged from qafix7.

`src/` was not edited; **wheel `68d5a98b…` and plugin `ea38d5bc…` are
unchanged**. Sdist rebuilt to `29347132…` (scripts + tests + CHANGELOG).

### Why ~78 here vs ChatGPT's earlier 6

ChatGPT's ~6-skip recording was a Darwin host with PyNaCl present, so Linux-only
and Darwin-facility tests mostly ran. This cloud-agent pack run is **Linux**
without PyNaCl, CryptoKit, Darwin verifier, codesign, sandbox-exec, Mach-O
fixtures, rsync holder-stage copy, or bubblewrap in the pack venv. Those tests
skip rather than fail. They are **not** counted as passes. Coverage that is
release-relevant runs on other jobs:

- PyNaCl / Ed25519: dedicated CI job `ed25519` (`python -m unittest tests.test_ed25519 -v` with `.[ed25519]`).
- CryptoKit / P-256 / phone peer / codesign / sandbox-exec / Mach-O / holder stage: Darwin `release-check` jobs (`macos-latest` / Python 3.11 and 3.14).
- bubblewrap confinement: Linux `release-check` jobs install `bubblewrap` via apt.
- HUMAN-ACCEPTANCE zsh sheet: **every `release-check` job**. Linux apt-get installs `zsh`; macOS already has zsh. `_require_zsh()` raises (does not skip) if zsh is missing. Local pack run: `test_human_acceptance_sheet_n1_n7_n10_unk_in_bash` ok, `…_in_zsh` ok.
- pytest missing: `test_p1_pytest_nonzero_returncode_not_passed` is skipped here; the returncode branch is covered synthetically in the same module.

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

Local pack unittest discover: **158.991s** vs 600s cap (second rebuild 160.586s).
Report Darwin 3.11 timings from the unittest line `Ran N tests in X s` in the
CI logs, **not** the GitHub Actions job wall clock. The reviewer measured
~419s and ~408s from actual logs on `2abc287`, not the 565/560s job times.
CI `Ran … in X s` numbers for **both macOS 3.11 jobs** (push + PR) are recorded
in the PR #63 body / final report after the pack-commit CI is terminal.
They are not guessed here. Packed `release_check.py` timeout is 600s;
the `release-check` job is `timeout-minutes: 20`.
A third unpacked-docs commit is not required for timings.

## 3. Controls whose outcomes changed (QA-HOOKS-03)

These two controls previously **accepted** leftover setuptools because of the
removed DistutilsMetaFinder / RECORD / known-safe-pth allowlists. They now
**reject**. Skip is not a pass. Clean acceptance is the sheet-prepared venv.

| Control | Previous outcome (qafix7) | New outcome (qafix8) | Why |
| --- | --- | --- | --- |
| `test_qa4_distutils_metafinder_is_not_treated_as_a_hijack` | accept real setuptools DistutilsMetaFinder when class identity + RECORD matched | leftover `distutils-precedence.pth` / `_distutils_hack` is refused | venv RECORD is attacker-controlled (`RECORD,,`); no RECORD-based shim trust |
| `test_qa_hooks_01_clean_stdlib_venv_with_real_setuptools_shim_is_accepted` | accept a stdlib venv that still had the real setuptools shim | leftover setuptools shim is refused; clean path is `test_qa_hooks_03_clean_sheet_venv_is_accepted` | any executable `.pth` import in the target venv is extra startup |

Every other existing control keeps its previous outcome (still refuse hijacks;
still accept a clean sheet venv). New regressions:

| Test | Outcome |
| --- | --- |
| `test_qa_hooks_03_leftover_setuptools_pth_is_rejected` | ok — leftover `distutils-precedence.pth` refuses with the sheet message |
| `test_qa_hooks_03_clean_sheet_venv_is_accepted` | ok — venv prepared per the sheet (`pip uninstall -y setuptools` then wheel) is `ok:true` |
| `test_qa_hooks_03_file_and_record_tamper_class_find_spec_is_rejected` | ok — reviewer file+RECORD tamper (class `find_spec`) refuses |
| `test_qa_hooks_03_file_and_record_tamper_instance_find_spec_is_rejected` | ok — reviewer file+RECORD tamper (instance `find_spec`) refuses |

## 4. QA3/QA4 + remaining QA-HOOKS controls (unchanged outcomes)

All named tests **ok** on the pack `release_check.py` run (Linux / CPython 3.12.3).
Skip is not a pass.

| Test | Outcome |
| --- | --- |
| `test_qa3_01_env_shebang_is_refused` | ok — env shebang is `UnsupportedShebangError` |
| `test_qa3_02_sitecustomize_approve_preload_is_refused` | ok — sitecustomize under the venv is refused |
| `test_qa3_03_sheet_n3_failure_stops_later_steps` | ok — bash and zsh; missing launcher never reaches a later STEP |
| `test_qa3_control_matrix_named_outcomes` | ok — shebang, origins, pth prepend, startup hooks, sheet stop |
| `test_qa4_lazy_import_after_verification_is_bound` | ok — remaining `runspecimen.*` modules imported after the first bind; origins stay under the verified package dir |
| `test_qa4_meta_path_finder_via_startup_hook_is_rejected` | ok — `_virtualenv.pth` plus a custom `sys.meta_path` finder is refused |
| `test_qa_hooks_01_spoofed_distutils_metafinder_via_virtualenv_is_rejected` | ok — reviewer spoof (`import _virtualenv` + fake DistutilsMetaFinder + old signing.py + spoofed `__file__`) refuses |
| `test_qa_hooks_01_fake_named_finder_via_sitecustomize_is_rejected` | ok — fake DistutilsMetaFinder added by sitecustomize refuses |
| `test_qa_hooks_02_virtualenv_pth_and_module_are_rejected` | ok — standard `_virtualenv.pth` / `_virtualenv.py` refused |
| `test_known_safe_pth_does_not_trust_import_virtualenv` | ok — `KNOWN_SAFE_PTH_IMPORT_LINES` is gone; `import _virtualenv` is still refused |

Provenance lives in `scripts/verify_installed_wheel.py`. After hashing RECORD
members it `pkgutil.walk_packages` remaining `runspecimen.*` modules and binds
each origin. Finders on `sys.meta_path` are allowed only when the finder's
class lives in a stdlib module whose realpath is under the interpreter stdlib
dir (frozen/built-in count as interpreter). BuiltinImporter and FrozenImporter
sit on `meta_path` as classes. There is no DistutilsMetaFinder RECORD allowlist.

## 5. Holder-policy refusal matrix (qafix4 / 5565000 vs this tree)

`test_holder_policy_allow_refuse_matrix_matches_qafix4` **ok**.
`test_default_json_matches_qafix4_5565000_for_covered_commands` **ok**.

Piped `approve` on qafix4 wheel `bd9e6520160b103b96e71762e562b9b8a8f8798e15cb36b200de038c490d46c4`
vs a wheel built from this tree: identical exit codes and first `RunSpecimen error:` line.

| Policy | Outcome (before and after) | Frozen first error line |
| --- | --- | --- |
| (none / typed-phrase) | refuse (no TTY) | interactive tty (unchanged wording) |
| `local` | refuse | `RunSpecimen error: execution policy local has no typed-phrase fallback` |
| `companion` | refuse | `RunSpecimen error: execution policy companion has no typed-phrase fallback` |
| `dual` | refuse | `RunSpecimen error: execution policy dual has no typed-phrase fallback` |

N10 sentence is frozen. Default JSON stdout for the covered commands is byte-identical
to 5565000 / qafix4. `--pretty` keeps the same exit codes; pretty is opt-in.

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
| older packs | not overwritten |
| `apps/` / `packaging/` / `src/` | not touched |

## QA4 named tests (pretty / sheet)

| Test | Outcome |
| --- | --- |
| `test_pretty_holder_policy_hint_does_not_say_use_the_holder` | ok |
| `test_pretty_verify_incomplete_payload_is_not_success` | ok |
| `test_pretty_verify_ok_false_is_not_success` | ok |
| `test_pretty_verify_non_boolean_ok_is_not_success` | ok |
| `test_pretty_verify_tampered_workspace_fails_nonzero` | ok |
| `test_pretty_never_defaults_ok_to_true_in_source` | ok |
| `test_human_acceptance_sheet_n1_n7_n10_unk_in_bash` | ok |
| `test_human_acceptance_sheet_n1_n7_n10_unk_in_zsh` | ok |
| `test_human_acceptance_rs_neg_requires_complete_line` | ok |

Zsh sheet job: **every GitHub Actions `release-check` matrix cell**, including
`release-check (macos-latest, 3.11)` which has zsh by default, and all Linux
cells after `sudo apt-get install -y bubblewrap zsh`.
