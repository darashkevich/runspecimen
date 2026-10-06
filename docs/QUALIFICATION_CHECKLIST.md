# Qualification checklist

This file is not packed into the sdist. It is not a production sign-off. It does not authorize a merge, tag, notarization, install, or upload.

Parent engineering tip: `b3367ebeff76a1ed0c6fd6ecda2f613e5e8e93a4`. That commit closed the shared-log race. Its pack remains `artifacts/rc15-2026-10-06-isolated-evidence/` and was not overwritten.

This checklist's package identity is the successor that corrects two stale claims: installed Secure Enclave admission is fail-closed, not undecided, and the Store note follows the 2026-09-28 Connect record. Pack: `artifacts/rc15-2026-10-06-qualification/`. The source commit is the one that adds that directory. A later edit of this file alone does not change the sdist.

`main` is `93f9b5708c1ba2d9b325ae2f9016d6a472fe6a20`. Source landing on `main` is not a public release.

D1 and D2 stay locked. `run_integration_complete` and `e2_closed` stay false. Holder id `com.darashkevich.runspecimen.holder` is the Developer ID packaging id only. It is not `production_verifier_pin()`.

## Engineering evidence for this pack

Recorded 2026-10-06 on this Mac. Interpreter: CPython 3.12.14 (`/tmp/rs-py312-rel-holder`). Command: `PYTHONPATH=src python -m unittest discover -s tests -v`, with the qualification pack already on disk.

| Item | Result |
| --- | --- |
| Tests | 658 |
| Failures | 0 |
| Exit status | 0 |
| Skips | 35 |
| Reproducibility | Executed. Rebuilt sdist `de90ab7a9b51cc7c944f06ac5085de6abe93804a25b72e40dbe23adad1fad464`. Rebuilt wheel `68685be9ffaf8fdc37dd26ae4d6f1987190e485252a97f118426137408a9012a`. Both match `SHA256SUMS` |

`release_check.py` on the same interpreter, before that suite, also exited 0 (658 tests, 36 skipped, then 4 distribution tests). The extra skip was the reproducibility comparison while this pack was not yet on disk. The suite above is the one that executed the comparison.

Skips, each one. These are unavailable dependencies or the wrong OS. They were not turned into passing stand-ins.

| Count | Reason |
| --- | --- |
| 24 | `PyNaCl not installed` |
| 5 | `PyNaCl not installed; pip install 'runspecimen[ed25519]'` |
| 3 | `bwrap is not installed; real confinement spawn skipped` |
| 2 | `ldd trust test only applicable on Linux` |
| 1 | `pytest not installed; returncode branch covered synthetically` |

CryptoKit and `sandbox-exec` tests ran on this Mac because those tools are present. That is not installed-holder or Secure Enclave qualification.

CI on parent `b3367eb` was 20/20 and does not cover this successor. This successor still needs its own CI before anyone treats the branch tip as the same evidence.

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `68685be9ffaf8fdc37dd26ae4d6f1987190e485252a97f118426137408a9012a` |
| `runspecimen-0.2.0rc15.tar.gz` | `de90ab7a9b51cc7c944f06ac5085de6abe93804a25b72e40dbe23adad1fad464` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6` |

The plugin zip matches the `b3367eb` pack. The wheel and sdist do not.

## Channels

Candidate selection, qualification, and release authorization are three different decisions. Engineering tests do not select a channel, do not qualify an installed or store product, and do not authorize publication.

### CLI / PyPI

| | |
| --- | --- |
| Supported | `doctor`, `validate`, `status`, receipts, and guarantee (1) typed approval on an ordinary contract with no `execution_approval`. Unpublished engine `0.2.0rc15`. |
| Excluded | PyPI listing of rc15. Installed holder. Secure Enclave admission. Evidence-expansion commands are not in published rc14. |
| Artifacts | This pack's wheel and sdist. Published rc14 bytes stay the public pin. |
| Completed evidence | The suite and reproducibility row above. Parent `b3367eb` CI does not cover this wheel. |
| Missing | A human guarantee (1) session on this exact wheel ([HUMAN_DEVICE_KIT.md](HUMAN_DEVICE_KIT.md)). A decision that this sdist, not rc14 and not the `b3367eb` sdist, is the candidate to publish. A post-upload byte compare. |
| Authorization | Separate from selection and from this suite. Not granted here. |

### Homebrew

| | |
| --- | --- |
| Supported | The published formula still installs rc14. |
| Excluded | A bottle or formula for this sdist. |
| Artifacts | No new bottle. Formula in-tree still pins rc14. |
| Completed evidence | None for this sdist. |
| Missing | Publication of the chosen sdist, then a formula update to that digest. |
| Authorization | Not granted. Do not point the tap at an unpublished sdist. |

### Plugins and marketplaces

| | |
| --- | --- |
| Supported | In-repo adapters call the CLI. `freshness_check` evaluates and does not write a report. The plugin does not ship the verifier and does not pass a holder. |
| Excluded | A marketplace listing. Approve tools. |
| Artifacts | Plugin zip `d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6`. |
| Completed evidence | Release-check plugin build on 2026-10-06. Cursor marketplace submission was recorded on 2026-09-21 as pending review (`docs/SUBMISSION.md`). That date was not re-checked on 2026-10-06. Claude, Grok, Gemini, Junie, and Muse listings are recorded there as not submitted. |
| Missing | Acceptance of any listing. A human decision to submit this zip. |
| Authorization | Not granted. Website source is `sites/runspecimen/` in the `darashkevich.com` repo, not this repository, and was not re-read on 2026-10-06. The in-repo note still says the live site pins `runspecimen==0.2.0rc14`. |

### Mac App Store

| | |
| --- | --- |
| Supported | Guarantee (1) only, on the already approved app. |
| Excluded | This SHA. The holder. Guarantee (2). A new upload. |
| Artifacts | Approved package `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`, **0.1.4 (9)**, build `51a18894-02e3-4846-86f5-29cc345567f0`. Connect query recorded 2026-09-28 as `READY_FOR_SALE`. Not re-queried on 2026-10-06. The 2026-09-24 `WAITING_FOR_REVIEW` note is historical. No public `apps.apple.com` URL is recorded. |
| Completed evidence | That 2026-09-28 record. Not a test of this pack. |
| Missing | A new archive only if a later decision chooses a new Store build. This pack is not that archive. |
| Authorization | Not granted. Do not upload from this checklist. |

### Direct Mac app and Developer ID holder

| | |
| --- | --- |
| Supported | Nothing installed from this pack. Guarantee (2) source exists and stays fail-closed. |
| Excluded | Notarization. A qualified installed holder. Local, companion, and dual execution. Replacing `/Applications/RunSpecimen.app` or `/Applications/RunSpecimen Holder.app`. |
| Artifacts | No new Developer ID archive. No new stage tar. The direct app in `/Applications` is still the 2026-09-26 copy. The holder there is still the 2026-09-30 copy. |
| Completed evidence | Isolated tests and source refusal. Not an installed run. |
| Missing | E2. A product that can create the Secure Enclave key is not this root daemon, and that design is not open. |
| Authorization | Not granted. |

### iOS companion

| | |
| --- | --- |
| Supported | Source for observe, enroll, sign, revoke, and rotate. Software tests. |
| Excluded | TestFlight, the App Store, and treating a signed install as acceptance. Phone approval is not physical presence at the Mac. |
| Artifacts | No signed device build of this SHA. The unsigned kit binary `4f38ee0a…` is from `5c3957a`, not this pack. |
| Completed evidence | Unit tests in CI on the parent tip, not a device session, and not this successor's CI yet. |
| Missing | A person signing a build of this SHA, then a separate acceptance decision. Install alone does not qualify the channel. |
| Authorization | Not granted. |

## Smallest remaining actions

1. Let CI finish on the successor commit. Do not treat parent `b3367eb` CI as this pack.
2. Choose whether the publish candidate is published rc14, the `b3367eb` sdist, or this qualification sdist. That choice is not this checklist.
3. If the choice is this sdist, run the guarantee (1) session in [HUMAN_DEVICE_KIT.md](HUMAN_DEVICE_KIT.md) and keep the identity row with the result.
4. Leave E2 fail-closed. Do not schedule installed local, companion, or dual runs.
5. Stop code changes on this candidate unless a later run reproduces a defect.

Human steps, and only those, are in [HUMAN_DEVICE_KIT.md](HUMAN_DEVICE_KIT.md).
