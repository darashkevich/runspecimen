# Release scope — 2026-09-27

This candidate is not a production release. Packaging still uses public `0.2.0rc14` identifiers. Do not replace those artifacts or retag them. Independent QA has not accepted this tip. Nothing here is merged to `main` or submitted to Apple.

## Included on `cursor/integrated-release-candidate`

| Item | Commit / location | Tests | Platform | Blocker |
| --- | --- | --- | --- | --- |
| Evidence-expansion engine and native workflows (requirements, freshness, config, decisions, snapshots, usage, coordination, eval, scenes) | PR #34 line through `92fd4cc`, plus this branch | Python evidence tests; Swift workflow gate | macOS app and CLI | Not merged. Store binary in review does not contain it |
| Confirmation-dialog race and concurrent pipe drain | `d7c61a9` and the capture helper on this branch | `WorkflowConfirmationGateTests`, capture drain tests | macOS | None in unit tests |
| Explicit truncation and malformed JSON errors | Capture decoder on this branch | `BoundedProcessCaptureTests` | macOS | None in unit tests |
| Owned process-group cleanup after the leader exits | This branch, `BoundedProcessCapture.swift` | Parent-exits, ignored SIGTERM, grandchild, flood, cancellation, cleanup-failure classification | macOS | A descendant that leaves the owned group cannot be killed safely. That case is reported only when the group signal fails or a member remains |
| Nested config secret names | This branch, `configsync.py` | `ConfigSecretStripTests` | CLI | Key-name matching does not see secrets under ordinary names or inside notes |
| About sheet Close and Escape | This branch, `AboutView.swift` | App target compiles. Running-app check still required | macOS | Not yet clicked on a launched app |
| Receipt digest, diff, and confirmed retain | Ported onto the workflow sheet on this branch | Existing CLI receipt tests. Native sheet has no separate UI test | macOS and CLI | Retain still needs a confirmed workflow. It does not approve |
| Deterministic eval fast path | PR #38, merged onto this branch | `tests/test_fastpath.py` | CLI only | Must not be described as a native control |

## Preserved and not merged into this candidate

| Item | Where it lives | Why it is not in this candidate |
| --- | --- | --- |
| Primary checkout dirty files, including iOS icon PNGs and the `Info-mas 2` / entitlements `2` copies | `/Users/yahor/Documents/Codex/2026-08-24/how-x20` | The checkout is behind the evidence branch. The `2` files look like accidental duplicates. Left untouched |
| PR #35 Cloud Agent environment | `.cursor/environment.json` on its own branch | Development-environment config, separate from the product |
| Biometric approval | `docs/BIOMETRIC_APPROVAL.md` only | No implementation. Local, companion, and dual policies need an architecture choice before any entitlement or relay |
| App Store submission `0.1.4 (9)` | Apple, unchanged | Do not withdraw or replace it without an explicit decision |

## Not delivered

- Hardware-backed local, companion, or dual biometric approval.
- A new engine version, tag, wheel, or sdist. `0.2.0rc14` stays the published release.
- A new Apple build number or an uploaded Store package.
- Proof from a launched app that About closes with the button and Escape.
- Linux bubblewrap execution in this session.
- Marketplace or PyPI publication.
