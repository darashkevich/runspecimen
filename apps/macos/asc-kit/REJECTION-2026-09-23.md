# Confirmed Apple feedback — 0.1.3 (8)

Read directly in App Store Connect on 2026-09-24. Submission:
`9c19e1cd-ebd1-4705-b683-5a5fdc2671f6`. Review date: September 23, 2026.
Device: MacBook Pro (14-inch, November 2024). Status: rejected / unresolved issues.

This supersedes inferred causes and the stale waiting-for-review status in STATUS.md.

## Exact issues to resolve before another upload

1. **2.5.1:** Bundled Python 3.9 `_hashlib` and `_ssl` reference Apple's private
   `TrustEvaluationAgent.framework`. `_lzma` references the disallowed lzma
   decoder/encoder/check/code/end/properties/raw/stream symbols listed by Apple.
   Rebuild with an explicitly selected non-Apple CPython runtime and inspect every
   nested Mach-O. Do not rename symbols or suppress scanner output. Any third-party
   liblzma linkage needs actual dependency provenance and compliant packaging;
   safest if unnecessary is to exclude lzma and test the frozen engine without it.
2. **4 — Design:** After closing the main window there is no menu item to reopen
   it. Add an explicit Show Main Window command and test close/reopen repeatedly,
   preserving the workspace and preventing duplicated initialization.
3. **2.4.5(i):** Apple requests removal of `com.apple.security.network.server`
   because it found no matching functionality. The current optional loopback
   dashboard uses it. Decide explicitly between removing the dashboard from MAS
   (native views remain) or retaining it with a clear demonstration and justification.
   Do not silently remove the entitlement while leaving a broken dashboard button.

## Candidate acceptance gate

- Separate version/build; freeze latest intended source and record exact revision/diff.
- Scan both staged runtime and final signed app for Apple's identified references.
- Verify main window close/reopen in the actual app, not merely source inspection.
- Check effective signed entitlements and dashboard behavior against the chosen policy.
- Repeat signing, sandbox, self-contained launch, icon, and human-PTY checks.
- Update reviewer notes, screenshots, and metadata to describe the actual candidate.
- No new upload/submission has been performed as part of this review.

## How later binaries address each item

| Rejection | 0.1.4 (9), the package on file | 0.1.5 (11), this candidate, not uploaded |
| --- | --- | --- |
| 2.5.1 private `TrustEvaluationAgent` and lzma symbols | Frozen with an explicit non-Apple CPython. `verify_mas_runtime.py` fails closed on those references. | Same scanner. A Store `.pkg` is valid only when that scan reports zero violations. |
| 4 Design, no way back to the main window | File → Show Main Window and Command-0. | The process stays running after the last window closes, and quit/relaunch restores a contract that is still inside the workspace. |
| 2.4.5(i) unused `network.server` | Entitlement removed. Store UI has no browser dashboard. | Same. `runspecimen dashboard` remains on the standalone CLI. |

Apple has not been asked to review 0.1.5 (11). 0.1.4 (9) is a different binary.
