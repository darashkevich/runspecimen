# Candidate manifest

This file is the current full-scope candidate. It is not a Store submission plan, and it does not describe a stable-only app update.

| Item | Identity |
| --- | --- |
| Branch | `cursor/integrated-release-candidate` |
| Base this pass continues | `38b8613b959a628e33486b12da25dad15652052c` |
| Engine / package | unpublished `0.2.0rc15` |
| Plugin | unpublished `0.2.0-rc.15` |
| App marketing version in the project | **0.1.5 (13)**. No newer store version is proposed here |
| Approved Mac app, unchanged | **0.1.4 (9)**, `READY_FOR_SALE`, build `51a18894-02e3-4846-86f5-29cc345567f0` |
| Submission record for that package | SHA-256 `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d` |
| Local export package, not modified by this work | mtime 2026-09-24 12:55:22, SHA-256 `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f` |
| Published engine, unchanged | `0.2.0rc14` / tag peel `25f4013c5c84b89b24024182f7c308dcffe084b4` |
| Published wheel / sdist / plugin zip | `d720bf5163a2b250699c30e804f89708e71c1c0d22682fbb43a4644b59c45948` / `6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3` / `0073e04e21bd225da328de06ef840ead6956a8cced4510a0025fb1e2ddc7fc16` |
| Homebrew | still pinned to published rc14 |

The exact commit of this candidate is the commit that contains this file. Unpublished rc15 archives of this tree, built by `release_check.py` on Python 3.12.14 (417 tests, 35 skipped):

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `24082fbf9006c627953f6d9c5b8f0c9dca9fb006efcae3b54472b7dfa641d871` |
| `runspecimen-0.2.0rc15.tar.gz` | `5af33bd635951819b8a71b7f546856fd114eb062dbc3d78eeb1dc5d6b24e434c` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

Copies are in `artifacts/rc15-2026-09-29-runtime-identity/` next to the approved archive. The wheel and plugin zip match the previous unpublished build. The sdist changed because `tests/test_runtime_identity_cli.py` is packaged. These are not the published rc14 bytes.

## Status

| Area | State |
| --- | --- |
| Capture failures, receipts, fast path, PR #34 evidence expansion | Implemented on this branch. Not merged |
| Local RSBA1 / RSBA2 stores and user-mediated carried package | Implemented and tested in process. `consumeForExecution` is not wired to a run. `evaluateExecution.started` stays false |
| iOS companion enroll, sign, revoke, rotate | Implemented. Enroll creates a key only for a missing file. Finalize and public revoke share the enrollment lock. Not run on a device by a person |
| macOS confirmation | Claim matches the displayed request id. A workspace or contract change drops pending work and an unstarted claim. `performClaimedWorkflow` refuses when the live paths differ. A command that has already started is not stopped. AppModel tests cover the handlers. They are not an accessibility proof of the sheet |
| Runtime identity | `scan` is symbols only. After archive signing, `record-identity` writes the full file map, artifact hash, 40-character git commit, and dirty flag. Export `verify-identity` fails closed when that signed-archive manifest is missing or the bytes differ. The pre-sign helper scan is not that manifest |
| Executor guarantees | (1) the app refuses its own transition. (2) and (3) are not built. This candidate does not choose among them and does not add a helper, relay, or Endpoint Security client |
| Human biometrics, protected pairing trust, Store archive verification | Not done. The unsigned iPhone app is rebuilt for the in-process enrollment lock and is still unsigned and not installed. The diagnostic binary is the `38b8613` build; this pass does not change that target |
| Privileged helper, relay, `network.server` | Not added |

`ProductionPolicy.accepts` is a test classifier. It does not enforce a biometric execution policy.
