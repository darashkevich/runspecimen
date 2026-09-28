# Release scope — 2026-09-27

This candidate is not a production release. Packaging still uses public `0.2.0rc14` identifiers. Do not replace those artifacts or retag them. Independent QA of `cd8b860` passed its claimed fixes and is not production sign-off. Nothing here is merged to `main` or submitted to Apple.

App Store Connect currently has macOS **0.1.4 (9)** `READY_FOR_SALE` (build `51a18894-02e3-4846-86f5-29cc345567f0`, source `0f50a2c` plus rejection fixes). That version stays as it is.

Proposed update scope, **not agreed**: ship the stable native and engine work on this branch (capture, secrets, receipts, About/Settings, fast path) as a new version such as **0.1.6 (1)**. Keep the biometric prototype and companion transport out of that binary's behavior. They stay on the branch as a non-gate prototype until Yahor accepts that split. No Store package is built until that agreement.

## Included on `cursor/integrated-release-candidate`

| Item | Commit / location | Tests | Platform | Blocker |
| --- | --- | --- | --- | --- |
| Evidence-expansion engine and native workflows (requirements, freshness, config, decisions, snapshots, usage, coordination, eval, scenes) | PR #34 line through `92fd4cc`, plus this branch | Python evidence tests; Swift workflow gate | macOS app and CLI | Not merged. Store binary in review does not contain it |
| Confirmation-dialog race and concurrent pipe drain | `d7c61a9` and the capture helper on this branch | `WorkflowConfirmationGateTests`, capture drain tests | macOS | None in unit tests |
| Explicit truncation, malformed JSON, and plain-text capture failures | Capture decoder and `CLIService.run` on this branch | `BoundedProcessCaptureTests`, including injected read and cleanup failures for the plain-text path | macOS | None in unit tests |
| Owned process-group cleanup after the leader exits | This branch, `BoundedProcessCapture.swift` | Parent-exits, ignored SIGTERM, grandchild, flood, cancellation, cleanup-failure classification | macOS | A descendant that leaves the owned group cannot be killed safely. That case is reported only when the group signal fails or a member remains |
| Nested config secret names | This branch, `configsync.py` | `ConfigSecretStripTests` | CLI | Key-name matching does not see secrets under ordinary names or inside notes |
| About sheet Close and Escape | This branch, `AboutView.swift` | Clicked on the development-signed app built from `f77a7c9` | macOS | That app is not a Store package and is not the later biometric commit |
| Receipt digest, diff, and confirmed retain | Ported onto the workflow sheet on this branch | Existing CLI receipt tests. Native sheet has no separate UI test | macOS and CLI | Retain still needs a confirmed workflow. It does not approve |
| Deterministic eval fast path | PR #38, merged onto this branch | `tests/test_fastpath.py` | CLI only | Must not be described as a native control |
| Local biometric prototype | This branch, `BiometricApproval.swift` | Software-key enrollment, field binding, tamper, replay, restart, user-writable rollback, and a blocked consume that loses to revoke | macOS | Not an execution gate. Secure Enclave signing has not had a real Touch ID prompt. Companion transport and privileged enforcement are separate undecided choices |

## Preserved and not merged into this candidate

| Item | Where it lives | Why it is not in this candidate |
| --- | --- | --- |
| Primary checkout dirty files, including iOS icon PNGs and the `Info-mas 2` / entitlements `2` copies | `/Users/yahor/Documents/Codex/2026-08-24/how-x20` | The checkout is behind the evidence branch. The `2` files look like accidental duplicates. Left untouched |
| PR #35 Cloud Agent environment | `.cursor/environment.json` on its own branch | Development-environment config, separate from the product |
| App Store submission `0.1.4 (9)` | Apple, unchanged | Do not withdraw or replace it without an explicit decision |

## Not delivered

- Biometric approval as an execution requirement. The prototype does not run a command.
- A real Secure Enclave or Touch ID exercise. Software-key tests are not that evidence.
- Companion or dual approval, a relay, or a privileged helper.
- Hardware-backed enforcement against a same-user agent.
- A new engine version, tag, wheel, or sdist. `0.2.0rc14` stays the published release.
- A new Apple build number or an uploaded Store package.
- A Store-package check that About closes. The development-signed `f77a7c9` app did dismiss About with Close and with Escape.
- Linux bubblewrap execution in this session.
- Marketplace or PyPI publication.
