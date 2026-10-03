# Codex recheck of 56ee890

Comment: https://github.com/darashkevich/runspecimen/pull/39#issuecomment-5932238955

Code SHA: `888b2c718ea492c26a8288eb70457f1d8ab882f8`. The candidate tip is the commit that adds this sentence; its parent is that code SHA.

PRs #40–#45 had no comments newer than that recheck. This note is not production sign-off. Nothing here was installed, published, merged, or submitted. No biometric prompt was run. The live holder was not repaired.

The GUI app sources did not change. The previous development GUI remains the build of `27bb0c7` app sources at `/tmp/rs-qa-codex-20261001/DerivedData/Build/Products/Release/RunSpecimen.app`. That bundle has no holder. This pass does not claim a new GUI acceptance.

## Already satisfied on 56ee890

Handwritten production crypto stays removed. `RS_HOLDER_SOCKET` stays ignored. Software test doubles stay refused when installed protection is on. Leases stay held when supervision is uncertain. Snapshots stay non-world-readable and omit enrollment, policy, spent nonces, and leases.

## Fixed here

1. **Snapshot cleanup and the positive execute test.** Dry-bind seals directories `0500`, so `shutil.rmtree(ignore_errors=True)` left the tree and the next consume raised `payload snapshot token already exists`. Cleanup now restores owner write and fails if the tree remains. `test_bootstrap_and_signed_local_execute_from_snapshots` still checks the PyNaCl-absent refusal, then runs snapshot execute instead of returning early. Test: `test_bootstrap_and_signed_local_execute_from_snapshots` (OK).

2. **Payload ownership.** Root seal no longer chowns the snapshot to the payload uid. An owner can chmod `0400` back to writable; that attack is `test_owner_chmod_mutates_and_root_seal_does_not_chown_payload` (OK). Root grants read with an ACL and keeps holder ownership. A failed grant fails closed.

3. **Double-fork supervision.** The payload stays paused until a fork watch is armed. A Darwin fork note does not identify the child, so `descendants_absent` stays false and the lease is kept. Signaling requires a matching start stamp. Test: `test_double_fork_setsid_retains_the_lease` (OK). The synthetic PPID test remains and is not the proof.

4. **Symbol gate wiring.** `apps/ios/Scripts/verify_ios_release_symbols.sh` runs the negative unittest and a Debug object that defines `beforeFinalSignatureDecision` (must fail) plus a clean object (must pass). CI calls it before `release_check`. No iOS app was installed. No provisioning update. This is not a device Release proof.

5. **Ed25519 is not hardware.** `test_vetted_ed25519_is_not_secure_enclave_approval` (OK). Actual Secure Enclave P-256 enrollment still needs a person. Production stays fail-closed. That item was not implemented as a software double.

## Local release_check

Homebrew Python 3.12.14, `/tmp/rs-py312-rel-holder`. 525 tests, 35 skipped. Apple `/usr/bin/python3` was not used.

Directory: `artifacts/rc15-2026-10-01-qa-py312-recheck/`

| Artifact | SHA-256 |
| --- | --- |
| wheel | `de8d2b5b3d1bf09d263489578c9a974b0255759a6b5f2bfa51f1a8d25b2064f2` |
| sdist | `c4bb5d28269eb54307fccbcdcf5f083858f3439acf18fb57670087c02a1c16f6` |
| plugin | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

The sdist does not contain its own hash. The plugin zip is unchanged. No Store package.
