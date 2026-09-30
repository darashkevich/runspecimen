# Candidate manifest

This file is the current full-scope candidate. It is not a Store submission plan, and it does not describe a stable-only app update.

| Item | Identity |
| --- | --- |
| Branch | `cursor/integrated-release-candidate` |
| Base this pass continues | `38b8613b959a628e33486b12da25dad15652052c` |
| Engine / package | unpublished `0.2.0rc15` |
| Plugin | unpublished `0.2.0-rc.15` |
| App marketing version in the project | **0.1.5 (13)**. That label also appears on a different tree: source `ea21a7fa17140dc15dab74493d384b2a8b7a150c`, engine rc14, package `e47ead2dee298d8f86dd191a5032b114608f954c150479719562e4319a9988fa`, report `runspecimen-candidates/0.1.5-13/QA-2026-09-29.md`. That report is not this candidate |
| Approved Mac app, unchanged | **0.1.4 (9)**, `READY_FOR_SALE`, build `51a18894-02e3-4846-86f5-29cc345567f0` |
| Submission record for that package | SHA-256 `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d` |
| Local export package, not modified by this work | mtime 2026-09-24 12:55:22, SHA-256 `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f` |
| Published engine, unchanged | `0.2.0rc14` / tag peel `25f4013c5c84b89b24024182f7c308dcffe084b4` |
| Published wheel / sdist / plugin zip | `d720bf5163a2b250699c30e804f89708e71c1c0d22682fbb43a4644b59c45948` / `6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3` / `0073e04e21bd225da328de06ef840ead6956a8cced4510a0025fb1e2ddc7fc16` |
| Homebrew | still pinned to published rc14 |

The exact commit of this candidate is the commit that contains this file. Unpublished rc15 archives of this tree, built by `release_check.py` on Python 3.12.14 (455 tests, 35 skipped):

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `e51b378dcf9f1f5fd6636f6732f24f1d32f7edc83ddaa34a36b8dde90c56fce7` |
| `runspecimen-0.2.0rc15.tar.gz` | `0bd8de2988b1b48948253faad21adaea1c902d95420404c6fef6acbd0100f75d` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

Copies are in `artifacts/rc15-2026-09-30-durable-domain/` next to the approved archive. The wheel and sdist changed because `holder_protocol.py` and `tests/test_holder_protocol.py` are packaged. The plugin zip matches the previous unpublished build. These are not the published rc14 bytes. The sdist does not contain this manifest. The 0.1.5 (13) package `e47ead2dee298d8f86dd191a5032b114608f954c150479719562e4319a9988fa` is source `ea21a7fa17140dc15dab74493d384b2a8b7a150c` and engine rc14. It is not this wheel or this sdist. `artifacts/rc15-2026-09-30-snapshot-verify/` stays as the record of `0f5dee9`.

## Status

| Area | State |
| --- | --- |
| Capture failures, receipts, fast path, PR #34 evidence expansion | Implemented on this branch. Not merged |
| Local RSBA1 / RSBA2 stores and user-mediated carried package | Implemented and tested in process. `consumeForExecution` is not wired to a run. `evaluateExecution.started` stays false |
| iOS companion enroll, sign, revoke, rotate | Implemented. Enroll creates a key only for a missing file. Finalize and public revoke share the enrollment lock. Not run on a device by a person |
| macOS confirmation | Claim matches the displayed request id. A workspace or contract change drops pending work and an unstarted claim. `performClaimedWorkflow` refuses when the live paths differ. A command that has already started is not stopped. AppModel tests cover the handlers. They are not an accessibility proof of the sheet |
| Runtime identity | `record-identity` writes an integrity record of artifact bytes and caller-supplied git metadata. It is not a cryptographic source attestation. `RS_RELEASE_GATE=1` isolates the reviewed commit before helper freeze and project generation. Export still requires that SHA and a clean source. A development archive may be dirty and cannot pass export |
| Executor guarantees | Yahor chose (2). (3) is excluded. `holder_protocol.py` binds exec to snapshot inodes, rejects a reused destination whose fd bytes differ, and separates go from commit. `run.py` does not call it. An embedded root daemon is not a Mac App Store path under guideline 2.4.5(v). The unsent Apple question is `docs/APPLE_DTS_HOLDER_QUESTION.md` |
| Human biometrics, protected pairing trust, Store archive verification | Not done. The unsigned iPhone app and the Release diagnostic in `artifacts/human-device-kit/` were built from `5c3957a3a8ddf9fceacc3096b2208ee7757e6b72`. Hashes are in `docs/HUMAN_DEVICE_KIT.md`. They are not installed |
| Privileged helper, relay, `network.server` | Not added |

`ProductionPolicy.accepts` is a test classifier. It does not enforce a biometric execution policy.
