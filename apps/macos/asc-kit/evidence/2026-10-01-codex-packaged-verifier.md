# QA comment after 06d3313

Comment: https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5933766654 (2026-10-01T14:41:36Z)

PRs #40–#45 had no review comments or reviews newer than 2026-10-01T14:26:15Z. Their issue comments in that window are the earlier superseded/left-open notes from this branch, not new defects. Pull request #39 had no new review comments or reviews.

Code SHA: `9727b0c996473cdeada25f54a8bf75e63e447a29`. The candidate tip is the commit that adds this sentence; its parent is that code SHA.

This note is not production sign-off. Nothing here was installed, published, merged, or submitted. No biometric prompt was run. No Secure Enclave private key was created. The live holder was not repaired. CI green is not readiness.

## Fixed

1. **Customer verification compiled with swiftc.** `verify_native_p256` now executes the packaged `native_p256_verify` binary after the provenance SHA-256 matches `1f61d80cefecadb0f1e4629530544bf0e28a8d27e2b4d57dfc253d3bec041bcc` and `codesign --verify --strict` succeeds. The signature is ad-hoc, identifier `com.darashkevich.runspecimen.native-p256-verify`, and `not_secure_enclave` is true. It is not Developer ID and not notarization. Test: `test_verifier_does_not_compile_on_the_customer_machine` failed while swiftc was invoked and passed after (OK).

2. **P-256 pairing stored an uncompared public key.** Pairing now requires `key_comparison` to equal the SHA-256 of the public key, and a provenance record for bridge `labeled-native-bridge-double-not-hardware` with the same public key, role, policy, and generation. Challenges include those paired fields. `hardware=True`, an imported secure-enclave label, and a software P-256 key under `installed_protection` stay refused. The labeled bridge is a test double, not a biometric. Tests: `test_p256_pairing_without_key_comparison_is_refused` failed before the check and passed after (OK). `test_cryptokit_p256_authorizes_a_bounded_run_and_is_not_hardware` reloads the holder and still completes one labeled-not-hardware local run (OK).

The protocol map is `docs/HOLDER_NATIVE_BRIDGE.md`. Cancellation, revocation, rotation, downgrade, and replay remain the existing holder refusals. They are not hardware acceptance.

## Human gates

Creating a Secure Enclave private key, Touch ID, Face ID, a paired-phone confirmation, a privileged install, and the final real bounded run stay with Yahor. macOS GUI sources did not change. The previous development GUI remains the build of `27bb0c7` app sources. This pass does not claim a new GUI acceptance.

## Local release_check

Homebrew Python 3.12.14, `/tmp/rs-py312-rel-holder`. 537 tests, 35 skipped. Apple `/usr/bin/python3` was not used.

Directory: `artifacts/rc15-2026-10-01-qa-py312-verifier/`

| Artifact | SHA-256 |
| --- | --- |
| wheel | `9b1b9590bd19f01cd3bc6f4ade847a8444d98e8abb95bc076c2071639bfab5d7` |
| sdist | `096b02cc6e112c9ce3c1191c5c693a5b7a973b5decfa7a504c5fc76888e8d705` |
| plugin | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

The sdist contains the packaged verifier and does not contain its own hash. The plugin zip is unchanged. No Store package.
