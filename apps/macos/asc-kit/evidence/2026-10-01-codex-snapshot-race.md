# Snapshot collision after the production-bridge push

No new QA comment after https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5935697881 (2026-10-01T16:23:50Z) assigned further work. Pull requests #40–#45 had no new review comments or reviews. The only later issue comment is the close note on #44: https://github.com/darashkevich/runspecimen/pull/44#issuecomment-5935780572 (2026-10-01T16:28:25Z).

The production-bridge comments remain:

- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5934004848 (2026-10-01T14:54:11Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5934005326 (2026-10-01T14:54:12Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5935697881 (2026-10-01T16:23:50Z)

Those steps are recorded in `2026-10-01-codex-production-bridge.md` on `a365a93fafce5275510fbfd0c1dbcc11441663b7`.

Code SHA: `0ce219a0b7b07658b7ab002b6e07ae8ac34ab54a`. The candidate tip is the commit that adds this sentence; its parent is that code SHA.

This note is not production sign-off. Nothing here was installed, published, merged, or submitted. No biometric prompt was run. No Secure Enclave private key was created. The live holder was not repaired. CI green is not readiness. GUI sources did not change, so there is no new GUI acceptance. The previous development GUI remains the build of `27bb0c7` app sources. The temp ad-hoc app of the production-bridge Swift sources stays `e91f849112514da56b159fc9f419fcdd430c9774ec2f7195b023b12971899c62`.

## Assigned step this commit answers

Pull-request CI on `a365a93` failed: https://github.com/darashkevich/runspecimen/actions/runs/36892646502. Job `release-check (macos-latest, 3.11)` reported `test_concurrent_consume_of_one_nonce_fails_closed` with `FileExistsError` instead of `HolderRefusal`. The push run https://github.com/darashkevich/runspecimen/actions/runs/36892637906 was green and is not readiness.

`_prepare_payload_snapshot` now turns that mkdir collision into `HolderRefusal("payload snapshot token already exists")`. The concurrent test builds the signed human once, then both threads call `consume`.

`test_snapshot_mkdir_collision_is_a_refusal` raised `FileExistsError` before the catch and passed after. `test_concurrent_consume_of_one_nonce_fails_closed` passed after (2 tests, OK).

## Local release_check

Homebrew Python 3.12.14, `/tmp/rs-py312-rel-holder`. 542 tests, 35 skipped. Apple `/usr/bin/python3` was not used.

Directory: `artifacts/rc15-2026-10-01-qa-py312-race/`

| Artifact | SHA-256 |
| --- | --- |
| wheel | `962b5dbbe5ee75b92230bdcb3fc168012b90c7be9af6f28b71f1ec5ad003e228` |
| sdist | `52147fdb43783f96df00857214bf4d045f8a2022ba0575d725325a3922cc010f` |
| plugin | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

The sdist does not contain its own hash. The plugin zip is unchanged. Older rc15 directories were not overwritten.

## Human steps still open

Developer ID signing and notarization of the verifier. Touch ID or password for `SecureEnclave.P256.Signing.PrivateKey`. Public-key fingerprint confirmation. Paired-phone enrollment. Privileged holder install. The final bounded run. APPROVE and `--human-invoked` were not used.
