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
| RSBA2 local, companion, and dual policies | `PolicyBoundApprovalStore` | `PolicyBoundApprovalTests` | Store only. Not the workspace lease | Execution boundary below |
| User-mediated companion package | `importUserMediatedPackage` | Import and `present_at_mac` rejection | No socket | Automatic delivery is a separate decision |
| iOS carried-approval screen | Observe shows the package and refuses to sign | Simulator compile succeeded. No device test | No Face ID call | Real device signing is a human step |
| Touch ID diagnostic | `preview` does not prompt. enroll/sign/reload/cancel/revoke require `--human-invoked` | Gate test. Human path skipped | Isolated `/tmp` directory | Yahor must run the prompt |
| Store browser dashboard | Excluded from the Store channel | Store policy test | Unchanged | Do not add `network.server` |
| Privileged helper / relay | Not built | n/a | n/a | Needs an explicit decision |

Software-key tests, a writable consumed marker, and an authentication callback are not a protected execution boundary.
