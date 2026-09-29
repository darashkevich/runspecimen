# Executor protection decision

Status: **not decided and not built.** No privileged helper, setuid binary, XPC service, Endpoint Security client, or new entitlement is in this candidate. `consumeForExecution` is not called by a run. `evaluateExecution` only calls a consume function a test supplies, and its `started` field stays false.

Owning a consumed-approval marker or a workspace lease does not stop another process from running the same command. A root-owned file can stop a second `runspecimen` from restoring that file. It cannot stop `/bin/sh`, the user's editor, or any other binary that can already read the workspace from executing the argv in the contract.

## What a sole path would have to control

For the helper to be the only process that can run the command, the operating system has to deny the exec to everyone else. A private file is not that control when the command is a user-owned program and user-owned inputs.

| Resource | Access control that would make the helper the only caller | What root ownership of a marker actually does |
| --- | --- | --- |
| The command binary and its inputs | The user must be unable to `exec` them. macOS does not offer a third-party app a sandbox it can apply to other processes. | Unchanged. The user can still run them. |
| Consumed-approval marker and RunSpecimen lease | Root-owned, mode `0700`, created by the helper | Stops the user from restoring those two files. Does not stop the command. |
| Enrollment snapshot the helper trusts | Same root-owned directory. A carried file's backend label is not enrollment | Stops the user from editing the snapshot. Does not stop the command. |
| The process that calls `posix_spawn` | Only the helper's code | Any other process can spawn the same argv. |
| Secure Enclave private key | User keychain, `biometryCurrentSet`. A helper does not receive it | Unchanged. |

The OS control that can deny an exec is Endpoint Security `ES_EVENT_TYPE_AUTH_EXEC`. It requires the restricted entitlement `com.apple.developer.endpoint-security.client`. Apple treats that entitlement as restricted: WWDC 2020 session 10159 says the app must request a provisioning profile, and the client is a system extension, not a Mac App Store helper. DTS has said the entitlement is granted separately and is not an App Store capability (developer.apple.com/forums/thread/759149, July 2024). This team has not been granted it. Using it to block the user's own shell would be a different product. It is not part of this recommendation, and it is not implemented.

A privileged helper installed with `SMJobBless` is outside the Mac App Store. Apple's archived EvenBetterAuthorizationSample says Mac App Store apps may not use elevated privileges. Guideline 2.4.5(v) forbids a Mac App Store app from escalating to root or using setuid. Guideline 2.4.5(ii) and (iv) require one self-contained bundle. Guideline 2.5.2 keeps the app inside its container. An XPC service inside `Contents/XPCServices` is replaced when the app is replaced (WWDC 2023 session 10266). QA1773 requires every Mach-O in a sandboxed bundle to be sandboxed. None of those make the helper the only process that can run a user-owned command.

## Admin and root

Root can replace a helper, delete its files, and exec anything. An administrator who can install a helper can also run the command directly. Same-user automation and administrator or root compromise are different threats. No design in this document stops root.

A signature still does not prove the person understood the command. Hardware authentication protects the signing operation.

## Recommended design

Keep the Mac App Store app sandboxed. Do not add a privileged helper. Do not apply for Endpoint Security for this receipt product.

The helper that only owns a marker and a lease does not meet the sole-path requirement, so building it would add a Developer ID install, a privileged prompt, and a second update channel without making the helper the only process that can run the command. The Endpoint Security alternative could deny other execs only after a separate Apple grant, cannot ship in this Store app, and would block the user from running their own command. That cost is not accepted here.

What the Store app does: sandbox, no `com.apple.security.network.server`, no browser dashboard, user-mediated companion file, approval state in the container. A same-user agent can run another binary or run the command directly. That limit stays open. It is not marked done.

`evaluateExecution` remains a test seam. It does not spawn and it does not take the lease.

## Authorization

No helper, relay, Endpoint Security client, or new entitlement is authorized. This note does not ask for one to be built. A later decision to pursue a sole execution path has to name Endpoint Security, the restricted entitlement, and the fact that it would block the user's own command. That decision is not this candidate.
