# QA comment after 14:26:15Z

Comment: https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5933766654 (2026-10-01T14:41:36Z)

PRs #40–#45 had no review comments or reviews newer than 2026-10-01T14:26:15Z. Pull request #39 had no new review comments or reviews. Yahor authorized the work that comment requests. That authorization does not include a biometric prompt or a live holder repair. The comment itself says there is no automatic live repair.

Code SHA: `60c799a3d4952f5487d37995a98dad484c127863`. The candidate tip is the commit that adds this sentence; its parent is that code SHA.

This note is not production sign-off. Nothing here was installed, published, merged, or submitted. No biometric prompt was run. No Secure Enclave private key was created, because `SecureEnclave.P256.Signing.PrivateKey()` raises a Touch ID or password prompt on this Mac. Production stays fail-closed for `hardware=True`, an imported secure-enclave label, and a software key when installed protection is on. CI green is not readiness.

## Already on 06d3313

Pipe cleanup and test-only socket isolation. Confirmed in source. Production `installed_socket_path()` still ignores `RS_HOLDER_SOCKET`.

## Already on 9727b0c

Packaged CryptoKit verifier, no runtime `swiftc`. P-256 pairing requires `key_comparison` and labeled provenance. Tests: `test_verifier_does_not_compile_on_the_customer_machine`, `test_p256_pairing_without_key_comparison_is_refused`.

## Fixed here

Consume and execute were putting `device-ed25519-not-hardware` inside a P-256 authorization, so a signature over `device-p256-not-hardware` failed. Those blobs now follow the paired algorithm. The execution receipt uses the same label and stays `hardware: false`.

`test_cryptokit_p256_authorizes_a_bounded_run_and_is_not_hardware` failed on that mismatch before the change and passed after (OK).

`tests/test_native_bridge_policies.py` (OK):

- `test_local_companion_and_dual_execute_and_are_not_hardware`
- `test_cancel_revoke_replay_rotation_binding_restart_and_concurrency`
- `test_concurrent_consume_of_one_nonce_fails_closed`

The bridge is `labeled-native-bridge-double-not-hardware`. It is not hardware acceptance. The map remains `docs/HOLDER_NATIVE_BRIDGE.md`.

## Not a GUI acceptance

macOS app sources did not change. The previous development GUI remains the build of `27bb0c7` app sources.

## Local release_check

Homebrew Python 3.12.14, `/tmp/rs-py312-rel-holder`. 540 tests, 35 skipped. Apple `/usr/bin/python3` was not used.

Directory: `artifacts/rc15-2026-10-01-qa-py312-bridge/`

| Artifact | SHA-256 |
| --- | --- |
| wheel | `12d863002bb78358e65651c138fa500c36d374c25a1d10edbd9dd5c5925ee63f` |
| sdist | `01e47325906c697ede08c0ef035fa3285cebb153fe4a5c4650274665edb39307` |
| plugin | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

The sdist does not contain its own hash. The plugin zip is unchanged. No Store package.

## Human gates

Touch ID, Face ID, a paired-phone confirmation, Secure Enclave key creation, a privileged install, and the final real bounded run stay with Yahor. The live `/Applications` holder was not repaired.
