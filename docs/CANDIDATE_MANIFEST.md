# Candidate manifest

This file is not a Store submission plan and it is not packed into the sdist. A version string does not identify the binary. The table below is the canonical package record for this pass. Earlier tables in previous commits of this file are historical. Do not overwrite prior `artifacts/rc15-*` directories.

| Item | Identity |
| --- | --- |
| Branch | `cursor/evidence-expansion-coherence` |
| Evidence-branch lineage | PR #39 merge `e2a32166662ec06a7b47a89df6ccabb3058263a8`, PR #47 merge `329e08bf83ecb3a512f880b5833cd90df46af23e`, PR #49 merge `18ef46180141bdd6ac02a0aa31299e5b52d85433` |
| Historical IRC tip | `cursor/integrated-release-candidate` remains `a0dc23361856db8a68075471860bd4ab25af838c`. Do not retarget work there |
| NEW-01 package tree | `5f35cfcf401107648d61b84e29da5a2e8b45f708` (packaged-suite discovery). Still the last change to engine/plugin payload bytes |
| Engine / package | unpublished `0.2.0rc15` |
| Plugin | unpublished `0.2.0-rc.15` |
| App marketing version in the project | **0.1.5 (13)**. That label also appears on a different tree: source `ea21a7fa17140dc15dab74493d384b2a8b7a150c`, engine rc14, package `e47ead2dee298d8f86dd191a5032b114608f954c150479719562e4319a9988fa`, report `runspecimen-candidates/0.1.5-13/QA-2026-09-29.md`. That report is not this candidate |
| Approved Mac app, unchanged | **0.1.4 (9)**, `READY_FOR_SALE`, build `51a18894-02e3-4846-86f5-29cc345567f0` |
| Submission record for that package | SHA-256 `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d` |
| Published engine, unchanged | `0.2.0rc14` / tag peel `25f4013c5c84b89b24024182f7c308dcffe084b4` |
| Published wheel / sdist / plugin zip | `d720bf5163a2b250699c30e804f89708e71c1c0d22682fbb43a4644b59c45948` / `6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3` / `0073e04e21bd225da328de06ef840ead6956a8cced4510a0025fb1e2ddc7fc16` |
| Homebrew | still pinned to published rc14 |

Canonical unpublished rc15 archives for this pass are in `artifacts/rc15-2026-10-05-golden-master/`. The sdist does not contain this manifest or its own hash. These are not the published rc14 bytes. There is one hash table.

OPEN-SDIST: the committed sdist `b2db7b78cb742ab8934368d634f46e1fde02ba4cb5c1950b2986bd3e9b080cb9` recorded builder uid/gid/uname (`ubuntu`/`1000`) and setuptools walk order, so a rebuild on another host produced `6979460d…`. `release_check.py` now rewrites the sdist with `SOURCE_DATE_EPOCH`, gzip mtime 0, numeric owner 0/0, empty uname/gname, sorted members, and 0644/0755 modes. The pack sdist was regenerated to `ddd6f667a09e5e18a71171329df62965bc8849c6d0efa144fa7f535493f828f6`. The wheel and plugin zip bytes were not rebuilt.

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `809431ea6683a7779e13eb3cd024c7bea4ce87dc90a483c9b8aa9892fac78dae` |
| `runspecimen-0.2.0rc15.tar.gz` | `ddd6f667a09e5e18a71171329df62965bc8849c6d0efa144fa7f535493f828f6` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6` |

The wheel matches the previous canonical table (`809431ea6683a7779e13eb3cd024c7bea4ce87dc90a483c9b8aa9892fac78dae`). The plugin zip matches the previous canonical table (`d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6`). The sdist hash changed because archive metadata is now host-independent and because `scripts/release_check.py`, `tests/test_release_archive_reproducibility.py`, and `CHANGELOG.md` shipped in the sdist. Prior `artifacts/rc15-*` directories were not overwritten, including `artifacts/rc15-2026-10-05-qa-py312-tree/` wheel/sdist `7b0883b7c7cb31cf512ff4763d28c40dac4867bc506e2a9c00eb59e955276d81` / `c84e0deaa471b4fc8040ae8c13b184223264db79c344e13b4982709c1f77344c`. There is no new holder stage tar. The prior sealed stage `5200682fec6d5cdeee72c81ea8a419b0b2d80022f648f77a75a783b4eee9cdc9` in `artifacts/rc15-2026-10-05-qa-py312-seal/` was not overwritten. The 0.1.5 (13) package `e47ead2dee298d8f86dd191a5032b114608f954c150479719562e4319a9988fa` is source `ea21a7fa17140dc15dab74493d384b2a8b7a150c` and engine rc14. It is not this wheel or this sdist.

## Status

| Area | State |
| --- | --- |
| Capture failures, receipts, fast path, PR #34 evidence expansion | Implemented on this branch. Not merged |
| Local RSBA1 / RSBA2 stores and user-mediated carried package | Implemented and tested in process. `consumeForExecution` is not wired to a run. `evaluateExecution.started` stays false |
| iOS companion enroll, sign, revoke, rotate | Implemented. Enroll creates a key only for a missing file. Finalize and public revoke share the enrollment lock. Not run on a device by a person |
| macOS confirmation | Claim matches the displayed request id. A workspace or contract change drops pending work and an unstarted claim. `performClaimedWorkflow` refuses when the live paths differ. A command that has already started is not stopped. AppModel tests cover the handlers. A development GUI of source `91081f5` (main hash `cfb41bcc…`) finished Compare, Diff, Retain cancel, and Retain copy on the synthetic fixture; that GUI binary does not contain the holder. Evidence is in `apps/macos/asc-kit/evidence/2026-09-28-rc15-acceptance.md`. The version string 0.1.5 (13) does not identify it |
| Runtime identity | `record-identity` writes an integrity record of artifact bytes and caller-supplied git metadata. It is not a cryptographic source attestation. `RS_RELEASE_GATE=1` isolates the reviewed commit before helper freeze and project generation. Export still requires that SHA and a clean source. A development archive may be dirty and cannot pass export |
| Executor guarantees | Yahor authorized a separate Developer ID holder. (3) is excluded. The Store app stays guarantee (1). Bundle id `com.darashkevich.runspecimen.holder` is accepted for Developer ID packaging and is not `production_verifier_pin()`. Installed Secure Enclave admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false. Unprivileged adapter tests remain non-installed. A separate product `/Applications/RunSpecimen Holder.app` embeds `SMAppService.daemon` with empty entitlements; Background Items were approved; the SMAppService.daemon was observed running as root with a root-owned state directory. Installed daemon path sets `installed_protection` true and `allow_test_double` false. Root/admin can still defeat the holder. Not Store parity. DTS question unsent. |
| Human biometrics, protected pairing trust, Store archive verification | Not done. Product sources for the diagnostic and the iPhone app are unchanged from `5c3957a3a8ddf9fceacc3096b2208ee7757e6b72` through `1873f42`, and the kit hashes in `docs/HUMAN_DEVICE_KIT.md` were re-read. `preview` exits 0. `enroll` without `--human-invoked` exits 2. They are not installed. A person still has to complete the hardware prompts |
| Privileged helper, relay, `network.server` | Not added |

`ProductionPolicy.accepts` is a test classifier. It does not enforce a biometric execution policy.
