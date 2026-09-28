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
