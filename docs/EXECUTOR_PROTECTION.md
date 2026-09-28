# Executor and state protection

Status: **recommendation. Nothing in this document is built, installed, or authorized.** A privileged helper is not part of the candidate.

The check that decides a run may start still lives in code the logged-in user can replace, and the approval files still live in a directory that user can restore. A Secure Enclave signature does not fix either fact. This note says where that check should live for a Mac App Store app, what that choice does and does not stop, and the one authorization that is still open.

## Recommendation

Keep enforcement inside the sandboxed Mac App Store app. Keep approval state in that app's container. Do not add a privileged helper, a setuid binary, or a new entitlement to the Store app.

A same-user agent and a root or admin compromise are different threats. The Store-feasible path accepts the first: a person or agent who can run another binary, rewrite a user-owned CLI, or restore a container backup still wins. It refuses the second as a product feature. Guideline 2.4.5(v) does not allow a Mac App Store app to escalate to root or use setuid.

## What has to hold before a run starts

These are properties of the component that is allowed to start a run. The prototype store does the first two for a directory the user can write. It does not do the rest, and no run path calls `consumeForExecution`.

1. Load the live enrollment under the same lock revocation uses. Role, backend, provenance, generation, and public key come from that record. A software key, a development key, a diagnostic key, or a swapped role fails closed. Two software keys are not Mac-plus-phone authentication.
2. Verify the RSBA2 signatures against the canonical bytes, including the generations inside those bytes, and reject a dual request whose public keys are equal. Do this at consume, not from caller-supplied fields.
3. Record the consumed marker in state the same component owns, in the same critical section as the workspace lease. A restore of an older marker must not make the nonce usable again.
4. Refuse to start when the binary that performs the check is not the measured Store binary.

## Resource ownership

| Resource | Owner in the recommended design | What a same-user agent can still do |
| --- | --- | --- |
| Store app binary | System install path, updated only through the Mac App Store (guideline 2.4.5(vii)) | Launch a different `runspecimen` from a writable path |
| Approval and enrollment files | App container. Guideline 2.5.2: the app may not read or write outside that container | Restore a backup of the container, or copy the files out and back |
| Secure Enclave key | User keychain, `biometryCurrentSet`, non-exportable | Use the key only through a prompt. Cannot copy the private key into a helper |
| Workspace lease | Same component that consumed the approval | Skip the component by running another binary |
| Companion package | A file a person carries. No socket, no relay | Substitute a different file. Import still checks the signature |

A root or admin process can ignore the sandbox, the container, and the user keychain. That is not the threat a Store app is allowed to close with a privileged helper.

## IPC

There is no helper and no XPC service in this candidate, so there is no new caller to authenticate.

If a later authorization adds a process, the checks that would be required are: the service is inside `Contents/XPCServices` of the same bundle, every Mach-O in that bundle is sandboxed (QA1773), and the service accepts only a connection whose responsible process matches the Store app (WWDC 2023 session 10266, environment and spawn constraints). An XPC service in the bundle is replaced when the bundle is replaced. It does not resist a same-user agent, and it is not a root helper. Those constraints are not implemented.

## Update, downgrade, and recovery

- Updates to the Store app come from the Mac App Store. A sidecar installer, a downloaded helper, or a second update channel conflicts with 2.4.5(iv) and 2.4.5(vii).
- A downgrade that skips the consume check is a failure. The recommended design has one binary and one container. It does not have a helper version to pin.
- Biometric-set change makes the Secure Enclave key unusable. Recovery is retire the public record and enroll again. The private key is not exported.
- Container restore is a same-user rollback of the consumed marker. The recommended design does not pretend to stop it. Stopping it would require state the user cannot restore, which a sandboxed app does not have.
- Losing the device or the biometric set does not require a root helper. It requires a new enrollment.

## Options

**Sandboxed App Store app, state in the container.** Recommended. No new entitlement. Matches 2.4.5(i), 2.4.5(ii), 2.4.5(v), and 2.5.2. Does not stop a same-user agent who runs another binary or restores the container. This is the only option that stays on the Store track without a new privilege.

**Developer ID privileged helper (`SMJobBless`).** Not recommended for the Store app. Not authorized. Not built. Apple's archived EvenBetterAuthorizationSample documents that helper as outside the Mac App Store, and that Mac App Store apps are not allowed to use elevated privileges. A third-party daemon is not itself sandboxed. A root helper also does not receive the app's Secure Enclave keys, which stay in the user keychain. It would still need a pinned signature, a downgrade refusal, a recovery path, and an IPC check of the caller. None of that is a reason to build it before the question below is answered. It is not assumed to be Store-compatible.

## Sources

Fetched from the current App Store Review Guidelines, https://developer.apple.com/app-store/review/guidelines/, on 2026-09-28:

- **2.4.5(i)** Mac App Store apps must be sandboxed and follow the macOS File System documentation.
- **2.4.5(ii)** They must be self-contained single app bundles and cannot install code or resources in shared locations.
- **2.4.5(iv)** They may not download or install standalone apps, kexts, additional code, or resources to add functionality.
- **2.4.5(v)** They may not request escalation to root privileges or use setuid attributes.
- **2.4.5(vii)** They must use the Mac App Store to distribute updates.
- **2.5.2** Apps should be self-contained and may not read or write data outside the designated container area, nor download, install, or execute code which changes features.

Also: archived EvenBetterAuthorizationSample (SMJobBless is for outside the Mac App Store); archived Creating XPC Services (the service lives in the app bundle); WWDC 2023 session 10266, "Protect your Mac app with environment constraints"; Technical Q&A QA1773 (every Mach-O in a sandboxed bundle, including an XPC service or an inherit helper, must have `com.apple.security.app-sandbox`).

## Authorization

One question, and it is an authorization rather than a design exercise:

**Do you authorize a non-App Store Developer ID privileged helper that owns approval state outside the sandbox, or do you keep enforcement inside the sandboxed App Store app, knowing a same-user agent can replace the CLI and restore the container?**

Until that is answered, the candidate keeps the second option and does not build the first. `consumeForExecution` stays unwired. No helper, relay, or new entitlement is added.
