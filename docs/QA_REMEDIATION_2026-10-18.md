# Independent QA remediation — 2026-10-18

Release state: **DO-NOT-SHIP pending independent recheck and remaining evidence**.
PR #76 remains draft. PR #75 was merged as `4514bdc`; Yahor confirmed Mac 0.1.5
withdrawn from review. The preparation identity is 0.1.6 (16), not permission
to upload, submit, publish, change trust, or run a contract.

The original DeepSeek report and reproductions are preserved outside this
checkout in `outputs/final-qa-2026-10-17/`. Remediation logs are in
`outputs/deepseek-remediation/`. The reviewed source archives remain unchanged.

| ID | Remediation / remaining evidence |
| --- | --- |
| MAIN-01 | Validated confirm/refuse acknowledgements survive post-ack cancellation in both the operation and task wrapper. Both-action production regressions pass. Pre-ack cancellation behavior is retained. |
| MAIN-02 | Disconnect clears token, URL, TLS pin, Mac key, holder pin (including UserDefaults), and refresh timestamp. Regression checks all fields and persisted holder pin. |
| MAIN-03 | Validation-driven disconnect publishes failure after invalidating tasks, preserving the refusal reason. Production regression passes. |
| MAIN-04 | CLI floor raised to rc15 to match the current upgrade guidance. Tests reject rc9/rc14 and accept rc15/final. This is a compatibility decision for the current app, not proof of hardware antirollback. |
| MAIN-05 | Schema fixtures isolate/restore pairing and holder defaults and use token read/write/delete seams. The failed-refresh test uses a controlled transport and directly asserts timestamp preservation. |
| MAIN-06 | Direct real-certificate delegate coverage exists in testIOSQA701AcceptsRealCertificateThroughDelegate, covering matching/normalized and mismatched pins. This does not prove a live handshake. User physically paired and tested Remote Confirm on c6b43f8; captured endpoint/certificate-specific live TLS evidence remains separate. |
| PR76-01 | Timestamp UI query uses its production accessibility identifier; initial Refresh hittability is asserted without scrolling; failure text has a unique connection-feedback identifier. Unit tests assert cancellation/failure timestamp preservation. Focused Refresh UI suite passes 3/3. |
| PR76-02 | Enrollment outcome belongs to the session, clears on new signing/invalidation/disconnect and changed key state, and is only published for the current operation. Regression covers refusal-to-key-state transition. |
| PR76-03 | Editing carried-key input clears its previous pin result. |
| PR76-04 | Actual system share-sheet Copy followed by foreground-app pasteboard inspection compares full diagnostics with the failure/retention guidance. Passed recovery-ui-verified.log; older interrupted runner logs retained. |
| PR76-05 | User screenshot at 16:07 on c6b43f8 verifies pin feedback directly below Pin after stale Xcode app was stopped. Visual check passed; automated macOS layout assertion remains absent. |
| PR75-01 | Active Store metadata, version/build tables and candidate documents aligned to 0.1.6 (16); historical artifact identities retained. New CI-discovered test compares binary/project identities with the Store paste sheets. It rejects the frozen PR75 snapshot. |
| PR75-02 | Preparation authorization and current identity recorded, superseding historical proposal; release remains blocked on QA. |
| PR75-03 | Export instructions invoke the script with a local destination; committed TEAMID plist is explicitly a template. |
| PR75-04 | Reported attributesOfItem call removed; stub detection reads at most 64 content bytes instead of file metadata. **UNVERIFIED:** archive-level required-reason API scan remains; diagnostic fstat-family code must be assessed in final linked Store bytes. |
| PR75-05 | Plist and script default to local export; upload requires explicit destination. Export gate tests pass. |
| DSH-01 | Candidate 0.2.2 reports maximum dashboard lifetime in its tool output and README. The existing bounded-lifetime contract is retained. |
| DSH-02 | EPERM inspection means group present; bounded escalation continues. Unconfirmed cleanup returns typed failure through CLI/dashboard tools. Deterministic permanent-EPERM regression passes. |
| DSH-03 | Root package-lock license aligned to Apache-2.0; third-party dependency licenses preserved. |
| DSH-04 | Dashboard test awaits process completion at a short lifetime and checks PID death and entry removal. No synchronization sleep. |
| DSH-05 | Budget expiry is timedOut, caller abort is cancelled; both are distinct from cleanupFailed. |
| DSH-06 | **UNVERIFIED:** clean registry install, real host model dispatch/hot reload, Windows and physical power loss. Windows remains explicitly unsupported, not claimed functional. |
| OBSERVE-ICON | Built simulator app contains primary AppIcon declarations and iPhone/iPad icon files. Source PNG is 1024x1024 without alpha. App Store Connect placeholder remains until an appropriate processed build is verified; no upload was performed. |

## Evidence so far

- iOS targeted outcome regressions: 4/4 pass; the initial confirm case failed
  against the pre-fix code. DeepSeek's independent failing reproductions are retained.
- Final schema/cancellation run: 125 schema/regression tests + 26 cancellation tests,
  zero failures. Dedicated disposable Simulator, Xcode 27.1/iOS 27.
- macOS native SwiftPM: 116 executed, 1 skipped, zero failures. Default Xcode-backed
  SwiftPM failed signing due to filesystem metadata; that log is preserved.
- Store identity: 2 tests pass; frozen PR75 is rejected by the same checker.
- Store export gate suite passes. No archive export/upload/submission performed.
- DSH candidate: 40/40 tests pass. Three new regressions fail against original
  0.2.1; original red log and new green log preserved.
- Full iOS run passed schema/cancellation and the recovery UI smoke test, then
  stalled during the following app relaunch. That run was interrupted and is not
  counted as a complete pass. A subsequent focused Refresh UI suite passes 3/3; the interrupted full run remains preserved.

The DSH source candidate is `work/dsh-final-qa-fixes`; its 0.2.2 tarball is in
`outputs/deepseek-remediation/`. It has not been installed or published.

Physical biometrics, real network pairing, power-loss durability, the final Store
archive/privacy scan and processed Observe icon require their own evidence. No
passing local suite closes those limits. The user ended DeepSeek QA on 2026-10-19. Its historical reports remain preserved; no further DeepSeek continuation is required or scheduled. Release qualification remains incomplete.

## Independent second-pass follow-up

DeepSeek independently verified the fixed code paths on c7476c4, with the same
125 schema +26 cancellation +3 Refresh UI results. Its report is preserved as
`outputs/deepseek-remediation/FINAL-QA-RECHECK-REPORT.md`; combined DO-NOT-SHIP.

- R-01: four active overview/FAQ/candidate documents aligned to 0.1.6 (16).
  Identity checker now checks those four in addition to the six Store files;
  a stale-overview regression and the original metadata mutation both pass.
  Extended checker failed on all four stale docs before their correction.
- DSH-01/R-03: the split-line README contradiction is corrected in candidate
  0.2.3. Normal parent exit with a remaining descendant returns a typed cleanup
  result after escalation. New regression fails on frozen 0.2.2; full suite41/41.
  Candidate0.2.2 source and artifacts remain preserved.
- R-02: an unsigned iOS device Release archive succeeds. Its120px/152px app icon
  PNGs have no alpha; both1024px AppIcon marketing renditions in Assets.car are
  Opaque=true. The simulator's opaque-alpha PNGs are not the device archive's
  output. Scan: observe-device-release-icon-scan.json. ASC placeholder still
  needs verification after an authorized upload; none was performed.
- R-04: stale rc9 comment corrected; existing successful enrollment production
  test now revokes the fixture key and asserts enrollment feedback disappears.
  This uses disposable storage/in-memory test hooks, not a real key action.
  A macOS pin-edit/layout UI test remains absent.
- The e20c35a CI follow-up removes an unnecessary socket write after admission
  refusal; real refusal bytes, deadline and frame bounds remain asserted.
  Targeted1/full46holder tests pass; original macOS CI failure is retained.

External evidence gates remain explicit. No release is authorized by these fixes.

## Grok review follow-up (2026-10-19)

Reviewed the user-supplied independent findings against f646ce3. No release authorization.

- P2-1: enrollment commits use a crypto operation that checks cancellation before starting but preserves a successful durable write. The receipt/challenge is consumed and key state reconciled after commit; later cancellation cannot report it as cancelled. Tests cover task cancellation at commit and explicit challenge cancellation after commit.
- P2-2: validated Confirm/Refuse acknowledgements survive cancellation at response delivery. Competing settlements are refused at the session boundary; both UI buttons disable while either operation runs. The prior transport-cancellation test expected acknowledged success to be erased and was corrected to assert the actual settlement.
- P3 refresh freshness: successful internal refresh updates the successful timestamp and outcome, clearing stale feedback.
- P3 disconnect evidence: test seeds saved pairing and an in-memory Keychain-token seam and asserts both persisted values are removed, alongside trust/field checks. It does not manipulate the user's real Keychain.
- P3 recovery export: UI test exercises the real share-sheet Copy action, then a test-only foreground-app pasteboard inspection compares the entire copied string with the visible failure and retention guidance. The original background test-runner pasteboard read stalled; those logs are retained.
- P3 admission evidence: new private-socket test runs the actual holder_daemon.serve accept/worker loop, with installation/identity/message handling mocked; real admission, framing, read deadline and cleanup remain in use. It proves busy refusal and admission recovery after timeout. It does not run the installed privileged service.
- P3 docs: asc-kit/STATUS.md now describes local export as the default and upload as explicit opt-in.
- P3 CI: upload-artifact actions consistently use v5.
- P3 stale enrollment refusal: Cancel clears session feedback.
- P3 version floor: parser rejects unsupported alpha/beta/dev suffixes instead of treating them as final/rc builds.

Regression evidence is preserved under outputs/grok-remediation at the sf workspace root. Initial targeted iOS tests failed with 12 assertions before fixes; six prerelease assertions failed before the parser fix. Coverage-only additions and documentation/CI corrections are not claimed as reproduced product failures. Earlier broad iOS runs also exposed an obsolete acknowledgement expectation and its status-refresh fixture; those failures are preserved rather than rerun away. The final runs use the corrected semantic expectation.

All physical/live TLS/Mac layout/final privacy/processed App Store Observe-icon gates above remain open. The user requested “Push and stop; no release”; PR76 remains draft and requires independent review of the new head.

Test harness cleanup follow-up: the red competing-settlement test previously returned at its failed expectation without resuming/awaiting the original request. It now drains that task on both success and assertion-failure paths. A targeted rerun passes (competing-task-cleanup.log). Grok displayed a user-reported Swift XCTest concurrency abort from the earlier failing broad run; the old acknowledgement fixture also incorrectly treated the post-ack status request as another settlement continuation. Both test-lifetime hazards are corrected; this is not a claim of a reproduced product crash or a completed exact-head CI run.


## Device follow-up — a64c297, 2026-10-19 15:33 Lisbon

The user observed Remote Confirm reaching APPROVED with the Mac challenge and typed APPROVE, without Face ID. This matches ADR-004: Remote Confirm is an opt-in, Mac-armed, pairing-token-authenticated HTTP settlement, not a Secure Enclave signature. `submitRemoteConfirmImpl` does not invoke a signer. Biometrics protect the distinct carried approval signing path. Added explicit UI copy so Remote Confirm does not imply biometric approval; no authorization policy was silently changed.

- Reinstall: detect a retained Keychain key when its enrollment file is absent. Show a dedicated retained-key state and offer “Choose a new key ID.” Enrollment refuses before creating a replacement under the same ID. Existing private keys remain untouched; missing generation/revocation records are never reconstructed as trusted active enrollment. A fresh ID still needs enrollment and import on the Mac.
- Key status: label online phone-peer and carried approval keys separately. Enrolling one does not enroll the other.
- Remote expiry: derive the countdown from `expires_at_unix` on a one-second timeline. Explicit expired/settled arm state overrides stale advertised capability. The submission boundary independently rejects expired arms.
- Mac pin feedback: bound the public-key editor height and group Pin plus its result in a fixed-height-content stack. Physical Mac layout recheck remains required.
- iPhone pairing: add a visible “Pair iPhone” navigation entry even while paired, rename the initial screen, and provide setup steps. The existing Mac companion service must still be configured on the Mac; this change does not remove its CLI setup requirement or create a new discovery/provisioning protocol.

Evidence: `outputs/grok-remediation/device-red.log` records three failing regressions before the fixes (expired arm, settled arm, retained key reported missing). `device-green.log` records 134 passing iOS tests. Expanded validation: 136 iOS tests and 5 UI tests passed (`device-final.log`), including the visible pairing navigation. Mac: 117 tests, 1 skipped, 0 failures (`device-macos.log`). Device observations supplied by the user are not substitutes for a rerun of the changed build. No real keys were enrolled, revoked, replaced, or deleted during this remediation. No release actions.


## Physical follow-up — 2026-10-19, c6b43f8

User verified live countdown and expiry-card removal. After stopping a stale Oct 17 Xcode Mac instance, a screenshot verifies pin feedback directly below Pin. Phone screenshots verify retained yd-phone-2 detection and new-ID yd-phone-3 enrollment at generation 1; user confirms Mac pin/import and Mark Mac updated. Permission-denied signing refused; user explicitly confirms Face ID scanned/authenticated before the subsequent Signed result. A fresh diagnostic request then refused cancelled authentication and showed no signed output. Evidence is preserved under outputs/grok-remediation (device-countdown-result.md and named screenshots). These are diagnostic UI/device checks, not signature verification, native provenance qualification, crash-recovery or release approval.

New UX defect: LocalAuthentication/Keychain errors surfaced as Unexpected error. Shared feedback now recognizes typed cancellation, denied/unavailable biometrics, lockout and failed authentication, including underlying wrapped errors. Unknown failures retain details under a neutral action-failure headline. This changes presentation only; no biometric policy, signing, trust or key-state behavior changed. Three regression tests failed before the correction (biometric-feedback-red.log); 139 iOS tests passed (biometric-feedback-green.log). New feedback still needs physical recheck on the updated build.


## Current remaining-work audit — 2026-10-19

- All original Grok f646ce3 P2/P3 code findings were addressed in a50f101/a64c297; see above and preserved red/green evidence. The older report is not an unreviewed current-head defect list.
- New paired-form issue reproduced: a failed re-pair cleared a working session. Pairing fields (including holder pins) also edited live session state before Connect. Fields now stay in a local draft, and only successful validation/persistence replaces live config and holder fields. Failed candidates retain current status, capabilities, credentials and pins. A Boolean operation result prevents an invalidated attempt from applying draft trust fields merely because an old connection remains paired. Initial failing test and final regression/UI results are under outputs/grok-remediation/pairing-edit-red.log, remaining-fixes-serial.log and pairing-context-final.log. Successful replacement clears old requests and cancels old tasks; leaving the form cancels its pending attempt.
- Remaining evidence, not automatically closed: physical wording/draft-form retest on final head, physical rotation crash/power-loss recovery and device cancel races, cryptographic export/verification of human-produced diagnostic signature, final linked Store privacy/required-reason scan, processed ASC icon after separately authorized upload, and exact-head CI completion.
- Mac service provisioning still requires CLI setup. Automatic discovery/network/certificate provisioning is a separate feature requiring a defined authenticated provisioning flow; the phone cannot start a Mac service that is not listening. No trust/network changes were made to simulate its completion.
- Privileged-holder/native enrollment integration limitations remain those documented in SCOPE_MATRIX and BIOMETRIC_APPROVAL. Diagnostic carried signing does not qualify that execution boundary. No merge, upload, publication, release, trust changes or human approval by an agent.

Validation accounting: remaining-fixes-serial.log completes 143 schema/regression tests, 26 cancellation tests and 6 UI tests, including backing out of edited pairing fields. A subsequent full schema/cancellation run in pairing-context-final.log covers the final successful-pair request-context reset. Mac native suite: 117 tests, 1 skipped, no failures (remaining-fixes-macos.log). Overlapping intermediate simulator runs were stopped and preserved; they are not claimed as complete passes.

## Exact-head QA follow-up — 22 October 2026 (QA-03)

Added the iPhone production privacy manifest declaring app-only UserDefaults
with CA92.1. Both project.yml and the committed Xcode project explicitly package
it. The existing Darwin Release symbol gate now also asserts the manifest in
the actual built app and audits every bundled Mach-O's undefined symbols and
known Objective-C selectors against required-reason API categories.

Apple's API list was rechecked on 22 October. The unsigned arm64 iPhone Release
bundle builds and passes the bundle audit and test-hook symbol gate. Its linked
API audit finds UserDefaults and no additional listed timestamp, boot-time,
disk-space or active-keyboard APIs; no speculative FileTimestamp reason was
added. Four new tests cover missing manifest, missing timestamp declaration,
valid app-only defaults and project wiring; the initial manifest test failed.
This symbol/selector audit does not prove absence of indirect API use or replace
final processed-archive review. No device install, release, trust or key action.
