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
| MAIN-06 | **UNVERIFIED:** direct real-certificate delegate coverage remains; a live TLS handshake and physical Mac pairing need separate validation. |
| PR76-01 | Timestamp UI query uses its production accessibility identifier; initial Refresh hittability is asserted without scrolling; failure text has a unique connection-feedback identifier. Unit tests assert cancellation/failure timestamp preservation. Focused Refresh UI suite passes 3/3. |
| PR76-02 | Enrollment outcome belongs to the session, clears on new signing/invalidation/disconnect and changed key state, and is only published for the current operation. Regression covers refusal-to-key-state transition. |
| PR76-03 | Editing carried-key input clears its previous pin result. |
| PR76-04 | The system Copy smoke test is retained. A production-session test asserts the exact string supplied to ShareLink includes the actual recovery failure and retention guidance. This does not prove the system pasteboard bytes. |
| PR76-05 | **UNVERIFIED:** automated macOS pin layout assertion still absent; build/code evidence does not replace visual layout verification. |
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
passing local suite closes those limits. Independent DeepSeek re-review of exact
new heads and candidate bytes is required before release.

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
