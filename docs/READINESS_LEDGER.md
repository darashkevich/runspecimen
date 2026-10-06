# Readiness ledger

Current engineering record for unpublished `0.2.0rc15`. Not a production sign-off. Not a claim of perfection. Do not merge, publish, retag, notarize, submit, deploy, install the holder, change entitlements, handle credentials, type `APPROVE`, or invoke biometrics from this document.

This file is the live ledger. Golden-master notes are historical. Later commits that only edit this file are evidence-only successors and are not a new package identity.

## Exact identity

| Item | Value |
| --- | --- |
| Working branch | `cursor/evidence-expansion-coherence` |
| Source SHA this ledger was written against | `dd85691e42e49df7a25caaddd27fa313e3fdf728` (PR #50 merge; also head of draft #51) |
| Historical IRC tip | `a0dc23361856db8a68075471860bd4ab25af838c` |
| NEW-01 package tree | `5f35cfcf401107648d61b84e29da5a2e8b45f708` |
| Engine | unpublished `0.2.0rc15` |
| Holder id | `com.darashkevich.runspecimen.holder` (D2 accepted) |
| Developer ID | team `UN6KF8636A`, designated requirement pinned |
| D1 | installed admission fail-closed; `run_integration_complete` false; `e2_closed` false |
| `main` | `93f9b5708c1ba2d9b325ae2f9016d6a472fe6a20` (published history through MAS freeze). Does not contain this candidate |

Draft operator merge to `main`: [#51](https://github.com/darashkevich/runspecimen/pull/51) (blocked on human/release gates).

## Artifact provenance

Canonical table: [CANDIDATE_MANIFEST.md](CANDIDATE_MANIFEST.md). Pack: `artifacts/rc15-2026-10-05-golden-master/`. Prior `artifacts/rc15-*` directories were not overwritten.

| File | SHA-256 | Provenance |
| --- | --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `809431ea6683a7779e13eb3cd024c7bea4ce87dc90a483c9b8aa9892fac78dae` | NEW-01 package tree. Unchanged by OPEN-SDIST |
| `runspecimen-0.2.0rc15.tar.gz` | `316938cea04f6747e32fd88f263533d710d489861fc36372c897680088fd63d3` | OPEN-SDIST rewrite at #50. Host-independent metadata |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6` | Unchanged |

**OPEN-SDIST (closed).** Historical mismatch: committed `b2db7b78cb742ab8934368d634f46e1fde02ba4cb5c1950b2986bd3e9b080cb9` kept builder uid/gid/uname, so a rebuild produced `6979460d…`. `release_check.py` now pins `SOURCE_DATE_EPOCH`, gzip mtime 0, owner 0/0, empty uname/gname, sorted members, 0644/0755. Regression: `tests/test_release_archive_reproducibility.py`. This host re-read the pack sdist and got `316938ce…`. Do not restore `b2db7b78…` as current.

Published rc14 bytes are unchanged. Homebrew still pins rc14.

## Tests at `dd85691` (not historical `9fde02a`)

`9fde02a` independent QA (650 Python / 6 skip, 110 Swift / 1 human skip, NEW-01 and R-01..R-06 closed) is **not** current-tip sign-off.

| Surface | Result | First pass vs retry | Channel |
| --- | --- | --- | --- |
| CI push [37392914454](https://github.com/darashkevich/runspecimen/actions/runs/37392914454) | Workflow **success**. All 9 jobs green | macos-app first `swift test` 110 / 1 skip / 0 fail, **no retry**, SMOKE OK | Engine + Mac app |
| CI PR #51 [37392937045](https://github.com/darashkevich/runspecimen/actions/runs/37392937045) | Workflow **success**. All 9 jobs green | macos-app **first pass failed** `testCancellationKillsAChildThatIgnoresSIGTERM` (child not ready in 5s). xattr retry hid it: 110 / 1 skip / 0 fail | Engine + Mac app |
| Holder Swift `apps/holder` | Not in CI at `dd85691` (24 tests: 21 socket + 3 feasibility) | n/a | Holder source only |

Historical `9fde02a` skips on a well-provisioned Mac were 6. Linux local golden-master was 650 / 78 skip. Darwin CI `release_check` at the golden-master SHA was 650 / 35 skip. This ledger does not reuse those counts as `dd85691` qualification.

## Open items

| ID | Class | Owner | Channel | Next action |
| --- | --- | --- | --- | --- |
| E2 | Engineering gap | Engineering | Installed holder / exact-run admission | Keep fail-closed. Root `launchd` cannot create or reload a Secure Enclave key ([SECURE_ENCLAVE_ADMISSION.md](SECURE_ENCLAVE_ADMISSION.md)). A biometric press does not close this. Any other design is a new decision |
| SWIFT-STARTUP | Engineering (in this follow-up) | Engineering | macos-app | Tests now pass `readyDeadline` 20s. Smoke records FIRST_PASS and retries only on codesign/xattr detritus |
| HOLDER-SWIFT-CI | Engineering (in this follow-up) | Engineering | Holder | Isolated `holder-swift` job: `apps/holder/Scripts/test_holder_isolated.sh`. No live socket, no install, first pass only |
| H1 | Human acceptance | Yahor | Local / companion / dual prompt | Press Touch ID / Face ID on a provenance-identified build. Does **not** close E2 |
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
| Developer ID holder | Source + isolated tests. Stage can write a temp package | Installed, notarized, SE admission, Store parity |
| iOS companion | Software tests. No device run | TestFlight / Store / physical presence at the Mac |
| Isolation | Default `none`. Opt-in `sandbox-exec` / `bwrap` are not an OS sandbox | Default confinement |

FAQ and USER_GUIDE already state unpublished rc15, default `none`, and E2 open. No site deploy.

## Remaining engineering limitation

Installed Secure Enclave admission stays fail-closed because this holder is a root daemon and Apple's current documents say that process cannot create, reload, or prompt for a Secure Enclave key. `run_integration_complete` and `e2_closed` stay false. H1 cannot close that gap.

## Smallest remaining decision/action list

1. Engineering: land this follow-up (startup deadline + isolated holder CI + this ledger) and read successor first-pass CI, including `holder-swift`.
2. Yahor (human): H1 on a named build, knowing it does not close E2.
3. Yahor (operator): H2–H6 only under a separate authorization; H7 is merge of #51 to `main`, not #39.
4. Product decision (not this prototype): whether a later per-user Aqua agent may create the key. That is not a root daemon and is not authorized here.
