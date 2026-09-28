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

Scan of this QA bundle: `TrustEvaluationAgent` absent, `com.apple.security.network.server` absent, `_lzma` still present in the bundled CPython `Python` binary. That last string is the original private-API rejection’s library name inside the frozen interpreter. This pass did not submit the app and did not treat the scan as a Store clearance.
