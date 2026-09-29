# Scope matrix

Unpublished candidate on `cursor/integrated-release-candidate`. Approved macOS **0.1.4 (9)** stays as it is. This is not a Store submission.

Completion gates for the current tip. "Implemented" means the code exists. "Integrated" means a real run or the Store archive uses it. "Auto" means a unit or GUI automation test. "Human" means a person completed the hardware or approval step. "Release" means the exact Store package for this commit passed the qualification checks.

| Gate | Implemented | Integrated | Auto | Human | Release |
| --- | --- | --- | --- | --- | --- |
| App refuses its own transition (guarantee 1) | Yes | CLI and development app | Yes | A large run still needs a person at the terminal | No |
| Same-user trust state (guarantee 2) | Design revised. Not built | No | Adversarial test shows the workspace lease inode can be replaced. A sandboxed Store-entitlement app could not reach a live Mach service | No | No |
| Global command blocking (guarantee 3) | Excluded | No | No | No | No |
| Biometric policies local / companion / dual | Store and iOS enroll/sign | Not the run path | Swift and simulator, no Secure Enclave | No | No |
| Protected pairing | Carried file and fingerprint comparison described | No relay | Label is not attestation | No | No |
| Receipts and confirmation | Yes | Development app | Fresh GUI on the same development app: negative reviewer digest, synthetic digest, diff, and missing-run diff | No | No |
| Release source isolation | Yes, `archive_mas.sh` | Not a Store archive of this tip | Prelude tests | No | No |
| Store package for this commit | No | No | Symbol and identity suites | No | No |

| Feature | Implementation | Tests | Integration | Blocker |
| --- | --- | --- | --- | --- |
| Capture, pipe-read and cleanup failures | On the branch since `cd8b860` | Swift capture suite | CLI and app share the decoder | None for the prototype |
| Receipts, workspace and contract guards | App workflows and `SessionRestore`. Retain confirmation is an in-sheet panel | Swift session tests; development-app digest, compare, diff, retain cancel, and retain confirm on a labeled synthetic fixture in `apps/macos/asc-kit/evidence/2026-09-28-rc15-acceptance.md` | Development app only. The fixture is not a human-approved run | A large captured run still waits for a person to type APPROVE |
| Fast path | PR #38 is in this branch | Existing eval tests | In the candidate | None known on this tip |
| PR #34 evidence expansion | Integrated on this branch, not merged | Python expansion tests | In the candidate | PR #34 itself remains open against its own base |
| PR #35 dev environment | Not product code | n/a | Not required for the app | None |
| Engine identity | Unpublished `0.2.0rc15` / plugin `0.2.0-rc.15` | `release_check.py` local build | Manifest `docs/CANDIDATE_MANIFEST.md` | Do not replace published rc14 bytes |
| Settings Close | AppKit button, Escape still dismisses | Development-app accessibility pass | In the macOS app | None |
| RSBA1 local biometric consume | Store, enrollment lock, expiry inside the lock | Swift biometric suite, one human Secure Enclave skip | Not called by any run | Not hardware proof |
| RSBA2 local, companion, and dual policies | `PolicyBoundApprovalStore`. Generations are inside the signed bytes. Consume rechecks dual keys, role, and backend | `PolicyBoundApprovalTests`, including generation rewrite, swapped role, and development-backend rejection | Store only. `consumeForExecution` is not the workspace lease. `evaluateExecution` does not start a run | Yahor chose guarantee (2). It is not implemented. The run must not treat this store as that boundary |
| User-mediated companion package | Parser plus Workflows “Carried approval”. A mismatched policy choice does not switch the package | Mac and iOS schema tests. Pin ignores a file’s Secure Enclave label | No socket. Not a device enrollment | Automatic delivery is a separate decision |
| iOS carried-approval screen | Shipping preview displays and clears stale state on edit. Sign refuses when the editor no longer matches the displayed request. Software signer is `RunSpecimenObserveDev` only | Shipping target exclusion test. Simulator tests call `automationRefused()` and do not call Secure Enclave | Public pairing file. No relay | Yahor must tap Face ID on a device. A software signature is not completion |
| iOS Secure Enclave companion | Buttons call enroll, sign, revoke, and rotate. Enroll creates a key only for a missing file. The post-wait reload, expiry, and revocation decision share the enrollment lock. Revoke writes the record before deleting the key | File-only enroll failures, hook revocation, public revoke blocked until finalize releases the lock, expiry-at-decision, stale-display, and lock-race tests. No Secure Enclave call in tests | Not invoked by an agent | Device prompt is human-operated. Re-enrollment after revoke is not a recovery flow |
| Touch ID diagnostic | Filesystem-order symlink resolution. Hop exhaustion fails closed. Interrupted and partial writes delete the new file | Symlink-then-parent, hop limit, directory replacement, partial write, failed fsync. Human path skipped | Directory must resolve under `/private/tmp/rs-touchid-diag` | Yahor must run the prompt |
| Store browser dashboard | Excluded from the Store channel | Store policy test | Unchanged | Do not add `network.server` |
| Protected RunSpecimen state | Yahor chose guarantee (2). The architecture is an embedded root daemon that spawns the command as the console user. It is not installed. Guarantee (3) is excluded. Verification code is not the run path | `tests/test_lease.py` shows a same-user unlink replaces the held lease inode and a workspace marker can be restored. That test passing means guarantee (2) is absent | Not wired to `run.py`. `consumeForExecution` is not called | Authorize the embedded daemon and one app-group entitlement, or leave (2) unimplemented on the Store channel. See `docs/EXECUTOR_PROTECTION.md` |
| Rejected private API symbols | `scan` checks every architecture slice. A tool failure is a violation. The CPython module name `_lzma` is not a violation. `record-identity` writes an integrity record of the file map, artifact hash, and caller-supplied git metadata. It is not a cryptographic source attestation. `RS_RELEASE_GATE=1` checks the caller, then freezes and generates inside a detached worktree of the expected SHA. A dirty or different caller never reaches freeze. A commit during freeze fails before project generation | `tests/test_rejected_runtime_symbols.py`, `tests/test_runtime_identity_cli.py`, and `tests/test_release_source_prelude.py` | `export_mas.sh` still rejects a dirty or different commit. A development archive may be dirty and cannot pass export | Do not strip the module name out of CPython |

Software-key tests, a writable consumed marker, and an authentication callback are not a protected execution boundary.
