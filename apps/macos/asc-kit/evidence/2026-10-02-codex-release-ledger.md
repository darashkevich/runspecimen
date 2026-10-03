# Release ledger completion

QA instruction: finish the unblocked engineering in `RELEASE-BLOCKER-LEDGER-2026-10-02.md`. The frozen baseline was tip `4a6b97fba97729b658a40ffc99d48c505978e4ba` (code `4b9755b66c5e60968cf3e432dd5e907f027d8393`). That baseline is not this candidate. A pin match authenticates verifier code. It does not authenticate biometric key origin or human approval.

Code commits: `74914f9b52784509182318b5261f6747ccdf9f77` and `60ea6eea6b892b30d4d47baa021b0ad63cd8646e`. The candidate tip is the commit that adds this sentence. Its parent is `abc6a79eecc08082926e64b6c326c0e966d5a752`. On a Mac without that Developer ID identity, the extracted-verifier test signs ad-hoc and still refuses the repository fallback. The compile-stage test skips when `swiftc` is absent and does not read a machine-local interpreter path.

This note is not production sign-off. Nothing here was installed, published, merged, notarized, or submitted. No biometric prompt was run. `SecureEnclave.P256.Signing.PrivateKey` was not called. The live `/Applications` apps and holder daemon pid 42554 were not repaired, signaled, or replaced. CI green is not readiness.

## Ledger

| ID | Status | Commit | Test | Evidence |
|---|---|---|---|---|
| E1 | fixed | `74914f9b52784509182318b5261f6747ccdf9f77` | `test_installed_protection_refuses_a_software_key_when_the_pin_matches` | this file |
| E2 | not closed. Session custody and a phone-peer comparison are in the control flow. A biometric press does not finish missing implementation. A live iPhone transport and a root-owned install are still unbuilt | `abc6a79eecc08082926e64b6c326c0e966d5a752` | `test_session_custody_signs_after_holder_reload`; `test_ipc_binding_refuses_a_foreign_peer_and_an_origin_string`; `test_stale_phone_challenge_is_refused`; `test_user_invoked_enrollment_cancel_rotation_and_revocation`; `test_concurrent_consume_of_a_custody_signature`; `test_phone_peer_comparison_enrolls_companion`; `test_companion_requires_a_phone_peer_not_a_local_key`; `test_os_boundary_mock_enrolls_local_and_paired_phone_without_a_prompt`; `test_installed_protection_refuses_a_software_key_when_the_pin_matches` | this file |
| E3 | package preparation, not installation qualification. The intact interpreter runs `bundle_runtime.py`; the payload copy is not executed. Live install remains H2 | `eb397ce7ec89ecad56eca7869b0432207001b93d` | `test_compiled_package_relocates_runtime_without_a_developer_interpreter`; `test_detached_interpreter_is_not_executed`; `test_dependency_cycles_and_collisions_are_bounded`; `test_fixture_lifecycle_stays_in_a_temp_root` | this file |
| E4 | fixed | `74914f9b52784509182318b5261f6747ccdf9f77` | `test_dangerous_build_directories_are_not_deleted` | this file |
| E5 | qualification-not-exploit, ordering fixed in source | `74914f9b52784509182318b5261f6747ccdf9f77` | `test_pre_import_refuses_a_symlink_and_a_writable_file`; `test_secret_is_not_read_when_support_is_hostile` | this file |
| E6 | fixed for the extracted verifier path | `74914f9b52784509182318b5261f6747ccdf9f77` | `test_extracted_artifact_is_the_holder_verifier_without_repo_fallback` | this file |
| E7 | artifacts prepared; package preparation is not installation qualification; Store archive and notarization remain H3 | `0c0d1c834d4e1f6ef783a001f142c1aa87b057dd` | `scripts/release_check.py` | this file, `artifacts/rc15-2026-10-02-qa-py312-flow/` |
| E8 | receipt compare/diff/retain, workspace switch, and retain cancellation re-driven on `/tmp/rs-qa-adapter-derived`. The UI has no separate in-flight large-output cancel control. The 74914f9 and flow sessions are not this tip | `eb397ce7ec89ecad56eca7869b0432207001b93d` | GUI session below | this file |
| E9 | fixed as documentation; hashes stay out of the sdist | `74914f9b52784509182318b5261f6747ccdf9f77` | `docs/CHANNEL_MATRIX.md`, `docs/CANDIDATE_MANIFEST.md` | this file |
| E10 | qualification-not-exploit. A client-claimed uid is not the socket peer. Daemon pid 42554 was not contacted and a second OS user was not used | `eb397ce7ec89ecad56eca7869b0432207001b93d` | `test_socket_peer_ignores_a_claimed_foreign_uid`; `test_holder_state_is_not_world_readable` | this file |
| E11 | matrix written; publication comparison remains after an authorized publish | `74914f9b52784509182318b5261f6747ccdf9f77` | `docs/CHANNEL_MATRIX.md` | this file |
| D1 | confirmed-and-implemented | `9946eff53154f9ee7cbaf301ff35203b9b57b402` | `test_confirmed_pin_is_exact_and_refuses_a_software_key`; `test_identity_mismatch_against_the_confirmed_pin`; `test_adhoc_repository_verifier_does_not_meet_the_confirmed_pin`; `test_extracted_artifact_is_the_holder_verifier_without_repo_fallback` | this file |
| H1 | human gate | none | not performed | this file |
| H2 | human gate | none | not performed | this file |
| H3 | human gate | none | not performed | this file |

E1 was a reproduced defect on the baseline: a caller `boundary_double` flag was admitted under `installed_protection` when a test pin matched. This candidate refuses that path for local, companion, and dual before key comparison. Wire JSON, an environment variable, a config file, and a dict constructor argument cannot select the double. The injected `TrustedNativeBoundary` exists only as a Python object passed by a test. It is not hardware, and it is refused when installed protection is on. The unset shipped pin means the baseline defect was not a claimed live exploit.

E2 is not closed. `HumanNativeSigner` sets `hardware` false and installed protection still refuses it when the confirmed pin matches. That class is a software signer. `HumanOperatedNativeAdapter` is a software injection point. A persisted origin string, including `human-operated-native-adapter` and `secure-enclave-human-prompt`, does not admit a software key under installed protection even when the verifier pin matches. A pin match authenticates verifier code only. It is not biometric key origin and not human approval. No live exploit is claimed: the shipped product is not installed. This is a source trust-boundary bug. The local button keeps the private key in a session closure and enrolls the public key. The paired-phone button issues a challenge and does not create a local key. A live iPhone transport is still unbuilt. Installed protection refuses the software double even when the D1 pin matches. Automation did not press either button and did not call `SecureEnclave.P256.Signing.PrivateKey`. Tests replace `os_secure_enclave_create_key`. A biometric press is H1 and does not finish the missing implementation.

E3 was marked fixed for an interpreter-only stage. The stage now includes a relocated interpreter, its standard library and libraries, the registration UI, the daemon at `Contents/MacOS/RunSpecimenHolderDaemon`, and the LaunchDaemon plist. `bundle_runtime.py` is started by `RS_HOLDER_BUNDLE_RUNNER`, an intact interpreter. The payload path is copied and is not executed. External libraries are copied once, by inode, and a basename collision gets one hash suffix instead of a stacked `lib-` prefix. `@executable_path`, `@loader_path`, and `@rpath` are resolved against the original Mach-O. A missing non-system library fails closed. `/usr/lib` and `/System` may remain unresolved as system libraries. Consent copies that package into a temp root and can update, roll back, and uninstall there. A live `/Applications` install still exits 4. That temp-root copy is package preparation, not installation qualification. It is not root-owned and it is not notarized.

E4 never deletes `HOLDER_BUILD_DIR`. The deletion mock was not invoked for `/`, the home directory, the repo, `/Applications`, a non-stage temp path, or a symlink. No destructive probe was executed.

E5 is an ordering concern, not a reproduced exploit. Import of holder runtime and the bootstrap secret now wait until the resolved path is checked. Installed multi-user proof was not run.

E6 refreshes provenance after signing. The repository verifier stays ad-hoc. A signed copy's provenance says `codesign`. The holder launch in the test resolved the verifier from the extracted directory after the repository fallback was patched to exit. The architecture check reports arm64 for the present binary. Display text is not a pin.

E7 prepared a wheel, an sdist, the unchanged plugin zip, and a separate Developer ID verifier zip. No Store archive was exported. No package was notarized or installed. Repeated 0.1.5 (13) labels are not this binary. The Store app remains guarantee (1). The Developer ID holder remains guarantee (2) and is not the Store app.

E10 did not inject a crash into daemon pid 42554, did not open a cross-user socket, and did not run as root. The mode check and the existing crash, descendant, and snapshot tests are qualification.

## D1 confirmed

Yahor confirmed this pair. `production_verifier_pin()` returns it. Confirmation did not enable a software key. The Store app does not carry the pin. This is not a production sign-off.

Signing a copy with `Developer ID Application: YAHOR DARASHKEVICH (UN6KF8636A)` did not prompt. Signed-copy SHA-256 `e74c0d74c31a077c7fd3557dbc9d96f28da0ff95f41c5d3668ba0b2f3ca1622a`. Its team and designated requirement equal the pin exactly. The repository binary stays ad-hoc. No new identity was stored.

## Earlier proposal text

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

After the confirmed pin, `release_check` wrote `artifacts/rc15-2026-10-02-qa-py312-pin/` and did not replace the tip or ledger directories. Homebrew Python 3.12.14. 573 tests, 35 skipped, then the 4-test follow-up, exit 0. The same skip reasons. The new sdist hash is not inside a file packed into that sdist.

- Wheel SHA-256: `84314444fdc97204cfc6bfe455b864b1cd43f8ad82f193dcdfedb708c5ec519e`
- Sdist SHA-256: `24babb09a034c403bbf41129a36536a57111745a8b0d7b92c0e0713fff26a592`
- Plugin zip SHA-256, unchanged: `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`

After the injected signer and the complete stage, `release_check` wrote `artifacts/rc15-2026-10-02-qa-py312-flow/` and did not replace the pin, tip, or ledger directories. Homebrew Python 3.12.14. 582 tests, 35 skipped, then the 4-test follow-up, exit 0. Skips: bubblewrap not installed (3), PyNaCl not installed (29), pytest not installed (1), Linux `ldd` checks (2). The new sdist hash is not inside a file packed into that sdist. Apple `/usr/bin/python3` was not the freeze interpreter and is not the holder payload interpreter.

- Wheel SHA-256: `1c6d192fd030818129d0043b54fbd5f0999102d7e5ad326b0dddeaac8e001961`
- Sdist SHA-256: `7f4bf6ed4e1bcb040ca36cbf0a29d9e40eeb8b971f4e610b08751692e37e782a`
- Plugin zip SHA-256, unchanged: `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`
- Staged holder package tar SHA-256, not installed: `224c2a28f1f7adc729ca1705d6e07a409ae0f41b5f7130990e7c641a4f520d4f`

The package tar was hashed from a temp stage and was not committed. It is not a Developer ID product and not a notarized archive.

## GUI

The `74914f9` GUI in `/tmp/rs-qa-ledger-derived` remains a receipt build and is not holder acceptance. Executable SHA-256 `b27d7d4d6553dec582cc9486ec73f4376ba82e439dd91315351e1540a9f30a7e`.

The pin commit changes the Mac app status string, so a new development build is `/tmp/rs-qa-pin-derived` from `9946eff53154f9ee7cbaf301ff35203b9b57b402`. Signature: Sign to Run Locally (ad-hoc). Sandbox on. `com.apple.security.network.client` present. `com.apple.security.network.server` absent. `get-task-allow` absent. The bundle has no holder. This is not holder acceptance.

Executable SHA-256: `0b2fbb2dd10fc6d6f6ebc87afd003e7aae72d729623e3da02b7cecb09765e2c4`

The receipt session below is the `74914f9` build. The pin build was not used for another receipt session. Labeled synthetic certificates, not a live run, were planted for `reviewer-demo/run-001` and `reviewer-demo/run-000`. Digest returned `certificate_id` `labeled-synthetic-reviewer-demo-run-001`. Live compare status was `match` for `outputs/labeled-synthetic.txt`. Diff reported `identical: false` with changed `exit_code` 0 versus 1 and `run_result` ok versus failed. Retain cancel left `/tmp/rs-qa-retain-ledger` empty. Retain confirm wrote `state.json`, `events.jsonl`, `approval.json`, `certificate.json`, and `manifest.json` (`kind` `retained_incident_bundle`, created `2026-10-02T15:04:24Z`, manifest SHA-256 `5d693e3f0f47ef3c516106258b4c821fce5bef2b788379d315eb8da8cd5a3c15`).

The window was resized to 900 by 700. Opening `/tmp/rs-qa-ledger-other-ws` (a truncated contract) disabled digest and showed "Select a contract with a campaign and a run." Opening the reviewer demo again restored the labeled digest. The specific stale-confirmation sentence was not observed because the workflow sheet closed during the switch. Large-output cancellation was not driven. Human approval was not performed.

Only QA pid 37395 was killed. The container `~/Library/Containers/com.darashkevich.runspecimen` was restored from a backup taken before the synthetic certificates. `/Applications/RunSpecimen.app` mtime stayed `2026-09-26 13:56:03`. `/Applications/RunSpecimen Holder.app` mtime stayed `2026-09-30 15:19:13`. Daemon pid 42554 was still alive.

This tip's development GUI is `/tmp/rs-qa-flow-derived`, built from parent `0c0d1c834d4e1f6ef783a001f142c1aa87b057dd`. Signature: Sign to Run Locally (ad-hoc). Sandbox on. `com.apple.security.network.client` present. `com.apple.security.network.server` absent. `get-task-allow` absent. The bundle has no holder. Executable SHA-256 `521c1705101f536f864e3abd6dc452fd8f9493667cb850d5ae02ab5761e479a4`. The 74914f9 and pin-build receipt sessions are not acceptance of this tip.

Labeled synthetic certificates were planted again for `reviewer-demo/run-001` and `reviewer-demo/run-000`. Digest returned `certificate_id` `labeled-synthetic-reviewer-demo-run-001`. Live compare status was `match` for `outputs/labeled-synthetic.txt`. Diff reported `identical: false` with changed `exit_code` 0 versus 1 and `run_result` ok versus failed. Retain cancel left `/tmp/rs-qa-retain-flow` empty. Retain confirm wrote `state.json`, `events.jsonl`, `approval.json`, `certificate.json`, and `manifest.json` (`kind` `retained_incident_bundle`, created `2026-10-02T16:58:39Z`, manifest SHA-256 `e91de91228f8644db8f5db8f47edcfbd0b5ab74d0820e238525f3b6c33e0e385`). Workspace switching, a truncated contract, and large-output cancellation were not re-driven in this session.

Only QA pid 87608 was killed. The container was restored from a backup taken before this session. `/Applications/RunSpecimen.app` mtime stayed `2026-09-26 13:56:03`. `/Applications/RunSpecimen Holder.app` mtime stayed `2026-09-30 15:19:13`. Daemon pid 42554 was still alive.

After the packager and adapter change, `release_check` wrote `artifacts/rc15-2026-10-02-qa-py312-adapter/` and did not replace the flow, pin, tip, or ledger directories. Homebrew Python 3.12.14. 598 tests, 35 skipped, then the 4-test follow-up, exit 0. Skips: bubblewrap not installed (3), PyNaCl not installed (29), pytest not installed (1), Linux `ldd` checks (2). The new sdist hash is not inside a file packed into that sdist. Apple `/usr/bin/python3` was not the freeze interpreter. Python 3.11 and 3.14 are not installed on this machine, so those package jobs stay with CI.

- Wheel SHA-256: `dd21591465348064f3be0305f25ff3ba20db2d31a4c18af9a81e331e9f1fb4af`
- Sdist SHA-256: `f9ca45081cb06724ec478c8bc03bc572eea616a991193af2ce7da6b2817ab79b`
- Plugin zip SHA-256, unchanged: `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`
- Staged holder package tar SHA-256, not installed: `6148a68ee67cb7ab58c4098d4cef8a3b781570a5f76ddc1c570ceb26f4750091`

The package tar was hashed from a temp stage and was not committed. It is not a Developer ID product and not a notarized archive. Copying it into a temp root would still be package preparation, not installation qualification.

This tip's development GUI is `/tmp/rs-qa-adapter-derived`, built from parent `eb397ce7ec89ecad56eca7869b0432207001b93d`. Signature: Sign to Run Locally (ad-hoc). Sandbox on. `com.apple.security.network.client` present. `com.apple.security.network.server` absent. `get-task-allow` absent. The bundle has no holder. This is not holder acceptance. Executable SHA-256 `99f1281ac2b3321a0c5e44b83ad5d2396b8dd64c8d418284ed39454d586c9b6e`. The flow, pin, and 74914f9 sessions are not acceptance of this tip.

A truncated contract at `/tmp/rs-qa-adapter-truncated/contract.json` made Digest receipt report "Select a contract with a campaign and a run." Opening the reviewer demo again restored the labeled digest. Digest returned `certificate_id` `labeled-synthetic-reviewer-demo-run-001`. Live compare status was `match` for `outputs/labeled-synthetic.txt` (`f56db73d871657d629ecddffa054fe9f22be1ba72f233f4804d663ca5e33ec9e`). Diff reported `identical: false` with `exit_code` 0 versus 1 and `run_result` ok versus failed. Retain cancel left `/tmp/rs-qa-adapter-retain` empty. Retain confirm wrote `state.json`, `events.jsonl`, `approval.json`, `certificate.json`, and `manifest.json` (`kind` `retained_incident_bundle`, created `2026-10-03T11:24:47Z`, manifest SHA-256 `b0e0c6b45c6907cd102d74dae33cae5cebeb824714b682fb0166c54f007e0170`). The sheet exposes Cancel workflow. It does not expose a separate control that cancels an in-flight large-output command.

Only QA pid 37076 was killed. The container was restored from a backup taken before this session. `/Applications/RunSpecimen.app` mtime stayed `2026-09-26 13:56:03`. `/Applications/RunSpecimen Holder.app` mtime stayed `2026-09-30 15:19:13`. Daemon pid 42554 was still alive.

`a33ba2b5cef3da180f7ed7147d4da04defa98009` changes the Linux socket-peer read only. It does not change Mac app sources, so the GUI above was not rebuilt and is not holder acceptance. Ubuntu CI had failed `test_socket_peer_ignores_a_claimed_foreign_uid` with `OverflowError` on the Darwin `LOCAL_PEERCRED` constant. Linux now uses `SO_PEERCRED`. The macOS jobs on that earlier push had already succeeded.

`release_check` after that fix wrote `artifacts/rc15-2026-10-02-qa-py312-peer/` and did not replace the adapter directory. Homebrew Python 3.12.14. 598 tests, 35 skipped, then the 4-test follow-up, exit 0. The same skip reasons. The new sdist hash is not inside a file packed into that sdist.

- Wheel SHA-256: `abebf177f221163a3fda57adb8c75d3c5b3cae71d96c85479835b51034c8ceaa`
- Sdist SHA-256: `d43ae04b833fbcc99a88261009f48a866c0e9efdbbc12629d2fe3ae6c082bc68`
- Plugin zip SHA-256, unchanged: `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`
- Staged holder package tar SHA-256, not installed: `f92d846630c979d9c379c46ddbeba48382b931fb2a3c5b6460bb88988981a1a3`

The next push's macOS 3.11 job failed only `test_accept_returns_connected_socket` (`unexpectedly None`) after the client thread missed the 0.2s accept. The package tests on that job passed. `af1bedc04bd4ed7a4501c80e723fac95eaf0b114` retries that accept. It does not change Mac app sources or the staged holder bytes. `release_check` wrote `artifacts/rc15-2026-10-02-qa-py312-accept/`. 598 tests, 35 skipped, then the 4-test follow-up, exit 0. The wheel hash is unchanged from the peer directory. The new sdist hash is not inside a file packed into that sdist.

- Wheel SHA-256, unchanged: `abebf177f221163a3fda57adb8c75d3c5b3cae71d96c85479835b51034c8ceaa`
- Sdist SHA-256: `a57f80dd4084f5206446cd9617012c906d45d6bda5034b30102cbeb4bc966ecf`
- Plugin zip SHA-256, unchanged: `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`
- Staged holder package tar SHA-256, unchanged and not installed: `f92d846630c979d9c379c46ddbeba48382b931fb2a3c5b6460bb88988981a1a3`

`88285c4e4ad39e82cb824d65b3f5700b65fb6f6b` resolves `@executable_path`, `@loader_path`, and `@rpath` against the original Mach-O and its `LC_RPATH`. `/usr/lib` and `/System` stay system libraries. A missing non-system library fails closed. Identity is SHA-256 bytes, not file size. The CI fixture is `test_relocatable_executable_path_closure_is_copied`, which clang-builds `@executable_path/../lib/libpython3.11.dylib`, `@loader_path/libextra.dylib`, and `@rpath/librpath.dylib`. The read-only Python 3.11 at `how-x20/.tools/python/bin/python3` passed `test_compiled_package_relocates_runtime_without_a_developer_interpreter`. Homebrew Python 3.12.14 passed the same test. The how-x20 tree was not written. The detached interpreter was not executed.

`release_check` wrote `artifacts/rc15-2026-10-02-qa-py312-enclave/` and did not replace the accept, peer, adapter, tip, pin, flow, or ledger directories. Homebrew Python 3.12.14. 605 tests, 35 skipped, then the 4-test follow-up, exit 0. Skips: bubblewrap not installed (3), PyNaCl not installed (29), pytest not installed (1), Linux `ldd` checks (2). The new sdist hash is not inside a file packed into that sdist. Apple `/usr/bin/python3` was not the freeze interpreter.

- Wheel SHA-256: `870a1adc49eb843919d91b72ef7e8d9715abc8f254ede13944215e69beccec65`
- Sdist SHA-256: `d227cafcd5572849ccba84095f12f7d704280a0a187951966e9fe2943928fb18`
- Plugin zip SHA-256, unchanged: `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`
- Staged holder package tar SHA-256, not installed: `7c1cc08d0091fc34aa685f78f93060d32c4b96dea36f0005ca036f286331077c`

The development GUI is `/tmp/rs-qa-enclave-derived`. Executable SHA-256 `b8c88c333898d57ad0b60f23b8b6694dc8e643f4d7f1e30ee88daea580f5c66d`. Sandbox on. `com.apple.security.network.client` present. `com.apple.security.network.server` absent. `get-task-allow` absent. The bundle has no holder. This is not holder acceptance and not a biometric press. Digest returned `certificate_id` `labeled-synthetic-reviewer-demo-run-001`. Live compare status was `match` for `outputs/labeled-synthetic.txt` (`eb8d6bd590f0561640a2349b1ea42fdcf72adef32a928021a622bdee35b8e72b`). Diff reported `identical: false` with `exit_code` 0 versus 1 and `run_result` ok versus failed. Retain cancel left `/tmp/rs-qa-enclave-retain` empty. Retain confirm wrote `state.json`, `events.jsonl`, `approval.json`, `certificate.json`, and `manifest.json` (`kind` `retained_incident_bundle`, created `2026-10-03T12:50:28Z`, manifest SHA-256 `c7e09df1cd35b980eee4f52ef27932208c39f548b19c73f6f7818a1d6d84d35f`). Only QA pid 80061 was killed. The container was restored. `/Applications/RunSpecimen.app` mtime stayed `2026-09-26 13:56:03`. `/Applications/RunSpecimen Holder.app` mtime stayed `2026-09-30 15:19:13`. Daemon pid 42554 was still alive. E2 stays open because a person has not pressed the control.

`release_check` wrote `artifacts/rc15-2026-10-02-qa-py312-custody/` and did not replace the enclave, accept, peer, adapter, tip, pin, flow, or ledger directories. Homebrew Python 3.12.14. 612 tests, 35 skipped, then the 4-test follow-up, exit 0. Skips: bubblewrap not installed (3), PyNaCl not installed (29), pytest not installed (1), Linux `ldd` checks (2). The new sdist hash is not inside a file packed into that sdist. Apple `/usr/bin/python3` was not the freeze interpreter.

- Wheel SHA-256: `576177c310c6d6202b679590e74f53d179a5db69c35e1b7be7e4c24b371c2146`
- Sdist SHA-256: `049113acec03730af76ec70d08b1646af9d4dc244bc10410b50a6a8bc29d0fe3`
- Plugin zip SHA-256, unchanged: `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`
- Staged holder package tar SHA-256, not installed: `6a4d1398163ca6f8df8a3a1e8593530d2f9bc2d8c734d220e856cf243c5dbc2c`

The development GUI is `/tmp/rs-qa-custody-derived`. Executable SHA-256 `b90d79b313c02a3c56f073446dafa5dd0575e00e51c35f65390c9bed500d651d`. Sandbox on. `com.apple.security.network.client` present. `com.apple.security.network.server` absent. `get-task-allow` absent. The bundle has no holder and the Secure Enclave buttons were not pressed. Digest returned `certificate_id` `labeled-synthetic-reviewer-demo-run-001`. Live compare status was `match` for `outputs/labeled-synthetic.txt` (`eb8d6bd590f0561640a2349b1ea42fdcf72adef32a928021a622bdee35b8e72b`). Diff reported `identical: false` with `exit_code` 0 versus 1 and `run_result` ok versus failed. Retain cancel left `/tmp/rs-qa-custody-retain` empty. Retain confirm wrote `state.json`, `events.jsonl`, `approval.json`, `certificate.json`, and `manifest.json` (`kind` `retained_incident_bundle`, created `2026-10-03T14:27:11Z`, manifest SHA-256 `af35a1c34fc87de9c01e09f5253a214dd1482c01e996a051d6cc1eae32585bb1`). Only QA pid 10258 was killed. The container was restored. `/Applications/RunSpecimen.app` mtime stayed `2026-09-26 13:56:03`. `/Applications/RunSpecimen Holder.app` mtime stayed `2026-09-30 15:19:13`. Daemon pid 42554 was still alive. This GUI is not holder acceptance and not a biometric press.

## Human acceptance path, not performed

Open the staged RunSpecimen Holder, not the Store app. Press **Enroll with Secure Enclave**. That calls `LiveSecureEnclaveKeyMaker.makeSessionKey`, which calls `SecAccessControlCreateWithFlags` with `biometryCurrentSet` and `SecureEnclave.P256.Signing.PrivateKey(accessControl:authenticationContext:)`. The person sees Touch ID or a password prompt. The private key stays in the session `sign` closure. The holder client then enrolls `mac-human`. A later signature calls that closure and prompts again. The screen says the holder enrolled the local session key, E2 is not closed, and a root-owned install is still unbuilt.

Press **Enroll paired phone**. That calls `issuePhoneChallenge` and does not create a local key. The person sees "Paired phone challenge is waiting for the iPhone peer" and that companion enrollment is not complete until the peer key is compared. Completing companion or dual still needs a live iPhone that signs the challenge. That transport is unbuilt. A local key labeled companion does not satisfy it.

Do not treat a D1 pin match as biometric origin or human approval. Do not type APPROVE.

## Human checklist

1. D1 is confirmed. A pin match authenticates verifier code only.
2. H1: on a provenance-identified holder build, press Enroll with Secure Enclave, complete the biometric prompt, then sign, cancel, rotate, and revoke. Press Enroll paired phone only when a real iPhone can answer the challenge.
3. H2: authorize a root-owned holder install, then run one bounded local, companion, and dual command and reject a replay. Leave the approved Store app in place.
4. H3: export the Store archive for this SHA and notarize the Developer ID holder. Historical 0.1.4 (9) does not qualify this SHA.
5. Retest this candidate tip independently. The `/tmp/rs-qa-enclave-derived` GUI is not acceptance of this tip.
