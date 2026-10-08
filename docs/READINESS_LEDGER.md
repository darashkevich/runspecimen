# Readiness ledger

Current engineering record for unpublished `0.2.0rc15`. Not a production sign-off. Not a claim of perfection. Do not merge, publish, retag, notarize, submit, deploy, install the holder, change entitlements, handle credentials, type `APPROVE`, or invoke biometrics from this document.

This file is the live ledger. Golden-master notes are historical. Later commits that only edit this file are evidence-only successors and are not a new package identity.

## Exact identity

| Item | Value |
| --- | --- |
| Working branch | `cursor/qa-docfix-rc15-1c51` (from `8015b6d` / `cursor/rc15-bump-pack-ced9`) |
| Source SHA this ledger was written against | Frozen QA candidate `8015b6d8017e5566f7558cc916dc0ee470c653ad`. Engine payload still `fb05284` plus this docs/help/acceptance successor. Not `main` |
| This follow-up | Qafix9-pack successor of qafix8. Pack `artifacts/0.2.0rc15-2026-10-08-qafix9/`. Version stays `0.2.0rc15`. Engine source is the PR #63 head that records that pack (not a self-referencing SHA). `src/` tree `f2c05c18b5a0156b616b0733f7653c45acf02b47`. Prior packs, including `artifacts/0.2.0rc15-2026-10-08-qafix8/`, `artifacts/0.2.0rc15-2026-10-08-qafix7/`, `artifacts/0.2.0rc15-2026-10-08-qafix6/`, `artifacts/0.2.0rc15-2026-10-08-qafix5/`, `artifacts/0.2.0rc15-2026-10-08-qafix4/`, `artifacts/0.2.0rc15-2026-10-07-qafix3/`, `artifacts/0.2.0rc15-2026-10-07-qafix2/`, `artifacts/0.2.0rc15-2026-10-07-qafix/`, and `artifacts/0.2.0rc15-2026-10-06-bump/`, not overwritten. Not production sign-off |
| Historical IRC tip | `a0dc23361856db8a68075471860bd4ab25af838c` |
| NEW-01 package tree | `5f35cfcf401107648d61b84e29da5a2e8b45f708` |
| Engine | unpublished `0.2.0rc15` |
| Holder id | `com.darashkevich.runspecimen.holder` (D2 accepted) |
| Developer ID | team `UN6KF8636A`, designated requirement pinned |
| D1 | installed admission fail-closed; `run_integration_complete` false; `e2_closed` false |
| `main` | `93f9b5708c1ba2d9b325ae2f9016d6a472fe6a20` (published history through MAS freeze). Does not contain this candidate |

Draft operator merge to `main`: [#51](https://github.com/darashkevich/runspecimen/pull/51) (blocked on human/release gates).

## Artifact provenance

Canonical table: [CANDIDATE_MANIFEST.md](CANDIDATE_MANIFEST.md). Checklist: [QUALIFICATION_CHECKLIST.md](QUALIFICATION_CHECKLIST.md). Pack: `artifacts/0.2.0rc15-2026-10-08-qafix9/`. Prior packs, including `artifacts/0.2.0rc15-2026-10-08-qafix8/` (`29347132…` / `68d5a98b…`), `artifacts/0.2.0rc15-2026-10-08-qafix7/` (`76052571…` / `68d5a98b…`), `artifacts/0.2.0rc15-2026-10-08-qafix6/` (`7bb9f811…` / `68d5a98b…`), `artifacts/0.2.0rc15-2026-10-08-qafix5/` (`a53d0725…` / `583c208b…`), `artifacts/0.2.0rc15-2026-10-08-qafix4/` (`e9e73401…` / `bd9e6520…`), `artifacts/0.2.0rc15-2026-10-07-qafix3/` (`cd09d72b…` / `bd9e6520…`), `artifacts/0.2.0rc15-2026-10-07-qafix2/` (`659c72cf…` / `b181822a…`), `artifacts/0.2.0rc15-2026-10-07-qafix/` (`1ac1ca57…` / `b181822a…`), `artifacts/0.2.0rc15-2026-10-06-bump/` (`886f90d0…` / `a68094f0…`), `artifacts/rc15-2026-10-06-qualification-docfix/` (`5fd68a6f…` / `a68094f0…`), `artifacts/rc15-2026-10-06-qualification/` (`de90ab7a…` / `68685be9…`), and `artifacts/rc15-2026-10-06-isolated-evidence/` (`682fe989…` / `809431ea…`), were not overwritten.

| File | SHA-256 | Provenance |
| --- | --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `48825ee2e1553e76ddb1fa0e7ef421c79c5e9f1ba25400d2eb963dba877cba7c` | `src/` tree `f2c05c18b5a0156b616b0733f7653c45acf02b47` (approval binding) |
| `runspecimen-0.2.0rc15.tar.gz` | `6ce004b298d29e4a5787cdbcf7cfd8017352c0829e851e1e9d10fdfa21c90ceb` | Packed engine + tests/CHANGELOG successor of qafix8 |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `ea38d5bc345eb8b2993611b50cfc943b97d55138a83205241fad6dd4bb3e9dcb` | Unchanged from qafix/qafix2/qafix3/qafix4/qafix5/qafix6/qafix7/qafix8; does not embed the wheel |

**OPEN-SDIST (closed).** Historical mismatch: committed `b2db7b78cb742ab8934368d634f46e1fde02ba4cb5c1950b2986bd3e9b080cb9` kept builder uid/gid/uname, so a rebuild produced `6979460d…`. `release_check.py` now pins `SOURCE_DATE_EPOCH`, gzip mtime 0, owner 0/0, empty uname/gname, sorted members, 0644/0755. Regression: `tests/test_release_archive_reproducibility.py`. The golden-master sdist `c001cb08…` stays in that directory. The `b3367eb` sdist `682fe989…` stays in `artifacts/rc15-2026-10-06-isolated-evidence/`. The `fb05284` sdist `de90ab7a…` stays in `artifacts/rc15-2026-10-06-qualification/`. The docfix sdist `5fd68a6f…` stays in `artifacts/rc15-2026-10-06-qualification-docfix/`. The bump pack sdist `886f90d0…` stays in `artifacts/0.2.0rc15-2026-10-06-bump/`. The qafix pack sdist `1ac1ca57…` stays in `artifacts/0.2.0rc15-2026-10-07-qafix/`. The qafix2 pack sdist `659c72cf…` stays in `artifacts/0.2.0rc15-2026-10-07-qafix2/`. The qafix3 pack sdist `cd09d72b…` stays in `artifacts/0.2.0rc15-2026-10-07-qafix3/`. The qafix4 pack sdist `e9e73401…` stays in `artifacts/0.2.0rc15-2026-10-08-qafix4/`. The qafix5 pack sdist `a53d0725…` stays in `artifacts/0.2.0rc15-2026-10-08-qafix5/`. The qafix6 pack sdist `7bb9f811…` stays in `artifacts/0.2.0rc15-2026-10-08-qafix6/`. The qafix7 pack sdist `76052571…` stays in `artifacts/0.2.0rc15-2026-10-08-qafix7/`. The qafix8 pack sdist `29347132…` stays in `artifacts/0.2.0rc15-2026-10-08-qafix8/`. The current pack sdist is `6ce004b2…` in `artifacts/0.2.0rc15-2026-10-08-qafix9/`. Do not restore the older digests as current.

Published rc14 bytes are unchanged. Homebrew still pins rc14.

## Tests

`9fde02a` independent QA (650 Python / 6 skip, 110 Swift / 1 human skip, NEW-01 and R-01..R-06 closed) is **historical** and is **not** current-tip sign-off.

### This follow-up (`cursor/qa-32cd6a2-fixes` on tip `32cd6a2`)

ChatGPT QA-32-01 is **real**. Marker-based `BoundedProcessCaptureTests` still pass `readyDeadline: 20` because cold CI `/usr/bin/python3` can exceed 5s before `READY`. Production `LiveProcessCapture` does not pass a marker, so the 5s default is not on the engine path (15-minute command timeout starts at spawn). The production default stays **5s** as `BoundedProcessCapture.defaultReadyDeadline`, pinned and exercised when omitted. Do not raise it to hide fixture startup.

Wheel comparison now checks the full member set (including `WHEEL`/`RECORD`) and validates RECORD payload hashes against zip bytes. Smoke retry matches only Apple codesign detritus strings and does not retry when an XCTest assertion is in the log. Isolated holder Swift fails if zero tests ran, refuses `RS_HOLDER_SOCKET` and `RS_HOLDER_INSTALL_CONSENT=yes`, and does not retry. Packed reproducibility tests add one case; expected Python count is **652**.

### Successor first-pass at `bd3db41` (PR #52, now merged)

20 unique SUCCESS checks (10 job names × push + PR). **Zero cancelled** jobs. Workflow conclusion **success** on both events. This is not production sign-off.

| Surface | Result | First pass vs retry | Channel |
| --- | --- | --- | --- |
| CI push [37404310314](https://github.com/darashkevich/runspecimen/actions/runs/37404310314) | Workflow **success**. All 10 jobs green, 0 cancelled | macos-app `FIRST_PASS: OK` 110 / 1 human skip / 0 fail (no retry). `testCancellationKillsAChildThatIgnoresSIGTERM` passed 2.826s. holder-swift `HOLDER_FIRST_PASS: OK` 24 / 0 fail (21 socket + 3 feasibility) | Engine + Mac app + isolated holder |
| CI PR #52 [37404325426](https://github.com/darashkevich/runspecimen/actions/runs/37404325426) | Workflow **success**. All 10 jobs green, 0 cancelled | macos-app `FIRST_PASS: OK` 110 / 1 human skip / 0 fail (no retry). holder-swift `HOLDER_FIRST_PASS: OK` 24 / 0 fail | Engine + Mac app + isolated holder |
| Darwin `release-check` 3.11/3.14 | 651 tests, 35 skipped, 0 failed | First pass (no hidden retry) | Engine |
| Ubuntu `release-check` 3.12 | 651 tests, 77 skipped, 0 failed | First pass | Engine |

651 vs historical 650 is successor work already on `dd85691` (OPEN-SDIST / P3), not a claim that `9fde02a` counts still apply.

### `51dcb0b` — packed-test defect, not a Swift regression

Push [37405306078](https://github.com/darashkevich/runspecimen/actions/runs/37405306078) and PR [37405309218](https://github.com/darashkevich/runspecimen/actions/runs/37405309218): workflow **failure**. 8 unique `release-check` names failed on both events. macos-app and holder-swift stayed first-pass green on both (`FIRST_PASS: OK` 110 / 1 skip; `HOLDER_FIRST_PASS: OK` 24 / 0 fail; no retry).

Cause: `tests/test_isolated_holder_ci_guard.py` is packed (`MANIFEST.in` `recursive-include tests *.py`). Rebuilt sdist `2c136c43ddbb6d55789f1342d0285225b494f719d3342b7248f9b8e8c09646cf` ≠ committed `316938ce…`. The four Python guards are withdrawn. Refuse-path stays in `apps/holder/Scripts/test_holder_isolated.sh`, `smoke_macos.sh`, and the `holder-swift` job. Expected Python count remains **651**. Archives were not rebuilt.

### Package-tree source `dd85691` (before this follow-up)

| Surface | Result | First pass vs retry | Channel |
| --- | --- | --- | --- |
| CI push [37392914454](https://github.com/darashkevich/runspecimen/actions/runs/37392914454) | Workflow **success**. All 9 jobs green | macos-app first `swift test` 110 / 1 skip / 0 fail, **no retry**, SMOKE OK | Engine + Mac app |
| CI PR #51 [37392937045](https://github.com/darashkevich/runspecimen/actions/runs/37392937045) | Workflow **success**. All 9 jobs green | macos-app **first pass failed** `testCancellationKillsAChildThatIgnoresSIGTERM` (child not ready in 5s). xattr retry hid it: 110 / 1 skip / 0 fail | Engine + Mac app |
| Holder Swift `apps/holder` | Not in CI at `dd85691` (24 tests: 21 socket + 3 feasibility) | n/a | Holder source only |

Historical `9fde02a` skips on a well-provisioned Mac were 6. Linux local golden-master was 650 / 78 skip. Darwin CI `release_check` at the golden-master SHA was 650 / 35 skip.

### Isolated evidence directories (this follow-up, parent `ae6a071`)

Concurrent same-user runs no longer share `rs-holder-swift-first.log`, `rs-macos-swift-first.log`, or a PID scratch directory. Each invocation creates an exclusive `mktemp` directory, writes that run's log inside it, copies the log out on failure, and deletes only the directory it created. `tests/test_isolated_script_evidence.py` covers concurrent logs, zero-test refusal, assertion-plus-codesign classification, and `RS_HOLDER_SOCKET` / install-consent refusal. Those tests use a PATH stub. They do not call a live daemon.

Local Homebrew Python 3.12.14 `release_check.py`: 658 tests, 36 skipped, 0 failed, then 4 distribution tests. The extra skip was `test_wheel_and_sdist_digests_repeat` while the new pack was not on disk yet. After `artifacts/rc15-2026-10-06-isolated-evidence/SHA256SUMS` existed, that test and the six evidence tests passed (9 tests, 0 skipped) and the rebuilt sdist matched `682fe989…`. Wheel `809431ea…` matched too. D1/D2 are unchanged: installed admission stays fail-closed, `run_integration_complete` and `e2_closed` stay false, and the accepted holder id stays out of `production_verifier_pin()`.

### Qualification suite (this successor)

CPython 3.12.14, pack already present: 658 tests, 35 skipped, exit 0. Rebuilt sdist `de90ab7a…` and wheel `68685be9…` matched `artifacts/rc15-2026-10-06-qualification/SHA256SUMS`. The 35 skips are PyNaCl (29), bubblewrap (3), Linux `ldd` (2), and pytest (1). They were not simulated as passes. Channel gates: [QUALIFICATION_CHECKLIST.md](QUALIFICATION_CHECKLIST.md). Package commit `fb05284` CI is 20/20 (push 37480847104, pull request 37480855659). Evidence-only tip `c0812ac` CI is 20/20 (push 37482547229, pull request 37482561658). The docs-only successor pack `artifacts/rc15-2026-10-06-qualification-docfix/` (sdist `5fd68a6f…`, wheel `a68094f0…`, plugin unchanged, report `1fb513a1…` on linux/3.12.3) stays historical. CI 20/20 on `d42fe583dc3dd04e3cd3315f50608045c144d818` (push 37487406807, pull request 37487436430), not on evidence-only `c226b692f100eab0f5b288edc7d99369abadef16`. This bump pack is `artifacts/0.2.0rc15-2026-10-06-bump/` (sdist `886f90d0…`, wheel `a68094f0…`, plugin unchanged, report `529718ff…` on linux/3.12.3). Local `release_check.py` first pass: 658 tests, 77 skipped, exit 0 (reproducibility skipped while the new pack was absent). Second pass: 658 tests, 76 skipped, exit 0; reproducibility compare executed against that directory and matched (`cmp` of all five files).

## Open items

| ID | Class | Owner | Channel | Next action |
| --- | --- | --- | --- | --- |
| E2 | Engineering gap | Engineering | Installed holder / exact-run admission | Keep fail-closed. Root `launchd` cannot create or reload a Secure Enclave key ([SECURE_ENCLAVE_ADMISSION.md](SECURE_ENCLAVE_ADMISSION.md)). A biometric press does not close this. Any other design is a new decision |
| SWIFT-STARTUP | Closed | Engineering | macos-app | Production default stays 5s (`defaultReadyDeadline`). Marker tests keep an explicit 20s CI python3 allowance. New tests pin the constant and fail a never-ready child at the default. Smoke does not retry assertion flakes |
| HOLDER-SWIFT-CI | Closed | Engineering | Holder | Isolated script refuses `RS_HOLDER_SOCKET` and install consent. Zero tests run fails the job. No retry |
| H1 | Human acceptance | Yahor | Local / companion / dual prompt | A human H1 diagnostic session ran 2026-10-06 on an `ae6a071` Release build (not this SHA). It found IOS-H1-01 through IOS-H1-09, including IOS-H1-08 (the Mac pinned a revoked key as active) and IOS-H1-02 (Rotate/Revoke do not prompt Face ID despite the hints). It is diagnostic and defect evidence. It is not candidate qualification, and it is not E2 acceptance |
| H2 | Release / operator | Yahor | Developer ID holder | Live SMAppService install on a real Mac. Unauthorized here |
| H3 | Release / operator | Yahor | Apple | Send [APPLE_DTS_HOLDER_QUESTION.md](APPLE_DTS_HOLDER_QUESTION.md) |
| H4 | Release / operator | Yahor | Holder | Developer ID sign + notarize |
| H5 | Release / operator | Yahor | Engine | PyPI / retag of unpublished rc15. Not authorized |
| H6 | Release / operator | Yahor | Store / TestFlight | Upload. Approved Store app remains **0.1.4 (9)** |
| H7 | Release / operator | Yahor | `main` | Merge draft [#51](https://github.com/darashkevich/runspecimen/pull/51) only after human gates. **#39 is already merged** into EEC |

## Channel vs capability

| Channel | Actual | Must not claim |
| --- | --- | --- |
| CLI wheel/sdist | Unpublished rc15; doctor/validate/status work without Darwin verifier | Published; PyPI; Homebrew pin |
| Plugins | Adapter calls CLI; `freshness_check` is evaluate-only | Marketplace listing |
| Mac App Store | Approved **0.1.4 (9)** guarantee (1) only | This SHA has a Store archive; holder inside Store app |
| Developer ID holder | Source + isolated tests + isolated CI first-pass. Stage can write a temp package | Installed, notarized, SE admission, Store parity |
| iOS companion | Software tests. No device run | TestFlight / Store / physical presence at the Mac |
| Isolation | Default `none`. Opt-in `sandbox-exec` / `bwrap` are not an OS sandbox | Default confinement |

FAQ and USER_GUIDE already state unpublished rc15, default `none`, and E2 open. No site deploy.

## Remaining engineering limitation

Installed Secure Enclave admission stays fail-closed because this holder is a root daemon and Apple's current documents say that process cannot create, reload, or prompt for a Secure Enclave key. `run_integration_complete` and `e2_closed` stay false. H1 cannot close that gap.

## Smallest remaining decision/action list

1. Yahor (human): H1 on a named, provenance-identified build. A biometric press does not close E2.
2. Yahor (operator): H2–H6 only under a separate authorization. H7 is merge of draft [#51](https://github.com/darashkevich/runspecimen/pull/51) to `main`, not #39. Do not merge #51 from this record.
3. Product decision (not this prototype): whether a later per-user Aqua agent may create the key. That is not a root daemon and is not authorized here.

Engineering first-pass recording for this follow-up is done. E2 remains the open engineering limitation.
