# Engineering gate report — evidence+approval slice

Not a production sign-off. No merge, publish, retag, notarize, install, APPROVE, or biometric invocation.

## Identity

| Item | SHA / value |
| --- | --- |
| Package-tree (packed inputs) | `5f35cfcf401107648d61b84e29da5a2e8b45f708` |
| Pack-recording | `0fcfc8f6c39c359a153a81d08cd048280ece5e08` |
| Independent QA / CI subject | `9fde02ad530a792fc180d963012e6a3010b3375d` (evidence-only successor of the pack) |
| Engine | unpublished `0.2.0rc15` |
| Holder id | `com.darashkevich.runspecimen.holder` (D2 accepted) |
| Developer ID | team `UN6KF8636A`, DR pinned |
| D1 | installed admission fail-closed; `run_integration_complete` false; `e2_closed` false |

This report file is an evidence-only successor. Do not use its commit as a package identity. Packed archives were not rebuilt.

## Artifact hashes (canonical, `docs/CANDIDATE_MANIFEST.md`)

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `809431ea6683a7779e13eb3cd024c7bea4ce87dc90a483c9b8aa9892fac78dae` |
| `runspecimen-0.2.0rc15.tar.gz` | `b2db7b78cb742ab8934368d634f46e1fde02ba4cb5c1950b2986bd3e9b080cb9` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `d27799f75c74aea92fdf9594235179caa1ed58d90ef39e9ccc5225b47c37dda6` |

Independent QA at `9fde02a`: all four committed pack checksum entries match. CI-rebuilt sdists differ (`3272c9a274097a54012cf95d9616d0d44cac95f76905affd759a133d0de37b18` Darwin; `700a0225702a66aa54463046bc4a9d27759d53d9dd9fbdec328502ef60c13c5d` ubuntu 3.12) while wheel and plugin match. Channel limitation: sdist gzip metadata is not reproducible across hosts. Not a packed-input change.

## Platform tests

| Surface | Result | Skips |
| --- | --- | --- |
| Linux CPython 3.12.3 unittest | 650 ran, 0 fail | 78 (PyNaCl 29, CryptoKit signer 21, Darwin P-256 9, Darwin phone peer 5, rsync 5, bwrap 3, plus 6 single Darwin/compiler/pytest skips). **Linux skips do not cover Darwin** |
| Linux targeted P1/P2/P3/plugins + six NEW-01 | 65 ran, 0 fail | 1 (`pytest` absent) |
| Independent QA Mac 3.11.10 at `9fde02a` | same 65 targeted, 0 fail | 1 |
| CI macos 3.11.9 / 3.14.7 `release_check` at `9fde02a` | 650 ran, 0 fail; `ok: true` | 35 (PyNaCl 29, bwrap 3, Linux ldd 2, pytest 1) |
| CI `macos-app` SwiftPM at `9fde02a` | retry green: 110 executed, 0 fail, SMOKE OK | 1 (`testSecureEnclaveHumanHarnessIsNotRunByAutomation`). First pass failed `testInterruptedOrPartialWritesLeaveNoFile` (missing `/private/tmp/rs-touchid-diag` intermediate); xattr retry hid it. Fixture now creates that root |
| Holder Swift `apps/holder` | **not run** | 21 `HolderSocketClientTests` + 3 `DaemonKeyFeasibilityTests` are absent from CI. No Swift here. YD_MBP unused (live daemon must not be touched) |

NEW-01: CLOSED at package tree `5f35cfc`; independent QA confirmed at `9fde02a`.

## CI links at `9fde02a`

- Push (cancels → workflow failure): https://github.com/darashkevich/runspecimen/actions/runs/37365807962
- PR (cancels → workflow failure): https://github.com/darashkevich/runspecimen/actions/runs/37365811742

Unique greens (all 9 names): ubuntu 3.9–3.14, macos 3.11, macos 3.14, macos-app. See `GOLDEN-MASTER-NOTES.md` for job URLs. No test-assertion failures in `release-check`. macos-app product tests passed only on retry until the fixture fix.

## Open findings

| ID | Class | Status |
| --- | --- | --- |
| E2 | Engineering gap | Open. Root-daemon Secure Enclave creation is unsupported. A biometric press does not close this. Installed admission stays fail-closed |
| Holder Swift CI | Engineering gap / evidence hole | `swift test --package-path apps/holder` is not a CI job. Exact-candidate counts unavailable |
| Sdist host hash | Channel limitation | Wheel/plugin stable; sdist hash varies by pack host. Canonical table is the Linux pack in this directory |
| Workflow cancel | Channel limitation | Duplicate push+PR jobs cancel; combined unique matrix is green |
| PR #39 body | Housekeeping | Not agent-managed. A labeled comment is sufficient |

## Residuals

**Engineering gaps:** E2 / `e2_closed` false / `run_integration_complete` false; holder Swift not in CI; Darwin rerun of the diagnostic-root fixture pending successor CI.

**Human acceptance:** H1 Touch ID / Face ID press. H1 does not close E2.

**Release / operator (not authorized):** H2 live holder install; H3 DTS send; H4 Developer ID + notarize; H5 PyPI/retag; H6 Store/TestFlight; H7 merge #39.

## Disposition

Engineering gate of the evidence+approval slice: NEW-01 closed; packed hashes stable; D1/D2 locked; combined CI unique matrix green at `9fde02a` with the macos-app retry caveat. Not production qualification. Not Mac/Swift/holder full coverage.
