# Comments after 2026-10-01T14:41:36Z

- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5934004848 (2026-10-01T14:54:11Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5934005326 (2026-10-01T14:54:12Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5935697881 (2026-10-01T16:23:50Z)

PRs #40–#45 had no issue comments, review comments, or reviews newer than 2026-10-01T14:41:36Z. Pull request #39 had no new review comments or reviews.

Code SHA: `1be516935439431efea884e7d51249d53e53938a`. The candidate tip is the commit that adds this sentence; its parent is that code SHA.

This note is not production sign-off. Nothing here was installed, published, merged, or submitted. No biometric prompt was run. No Secure Enclave private key was created. The live holder was not repaired. CI green is not readiness.

## Steps from 5934005326

Close pull request #44 as superseded. Done: https://github.com/darashkevich/runspecimen/pull/44. The production `RS_HOLDER_SOCKET` override was not merged. Isolation on this branch remains a test patch of `installed_socket_path`.

## Steps from 5935697881

The labeled double on `4317531` was not treated as the production bridge.

Installed protection now refuses P-256 pairing through `production_enrollment_refusal()`: the packaged verifier is ad-hoc, not Developer ID; the labeled double is a separate path; local and companion signers are not connected; Secure Enclave key creation is not called. `test_production_bridge_rejects_adhoc_verifier_and_the_labeled_double` failed before this check (`software P-256 is not a Secure Enclave` only) and passed after (OK).

The Mac control `ProductionNativeBridgeGate` states the same refusal. Pinning a carried key still does not become production enrollment. `allowsProductionEnrollment` stays false even for a secure-enclave / production label.

The wheel remains `py3-none-any` with one Darwin arm64 Mach-O. Other platforms fail closed. The hash pin plus the ad-hoc signature is not a trusted publisher. The ledger is `docs/HOLDER_GATE_LEDGER.md`.

## Development app

GUI sources changed. Temp Release build, Sign to Run Locally, not installed:

`/tmp/rs-qa-prod-bridge-derived-2/Build/Products/Release/RunSpecimen.app`

Main executable SHA-256 `e91f849112514da56b159fc9f419fcdd430c9774ec2f7195b023b12971899c62`.

Signature is ad-hoc. TeamIdentifier is not set. Sandbox is on. `com.apple.security.network.server` is absent. `com.apple.security.get-task-allow` is absent. This is not GUI acceptance and not a Store build. The earlier Apple Development build of `27bb0c7` app sources was not replaced.

## Local release_check

Homebrew Python 3.12.14, `/tmp/rs-py312-rel-holder`. 541 tests, 35 skipped. Apple `/usr/bin/python3` was not used.

Directory: `artifacts/rc15-2026-10-01-qa-py312-prod-bridge/`

| Artifact | SHA-256 |
| --- | --- |
| wheel | `1c31e07c255bad7c684f479757acb448c5e5351ee23ee014080f7b58d875e55a` |
| sdist | `c9168e19c35ef41e80586f289e7e39a085a850162cb0437bcbe37d30e494b1f6` |
| plugin | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

The sdist does not contain its own hash. The plugin zip is unchanged.

## Human steps still open

Developer ID signing and notarization of the verifier. Touch ID or password for `SecureEnclave.P256.Signing.PrivateKey`. Public-key fingerprint confirmation. Paired-phone enrollment. Privileged holder install. The final bounded run. APPROVE and `--human-invoked` were not used.
