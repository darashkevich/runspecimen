# Development-app acceptance, 2026-09-28

Unpublished candidate. Not a Store package. Not uploaded.

App: `/private/tmp/rs-local-qa-next/DerivedData/Build/Products/Release/RunSpecimen.app`
Version string: 0.1.5 (13). Apple Development: jahorka@gmail.com (PK6W7JVY6D). Sandbox true. `com.apple.security.network.server` absent.
Bundled helper reported `runspecimen 0.2.0rc15`.
`/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03. The shared container was restored after the session.

## What the GUI did

- Workspace switch: restored `/private/tmp/rs-qa-ws/beta` with no contract, then Open Workspace selected `/private/tmp/rs-qa-ws/alpha` and cleared the contract. Opening `/private/tmp/rs-qa-ws/empty-other` cleared it again. Open Reviewer Demo then showed campaign `reviewer-demo`, run `run-001`.
- Malformed contract: alert “Could not read contract: The data couldn’t be read because it isn’t in the correct format.”
- Unreadable contract (`chmod 000`): alert “The file “unreadable.json” couldn’t be opened because you don’t have permission to view it.”
- Contract outside the workspace: alert “Contract must be a regular file inside the selected workspace.”
- Opening `contract.json` inside alpha left the workspace on alpha.
- Receipts on the reviewer demo: Digest and Compare output bytes both showed `RunSpecimen error: certificate not found for reviewer-demo/run-001`. Typing Other campaign `other-campaign` and Other run `other-run` enabled Diff receipts, which showed the same missing-certificate error.
- Retain: Choose retain folder set `/private/tmp/rs-qa-matrix/retain`. Retain… presented “Retain incident pack” with “Cancel copies nothing.” The Cancel button was pressed. The destination stayed empty.
- Output on screen: Doctor OK, Python 3.12.14; Chain OK; status JSON for `reviewer-demo` / `run-001`, phase `none`, approval null. Lifecycle Validate was enabled. Command-1 produced no error sheet and did not change that status. No run was started. APPROVE was not typed.
- Resize: window size changed from 880×600 to 1200×820.
- Keyboard: Tab moved focus to the RunSpecimen window. Settings closed with Escape. About closed from its sheet button.
- Accessibility: Settings Close is an AppKit button. System Events reported `name=Close Settings` and `description=Close Settings`, and the click dismissed the sheet. SwiftUI buttons inside Workflows did not publish their titles; the receipt actions were reached by control order, and the confirmation buttons did publish “Retain incident pack” and “Cancel”.

A large captured run was not produced. That path waits for a human APPROVE, which this pass did not type. Byte-cap behavior remains in `BoundedProcessCaptureTests`.

## Local unpublished archives

`scripts/release_check.py --output-dir /tmp/rs-rc15-artifacts` passed. Python 3.12.14 ran 409 tests, 35 skipped (PyNaCl, pytest, and Linux `ldd` checks absent in this interpreter), then built:

| File | SHA-256 |
| --- | --- |
| `runspecimen-0.2.0rc15-py3-none-any.whl` | `24082fbf9006c627953f6d9c5b8f0c9dca9fb006efcae3b54472b7dfa641d871` |
| `runspecimen-0.2.0rc15.tar.gz` | `50c24f85882226066d0278c612e9564367a0cf22ec824c96877e71ef41a9acd7` |
| `runspecimen-plugin-0.2.0-rc.15.zip` | `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` |

These are not the published rc14 archives and were not uploaded. Published wheel `d720bf5163a2b250699c30e804f89708e71c1c0d22682fbb43a4644b59c45948`, sdist `6ffcfe2fba33dea6b4b8bdf9369f8a05b5d4e286a1e8e01ec46bdbb81cfc4af3`, plugin zip `0073e04e21bd225da328de06ef840ead6956a8cced4510a0025fb1e2ddc7fc16` were not replaced. Homebrew still pins rc14.

Swift on this tree: 75 tests, 1 skipped, 0 failures. The skip is the human Secure Enclave harness. The diagnostic binary was run without `--human-invoked` and exited 2.

## Later pass on the same unpublished identity

RSBA2 generations are inside the signed bytes. Import accepts only version `RSBA2`. `consumeEnrolled` reloads the live enrollment under the revocation lock. A crafted dual record that stores one public key twice is rejected and does not spend the nonce. The diagnostic directory must resolve to `/private/tmp/rs-touchid-diag` or a directory inside it. `preview` was run and exited 0. `enroll` without `--human-invoked` exited 2. Secure Enclave was not called.

Swift: 89 tests, 1 skipped, 0 failures. iOS Observe simulator build succeeded. The carried-approval screen can create a development software P-256 key and sign the displayed request. That signature is not Face ID, is not sent, and is not a Mac approval.

`scripts/release_check.py --output-dir /tmp/rs-qa-c072-fix-artifacts` passed on Python 3.12.14: 409 tests, 35 skipped. The wheel, sdist, and plugin zip hashes matched the earlier unpublished rc15 archives above, because those archives do not pack `apps/` or `docs/BIOMETRIC_APPROVAL.md`. They were not uploaded. Published rc14 hashes were not replaced.

The development app was rebuilt at the same path. Authority remained Apple Development: jahorka@gmail.com (PK6W7JVY6D). Sandbox true. `network.server` absent. Version string 0.1.5 (13). Payload helper still `runspecimen 0.2.0rc15`. The app launched. Settings Close reported `name=Close Settings` and `description=Close Settings`, the click set sheets to 0, and Escape dismissed Settings again. The earlier workspace, receipt, retain, and resize matrix was not repeated. APPROVE was not typed. The process was quit and the shared container restored. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03.

## Filesystem-order diagnostic and iOS isolation

`TouchIDDiagnosticGate` resolves each symlink before applying `..`. A path whose parent realpath leaves `/private/tmp/rs-touchid-diag` is refused. Hop 17 fails closed. Writes go through an owned directory descriptor opened with `O_NOFOLLOW`. Swift on this tree: 94 tests, 1 skipped, 0 failures. The skip is still the human Secure Enclave harness. `preview` exited 0 and printed the sample companion request. `enroll` without `--human-invoked` exited 2. Secure Enclave was not called.

`RSBA2Package.parse` rejects a missing, empty, or NUL field, a non-canonical generation, and a role key that the policy does not use. Mac and iOS tests share that parser. The companion canonical vector digest is `7f0b15d280bc57ac4416fc0e170e2480117bd78e316b570ed6d84ce6d73abced` on both. Enrollment records carry role and provenance. A swapped role and a software-development key fail `consumeEnrolled` without spending the nonce. `consumeForExecution` rejects two software keys. No run path calls it. A software consume is not biometric completion.

The shipping Observe target does not compile `DevelopmentCompanionSigner.swift`. That file is only in `RunSpecimenObserveDev`, behind `RS_OBSERVE_DEV_SIGNER`. The shipping scheme does not build the dev target. The shipping debug dylib contains “Enroll this iPhone” and does not contain `ios-dev-phone`. The dev dylib contains both. `NSFaceIDUsageDescription` is present. iOS simulator schema tests on iPhone 17: 3 passed. They call enroll, sign, and revoke with `humanTap: false` and create no pairing file. Face ID was not prompted.

`scripts/release_check.py --output-dir /tmp/rs-qa-764fix-artifacts` on Python 3.12.14: 409 tests, 35 skipped. Wheel, sdist, and plugin zip hashes matched the unpublished rc15 archives above. They were not uploaded.

## Development-app matrix on this build

App path unchanged. Authority Apple Development: jahorka@gmail.com (PK6W7JVY6D). Sandbox true. `network.server` absent. Version 0.1.5 (13). Settings shows the bundled helper path and `runspecimen 0.2.0rc15`.

- Open Reviewer Demo showed campaign `reviewer-demo`, run `run-001`, Doctor OK, Python 3.12.14, Chain OK, and status JSON phase `approved` from the bundled demo record. This pass did not type APPROVE and did not start a run.
- Malformed contract: “Could not read contract: The data couldn’t be read because it isn’t in the correct format.”
- Unreadable contract: “The file “unreadable.json” couldn’t be opened because you don’t have permission to view it.”
- Contract outside the workspace: “Contract must be a regular file inside the selected workspace.”
- Receipts on the reviewer demo: Digest and Compare output bytes both showed `RunSpecimen error: certificate not found for reviewer-demo/run-001`. Other campaign `other-campaign` and Other run `other-run` then Diff receipts showed the same missing-certificate error.
- Retain: Choose retain folder set `/private/tmp/rs-qa-764-matrix/retain`. Retain… presented buttons described “Retain incident pack” and “Cancel”. Cancel was pressed. The destination stayed empty.
- Lifecycle Validate produced no error sheet. No run was started.
- Resize: window size changed to 1200×820.
- Settings Close reported `name=Close Settings` and `description=Close Settings`. The click set sheets to 0. Escape dismissed Settings again.
- About showed app version 0.1.5 (13) and CLI `runspecimen 0.2.0rc15`. The Close control did not publish the name “Close About”; the only button in that sheet dismissed it.
- File > Close left no window. File > Show Main Window brought “RunSpecimen” back.

The process was quit by its QA binary pid. The shared container was restored from the backup taken before launch. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03.

Scan of this QA bundle: `TrustEvaluationAgent` absent, `com.apple.security.network.server` absent. The bundled CPython `Python` binary contains the module-table name `_lzma` between `_lsprof` and `_markupbase`. That name is also in the approved 0.1.4 (9) binary. It is not the rejected `lzma_*` symbol or a `liblzma` load command. This pass did not submit the app and did not treat the scan as a Store clearance.

## Post-authentication and carried pin, 2026-09-29

Swift on this tree: 98 tests, 1 skipped, 0 failures. The skip is `testSecureEnclaveHumanHarnessIsNotRunByAutomation`. iOS ObserveSchemaTests on the iPhone 17 simulator: 6 passed. They call `automationRefused()` and the file-only revocation and stale-display helpers. They do not call Secure Enclave. `preview` exited 0. `enroll` without `--human-invoked` exited 2.

A carried pairing file that says `secure-enclave` / `production` is stored as `unverified` / `carried-pin`. `consumeForExecution` is still not called by a run. `evaluateExecution` records a consume double and leaves `started` false. Partial and interrupted diagnostic writes remove the new file.

The development app was rebuilt at `/private/tmp/rs-local-qa-next/DerivedData/Build/Products/Release/RunSpecimen.app`. Version 0.1.5 (13). Apple Development: jahorka@gmail.com (PK6W7JVY6D). Sandbox true. `network.server` absent. Bundled CLI `runspecimen 0.2.0rc15`.

GUI on that binary, without typing an approval phrase:

- Reviewer demo showed Doctor OK, Python 3.12.14, Chain OK, and CLI source Bundled Helpers. Opening beta, alpha, and empty-other showed “Select a contract” and the new workspace path.
- Malformed, unreadable, and outside-workspace contracts showed the same alerts as the previous pass.
- Digest, then Compare and Diff, showed `RunSpecimen error: certificate not found for reviewer-demo/run-001`.
- Pin carried public key, for a file labeled secure-enclave, showed “Pinned phone-key as an unverified carried key. The file's Secure Enclave label was not accepted.”
- Choosing Local for a companion package showed “The package policy is companion. This control will not switch it to local.” Choosing the package policy again showed “The package was not imported. No other policy was tried.”
- Validate on the reviewer demo left no error sheet. The window resized to 1200×820.
- Settings Close is the AppKit button `Close Settings`. The click set sheets to 0. Escape dismissed Settings again.
- About showed 0.1.5 (13) and `runspecimen 0.2.0rc15`. Close About is now an AppKit button. The click set sheets to 0.
- File > Close left 0 windows. File > Show Main Window brought RunSpecimen back. A second launch came up with no sheet.
- Retain’s confirmation was not identified in this pass. The retain folder stayed empty. No run was started.

The QA process was quit by its own pid. The shared container was restored from the backup taken before launch. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03.

This is not a Store archive, not a device biometric proof, and not an execution boundary. The module-table name `_lzma` stays, matching the approved binary. The executor note in `docs/EXECUTOR_PROTECTION.md` does not authorize a helper.

## Positive receipts and symbol classification, 2026-09-29

The scanner in `apps/macos/Scripts/verify_mas_runtime.py` reads every nested Mach-O with `otool -L` and full `nm`, not `nm -u` alone. A violation is a private-framework or `TrustEvaluationAgent` load command, a non-system absolute dependency, a `liblzma` dependency, or a symbol line containing `_lzma_` or `TrustEvaluationAgent`. The CPython module name `_lzma.` and `_PyInit__lzma` are not violations. `tests/test_rejected_runtime_symbols.py` and `apps/macos/Scripts/test_mas_runtime.py` cover that split. The rebuilt QA app, the approved 0.1.4 (9) archive app, and `/Applications/RunSpecimen.app` each scanned at 48 Mach-O files and 0 violations. The extension modules `lzma` and `_lzma` stay excluded by `freeze_helper.sh`. The interpreter table is not stripped.

iOS ObserveSchemaTests on the iPhone 17 simulator: 7 passed, including `testRevocationUnderTheEnrollmentLockBumpsOnce`. Those tests do not call Secure Enclave.

Synthetic fixture, labeled as such and not a human-approved run, at `/private/tmp/rs-qa-synthetic-receipts/workspace`. Campaign `synthetic-receipt`, runs `synthetic-001` and `synthetic-002`. Output `outputs/synthetic-result.txt` is the bytes `synthetic-receipt-bytes` plus a newline. SHA-256 `508633c27446ba22c30abcf7241d6ce8faf502f7d7cb47e541a0ded32a7ad07f`. Certificate ids `synthetic-not-a-run-synthetic-001` and `synthetic-not-a-run-synthetic-002`. No approval phrase was typed.

On the rebuilt development app `0.1.5 (13)`, Apple Development: jahorka@gmail.com (PK6W7JVY6D), sandbox true, `network.server` absent:

- Digest receipt showed `kind` `receipt_digest`, campaign `synthetic-receipt`, run `synthetic-001`, exit code 0, and that SHA-256 under `output_digests` for `outputs/synthetic-result.txt`.
- Compare output bytes showed the same SHA-256 as both `live` and `recorded`, with status `match`.
- After Other campaign `synthetic-receipt` and Other run `synthetic-002` were committed, Diff receipts showed `kind` `receipt_diff`, `identical` false, exit code 0 against 7, and the recorded hash against 64 zeroes.
- Choose retain folder selected `/private/tmp/rs-qa-synthetic-receipts/retain`. Retain incident pack then showed the confirmation title `Retain incident pack`, the detail naming `synthetic-receipt/synthetic-001` and that outside path, and the buttons `Retain incident pack` and `Cancel workflow`. Cancel workflow was clicked. The destination stayed empty.
- A second pass, after a one-line synthetic `events.jsonl` was added beside the certificate, clicked the confirmation button `Retain incident pack` (the panel button, not the scroll-view button that only stages the request). The destination then contained `certificate.json` and `events.jsonl`. Those copies were deleted after the check. This is still not a human-approved run.

The QA process was quit by its own pid. The shared container was restored from the backup taken before launch. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03. This is not a Store archive and not a device biometric proof.

Mac diagnostic `preview` exited 0 and printed that it made no Secure Enclave call. `enroll` without `--human-invoked` exited 2. An unsigned Release build for a generic iPhone is at `/tmp/rs-device-builds/ios-unsigned/Build/Products/Release-iphoneos/RunSpecimenObserve.app`. `codesign` reports it is not signed. It was not installed. A signed device build failed because no provisioning profile for `com.darashkevich.runspecimen.observe` is on this Mac, and automatic profile creation was not enabled. The shipping binary does not contain `ios-dev-phone`. Secure Enclave enroll, sign, revoke, and rotate are implemented and have not been run on a device by a person.

Local `release_check.py` on Python 3.12.14: 411 tests, 35 skipped (PyNaCl, bubblewrap, and Linux `ldd`; the new symbol tests ran). Unpublished rc15 wheel SHA-256 `24082fbf9006c627953f6d9c5b8f0c9dca9fb006efcae3b54472b7dfa641d871` (unchanged). Plugin zip SHA-256 `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` (unchanged). Sdist SHA-256 `cdf8cbe74125a301b620f2b8ef27170245be185443302b2dc39d114a401b1648` (changed because `tests/` and `docs/` are in the sdist). Copies are in `artifacts/rc15-2026-09-29-symbol-receipts/` next to the approved 0.1.4 (9) archive. Published rc14 hashes are unchanged. `apps/` is not in the sdist, so this evidence file does not change those hashes.

## Enrollment lock, confirmation identity, and bound scans, 2026-09-29

Enroll creates a Secure Enclave key only when `load` reports the pairing file missing. A malformed file, an unreadable file, an active record, and a revoked record do not call key creation and do not replace the file. There is no recovery flow that rewrites a revoked record back to generation 1. The post-Face-ID reload, the revocation check, and the expiry clock run inside one enrollment-lock critical section. A revocation injected between that reload and the decision discards the signature. A signature already returned is not revoked by this check.

Confirmation claims the request only when its id is still the one on the panel. Cancel, sheet close, a workspace or contract change, and a second confirm do not run the staged command. A stale id does not claim the newer request. The staged `--out` path stays on the claimed request.

The runtime scanner visits every architecture slice from `lipo -archs`. An `otool` or `nm` failure is a violation. A clean symbol result is bound to the SHA-256 of each Mach-O. The approved xcarchive app scanned at 48 Mach-O files, each `arm64`, 0 violations. Re-scanning with those recorded hashes matched. Changing one hash failed the scan. The report is `artifacts/scans/approved-0.1.4-build9.json`. The CPython module-table name was not stripped.

The local export `RunSpecimen.pkg` mtime is still 2026-09-24 12:55:22. Its SHA-256 today is `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f`. The submission record still says `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`. This pass did not modify that package.

Swift package tests: 101, 1 skipped, 0 failures. iOS ObserveSchemaTests: 10 passed on the iPhone 17 simulator, including the missing-file enroll test and the revocation-at-decision test. They do not call Secure Enclave. Python 3.12.14 `release_check.py`: 412 tests, 35 skipped. Wheel and plugin zip are unchanged from the hashes above. Sdist SHA-256 `fd192b4e0df317cefc43cb8e25cda52ab545bcea49b905f78e3c0ecd4ff443f5`. Copies are in `artifacts/rc15-2026-09-29-enroll-lock/`.

Diagnostic `preview` exited 0. `enroll` without `--human-invoked` exited 2. The unsigned iPhone app and the diagnostic binary are in `artifacts/human-device-kit/`. The iPhone app is not signed and was not installed. Steps are in `docs/HUMAN_DEVICE_KIT.md`. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03.

The executor choice is which of the three guarantees in `docs/EXECUTOR_PROTECTION.md` is required. This pass does not choose it and does not add a helper, relay, or Endpoint Security client.

## Runtime identity and claim-time context, 2026-09-29

`verify_mas_runtime.py` now has three commands. `scan` checks symbols and slices only. `record-identity` writes the full file map, the hash of that map, a 40-character git commit, and a dirty flag. `verify-identity` fails when the manifest is missing, is not JSON, has the wrong stage, lacks that commit or dirty flag, or any file byte or symlink target differs. A symlink that leaves the artifact root is not recorded. `freeze_helper.sh` only scans, because signing changes bytes. `archive_mas.sh` records stage `signed-archive` after the archive exists, into `runtime-identity.json` beside the xcarchive rather than inside the app. `export_mas.sh` verifies that manifest. A frozen-helper identity does not satisfy the signed-archive check. A free-text source label is not a git commit.

`tests/test_runtime_identity_cli.py` drives the CLI. It covers a missing manifest, a non-commit label, a stage mismatch, a post-sign record that no longer matches the pre-sign bytes, a later alteration, a retargeted symlink, and a symlink that escapes the root. Those tests ran inside `release_check.py`. They are not a substitute for exporting a Store package.

`chooseWorkspace` and `chooseContract` call `noteWorkspaceSelection` and `noteContractSelection`. Those handlers drop a pending request and a claim that has not started. `claimConfirmedWorkflow` refuses when the live workspace or contract differs from the staged request. `performClaimedWorkflow` then drops that unstarted claim, does not call the CLI, and sets “The workspace or contract changed before this workflow ran. Nothing was written.” A command that has already passed `beginExecution` is not stopped; it keeps the arguments captured at claim. Closing the sheet still clears only an unclaimed request, so a confirm that already claimed still runs if the paths have not changed. `AppModelWorkflowContextTests` calls those handlers. `WorkflowConfirmationGateTests` covers the gate. Neither suite is an accessibility proof of the sheet, and this pass did not repeat the GUI session.

The iOS hook that mutates the record between reload and decision remains. `testPublicRevokeAfterFinalizeSeesTheRecordTheDecisionAlreadyAccepted` holds the enrollment lock inside `finalizeSignature` and calls public `revoke` on another queue. Revoke does not return while the lock is held, and the file stays active generation 1. After the decision returns, revoke completes at generation 2. `testFinalizeAfterPublicRevokeDiscardsTheSignature` revokes first; finalize then throws malformed enrollment. ObserveSchemaTests: 12 passed, 0 failures, on the iPhone 17 simulator. They do not call Secure Enclave.

`withLock` now also takes an in-process lock, so the unsigned Release iphoneos app was rebuilt. `codesign` reports it is not signed at all. Bundle `com.darashkevich.runspecimen.observe`, version 0.1.0 (1), arm64. The scan is 1 Mach-O and 0 violations, written to `artifacts/scans/human-kit-ios-unsigned.json`. The app was not installed. It does not contain `ios-dev-phone`. The diagnostic binary was not rebuilt.

Swift package tests: 105, 1 skipped, 0 failures. The skip is the human Secure Enclave harness. 102 are `RunSpecimenCoreTests`. 3 are `RunSpecimenAppTests`.

Python 3.12.14 `release_check.py`: 417 tests, 35 skipped. Wheel SHA-256 `24082fbf9006c627953f6d9c5b8f0c9dca9fb006efcae3b54472b7dfa641d871` (unchanged). Plugin zip SHA-256 `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` (unchanged). Sdist SHA-256 `5af33bd635951819b8a71b7f546856fd114eb062dbc3d78eeb1dc5d6b24e434c`. Copies are in `artifacts/rc15-2026-09-29-runtime-identity/`. Published rc14 hashes are unchanged. Homebrew still pins rc14.

The local export `RunSpecimen.pkg` mtime is still 2026-09-24 12:55:22 and its SHA-256 is still `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f`. The submission record still says `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`. This pass did not modify that package. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03.

This is not a Store archive, not a device biometric proof, and not an execution boundary. The executor choice in `docs/EXECUTOR_PROTECTION.md` is still open. No helper, relay, or Endpoint Security client was added.

## Test seams, capture injection, and one-time identity, 2026-09-29

`beforeConsumptionDecision`, `beforeExclusiveAccess`, and `beforeFinalSignatureDecision` are compiled only when `RUNSPECIMEN_TEST_HOOKS` is set. `swift test` sets that flag for its Debug build of `RunSpecimenCore` in `Package.swift`. The Xcode Store target does not set it. `xcodebuild -project apps/macos/RunSpecimen.xcodeproj -scheme RunSpecimen -configuration Release build` produced `/tmp/rs-store-nm/DerivedData/Build/Products/Release/RunSpecimen.app`. `nm` on `Contents/MacOS/RunSpecimen`, on `libRunSpecimenCore.a`, and on the Release `BiometricApproval.o` found none of the three names. The same Debug object file from `swift test` does contain `beforeConsumptionDecision` and `beforeExclusiveAccess`, so the names are visible when the flag is on. The iOS Release app and the Release diagnostic binary also omit the names. An iOS Debug build defines the flag because the unit-test host is the app target. `RunSpecimenObserveDev` does not define it.

`finalizeSignature` names the pre-seam load `readableBeforeWait` and uses that record's key id. The decision still uses the reload after the seam. The in-process enrollment lock is one lock for every directory; the shipping app uses one directory per launch.

`CLIService` takes a `ProcessCapturing` value. `CLIServiceCaptureFailureTests` passes a synthetic capture into `runLifecycle` and `version` for timeout, cancellation, a pipe read error, and a cleanup failure. A printed `runspecimen 0.2.0rc15` line does not make those calls succeed. Swift package tests: 107, 1 skipped, 0 failures (102 core, 5 app). iOS ObserveSchemaTests: 12 passed. They do not call Secure Enclave.

`record-identity --fail-if-exists` refuses to replace an existing manifest. `archive_mas.sh` passes that flag. A second record leaves the first file bytes unchanged.

The approved archive app scanned at 48 Mach-O files, each `arm64`, 0 violations. The report is `apps/macos/asc-kit/evidence/scan-0.1.4-9.json`. It does not replace the submission package hash. The local export `RunSpecimen.pkg` mtime is still 2026-09-24 12:55:22 and its SHA-256 is still `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f`. The submission record still says `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`.

Python 3.12.14 `release_check.py`: 418 tests, 35 skipped. Wheel SHA-256 `24082fbf9006c627953f6d9c5b8f0c9dca9fb006efcae3b54472b7dfa641d871` (unchanged). Plugin zip SHA-256 `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` (unchanged). Sdist SHA-256 `9087e8fae39ed25a8aa51e21d70bc1a2a3be1318e4c583fcc885b46e5ed8e276`. Copies are in `artifacts/rc15-2026-09-29-test-seams/`. Published rc14 was not replaced. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03.

The unsigned iPhone app and the Release diagnostic in `artifacts/human-device-kit/` were rebuilt from this tree. The iPhone app is not signed and was not installed. Diagnostic `preview` exited 0. `enroll` without `--human-invoked` exited 2. Exact human commands are in `docs/HUMAN_DEVICE_KIT.md`. No helper, relay, or Endpoint Security client was added.

## Release source gate and GUI acceptance, 2026-09-29

`runtime-identity.json` is an integrity record of artifact bytes plus caller-supplied git metadata. It is not an independent cryptographic source attestation. `record-identity` without `--release-gate` may describe a dirty tree, including a forty-zero commit. `verify-identity` without the gate checks bytes only.

The release path is different. `archive_mas.sh` writes `source-before.json` before `xcodebuild archive`. When `RS_RELEASE_GATE=1`, that snapshot requires `RS_EXPECTED_GIT_COMMIT` and a clean `HEAD` equal to that SHA. After the archive exists, `source-after.json` is compared with `check-source-stable`. A commit move fails every archive. A dirty tree fails only the release gate. `record-identity` still refuses to replace an existing manifest. `export_mas.sh` requires the same expected SHA and `verify-identity --release-gate`. A development archive cannot pass that export.

`tests/test_runtime_identity_cli.py` covers a dirty integrity record that fails the gate, a wrong expected commit, and a source change during the build (dirty tree, then a new commit). Those tests use a temporary git repository. They do not rebuild or replace the approved package.

Swift package tests on this tree: 107, 1 skipped, 0 failures (102 core, 5 app). No Swift product source changed in this pass, so the iOS ObserveSchemaTests were not rerun. Python 3.12.14 `release_check.py`: 421 tests, 35 skipped. Wheel SHA-256 `24082fbf9006c627953f6d9c5b8f0c9dca9fb006efcae3b54472b7dfa641d871` (unchanged). Plugin zip SHA-256 `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` (unchanged). Sdist SHA-256 `1c9ea0c3efa96838821b689cdc508a245cf940cc616cb2dbc25e6ca87cddeb04`. Copies are in `artifacts/rc15-2026-09-29-provenance/`. The sdist contains the new identity tests and does not contain this evidence file or `docs/CANDIDATE_MANIFEST.md`. Published rc14 was not replaced.

GUI acceptance used a separately located Apple Development build at `/private/tmp/rs-local-qa-provenance/DerivedData/Build/Products/Release/RunSpecimen.app`. The build did not pass `-allowProvisioningUpdates`. The bundle is sandboxed and has no `network.server` entitlement. It was not copied over `/Applications/RunSpecimen.app`. The shared container was copied aside before launch and restored after quit. The synthetic fixture is `/private/tmp/rs-qa-synthetic-receipts`. Its certificates are labeled `synthetic-not-a-run`.

Accessibility: About opened from the menu and closed with the AppKit button `Close About`. Settings opened with Command-comma and closed with `Close Settings`, then opened again and closed with Escape. In Workflows, Tab moved focus from the Snapshot id field to the next text field.

Receipts: Digest on the reviewer demo reported that the certificate was not found. Digest on the synthetic workspace showed `receipt_digest` for `synthetic-receipt` / `synthetic-001` and output SHA-256 `508633c27446ba22c30abcf7241d6ce8faf502f7d7cb47e541a0ded32a7ad07f`, with the note that this is not `runspecimen verify`. Compare output bytes reported a match, then a differs result after the output file was changed, and the original bytes were restored. Diff receipts against `synthetic-002` showed a receipt diff that is not identical. Diff against `missing-run` reported that the certificate was not found. The diff fields needed focus, an accessibility value, and Tab before the button used the new text.

Retain: Cancel workflow left `/private/tmp/rs-qa-synthetic-receipts/retain` empty. The confirmation button then copied `certificate.json` and `events.jsonl` into that folder. Those copies were removed. Staging retain again and choosing Open Reviewer Demo removed Cancel workflow and wrote nothing. Staging retain and reselecting the reviewer demo contract also removed the confirmation. Command-W closed the main window. File → Show Main Window brought it back.

AppModel tests are not this GUI pass. This pass did not type an approval phrase, did not call Secure Enclave, and did not start a run. The diagnostic and unsigned iPhone binaries named in `docs/HUMAN_DEVICE_KIT.md` were built from `5c3957a3a8ddf9fceacc3096b2208ee7757e6b72`. This change does not modify those sources, so those hashes stay on that build.

The local export `RunSpecimen.pkg` mtime is still 2026-09-24 12:55:22 and its SHA-256 is still `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f`. The submission record still says `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03. `docs/EXECUTOR_PROTECTION.md` now lists what app-only enforcement, protected state, and global execution blocking would each take. None of those choices was implemented. No helper, relay, or Endpoint Security client was added.

## Isolated release source, and the executor choice, 2026-09-29

`release_source_prelude.sh` runs before helper freeze and Xcode project generation. With `RS_RELEASE_GATE=1` it refuses a dirty tree or a different commit before the freeze command. A passing check builds from a detached worktree of `RS_EXPECTED_GIT_COMMIT`. A commit made during freeze fails before project generation. The caller's checkout is left at its original commit. A development build still freezes a dirty tree in place, and export still rejects that archive. `tests/test_release_source_prelude.py` drives the prelude with stand-in commands. It does not run PyInstaller or `xcodebuild`, and it does not rebuild the approved package.

Python 3.12.14 `release_check.py`: 426 tests, 35 skipped. Wheel SHA-256 `24082fbf9006c627953f6d9c5b8f0c9dca9fb006efcae3b54472b7dfa641d871` (unchanged). Plugin zip SHA-256 `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d` (unchanged). Sdist SHA-256 `cde8732f32367650282dbe8bfcb8e9c0d60fcfafbfe47c354a048cd3bc8c399c`. Copies are in `artifacts/rc15-2026-09-29-isolated-source/`. Swift and iOS sources are unchanged from `b9b9ae432d0ab44b96aafbf2b7d0255c4be5ede0`, where Swift was 107 tests, 1 skipped, 0 failures. Those tests were not rerun for this script-only change.

GUI evidence stays the pass recorded above for the development app. It was not repeated here. It is not these unit tests. No approval phrase was entered and Secure Enclave was not called.

Yahor chose guarantee (2). Guarantee (3) is excluded. On macOS 27.0 as uid 501, a same-user process unlinked a held `execution.lock` and acquired a new file at that path while the first holder still reported the lease held. The app container is owned by that user, mode `drwx------`, and accepted a create and delete of a probe file, which was removed. `uchg` blocked a write until the same user cleared the flag. `/Applications/RunSpecimen.app` is owned by root and was not modified; its mtime stayed 2026-09-26 13:56:03. The local export package mtime is still 2026-09-24 12:55:22, SHA-256 still `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f`. The submission record still says `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`.

Guarantee (2) is not achieved. The run path still uses a typed terminal phrase. That is guarantee (1). The chosen biometric policy, local Touch ID by default, an explicitly selected paired iPhone, and dual approval for sensitive runs, is recorded in `docs/EXECUTOR_PROTECTION.md` and is not yet the run gate. A typed phrase must not silently replace a required biometric policy. No helper, relay, or new entitlement was added. The remaining decision is whether to authorize a separate holder the same user cannot rewrite.

## Holder design and the workspace-lease attack, 2026-09-29

`docs/EXECUTOR_PROTECTION.md` names the holder: a Developer ID launch daemon outside the Store bundle, running as a system user, owning enrollment, policy, consumed nonces, and the execution lease. The Store app would be an XPC client authenticated by Team ID `UN6KF8636A`. That daemon is not authorized and was not installed. `consumeForExecution` is still not called by `run.py`. Wiring it to the workspace lease would describe guarantee (1) as guarantee (2).

`tests/test_lease.py` unlinks a held `execution.lock` and acquires a new file at the same path. Both holders stay acquired and the inode changes. Restoring a workspace marker file succeeds. `build_app.sh` exits before compilation when `RS_RELEASE_GATE=1`, so a release freeze cannot start from the live tree through that script.

Python 3.12.14 `release_check.py`: 428 tests, 35 skipped. The 35 skips are the usual local 3.12 set (PyNaCl, bubblewrap, Linux `ldd`), not hidden failures. Wheel SHA-256 `24082fbf9006c627953f6d9c5b8f0c9dca9fb006efcae3b54472b7dfa641d871`. Plugin zip SHA-256 `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`. Sdist SHA-256 `44ef71f43812aae5ab83fa8d942a217be9a029438f41578d7157a4dfd8d25c7f`. Copies are in `artifacts/rc15-2026-09-29-holder-design/`. Swift sources are unchanged, so the Swift 107 / 1 skip result from `b9b9ae4` was not rerun.

The same development app used for the earlier receipt pass, `/private/tmp/rs-local-qa-provenance/DerivedData/Build/Products/Release/RunSpecimen.app`, was launched again. About closed with `Close About`. Settings closed with `Close Settings`. Command-W left no window. Show Main Window reopened `RunSpecimen`. The shared container was restored. Receipts were not clicked again; that pass remains the one recorded above, on app sources this commit does not change. No approval phrase was entered.

`/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03. The local export package mtime is still 2026-09-24 12:55:22 and SHA-256 is still `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f`. The submission record still says `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`. Neither hash was rewritten.

## Prelude root, holder revision, and a fresh GUI pass, 2026-09-29

`release_source_prelude.sh` resolved `../..` from `apps/macos/Scripts`, which is `apps/`, then looked for `apps/apps/macos`. With `RS_REPO` unset it exited 1. The default is now three levels up, the repository root. Tests call the prelude as `apps/macos/Scripts/release_source_prelude.sh` from the repository, as `Scripts/release_source_prelude.sh` from `apps/macos`, and through a stub `archive_mas.sh` whose release branch matches production: the isolated re-entry runs with `RS_REPO` removed. Those tests do not set `RS_REPO` or `RS_PRELUDE_ONLY`, and they do not sign or call `xcodebuild`.

Python 3.12.14 `release_check.py`: 431 tests, 35 skipped. The 35 skips are the local 3.12 set (PyNaCl, bubblewrap, Linux `ldd`). Wheel SHA-256 `24082fbf9006c627953f6d9c5b8f0c9dca9fb006efcae3b54472b7dfa641d871`. Plugin zip SHA-256 `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`. Sdist SHA-256 `0636d83a43d3648884527afd94ec1748dbb78a160e09f311c87b6dbb2c92d87a`. Copies are in `artifacts/rc15-2026-09-29-prelude-root/`. Swift and iOS sources are unchanged, so those suites were not rerun.

The holder design in `docs/EXECUTOR_PROTECTION.md` now separates the root holder from the console-user payload, specifies authenticated enrollment and protected pairing, re-hashes inputs before the go byte, and defines consume, arm, run, and recover so an already-running child is not launched twice. It is not installed.

XPC check, same development identity `Apple Development: jahorka@gmail.com (PK6W7JVY6D)`, Team ID `UN6KF8636A`. A throwaway app signed with `RunSpecimen.mas.entitlements` (no app group, no mach-lookup) could not complete a lookup that an unsandboxed client completed. The listener was a temporary user LaunchAgent named `com.darashkevich.runspecimen.xpcprobe.listener`, not a root daemon. The unsandboxed client received `ok=holder`. The sandboxed app received `Connection invalid` for a normal lookup and for `XPC_CONNECTION_MACH_SERVICE_PRIVILEGED`. A bare executable with those entitlements exited 133. The agent was removed afterward. `launchctl` does not find it. The product entitlements file was not edited.

Store distribution is not established. Guideline 2.4.5 (ii), (iii), (iv), (v), and (vii) still apply. An external daemon is not compliant merely because it sits outside the bundle. The smallest decision left is whether to authorize one embedded root `SMAppService` daemon plus one app-group entitlement. That was not implemented.

Fresh GUI on `/private/tmp/rs-local-qa-provenance/DerivedData/Build/Products/Release/RunSpecimen.app`, Apple Development, not installed over `/Applications`. The shared container was restored after quit. No approval phrase was entered.

- Reviewer demo: Doctor OK, Python 3.12.14, campaign `reviewer-demo`, run `run-001`, phase `approved`. Digest reported `certificate not found for reviewer-demo/run-001`.
- Synthetic workspace `/private/tmp/rs-qa-synthetic-receipts/workspace` and its contract. Digest showed `kind` `receipt_digest`, certificate `synthetic-not-a-run-synthetic-001`, campaign `synthetic-receipt`, run `synthetic-001`, exit code 0, output SHA-256 `508633c27446ba22c30abcf7241d6ce8faf502f7d7cb47e541a0ded32a7ad07f`. The note says this is not `runspecimen verify`.
- Diff against `synthetic-002` showed `kind` `receipt_diff` and `identical` false. Diff against `missing-run` reported `certificate not found for synthetic-receipt/missing-run`.
- Tab from Snapshot id moved focus to the next text field. About showed app version 0.1.5 (13) and CLI `runspecimen 0.2.0rc15`, then Close About. Close Settings dismissed Settings. File → Close left no window. Show Main Window reopened `RunSpecimen`. The window size read back as 1180×820 and then 900×640.

The two package hashes are different artifacts, as `apps/macos/asc-kit/STATUS.md` already records. `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d` is the submitted 0.1.4 (9) package for build `51a18894-02e3-4846-86f5-29cc345567f0`. `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f` is the local export that reused the version label and was not submitted. Re-read on this pass: mtime 2026-09-24 12:55:22, size 12977696, same local hash. The installed app mtime stayed 2026-09-26 13:56:03. Neither record was rewritten. This commit is not a Store archive.

## Snapshot binding, launch handshake, and which 0.1.5 (13) report is which, 2026-09-30

`src/runspecimen/holder_protocol.py` is an unprivileged specification. `src/runspecimen/run.py` does not import it. Binding copies each declared input, the executable, the script, and declared dependencies onto a new inode opened with `O_NOFOLLOW`, then rewrites argv to those paths. A symlink at bind time fails. Replacing the original after the snapshot fd is open does not change the fd or the rewritten path. A later stat of the original is not the binding. The working directory is the snapshot directory. Outputs are separate files. An `env` shebang fails closed. System libraries are named as a residual, not as covered files.

The wrapper execs only after a durable Acked record and a commit byte. Go alone leaves the image as the wrapper. Recovery after a crash is not the parent: `waitpid` returns `ECHILD`, which is not an exit status. PID reuse is not killed and not adopted. A live descendant holds the lease so a second nonce cannot spawn. The same nonce cannot spawn again.

`tests/test_holder_protocol.py` covers those cases, including one real orphan. Python 3.12.14 `release_check.py`: 444 tests, 35 skipped. The 35 skips are the local 3.12 set (PyNaCl, bubblewrap, Linux `ldd`). Wheel SHA-256 `64ff9f7fa1aa94fb2e4a60009534dab590e4857c028005f4da087cfbc419ab54`. Sdist SHA-256 `7ac3f822408a9465124ef67bfa5a7d7effcf2f69dde807270bd76b44398c1d29`. Plugin zip SHA-256 `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`. Copies are in `artifacts/rc15-2026-09-30-protocol/`. Swift sources are unchanged, so the Swift 107 / 1 skip result from the 094480a review was not rerun for this commit.

`runspecimen-candidates/0.1.5-13/QA-2026-09-29.md` and `ACCEPTANCE.md` describe source `ea21a7fa17140dc15dab74493d384b2a8b7a150c`, engine `0.2.0rc14`, package SHA-256 `e47ead2dee298d8f86dd191a5032b114608f954c150479719562e4319a9988fa`, and the development app `/private/tmp/rs-local-qa-13/DerivedData/Build/Products/Release/RunSpecimen.app`. That GUI and that package belong to that source. They are not acceptance of this rc15 commit. The version string 0.1.5 (13) appears in both trees and does not identify the source. This pass did not repeat GUI and did not build a Store archive.

Guideline 2.4.5(v) prohibits root escalation for a Mac App Store app. An embedded root daemon is not treated as Store-compatible. `docs/APPLE_DTS_HOLDER_QUESTION.md` is the question that would ask Apple. It was not sent. No daemon was installed. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03. The local export package hash is still `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f`. The submission record is still `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`.

## Snapshot destinations are checked through the opened fd, 2026-09-30

A precreated `files/<sha256>` with the right name and wrong bytes is rejected. The binder opens that path with `O_NOFOLLOW`, requires a regular file, and hashes the bytes from the fd. `Snapshot.digest` is that hash. A symlink or directory at the destination is rejected. A short write is retried. A failed write unlinks the partial file, and a failed unlink is reported as cleanup failure. Every executable, script, input, and dependency needs a lowercase sha256 fingerprint.

The executable, the shebang interpreter, and a rebound script are mode `0555`. The script shebang names the snapshot interpreter. A test runs that returned command. The interpreter is a regular file whose own shebang is `/bin/sh`. Where `/bin/sh` is a symlink, the binder refuses to snapshot it. The kernel may still use that shell to start the regular-file interpreter. That shell is not a snapshot. The command prints the approved input. `run.py` does not call this module.

`HolderSim.persists` is false. Its crash tests are not fsync results. `write_durable_record` fsyncs a file. `assess_durable` never spawns and always reports `echild`. A missing file is not a launch. A partial record keeps the lease. Those file tests are separate from the simulator.

Python 3.12.14 `release_check.py`: 453 tests, 35 skipped. Wheel SHA-256 `1ba89b3c4352ad072d3099c6c17d0c04a2824966fa9cdcc9f7bcf58956ed7813`. Sdist SHA-256 `419f1a31160776b592cf2c7bac0b4089c48a44844a775ed351a96148a3aee0f5`. Plugin zip SHA-256 `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`. Copies are in `artifacts/rc15-2026-09-30-snapshot-verify/`. Swift sources are unchanged. No daemon was installed. The Apple question was not sent. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03. The local package hash is still `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f`. The submission record is still `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`.

## Malformed durable identity stays a held lease, 2026-09-30

`assess_durable({'phase': []})` and a phase that is an object return a partial record with the lease held. They do not raise. A bool is not a pid or a start time. A negative or zero pid or start time is not complete. The same shapes were written as JSON files and read back before assessment. `HolderSim.recover` applies the same phase and identity checks to its in-memory dict. That simulator still does not fsync. The file tests and the simulator tests are separate. Neither spawns.

`tests/test_holder_protocol.py` is 24 tests. Python 3.12.14 `release_check.py`: 455 tests, 35 skipped. Wheel SHA-256 `e51b378dcf9f1f5fd6636f6732f24f1d32f7edc83ddaa34a36b8dde90c56fce7`. Sdist SHA-256 `0bd8de2988b1b48948253faad21adaea1c902d95420404c6fef6acbd0100f75d`. Plugin zip SHA-256 `692ef035b45b2a12e9a99c86583390badcad6bae5638e4267bfc8e876b0f0b2d`. Copies are in `artifacts/rc15-2026-09-30-durable-domain/`. No daemon was installed. The Apple question was not sent. `/Applications/RunSpecimen.app` mtime stayed 2026-09-26 13:56:03. The local package hash is still `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f`. The submission record is still `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`.
