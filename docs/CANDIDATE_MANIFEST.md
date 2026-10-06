# Candidate manifest

This file is not a Store submission plan and it is not packed into the sdist. A version string does not identify the binary. The table below is the canonical package record for this pass. Earlier tables in previous commits of this file are historical. Do not overwrite prior `artifacts/rc15-*` or `artifacts/0.2.0rc15-*` directories.

| Item | Identity |
| --- | --- |
| Branch | `cursor/evidence-expansion-coherence` |
| Evidence-branch lineage | PR #39 merge `e2a32166662ec06a7b47a89df6ccabb3058263a8`, PR #47 merge `329e08bf83ecb3a512f880b5833cd90df46af23e`, PR #49 merge `18ef46180141bdd6ac02a0aa31299e5b52d85433`, PR #50 merge `dd85691e42e49df7a25caaddd27fa313e3fdf728`, PR #52 merge `32cd6a2907c347b050a8ab67bc9e3547a55f44f6`, PR #53 merge `ae6a07123150b7ad057c60bfaa188a59833c1bbc`, PR #54 merge `97c8704d1ac67e66776aa1c9fb1d1692e1da9fcf`. Source parent of this pack: `311da6c72e95721dac40c7466040898f6e5de83f` (carried-companion pin refuses a non-active state; Swift/docs only, not in the wheel) |
| Historical IRC tip | `cursor/integrated-release-candidate` remains `a0dc23361856db8a68075471860bd4ab25af838c`. Do not retarget work there |
| NEW-01 package tree | `5f35cfcf401107648d61b84e29da5a2e8b45f708` (packaged-suite discovery). Last change to engine payload: `fb05284` (refusal string). Last change to plugin payload: `6023249` (2026-10-05); plugin zip unchanged since |
| Engine / package | unpublished `0.2.0rc15` |
| Plugin | unpublished `0.2.0-rc.15` |
| App marketing version in the project | **0.1.5 (13)**. That label also appears on a different tree: source `ea21a7fa17140dc15dab74493d384b2a8b7a150c`, engine rc14, package `e47ead2dee298d8f86dd191a5032b114608f954c150479719562e4319a9988fa`, report `runspecimen-candidates/0.1.5-13/QA-2026-09-29.md`. That report is not this candidate |
| Approved Mac app, unchanged | **0.1.4 (9)**, `READY_FOR_SALE`, build `51a18894-02e3-4846-86f5-29cc345567f0` |
| Submission record for that package | SHA-256 `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d` |
| Published engine, unchanged | `0.2.0rc14` / tag peel `25f4013c5c84b89b24024182f7c308dcffe084b4` |
| Published wheel / sdist / plugin zip | `d720bf5163a2b250699c30e804f89708e71c1c0d22682fbb43a4644b59c45948` / `6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3` / `0073e04e21bd225da328de06ef840ead6956a8cced4510a0025fb1e2ddc7fc16` |
| Homebrew | still pinned to published rc14 |

Canonical unpublished rc15 archives for this pass are in `artifacts/0.2.0rc15-2026-10-06-bump/`. The sdist does not contain this manifest or its own hash. These are not the published rc14 bytes. There is one hash table. Qualification notes: [QUALIFICATION_CHECKLIST.md](QUALIFICATION_CHECKLIST.md).

Prior packs `artifacts/rc15-2026-10-06-qualification-docfix/` (sdist `5fd68a6f06d7712ce16d57f3d892a505256349820428b51dc978ee4e97a7fde4`, wheel `a68094f0a4321b5ca19af047b48ecb6a7505c3b9b3d166b996775b1d0ebbfa9f`), `artifacts/rc15-2026-10-06-qualification/` (sdist `de90ab7a9b51cc7c944f06ac5085de6abe93804a25b72e40dbe23adad1fad464`, wheel `68685be9ffaf8fdc37dd26ae4d6f1987190e485252a97f118426137408a9012a`), and `artifacts/rc15-2026-10-06-isolated-evidence/` (sdist `682fe9892d6c3ab3f90b566c957bea0beeb6404ce73d3b09ddaac1f05833ce78`, wheel `809431ea6683a7779e13eb3cd024c7bea4ce87dc90a483c9b8aa9892fac78dae`) were not overwritten. This successor rebuilds the unpublished `0.2.0rc15` pack from source parent `311da6c`. `src/` is unchanged since `fb05284`, so the wheel matches the docfix pack. Packed `docs/RELEASE_CANDIDATE_REPORT.md` (A17 banner) and `tests/test_release_archive_reproducibility.py` (golden pack path) moved, so the sdist moved. The plugin zip did not. `release_check.py` still rewrites the sdist with `SOURCE_DATE_EPOCH`, gzip mtime 0, numeric owner 0/0, empty uname/gname, sorted members, and 0644/0755 modes. CI Python 3.9 installs setuptools 82.0.1 and may emit a different wheel `Generator` line than this 84.0.0 wheel; the sdist hash stays interpreter-identical.

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `a68094f0a4321b5ca19af047b48ecb6a7505c3b9b3d166b996775b1d0ebbfa9f` |
| `runspecimen-0.2.0rc15.tar.gz` | `886f90d0e2d9532e9c5c191f6d67095f72159fb7b6e019917a471f98b5f9f805` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6` |

The wheel and plugin zip match the previous canonical table (`a68094f0…` / `d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6`). The sdist changed because packed docs and the packed golden-pack pointer changed. Prior `artifacts/rc15-*` directories were not overwritten, including `artifacts/rc15-2026-10-06-qualification-docfix/`, `artifacts/rc15-2026-10-06-qualification/`, `artifacts/rc15-2026-10-06-isolated-evidence/`, and `artifacts/rc15-2026-10-05-golden-master/` sdist `c001cb088f8710802a84149d32843667f36b8fb0dedd941abbbd9dd18137a2da`. There is no new holder stage tar. The prior sealed stage `5200682fec6d5cdeee72c81ea8a419b0b2d80022f648f77a75a783b4eee9cdc9` in `artifacts/rc15-2026-10-05-qa-py312-seal/` was not overwritten. The 0.1.5 (13) package `e47ead2dee298d8f86dd191a5032b114608f954c150479719562e4319a9988fa` is source `ea21a7fa17140dc15dab74493d384b2a8b7a150c` and engine rc14. It is not this wheel or this sdist.

## Status

| Area | State |
| --- | --- |
| Capture failures, receipts, fast path, PR #34 evidence expansion | Merged into `cursor/evidence-expansion-coherence` via #39. Draft #51 to `main` is open and blocked on human/release gates. Not on `main`. #34 is closed as superseded |
| Local RSBA1 / RSBA2 stores and user-mediated carried package | Implemented and tested in process. `consumeForExecution` is not wired to a run. `evaluateExecution.started` stays false |
| iOS companion enroll, sign, revoke, rotate | Implemented. Enroll creates a key only for a missing file. Finalize and public revoke share the enrollment lock. Not run on a device by a person |
| macOS confirmation | Claim matches the displayed request id. A workspace or contract change drops pending work and an unstarted claim. `performClaimedWorkflow` refuses when the live paths differ. A command that has already started is not stopped. AppModel tests cover the handlers. A development GUI of source `91081f5` (main hash `cfb41bcc…`) finished Compare, Diff, Retain cancel, and Retain copy on the synthetic fixture; that GUI binary does not contain the holder. Evidence is in `apps/macos/asc-kit/evidence/2026-09-28-rc15-acceptance.md`. The version string 0.1.5 (13) does not identify it |
| Runtime identity | `record-identity` writes an integrity record of artifact bytes and caller-supplied git metadata. It is not a cryptographic source attestation. `RS_RELEASE_GATE=1` isolates the reviewed commit before helper freeze and project generation. Export still requires that SHA and a clean source. A development archive may be dirty and cannot pass export |
| Executor guarantees | Yahor authorized a separate Developer ID holder. (3) is excluded. The Store app stays guarantee (1). Bundle id `com.darashkevich.runspecimen.holder` is accepted for Developer ID packaging and is not `production_verifier_pin()`. Installed Secure Enclave admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false. Unprivileged adapter tests remain non-installed. A separate product `/Applications/RunSpecimen Holder.app` embeds `SMAppService.daemon` with empty entitlements; Background Items were approved; the SMAppService.daemon was observed running as root with a root-owned state directory. Installed daemon path sets `installed_protection` true and `allow_test_double` false. Root/admin can still defeat the holder. Not Store parity. DTS question unsent. |
| Human biometrics, protected pairing trust, Store archive verification | A human H1 diagnostic session ran 2026-10-06 on an `ae6a071` Release build (not this SHA). It found IOS-H1-01 through IOS-H1-09, including IOS-H1-08 (the Mac pinned a revoked key as active) and IOS-H1-02 (Rotate/Revoke do not prompt Face ID despite the hints). It is diagnostic and defect evidence. It is not candidate qualification, and it is not E2 acceptance. Product sources for the diagnostic and the iPhone app were unchanged from `5c3957a3a8ddf9fceacc3096b2208ee7757e6b72` through `1873f42`, and the kit hashes in `docs/HUMAN_DEVICE_KIT.md` were re-read. Since `1873f42`, iOS and macOS core sources changed; the kit hashes do not identify this candidate. `preview` exits 0. `enroll` without `--human-invoked` exits 2. They are not installed. |
| Privileged helper, relay, `network.server` | Not added |

`ProductionPolicy.accepts` is a test classifier. It does not enforce a biometric execution policy.
