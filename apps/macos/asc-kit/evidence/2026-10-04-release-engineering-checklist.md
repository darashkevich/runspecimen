# Release engineering checklist — 2026-10-04

Code SHA: `333dc70918905ee026ef3c0482f7ad96f5b7d68d`. The candidate tip is the evidence commit whose parent is that SHA. This file is the resume point. It is not a production sign-off.

Unmade decision, still refused: what evidence, other than an origin string or a pin match, identifies the Secure Enclave key so installed protection can accept its exact-run signature. D1 stays team `UN6KF8636A`, identifier `com.darashkevich.runspecimen.native-p256-verify`, and the designated requirement recorded for that pair. A pin match authenticates verifier code only.

## Status

1. Trusted enrollment and phone receipts. Done for the software session path. Phone commit requires a holder receipt signed by the pinned Mac key. Tests: `test_phone_receipt_rejects_forged_flags_wrong_key_replay_and_stale`, `test_phone_invalidate_clears_signature_and_verification_is_not_enrollment`, `testForgedFlagsWrongKeyChallengeReplayCancelAndStaleDoNotCommit`. Installed Secure Enclave admission remains the unmade decision.
2. UI path to snapshot-bound execute. The Sign with session key control calls `issue-exact-run`, `authorize-exact-run`, and `execute-exact-run`. Local excludes a phone-only signature. Companion and dual require the phone key. Tests: `test_exact_run_signature_authorizes_one_nonce_and_refuses_software`, `test_exact_run_companion_and_dual_require_the_phone_key`, `test_exact_run_expiry_and_generation_do_not_reach_the_lease`. `run_integration_complete` stays false. Installed protection still refuses a software double. Not closed.
3. Swift and iOS client tests. Done for this pass. `HolderSocketClientTests` 12 passed in `/private/tmp/rs-qa-receipt-swift`, including `testRestartAndConcurrentExchangesBothComplete`, `testSaturatedBacklogConnectDoesNotBlock`, `testNonreadingPeerStopsTheWrite`, `testPeerCloseDoesNotRaiseSIGPIPE`, and `testStagedCustodyCommitFailureKeepsThePreviousGeneration`. Phone tests passed in `/private/tmp/rs-qa-receipt-phone`, including cancellation and `testPhoneKeyCommitFailureKeepsThePreviousGeneration`.
4. Developer ID package preparation. Done as preparation only. Temp-root install, update, and rollback printed `NOT_INSTALLED=1` and were deleted. Staged tar `1464bda1f1f174b01adb592816819f9bb9afea5bb547e982133a0272014ff323`. Not installed and not notarized.
5. GUI receipt compare, diff, and retain. Not re-driven on this SHA. Earlier sessions are not this candidate. Still engineering. If a later bundle has no holder, that session is not holder acceptance.
6. Ledger and PR comments. The external ledger is appended and does not close E2. PR #39 has no comment newer than 2026-10-02. PRs 40-45 are not open. None were merged.
7. Channel matrix. `docs/CHANNEL_MATRIX.md` keeps Store as guarantee (1) and the Developer ID holder as guarantee (2). CLI, plugins, and iOS stay unpublished. The Store app does not carry the Developer ID pin. Hashes for this tip are in the evidence file, not in the sdist.
8. Regressions. `release_check` on Homebrew Python 3.12.14: 627 tests, 35 skipped, then 4 tests, exit 0. Artifacts: `artifacts/rc15-2026-10-04-qa-py312-receipt/`. Wheel `f6a57ae99acdfe987260c6c92df9c45e57905897f1872c800914a30e8249d49c`. Sdist `79e94a7c01b3f01069f1a1fb29610862d72e4b43b0e4cc5a2b23330b219ce7ce`. Plugin unchanged `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`. CI is recorded after the push. CI green is not readiness.

## Human acceptance, not performed

1. Enroll with Secure Enclave on the holder and confirm Touch ID or Face ID yourself. Copy the printed Mac session public key into RunSpecimenObserve. Do not treat that copy as Secure Enclave admission.
2. Pair with the companion URL and token from `runspecimen companion --print-token`. Publish a phone challenge, sign it on the phone, then accept it on the Mac in the same session so the holder can seal the receipt. Confirm a forged verified flag does not enroll the phone key.
3. Run one harmless local exact run, one companion run, and one dual run from the snapshot fields. Confirm a phone-only signature is refused for local, a Mac-only signature is refused for companion, and dual requires both.
4. Cancel a phone challenge before it posts, and confirm a late cancel does not enroll. Revoke the phone key and confirm the next receipt is refused. Replay the same receipt and confirm the second commit is refused.
5. Qualify an exact archive separately. Do not treat this package tar or a green CI run as that qualification.

## Installed-app crash, diagnosis stopped

On 2026-10-04 at 16:29, `/Applications/RunSpecimen.app` pid 38191, bundle `com.darashkevich.runspecimen`, version 0.1.5 (12), was EXC_CRASH SIGKILL, Taskgated Invalid Signature, incident `663D979D-DC02-42EB-9485-479368CDEB6A`. `codesign --verify --strict --verbose=4` said the app is valid on disk and satisfies its Designated Requirement. Authority is Apple Distribution: YAHOR DARASHKEVICH (UN6KF8636A). There is no `_MASReceipt` and the staple is absent, so a direct launchd start is rejected. The bundle mtime is `2026-09-26 13:56:03`. `/Applications/RunSpecimen Holder.app` mtime is `2026-09-30 15:19:13`. Neither app was re-signed, replaced, or repaired, and daemon pid 42554 was not signaled.
