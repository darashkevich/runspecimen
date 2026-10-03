# Production boundary control flow

QA instruction: tip `1927a16` / code `ef64c35` is not production readiness. `allowsProductionEnrollment` was an unconditional false, `production_verifier_pin()` is unset, and installed signature verification refused every path. Continue the native enroll, pair, and sign-into-holder path for local, companion, and dual by injecting a boundary double and a test pin. Do not write a proposed identity into the shipped pin. Do not call that proposal production. Do not prompt for biometrics. Do not install, publish, merge, notarize, or submit.

Comments read after 2026-10-02:

- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5947032334 (2026-10-02T06:58:01Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5947032550 (2026-10-02T06:58:02Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5947249102 (2026-10-02T07:17:46Z)
- https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5947249301 (2026-10-02T07:17:47Z)

Those comments said stop and said not to stub the pin with a real team. This pass follows the later instruction to finish the source path and to keep the proposal out of `production_verifier_pin()`.

Code SHA: `4b9755b66c5e60968cf3e432dd5e907f027d8393`. The candidate tip is the commit that adds this sentence; its parent is that code SHA.

This note is not production sign-off. The pin was not authorized. Nothing here was installed, published, merged, notarized, or submitted. No biometric prompt was run. No Secure Enclave private key was created. The live holder was not repaired. CI green is not readiness.

## Control flow

Local, companion, and dual enroll, pair, and sign into holder consume and execute when the backend is `production-boundary-double-not-hardware`, the provenance is `native-production-bridge`, a pin is injected, and the verifier team identifier and designated requirement match. The boundary double is not hardware. A caller that claims hardware is refused. An unset pin is refused. A display string that contains "Developer ID" is refused. A passing record stores `hardware: false`.

`allowsProductionEnrollment` follows that flow. It stays false for Secure Enclave key creation and for any call that claims hardware. It is true only when the boundary backend, production provenance, injected pin, and connected verifier are all present and hardware is false. Two-argument calls stay false.

Installed signature verification checks the injected or configured pin and `codesign --verify --strict`. The shipped `production_verifier_pin()` still returns none, so the installed path fails closed. `TESTTEAMID` is a test fixture.

Cancellation, revocation, exact-run binding, replay, caller rotation, mutated launch, restart, protocol downgrade, concurrent double-consume, relative-interpreter refusal, closed-gate refusal, lease retention on supervision uncertainty, and non-world-readable snapshots that omit enrollment, policy, spent nonces, and leases stay on the existing suite. Replay on the boundary path raises `already consumed`.

## Unconfirmed proposal

This is a candidate for Yahor to confirm. It is not the shipped pin and it is not production.

The login keychain already had `Developer ID Application: YAHOR DARASHKEVICH (UN6KF8636A)`. Signing a copy of the verifier with that identity did not prompt. No new identity was stored. The repository binary stays ad-hoc.

- Team ID candidate: `UN6KF8636A`
- Verifier identifier candidate: `com.darashkevich.runspecimen.native-p256-verify`
- Designated requirement candidate, from `codesign -d -r-` of the signed copy: `identifier "com.darashkevich.runspecimen.native-p256-verify" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ and certificate leaf[field.1.2.840.113635.100.6.1.13] /* exists */ and certificate leaf[subject.OU] = UN6KF8636A`
- Signed copy SHA-256: `353203f46757b1ea6c4685ba8b24633b88a6243c90fa75de240e1eab776d5b71`

## Rotation plan

This is a plan. It was not installed.

A later pin change is enrolled only after the current pin accepts the new team identifier and designated requirement. Until that enrollment is stored, the previous pin remains the only accepted identity. An old verifier is revoked by recording its team identifier and designated requirement so a later verify of that identity fails closed. A missing pin fails closed: `production_verifier_pin()` returns none, and identity verification raises before consume or execute when nothing is injected. Display text is not a substitute.

## Tests

`tests/test_production_boundary.py`:

- `test_shipped_pin_is_unset_and_refuses_the_boundary`
- `test_hardware_claim_is_refused`
- `test_display_text_wrong_team_and_wrong_requirement_are_refused`
- `test_boundary_signers_connect_for_local_and_phone`
- `test_replay_stays_refused_on_the_boundary_path`
- `test_local_companion_and_dual_boundary_execute`
- `test_pure_package_omits_verifier_and_artifact_resolves_it`

Focused Python before `release_check`: those tests plus the isolated-enrollment module and `test_cryptokit_p256_authorizes_a_bounded_run_and_is_not_hardware`. Swift `testCarriedPinIgnoresTheFilesSecureEnclaveLabel` passed. The pure wheel and sdist do not contain `runspecimen/platform/darwin_arm64/native_p256_verify`. `doctor`, `validate`, and `status` do not enroll when that Mach-O is absent; they report it absent and production enrollment fails closed. The plugin does not ship the verifier, does not pass a holder, and only calls the CLI. The plugin zip is unchanged.

## Local release_check

Homebrew Python 3.12.14, `/tmp/rs-py312-rel-holder`. 559 tests, 35 skipped. Apple `/usr/bin/python3` was not used.

Directory: `artifacts/rc15-2026-10-02-qa-py312-boundary/`

| Artifact | SHA-256 |
| --- | --- |
| wheel | `33476ce3541d0431b2679511274a9b5dc4447fa1b95849de60e2e7bb91b0a7d1` |
| sdist | `925dce42a1bcaddcc7ee08fc7200f3cbf6398040ce309244ad43b4d9cdabb7bd` |
| plugin | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |
| Developer ID verifier zip | `ad9dd78af4e5fb467251868eecf9c7bf0426d4d04e60b6deca7b0c85a5376e90` |

The zip member is `runspecimen/platform/darwin_arm64/native_p256_verify`. The sdist does not contain that Mach-O, its own hash, or the zip hash. Older rc15 directories were not overwritten.

## Development app

Built from code SHA `4b9755b66c5e60968cf3e432dd5e907f027d8393` in `/tmp/rs-qa-boundary-derived`. Not installed. Development signature only. No `-allowProvisioningUpdates`.

Main executable SHA-256 `f9f3ae13fe56e30270bad6a0291a51d7eff9293c1d7bb5c31c170918b5619a95`.

Authority `Apple Development: jahorka@gmail.com (PK6W7JVY6D)`. TeamIdentifier `UN6KF8636A`. Sandbox is on. `com.apple.security.network.client` is present. `com.apple.security.network.server` is absent. `com.apple.security.get-task-allow` is absent. The bundle contains no holder. This is not holder acceptance. The `27bb0c7`, `91081f5`, and `/tmp/rs-qa-enroll-derived` builds were not reused.

Receipts on the bundled reviewer demo, which is approved and has no certificate:

- Digest: `certificate not found for reviewer-demo/run-001`.
- Compare (`digest --live`): the same refusal. There is no certificate to compare.
- Diff against campaign `reviewer-demo` run `run-000`: the displayed error stayed `certificate not found for reviewer-demo/run-001`, which is the selected receipt diff loads first.
- Retain, after choosing `/tmp/rs-qa-retain-boundary` and confirming: wrote `state.json`, `events.jsonl`, `approval.json`, and `manifest.json`. Kind `retained_incident_bundle`. `certificate_id` is null. Created `2026-10-02T14:24:34Z`. Manifest SHA-256 `8d85b1fb0070ba7f20515111b73fd8da1a4d7902e195753dec4448942f4e4c69`. No upload.

The app container was backed up and restored. Only QA pid 9687 was stopped. `/Applications/RunSpecimen.app` stayed `2026-09-26 13:56:03`. `/Applications/RunSpecimen Holder.app` stayed `2026-09-30 15:19:13`. Daemon pid 42554 was still running.

## Wording

The workflows status, FAQ, scope matrix, gate ledger, and native-bridge note no longer say the only remaining gap is a person. They say source integration and trust configuration remain open, the shipped pin is unset, and a display name is not a pin.

## Human gates, not performed

1. Biometric enrollment. `SecureEnclave.P256.Signing.PrivateKey` was not called.
2. Fingerprint confirmation for the Mac key and the paired phone key.
3. Privileged holder install. The live holder was not replaced.
4. One real bounded run. APPROVE was not typed and `--human-invoked` was not used.

Confirming `UN6KF8636A` and the designated requirement above is a separate human decision. Until that happens the shipped pin stays unset.
