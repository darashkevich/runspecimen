# Release ledger completion

QA instruction: finish the unblocked engineering in `RELEASE-BLOCKER-LEDGER-2026-10-02.md`. The frozen baseline was tip `4a6b97fba97729b658a40ffc99d48c505978e4ba` (code `4b9755b66c5e60968cf3e432dd5e907f027d8393`). That baseline is not this candidate. A pin match authenticates verifier code. It does not authenticate biometric key origin or human approval.

Code commits: `74914f9b52784509182318b5261f6747ccdf9f77` and `60ea6eea6b892b30d4d47baa021b0ad63cd8646e`. The candidate tip is the commit that adds this sentence. Its parent is `929234e409bd9187c246ee2a9e19ff5d717076e9`. On a Mac without that Developer ID identity, the extracted-verifier test signs ad-hoc and still refuses the repository fallback. The compile-stage test skips when `swiftc` is absent and does not read a machine-local interpreter path.

This note is not production sign-off. Nothing here was installed, published, merged, notarized, or submitted. No biometric prompt was run. `SecureEnclave.P256.Signing.PrivateKey` was not called. The live `/Applications` apps and holder daemon pid 42554 were not repaired, signaled, or replaced. CI green is not readiness.

## Ledger

| ID | Status | Commit | Test | Evidence |
|---|---|---|---|---|
| E1 | fixed | `74914f9b52784509182318b5261f6747ccdf9f77` | `test_installed_protection_refuses_a_software_key_when_the_pin_matches` | this file |
| E2 | fixed in source; human biometric step remains H1 | `74914f9b52784509182318b5261f6747ccdf9f77` | `test_injected_control_flow_cancel_revoke_rotate_restart_downgrade_and_race`; Swift `testCarriedPinIgnoresTheFilesSecureEnclaveLabel` | this file |
| E3 | fixed for stage and refusal; signed root-owned install remains H2/H3 | `60ea6eea6b892b30d4d47baa021b0ad63cd8646e` | `test_compiled_stage_is_adhoc_signed_and_not_installed`; `test_stage_embeds_an_interpreter_and_refuses_install` | this file |
| E4 | fixed | `74914f9b52784509182318b5261f6747ccdf9f77` | `test_dangerous_build_directories_are_not_deleted` | this file |
| E5 | qualification-not-exploit, ordering fixed in source | `74914f9b52784509182318b5261f6747ccdf9f77` | `test_pre_import_refuses_a_symlink_and_a_writable_file`; `test_secret_is_not_read_when_support_is_hostile` | this file |
| E6 | fixed for the extracted verifier path | `74914f9b52784509182318b5261f6747ccdf9f77` | `test_extracted_artifact_is_the_holder_verifier_without_repo_fallback` | this file |
| E7 | artifacts prepared; Store archive and notarization remain H3 | `74914f9b52784509182318b5261f6747ccdf9f77` | `scripts/release_check.py` | this file, `artifacts/rc15-2026-10-02-qa-py312-ledger/` |
| E8 | fixed for labeled synthetic receipts on a development GUI | `74914f9b52784509182318b5261f6747ccdf9f77` | GUI session below | this file |
| E9 | fixed as documentation; hashes stay out of the sdist | `74914f9b52784509182318b5261f6747ccdf9f77` | `docs/CHANNEL_MATRIX.md`, `docs/CANDIDATE_MANIFEST.md` | this file |
| E10 | qualification-not-exploit | `74914f9b52784509182318b5261f6747ccdf9f77` | `test_holder_state_is_not_world_readable`; existing `test_every_crash_boundary_launches_once`, `test_setsid_descendant_keeps_lease_until_tree_gone`, `test_double_fork_setsid_retains_the_lease` | this file |
| E11 | matrix written; publication comparison remains after an authorized publish | `74914f9b52784509182318b5261f6747ccdf9f77` | `docs/CHANNEL_MATRIX.md` | this file |
| D1 | blocked on a named decision: Yahor confirms the verifier identity | none; pin not written | `test_shipped_pin_is_unset_and_refuses_the_boundary` | this file |
| H1 | human gate | none | not performed | this file |
| H2 | human gate | none | not performed | this file |
| H3 | human gate | none | not performed | this file |

E1 was a reproduced defect on the baseline: a caller `boundary_double` flag was admitted under `installed_protection` when a test pin matched. This candidate refuses that path for local, companion, and dual before key comparison. Wire JSON, an environment variable, a config file, and a dict constructor argument cannot select the double. The injected `TrustedNativeBoundary` exists only as a Python object passed by a test. It is not hardware, and it is refused when installed protection is on. The unset shipped pin means the baseline defect was not a claimed live exploit.

E2 does not accept a caller hardware label. `begin_human_secure_enclave_enrollment` and Swift `beginHumanSecureEnclaveEnrollment` raise without calling Secure Enclave. `allowsProductionEnrollment` is true only for the human-step origin when a pin, a connected verifier, and installed protection are all set. It is false for the software double. Cancellation, revoke, rotate, restart, downgrade, and one-winner consume were exercised on the injected boundary with installed protection off. Edit-after-display remains the Swift carried-pin test: a file's Secure Enclave label is ignored. A person still has to perform H1.

E3 stages a unique directory, embeds a caller-supplied interpreter, and can compile the daemon and ad-hoc-sign that binary. `install`, `update`, `rollback`, and `uninstall` exit 4. `/usr/bin/python3` is not a fallback. The stage was not copied to `/Applications`. It is not root-owned and it is not notarized. The ownership file is a plan only.

E4 never deletes `HOLDER_BUILD_DIR`. The deletion mock was not invoked for `/`, the home directory, the repo, `/Applications`, a non-stage temp path, or a symlink. No destructive probe was executed.

E5 is an ordering concern, not a reproduced exploit. Import of holder runtime and the bootstrap secret now wait until the resolved path is checked. Installed multi-user proof was not run.

E6 refreshes provenance after signing. The repository verifier stays ad-hoc. A signed copy's provenance says `codesign`. The holder launch in the test resolved the verifier from the extracted directory after the repository fallback was patched to exit. The architecture check reports arm64 for the present binary. Display text is not a pin.

E7 prepared a wheel, an sdist, the unchanged plugin zip, and a separate Developer ID verifier zip. No Store archive was exported. No package was notarized or installed. Repeated 0.1.5 (13) labels are not this binary. The Store app remains guarantee (1). The Developer ID holder remains guarantee (2) and is not the Store app.

E10 did not inject a crash into daemon pid 42554, did not open a cross-user socket, and did not run as root. The mode check and the existing crash, descendant, and snapshot tests are qualification.

## Unconfirmed D1 proposal

Yahor has not confirmed this. It is not written into `production_verifier_pin()`. Confirmation must not enable the E1 software exception. The shipped pin stays unset and fails closed.

- Team: `UN6KF8636A`
- Common name already on the login keychain: `Developer ID Application: YAHOR DARASHKEVICH (UN6KF8636A)`
- Verifier identifier: `com.darashkevich.runspecimen.native-p256-verify`
- Designated requirement: `identifier "com.darashkevich.runspecimen.native-p256-verify" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ and certificate leaf[field.1.2.840.113635.100.6.1.13] /* exists */ and certificate leaf[subject.OU] = UN6KF8636A`
- Earlier signed-copy SHA-256, still the proposal: `353203f46757b1ea6c4685ba8b24633b88a6243c90fa75de240e1eab776d5b71`

A later pin change is enrolled only after the current pin accepts the new team and designated requirement. An old verifier is revoked by recording its team and requirement so later verification fails closed. A missing pin fails closed because `production_verifier_pin()` returns none. `TESTTEAMID` is a fixture. Display text is not a substitute.

This pass signed a new verifier copy without a prompt. Its bytes differ from the proposal copy. Provenance SHA-256 of that new binary is `97fd351c700054713f46641ba689a00c4030b639cc3f74bc4200d38a83fc3041`. The zip that contains it is listed below. No new identity was stored. The repository binary stays ad-hoc.

## Artifacts

Directory `artifacts/rc15-2026-10-02-qa-py312-ledger/`, built by Homebrew Python 3.12.14 in `/tmp/rs-py312-rel-holder` before the compiled-stage commit. The sdist does not contain `native_p256_verify` and does not contain these hashes.

- Wheel SHA-256: `5e2eba35a7f0ea5a61d9f97d86e071922b77ea2fa4b1b5c22d97444113c17dd6`
- Sdist SHA-256: `6e6742d17b4aba2e20cc9ed061898c2b4a8aa53ea0aa29b7b0a573d16ce2a6f7`
- Plugin zip SHA-256: `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`
- Developer ID verifier zip SHA-256: `a8f760a9a8d1aabc6b7b8ddbcf7c333bbe352b7e2cd52e01d1e89aaf899c6e10`

`release_check` reported 570 tests, 35 skipped, then a 4-test follow-up, exit 0. Skips: bubblewrap not installed (3), PyNaCl not installed (29), pytest not installed (1), Linux `ldd` checks (2). Apple `/usr/bin/python3` was not used to freeze. After that, `test_compiled_stage_is_adhoc_signed_and_not_installed` passed on its own. The full suite was not repeated after that one test was added.

Those ledger-directory hashes were built at `74914f9b52784509182318b5261f6747ccdf9f77`. After that commit, the files packed into the sdist that changed are `tests/test_production_boundary.py` and `tests/test_release_ledger.py`. `docs/CANDIDATE_MANIFEST.md` also changed, and it is not in the sdist. `src` and the plugin inputs did not change. A later `release_check` of the tip, same Homebrew Python 3.12.14 venv, wrote `artifacts/rc15-2026-10-02-qa-py312-tip/` and did not replace the ledger directory.

- Wheel SHA-256, unchanged: `5e2eba35a7f0ea5a61d9f97d86e071922b77ea2fa4b1b5c22d97444113c17dd6`
- Sdist SHA-256, this tip: `57214358c27f99b2f4dcf40fbcd53c2efb97f1f8b78e9e79ebd34afa1bb02ce2`
- Plugin zip SHA-256, unchanged: `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`

That run reported 571 tests, 35 skipped, then the same 4-test follow-up, exit 0. The extra test is the compiled holder stage, which ran here because `swiftc` is present. The skip reasons are the same. The sdist hash above is not inside a file packed into that sdist.

## GUI

Built from `74914f9b52784509182318b5261f6747ccdf9f77` into `/tmp/rs-qa-ledger-derived`. The following commit does not change the Mac app sources. Signature: Sign to Run Locally (ad-hoc). Sandbox on. `com.apple.security.network.client` present. `com.apple.security.network.server` absent. `get-task-allow` absent. The bundle has no holder. This is not holder acceptance.

Executable SHA-256: `b27d7d4d6553dec582cc9486ec73f4376ba82e439dd91315351e1540a9f30a7e`

Labeled synthetic certificates, not a live run, were planted for `reviewer-demo/run-001` and `reviewer-demo/run-000`. Digest returned `certificate_id` `labeled-synthetic-reviewer-demo-run-001`. Live compare status was `match` for `outputs/labeled-synthetic.txt`. Diff reported `identical: false` with changed `exit_code` 0 versus 1 and `run_result` ok versus failed. Retain cancel left `/tmp/rs-qa-retain-ledger` empty. Retain confirm wrote `state.json`, `events.jsonl`, `approval.json`, `certificate.json`, and `manifest.json` (`kind` `retained_incident_bundle`, created `2026-10-02T15:04:24Z`, manifest SHA-256 `5d693e3f0f47ef3c516106258b4c821fce5bef2b788379d315eb8da8cd5a3c15`).

The window was resized to 900 by 700. Opening `/tmp/rs-qa-ledger-other-ws` (a truncated contract) disabled digest and showed "Select a contract with a campaign and a run." Opening the reviewer demo again restored the labeled digest. The specific stale-confirmation sentence was not observed because the workflow sheet closed during the switch. Large-output cancellation was not driven. Human approval was not performed.

Only QA pid 37395 was killed. The container `~/Library/Containers/com.darashkevich.runspecimen` was restored from a backup taken before the synthetic certificates. `/Applications/RunSpecimen.app` mtime stayed `2026-09-26 13:56:03`. `/Applications/RunSpecimen Holder.app` mtime stayed `2026-09-30 15:19:13`. Daemon pid 42554 was still alive.

## Human checklist

1. Confirm or reject the D1 identity above. Do not treat a pin match as biometric origin.
2. On a provenance-identified build, enroll, sign, cancel, rotate, and revoke with a real biometric prompt (H1).
3. Authorize a root-owned holder install, then run one bounded local, companion, and dual command and reject a replay (H2). Leave the approved Store app in place.
4. Export the Store archive for this SHA and notarize the Developer ID holder (H3). Historical 0.1.4 (9) does not qualify this SHA.
5. Retest this candidate tip independently. Do not reuse the 4a6b97f GUI or the September 30 archives.
