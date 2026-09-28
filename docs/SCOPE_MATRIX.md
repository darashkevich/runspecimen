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
| RSBA2 local, companion, and dual policies | `PolicyBoundApprovalStore`. Generations are inside the signed bytes. Consume rechecks dual keys | `PolicyBoundApprovalTests`, including generation rewrite, unknown version, and a crafted same-key record | Store only. Not the workspace lease | Execution boundary in `docs/EXECUTOR_PROTECTION.md` |
| User-mediated companion package | `importUserMediatedPackage` accepts only exact `RSBA2` | Import, unknown version, unknown key, non-canonical generation, `present_at_mac` | No socket | Automatic delivery is a separate decision |
| iOS carried-approval screen | Shared `RSBA2Package` parser. Development software P-256 signer on the preview screen | Simulator compile. No device test. No Face ID | Signature stays on the phone | Face ID / Secure Enclave on device is a human decision. Preview is not feature completion |
| Touch ID diagnostic | `preview` does not prompt. sign/reload/cancel print the exact request before Secure Enclave. enroll/sign/reload/cancel/revoke require `--human-invoked` | Gate test, including traversal and bare `/tmp`. Human path skipped | Directory must resolve under `/private/tmp/rs-touchid-diag`. Diagnostic keychain service is separate | Yahor must run the prompt |
| Store browser dashboard | Excluded from the Store channel | Store policy test | Unchanged | Do not add `network.server` |
| Privileged helper / relay | Not built. Design only in `docs/EXECUTOR_PROTECTION.md` | n/a | n/a | A helper is not assumed to meet the anti-replacement goal or to be Store-feasible |

Software-key tests, a writable consumed marker, and an authentication callback are not a protected execution boundary.
