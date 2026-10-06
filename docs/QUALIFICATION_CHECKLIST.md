# Qualification checklist

This file is not packed into the sdist. It is not a production sign-off. It does not authorize a merge, tag, notarization, install, or upload.

## Identities

Keep these three apart. Do not cite one as another.

| Role | SHA | Notes |
| --- | --- | --- |
| Parent engineering tip | `b3367ebeff76a1ed0c6fd6ecda2f613e5e8e93a4` | Closed the shared-log race. Pack `artifacts/rc15-2026-10-06-isolated-evidence/` (wheel `809431ea…`, sdist `682fe989…`). Not overwritten |
| Previous package tree | `fb05284d897d165b6fab9ad544ff9a1116675294` | Successor of `b3367eb`. Corrected the installed-admission refusal string ("stays fail-closed", not "undecided") and the Store note (2026-09-28 Connect record). Pack `artifacts/rc15-2026-10-06-qualification/` (wheel `68685be9…`, sdist `de90ab7a…`). Not overwritten |
| Evidence-only parent | `c0812acda391e6729880d06d5177587d4ccec792` | Unpacked docs/CI record only. A rebuild at `c0812ac` is byte-identical to the `fb05284` pack (verified 2026-10-06). Not overwritten |
| Docs-only package tree | `d42fe583dc3dd04e3cd3315f50608045c144d818` | Packed-doc errata plus pack `artifacts/rc15-2026-10-06-qualification-docfix/`. No `src/` change. Old packs untouched. Not a release. CI 20/20 on this SHA: push [37487406807](https://github.com/darashkevich/runspecimen/actions/runs/37487406807), pull request [37487436430](https://github.com/darashkevich/runspecimen/actions/runs/37487436430) |
| Evidence-only successor | `c226b692f100eab0f5b288edc7d99369abadef16` | Unpacked H1 and CI wording only. No `artifacts/` or `src/` change, so the pack bytes stay `d42fe58`. A QA snapshot saw 19 success and one unfinished check. That snapshot is not the `d42fe58` 20/20 copied forward. The finished runs on this SHA are push [37488988851](https://github.com/darashkevich/runspecimen/actions/runs/37488988851) and pull request [37488995481](https://github.com/darashkevich/runspecimen/actions/runs/37488995481), both success. Merged here as `97c8704d1ac67e66776aa1c9fb1d1692e1da9fcf` |

`main` is `93f9b5708c1ba2d9b325ae2f9016d6a472fe6a20`. Landing source on `main` is not a public release.

D1 and D2 stay locked. `run_integration_complete` and `e2_closed` stay false. Holder id `com.darashkevich.runspecimen.holder` is the Developer ID packaging id only. It is not `production_verifier_pin()`. The pinned Developer ID designated requirement is unchanged.

## Engineering evidence for this pack

Two recordings on the parent package tree, on the same Mac, both with the qualification pack already on disk, so the reproducibility byte-compare executed and did not skip. They do not replace this successor's own `release_check` recording.

| Item | Original record (2026-10-06) | Independent re-run (2026-10-06, 16:02–16:06 WEST, ran twice) |
| --- | --- | --- |
| Commit | `fb05284` | `c0812ac` (same package tree as `fb05284`) |
| Interpreter | CPython 3.12.14, venv `/tmp/rs-py312-rel-holder` | CPython 3.12.14 (Homebrew), fresh venv `/tmp/rs-relprep-venv` (setuptools 84.0.0, wheel 0.48.0, pip 26.2.1) |
| Command | `PYTHONPATH=src python -m unittest discover -s tests -v` | `python scripts/release_check.py --output-dir …` (full gate) |
| Tests | 658 | 658, then 4 distribution tests against the extracted sdist |
| Passed | 623 | 623, then 4/4 |
| Skipped | 35 | 35 |
| Failures / errors | 0 / 0 | 0 / 0 |
| Exit status | 0 | 0 |
| Reproducibility | Executed. sdist `de90ab7a…`, wheel `68685be9…` match `SHA256SUMS` | Executed. Same digests. All five files in the output directory are byte-identical (`cmp`) to `artifacts/rc15-2026-10-06-qualification/`, including `release-report.json` and `SHA256SUMS` |

Before the `fb05284` pack existed, `release_check.py` exited 0 with 36 skips. The extra skip was the reproducibility comparison. That run is superseded by the two above.

This successor's local `release_check.py` is recorded in `artifacts/rc15-2026-10-06-qualification-docfix/`. CPython 3.12.3, venv `/tmp/rs-relprep-docfix` (setuptools 84.0.0, wheel 0.48.0, pip 26.2.1). First pass: 658 tests, 47 skipped, 0 failed, then 4/4 distribution tests, exit 0. The extra skip was `test_wheel_and_sdist_digests_repeat` while the new pack was not on disk. Second pass (`--output-dir /tmp/rs-docfix-verify`): 658 tests, 46 skipped, 0 failed, then 4/4, exit 0. The reproducibility compare executed against `artifacts/rc15-2026-10-06-qualification-docfix/` and printed `reproducible sdist 5fd68a6f…` / `reproducible wheel a68094f0…`. The three archives in the verify directory were byte-identical (`cmp`) to that pack. CI 20/20 success on `d42fe583dc3dd04e3cd3315f50608045c144d818`: push run 37487406807, pull request run 37487436430. That is not `c226b692f100eab0f5b288edc7d99369abadef16`. The 46 Linux skips are Darwin-only or host-specific (CryptoKit, P-256 verifier, phone peer, rsync/holder stage, codesign, sandbox-exec, relocatable Mach-O, and the bwrap missing-backend case). None was turned into a passing stand-in.

Skips on the parent Mac recordings, each one. These are unavailable dependencies or the wrong OS. None was turned into a passing stand-in.

| Count | Reason |
| --- | --- |
| 24 | `PyNaCl not installed` |
| 5 | `PyNaCl not installed; pip install 'runspecimen[ed25519]'` |
| 3 | `bwrap is not installed; real confinement spawn skipped` |
| 2 | `ldd trust test only applicable on Linux` |
| 1 | `pytest not installed; returncode branch covered synthetically` |

CryptoKit and `sandbox-exec` tests ran on that Mac because those tools are present. That is not installed-holder or Secure Enclave qualification.

CI, all with conclusion `success` (10 jobs per event: 8 `release-check` matrix entries, `macos-app`, `holder-swift`):
- Package commit `fb05284`: push [37480847104](https://github.com/darashkevich/runspecimen/actions/runs/37480847104), pull request [37480855659](https://github.com/darashkevich/runspecimen/actions/runs/37480855659).
- Evidence-only tip `c0812ac`: push [37482547229](https://github.com/darashkevich/runspecimen/actions/runs/37482547229), pull request [37482561658](https://github.com/darashkevich/runspecimen/actions/runs/37482561658).
- Docs-only package tree `d42fe58`: CI 20/20, push [37487406807](https://github.com/darashkevich/runspecimen/actions/runs/37487406807), pull request [37487436430](https://github.com/darashkevich/runspecimen/actions/runs/37487436430).
- Evidence-only successor `c226b69`: push [37488988851](https://github.com/darashkevich/runspecimen/actions/runs/37488988851), pull request [37488995481](https://github.com/darashkevich/runspecimen/actions/runs/37488995481), both success. Not a copy of the `d42fe58` runs. Merge `97c8704` push [37490697272](https://github.com/darashkevich/runspecimen/actions/runs/37490697272) succeeded. Its pull request run is a separate event.
- Parent `b3367eb` CI covers a different tree. None of this is production sign-off.

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `a68094f0a4321b5ca19af047b48ecb6a7505c3b9b3d166b996775b1d0ebbfa9f` |
| `runspecimen-0.2.0rc15.tar.gz` | `5fd68a6f06d7712ce16d57f3d892a505256349820428b51dc978ee4e97a7fde4` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6` |
| `release-report.json` | `1fb513a14d0f85c35140868daf4f52948eade152fd81915242cd884417104bcf` |

Wheel, sdist, and plugin match the expected Mac-prep archive hashes. `release-report.json` records `platform: linux` and `python: 3.12.3`, so its digest is this host's recording, not the Darwin 3.12.14 prep digest `af3b37aa…`. Archive bytes are the package identity.

The plugin zip matches the `b3367eb` and `fb05284` packs. The wheel and sdist do not. Prior packs `artifacts/rc15-2026-10-06-qualification/` and `artifacts/rc15-2026-10-06-isolated-evidence/` were not modified.

Packed-doc errata that were present in the `fb05284` pack (`docs/HOLDER_NATIVE_BRIDGE.md` and `docs/HOLDER_GATE_LEDGER.md` calling installed admission "undecided"; stale marketplace, Homebrew, and Store status lines; README linking a missing `docs/GROK_TANDEM.md`) are corrected in this successor pack. That correction is why this pack has a new directory. It is not an edit of the previous packs.

Known packed-doc erratum remaining in this pack: the `docs/RELEASE_CANDIDATE_REPORT.md` banner (A17) still names the old pack `artifacts/rc15-2026-10-06-qualification/` as the current identity. The correct current pack for this successor is `artifacts/rc15-2026-10-06-qualification-docfix/`. Do not edit that packed file here. Fix it only if a future pack is built.

## Release steps (apply to every channel)

Candidate selection, qualification, and release authorization are three distinct steps, in this order. A green suite or CI run is evidence toward qualification only. It does not select a candidate, and it does not authorize a release. Landing source on `main` is a fourth, separate step, and it is not a release.

## Channels

### CLI / PyPI

| | |
| --- | --- |
| Supported | `doctor`, `validate`, `status`, receipts, and guarantee (1) typed approval in a real terminal on an ordinary contract with no `execution_approval`. Unpublished engine `0.2.0rc15` |
| Excluded | PyPI listing of rc15. Installed holder. Secure Enclave admission. Contracts with `execution_approval` of `local`, `companion`, or `dual` (they refuse the phrase). Evidence-expansion commands are not in published rc14 |
| Artifacts | This pack's wheel `a68094f0…` and sdist `5fd68a6f…`. Published rc14 stays the public pin (wheel `d720bf51…`, sdist `6ffcfe2f…`; PyPI latest is still `0.2.0rc14` and has no rc15, checked 2026-10-06) |
| Completed evidence | Parent suite, reproducibility compare, and release-check rows above. CI green on `fb05284` and `c0812ac`. CI 20/20 success on `d42fe583dc3dd04e3cd3315f50608045c144d818`: push run 37487406807, pull request run 37487436430. That is not `c226b692f100eab0f5b288edc7d99369abadef16`. |
| Missing (acceptance) | A human guarantee (1) session on this exact wheel (see HUMAN_DEVICE_KIT.md or the rc15 human acceptance sheet). A post-upload byte compare after any upload |
| Selection | Not made. Choose among published rc14, the `b3367eb` sdist, the `fb05284` sdist, or this docs-only successor pack |
| Authorization | Separate from selection and from qualification. Not granted here |

### Homebrew

| | |
| --- | --- |
| Supported | The published formula installs rc14 (tap sha256 `6ffcfe2f…`, checked 2026-10-06) |
| Excluded | A bottle or formula for any rc15 sdist |
| Artifacts | No new bottle. The in-tree formula still pins rc14 |
| Completed evidence | None for rc15 |
| Missing | PyPI and GitHub publication of the selected sdist first, then a formula update to that digest and a `brew install` / `--version` check |
| Selection / Authorization | Follows the CLI decision. Not granted. Do not point the tap at an unpublished sdist |

### Plugins and marketplaces

| | |
| --- | --- |
| Supported | In-repo adapters call the CLI. `freshness_check` evaluates and does not write a report. The plugin does not ship the verifier, does not pass a holder, and has no approve tool |
| Excluded | Any marketplace listing. Approve tools |
| Artifacts | Plugin zip `d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6` (identical in the `b3367eb`, `fb05284`, and this successor pack). This zip was not submitted anywhere |
| Completed evidence | Release-check plugin build and installed-adapter smoke, 2026-10-06 |
| Historical submissions (rc14 era; recorded 2026-09-21 in `docs/SUBMISSION.md`, not re-checked unless noted) | Cursor: form submitted, not listed. Claude Code: directory form submitted, not listed. JetBrains Junie: catalog PR #16 open, not merged (re-checked 2026-10-06; still open). Gemini CLI: crawler-indexed via topic and root manifest, not indexed. Codex/OpenAI: not submitted (verified identity required). Grok, Antigravity, Muse, Windsurf: not submitted |
| Missing | Acceptance of any listing. A human decision on whether this zip replaces what the pending submissions point at |
| Selection / Authorization | Not granted. Website source is `sites/runspecimen/` in `darashkevich/darashkevich.com` (main `64fb32d`, 2026-09-23). Read 2026-10-06: the live page pins `runspecimen==0.2.0rc14` and says "Not listed on Cursor Marketplace or Codex" |

### Mac App Store

| | |
| --- | --- |
| Supported | Guarantee (1) only, on the already approved app |
| Excluded | This SHA. The holder. Guarantee (2). A new upload |
| Artifacts | Approved package `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`, **0.1.4 (9)**, build `51a18894-02e3-4846-86f5-29cc345567f0`, engine rc14. Historical Connect query of 2026-09-28: `READY_FOR_SALE`, `downloadable=true`. Not re-queried on 2026-10-06. The 2026-09-24 `WAITING_FOR_REVIEW` note is historical. No public `apps.apple.com` URL is recorded. A public iTunes lookup by bundle id on 2026-10-06 returned no result. That is not a Connect query. The website (source dated 2026-09-23) still says "Mac App Store is not public" |
| Completed evidence | That 2026-09-28 record. Not a test of this pack |
| Missing | A new archive only if a later selection chooses a new Store build. This pack is not that archive |
| Selection / Authorization | Not granted. Do not upload from this checklist |

### Direct Mac app and Developer ID holder

| | |
| --- | --- |
| Supported | Nothing installed from this pack. Guarantee (2) source exists and stays fail-closed |
| Excluded | Notarization. A qualified installed holder. Local, companion, and dual execution. Replacing `/Applications/RunSpecimen.app` or `/Applications/RunSpecimen Holder.app` |
| Artifacts | No new Developer ID archive. No new stage tar. On 2026-10-06 the direct app in `/Applications` was still the 2026-09-26 copy (0.1.5 (12)), and the holder was still the 2026-09-30 copy (0.1.0 (1)). A pre-existing holder daemon from that copy is running. Neither is this candidate |
| Completed evidence | Isolated tests (`holder-swift` green on `fb05284` and `c0812ac`) and source refusal. Not an installed run. A human H1 diagnostic session ran 2026-10-06 on an `ae6a071` Release build (not this SHA). It found IOS-H1-01 through IOS-H1-09, including IOS-H1-08 (the Mac pinned a revoked key as active) and IOS-H1-02 (Rotate/Revoke do not prompt Face ID despite the hints). It is diagnostic and defect evidence. It is not candidate qualification, and it is not E2 acceptance. CI 20/20 success on `d42fe583dc3dd04e3cd3315f50608045c144d818`: push run 37487406807, pull request run 37487436430. That is not `c226b692f100eab0f5b288edc7d99369abadef16`. |
| Missing | E2, an open engineering gap. A root daemon cannot create the Secure Enclave key, and any other design is a new decision that is not opened here |
| Selection / Authorization | Not granted |

### iOS companion

| | |
| --- | --- |
| Supported | Source for observe, enroll, sign, revoke, and rotate |
| Excluded | TestFlight, the App Store, and treating a signed install as acceptance. Phone approval is not physical presence at the Mac. Installed companion and dual runs (blocked by E2) |
| Artifacts | No signed device build of this SHA. The unsigned kit binary `4f38ee0a…` is from `5c3957a`. iOS sources have changed since (12 commits touch `apps/ios` after `1873f42`), so it is not this pack |
| Completed evidence | On `fb05284` / `c0812ac` CI: an unsigned Release build of the shipping Observe product plus a symbol scan (`verify_ios_release_symbols.sh` in the Darwin `release-check` jobs). The shared `RSBA2Package.swift` is exercised by `macos-app`. CI does not run the iOS XCTest targets (`ObserveSchemaTests`, `PhonePeerCancellationTests`), and no iOS unit-test result is recorded for this SHA. A human H1 diagnostic session ran 2026-10-06 on an `ae6a071` Release build (not this SHA). It found IOS-H1-01 through IOS-H1-09, including IOS-H1-08 (the Mac pinned a revoked key as active) and IOS-H1-02 (Rotate/Revoke do not prompt Face ID despite the hints). It is diagnostic and defect evidence. It is not candidate qualification, and it is not E2 acceptance. CI 20/20 success on `d42fe583dc3dd04e3cd3315f50608045c144d818`: push run 37487406807, pull request run 37487436430. That is not `c226b692f100eab0f5b288edc7d99369abadef16`. |
| Known defects | The 2026-10-06 H1 session on an `ae6a071` Release build is diagnostic and defect evidence. It is not candidate qualification, and it is not E2 acceptance. IOS-H1-08 was a carried-import defect: `pinCarriedCompanion` ignored `state` and wrote `active`. The Swift successor of `97c8704` refuses a missing, revoked, or other state and does not write an active record over a refusal or a local revocation. It is not an installed-admission bypass. D1 stays fail-closed. IOS-H1-02: revoke does not construct `LAContext`. Rotate calls enroll for the replacement key, then revokes the current key without a Face ID prompt. The hints now say that. P2 items IOS-H1-01, -03 to -07, and -09 are unchanged. None of this is in the wheel, sdist, or plugin zip |
| Missing | A device session. Simulator tests are engineering evidence only. Later, a person signing a build of this SHA, then a separate acceptance decision. Signing or installing alone does not qualify the channel |
| Selection / Authorization | Not granted |

## Smallest remaining actions

1. Selection (Yahor): choose the CLI publish candidate. The options are published rc14, the `b3367eb` sdist, the `fb05284` sdist, or this docs-only successor pack. Green CI does not make this choice. CI 20/20 success on `d42fe583dc3dd04e3cd3315f50608045c144d818`: push run 37487406807, pull request run 37487436430. That is not `c226b692f100eab0f5b288edc7d99369abadef16`.
2. Qualification (Yahor, in person): run the guarantee (1) session on the chosen wheel, and keep the identity row with the result. A human H1 diagnostic session ran 2026-10-06 on an `ae6a071` Release build (not this SHA). It found IOS-H1-01 through IOS-H1-09, including IOS-H1-08 (the Mac pinned a revoked key as active) and IOS-H1-02 (Rotate/Revoke do not prompt Face ID despite the hints). It is diagnostic and defect evidence. It is not candidate qualification, and it is not E2 acceptance.
3. Authorization (Yahor): a separate, explicit release decision. After any upload, compare the published bytes with the selected pack.
4. Leave E2 fail-closed. Do not schedule installed local, companion, or dual runs.
5. Keep the CLI and plugin bytes at `artifacts/rc15-2026-10-06-qualification-docfix/` unless a packed defect is reproduced. Swift-only fixes do not get a new pack.
6. Leave installed local, companion, and dual acceptance blocked. The carried-import fix does not close E2.
