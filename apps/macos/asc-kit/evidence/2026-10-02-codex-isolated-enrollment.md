# Isolated native enrollment

QA instruction: implement the trusted enrollment, pairing, and signing path for local, phone, and dual with an isolated double. Do not add another refusal stub. Validate the verifier by team identifier and designated requirement, not by display text that contains "Developer ID". Place the helper where the holder loads it, and keep it out of the pure wheel. The bridge is engineering, not a wait on Yahor.

Comments read:

- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5935697881 (2026-10-01T16:23:50Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5947032334 (2026-10-02T06:58:01Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5947032550 (2026-10-02T06:58:02Z)

PRs #40–#45 had no new review comments. The only issue comment after 16:23:50Z on those pulls is the earlier close of #44.

Code SHA: `ef64c35993449869408f5dc68a4aaa25866ed0c5`. The candidate tip is the commit that adds this sentence; its parent is that code SHA.

This note is not production sign-off. Nothing here was installed, published, merged, notarized, or submitted. No biometric prompt was run. No Secure Enclave private key was created. The live holder was not repaired. CI green is not readiness.

## What changed

`native_signers_connected` reports mac and phone roles that paired through `isolated-native-bridge-double-not-hardware`. It no longer returns a hardcoded false. Installed protection still refuses that double. `production_verifier_pin()` stays unset. A codesign display line that contains "Developer ID" does not match a pin.

Before this change, `packaged_verifier_publisher()` returned `publisher_trusted: True` for `Authority=Developer ID Application: Not A Pin` with `TeamIdentifier=WRONGTEAM`. After, identity match is false unless both the team and the designated requirement equal the pin.

The phone peer key uses the existing pairing record: role `phone`, public key, fingerprint, generation, and policy inside the canonical challenge. No new phone channel was invented.

## Tests

`test_developer_id_display_text_is_not_sufficient`, `test_wrong_team_is_refused`, `test_wrong_designated_requirement_is_refused`, `test_installed_protection_refuses_the_isolated_double`, `test_signers_connected_follow_paired_roles`, `test_local_companion_and_dual_isolated_execute` (local, companion, and dual, `hardware: false`). Focused run: 14 tests, OK.

Swift `testCarriedPinIgnoresTheFilesSecureEnclaveLabel` passed. `IsolatedNativeEnrollment.complete` records local and companion with `hardware == false`. `allowsProductionEnrollment` stays false.

## Local release_check

Homebrew Python 3.12.14, `/tmp/rs-py312-rel-holder`. 552 tests, 35 skipped. Apple `/usr/bin/python3` was not used.

Directory: `artifacts/rc15-2026-10-02-qa-py312-enroll/`

| Artifact | SHA-256 |
| --- | --- |
| wheel | `08bf99f001de581648735276576e2e8bf8b7a7841d84bc24c42459e57b65061f` |
| sdist | `2d7920be5616f7cdeb0fd03f9f01e8d41d94fcc3c558d128709f47473a460655` |
| plugin | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

The sdist does not contain its own hash or `native_p256_verify`. The plugin zip is unchanged. Older rc15 directories were not overwritten.

## Development app

GUI sources changed. Temp Release build, Sign to Run Locally, not installed:

`/tmp/rs-qa-enroll-derived/Build/Products/Release/RunSpecimen.app`

Main executable SHA-256 `7dc62322fea0399a223e7e35fd98e071d309bfd97e7adca11d90187692ad0124`.

Signature is ad-hoc. TeamIdentifier is not set. Sandbox is on. `com.apple.security.network.client` is present. `com.apple.security.network.server` is absent. `com.apple.security.get-task-allow` is absent. The bundle contains no holder. This is not GUI acceptance. The earlier builds of `27bb0c7` app sources were not reused.

## Human acceptance steps, not run

1. Biometric enrollment via `SecureEnclave.P256.Signing.PrivateKey` (Touch ID, Face ID, or a password prompt).
2. Fingerprint confirmation for the Mac key and the paired phone key.
3. Privileged holder install. The live holder was not replaced.
4. One real bounded run. APPROVE and `--human-invoked` were not used.

## Blocking design decision

The production team identifier and the designated requirement string for the verifier are not in the protocol. `production_verifier_pin()` returns none. The test pin `TESTTEAMID` is a fixture and is not a production identity.
