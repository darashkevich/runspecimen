# Scope matrix

Unpublished candidate on `cursor/integrated-release-candidate`. Approved macOS **0.1.4 (9)** stays as it is. This is not a Store submission.

| Feature | Implementation | Tests | Integration | Blocker |
| --- | --- | --- | --- | --- |
| Capture, pipe-read and cleanup failures | On the branch since `cd8b860` | Swift capture suite | CLI and app share the decoder | None for the prototype |
| Receipts, workspace and contract guards | App workflows and `SessionRestore` | Swift session tests; development-app pass recorded in `apps/macos/asc-kit/evidence/2026-09-28-rc15-acceptance.md` | Development app only | A large captured run still waits for a person to type APPROVE |
| Fast path | PR #38 is in this branch | Existing eval tests | In the candidate | None known on this tip |
| PR #34 evidence expansion | Integrated on this branch, not merged | Python expansion tests | In the candidate | PR #34 itself remains open against its own base |
| PR #35 dev environment | Not product code | n/a | Not required for the app | None |
| Engine identity | Unpublished `0.2.0rc15` / plugin `0.2.0-rc.15` | `release_check.py` local build | Manifest `docs/CANDIDATE_MANIFEST.md` | Do not replace published rc14 bytes |
| Settings Close | AppKit button, Escape still dismisses | Development-app accessibility pass | In the macOS app | None |
| RSBA1 local biometric consume | Store, enrollment lock, expiry inside the lock | Swift biometric suite, one human Secure Enclave skip | Not called by any run | Not hardware proof |
| RSBA2 local, companion, and dual policies | `PolicyBoundApprovalStore`. Generations are inside the signed bytes. Consume rechecks dual keys, role, and backend | `PolicyBoundApprovalTests`, including generation rewrite, swapped role, and development-backend rejection | Store only. `consumeForExecution` is not the workspace lease | Executor recommendation in `docs/EXECUTOR_PROTECTION.md` |
| User-mediated companion package | `RSBA2Package.parse` is a complete request. Missing, empty, NUL, and inconsistent role fields fail | Mac and iOS schema tests share that parser | No socket | Automatic delivery is a separate decision |
| iOS carried-approval screen | Shipping preview only displays and clears stale state on edit. Software signer is `RunSpecimenObserveDev` only | Shipping target exclusion test. Simulator schema tests call hardware methods with `humanTap: false` | Public pairing file. No relay | Yahor must tap Face ID on a device. A software signature is not completion |
| iOS Secure Enclave companion | `CompanionSecureEnclaveEnrollment` persists role `companion`, backend `secure-enclave`, provenance `production`. Revoke bumps generation | Automated tests return before Secure Enclave | Not invoked by an agent | Device prompt is human-operated |
| Touch ID diagnostic | Filesystem-order symlink resolution. Hop exhaustion fails closed. Writes use an owned directory descriptor | Symlink-then-parent, missing leaf, root symlink, 17 hops, directory replacement. Human path skipped | Directory must resolve under `/private/tmp/rs-touchid-diag` | Yahor must run the prompt |
| Store browser dashboard | Excluded from the Store channel | Store policy test | Unchanged | Do not add `network.server` |
| Privileged helper / relay | Not built. Recommendation is the sandboxed app container, in `docs/EXECUTOR_PROTECTION.md` | n/a | n/a | One authorization: Developer ID helper, or stay in the sandboxed app |

Software-key tests, a writable consumed marker, and an authentication callback are not a protected execution boundary.
