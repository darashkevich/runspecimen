# QA comment after 91900f8

Comment: https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5932938695

PRs #40–#45 had no issue comments, review comments, or reviews newer than 2026-10-01T13:15:40Z. Pull request #39 had no new review comments.

Code SHA: `68465b27109690bfaa5a648d2651b1ba70b4e781`. The candidate tip is the commit that adds this sentence; its parent is that code SHA.

This note is not production sign-off. Nothing here was installed, published, merged, or submitted. No biometric prompt was run. The live holder was not repaired. CI green is not readiness.

## Already satisfied on 91900f8

Snapshot ownership is not chowned to the payload. Read access for a root holder is an ACL. Unprivileged tests are not installed multi-uid acceptance. The Linux subreaper is cleared after the payload parent exits; this Mac run does not independently prove that Linux behavior. CI on `91900f8` did.

## Fixed

1. **Snapshot execute exit 1.** `os.execv("python3")` cannot search `PATH`, so the helper exited 1 and the assertion did not show stderr. A relative executable is now refused before spawn (`launch executable is not an absolute file`) and the lease stays held. The signed snapshot job uses an absolute interpreter, and a non-zero exit includes stderr. Tests: `test_bootstrap_and_signed_local_execute_from_snapshots` (OK), `test_relative_interpreter_is_refused_before_spawn` (OK).

2. **Closed gate is not permission.** `holder_supervise_exec` requires the single go byte. EOF, a wrong byte, and a read error return 2 and do not exec. Spawn or arm failure closes the gate without that byte, reaps the child, and keeps the lease when the child is still alive. Tests: `test_closed_gate_wrong_byte_and_read_error_do_not_exec` (OK), `test_unarmed_spawn_reaps_without_running_and_keeps_a_living_child` (OK).

3. **Shipping Observe scan.** `apps/ios/Scripts/verify_ios_release_symbols.sh` still runs the fixture tests and the Debug C control. On Darwin it builds Observe Release and Debug with `CODE_SIGNING_ALLOWED=NO` and no provisioning update, scans the Release Mach-Os, and requires the Debug product to be rejected because it defines `beforeFinalSignatureDecision`. Local result: fixtures passed, shipping scan passed. Unsigned Release executable SHA-256 `560dd5b04a01d256f4634391277615a373d3a6ba9ec6a5db6b7a5644fb70d57a`. That binary was not signed, not installed, and is not a GUI acceptance.

4. **CryptoKit P-256 is not a Secure Enclave.** `native_p256_verify.swift` checks signatures with CryptoKit. A software key can authorize one labeled-not-hardware bounded run. `installed_protection` refuses that key. `hardware=True` and an imported `secure-enclave` label stay refused. No Secure Enclave private key was created and no Touch ID, Face ID, or paired-phone prompt was shown. Test: `test_cryptokit_p256_authorizes_a_bounded_run_and_is_not_hardware` (OK).

## Local release_check

Homebrew Python 3.12.14, `/tmp/rs-py312-rel-holder`. 530 tests, 35 skipped. Apple `/usr/bin/python3` was not used.

Directory: `artifacts/rc15-2026-10-01-qa-py312-gate/`

| Artifact | SHA-256 |
| --- | --- |
| wheel | `9fde01b23a512fdc292b8e73f6dadda19b8374400053e6be1d3f8f864bd1c3fa` |
| sdist | `312038f72ececfa11d2ad5710a3a007ee7fe9095a5778c95ca097b5ed66c2eee` |
| plugin | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

The sdist does not contain its own hash. The plugin zip is unchanged. No Store package.

The macOS GUI app sources did not change. The previous development GUI remains the build of `27bb0c7` app sources. This pass does not claim a new GUI acceptance.

Production Secure Enclave enrollment still uses biometric access control on `SecureEnclave.P256.Signing.PrivateKey`. This session did not call that function. A software P-256 signature is not that enrollment.
