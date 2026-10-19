# Authorized blocker remediation — 19 October 2026

Based on main `4514bdc7f2f1718889c21cc50920d7fea6314ece` and the separate PR #76 continuation from `3670fa82c9277f03b0ee66ba9303d77c166baa1d`.

| Finding | Change / disposition |
| --- | --- |
| PR75-01 | Active Store and release documentation identifies the existing project version 0.1.6 (16). Historical artifact versions remain historical. CI compares both Info plists, project.yml, pbxproj, the ASC metadata, APP_STORE and active release documents. Mutation tests exercise each source. This does not select scope or authorize a build/upload. |
| PR75-03 / PR75-05 | Checklists call export_mas.sh. Committed options and script default to local export. Unresolved/invalid team IDs fail before export. Upload remains an explicit selection requiring separate authorization. |
| PR75-04 | Removed the CLI discovery attributesOfItem size probe in favor of a bounded 64-byte content read. Moved the standalone diagnostic filesystem gate into its own Swift source, excluded from the Xcode Store target. The committed pbxproj already lists sources explicitly and does not include that new file. The diagnostic remains available through Swift Package Manager. No FileTimestamp reason was added for this excluded code. |
| DSH-01 / DSH-04 | Land the frozen 0.2.3 candidate. Dashboard lifetime is timeoutMs, default 600000 ms / ten minutes from launch, bounded even without an explicit stop. Tool output reports that same maximum lifetime. 0.2.2 already enforced/reported the bound, but retained one contradictory README paragraph. 0.2.3 corrected that paragraph. |
| DSH-02 | Already fixed in 0.2.2: EPERM cannot establish process death; persistent inspection denial becomes bounded typed cleanup failure. 0.2.3 additionally fixes the normal-parent-exit/surviving-descendant path to retain its typed cleanup result. |
| DSH-03 | Already fixed in 0.2.2: package and lockfile root licence both Apache-2.0; retained in 0.2.3. Added a consistency assertion. |
| DSH-05 | Already fixed in 0.2.2: timedOut and cancelled are separate outcomes. Retained in 0.2.3. |
| MAIN-05 | Each schema test owns a unique UserDefaults suite and an in-memory pairing token. Removing an injected token error hook cannot fall through to the real Keychain. Ported to main and PR #76 independently. |
| PR76 P3s | Separate PR #76 head clears interrupted settlement drafts, maps biometric enrollment cancellation to neutral feedback, and prevents unchanged pairing form drafts restoring old session/holder pins after verified re-pairing. |

## Privacy review

Apple's current [required-reason API list](https://developer.apple.com/documentation/bundleresources/app-privacy-configuration/nsprivacyaccessedapitypes/nsprivacyaccessedapitype) was checked on 2026-10-19. attributesOfItem is not itself named, but stat, fstat, fstatat, lstat and timestamp properties are listed. A size-only purpose does not exempt a listed stat call.

An initial Release app build exposed fstat/fstatat/lstat imports from unused diagnostic code. After separating that diagnostic, the actual Xcode Release Store Core library built successfully and its undefined symbols contained none of these file-timestamp APIs. The Store CLI discovery no longer reads file attributes. This is source/build evidence for these paths, not verification of a final processed Store archive or every embedded runtime dependency. Final artifact privacy review remains necessary before release.

## Validation and evidence

Evidence retained outside the checkout under `sf/outputs/grok-remediation/`:

- `authorized-blockers-ios-red.log`: four new PR #76/isolation tests reproduced 12 failed assertions before fixes.
- `authorized-blockers-ios-green-final.log`: 156 schema tests passed on the PR #76 continuation.
- `authorized-main-ios-green.log`: 118 schema tests passed on the main-based branch.
- `authorized-store-red.log`, `authorized-export-red.log`, `authorized-privacy-red.log`, `authorized-source-staging-red.log`: documentation, unresolved-team, diagnostic exclusion and source staging failures before their fixes.
- `authorized-store-green.log`: release identity/export/privacy/source-staging checks pass. CI includes these checks.
- `authorized-dsh-baseline-red.log`: 0.2.1 fails timeout/lifetime/descendant regressions. The EPERM baseline was not rerun against 0.2.1 because that implementation lacks the bounded cleanup guarantee.
- `authorized-dsh-022-check.log`: 0.2.2 passes timeout, persistent EPERM and lifetime regressions, but fails the added typed parent-exit regression.
- `authorized-dsh-green-final.log`: 43 DSH tests passed; candidate lib files remain those of frozen 0.2.3.
- `authorized-macos-tests-clean.log`: 110 Core tests (one skipped) plus six app tests passed. The first attempt hit a generated-bundle resource-fork signing error; a clean temporary scratch directory resolved it.
- `authorized-store-core-build.log`, `authorized-store-core-symbols.log`: Xcode Release Core build and undefined-symbol audit.

The simulator XCTest logs report all tests passing. Xcode's result finalizer logs an invalid operatingSystemBuild value on this host and can remain running after the suites finish; these logs are test-suite evidence, not a clean archive/export result.

The broader offline release gate initially stopped at its environment prerequisite: this Python installation lacks setuptools >=77 in its non-user site-packages. It did not build or validate a distributable release.

## Decisions left with Yahor

PR75-02 scope/build selection, MAIN-04 CLI minimum version, remote-confirm biometric policy and the replacement QA reviewer are unchanged. No merge, upload, release, installed trust/key changes or approval actions were performed.
