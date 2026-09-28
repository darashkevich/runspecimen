# Executor and state protection

Status: **design for a decision. Nothing in this document is built, installed, or authorized.**

The goal is that a same-user agent cannot replace the program that decides a run may start, and cannot roll back an approval that was already consumed. The current macOS app and the `runspecimen` CLI are files the logged-in user can rewrite. A Secure Enclave signature does not fix a replaced executor. Restoring the approval directory and deleting the consumed marker spends the nonce again. Those are properties of this tree, not a future claim.

This is separate from companion transport. A carried RSBA2 file, an outbound relay, and a listening server are about how bytes move. They do not hold the workspace lease and they do not stop a replaced CLI. `com.apple.security.network.server` stays rejected. No relay is built.

## Trust assumptions

- The person using the Mac can be prompted. A prompt is not proof that the process which later starts the run is the process that showed the prompt.
- Enrollment records, pending approvals, and consumed markers live in a directory the user can write.
- The CLI on `PATH`, a Homebrew prefix, and a development-signed `.app` the user can replace are all user-writable.
- A signature verifies bytes. It does not pin the binary that verifies them.
- The approved App Store app **0.1.4 (9)** is a different, already-shipped build. This design does not change it. It also does not say that an App Store binary by itself is a protected executor.

## What has to be true before a run starts

Whatever component is allowed to start a run has to do all of the following in one place the agent cannot swap out:

1. Load the live enrollment under the same lock that revocation uses. A revoked or missing generation fails closed.
2. Check the RSBA2 signatures, the exact version, the generations inside the signed bytes, and the dual-key inequality at that moment. A caller-supplied generation is not accepted.
3. Take the workspace lease only after those checks, and record the consumed marker in state that a user-writable restore cannot put back.
4. Refuse to start if the binary, the policy, or the state store is not the one that was measured.

The store in this tree does steps 1 and 2 for a prototype directory. It does not do steps 3 or 4. Do not connect `consumeEnrolled` to the lease until the location below is chosen.

## Options

**Leave the check in the user-writable app and CLI.** No new entitlement. This is what the code does today. It cannot meet an anti-replacement or anti-rollback goal. A person or agent who can write the binary or the approval directory wins.

**A privileged helper.** Not authorized. Not implemented. A helper would have to be the only process that can read the protected state and the only process that can spawn the run. Even then:

- A Mac App Store app generally cannot install a root helper with `SMJobBless`. Planning as if a helper is available inside the Store sandbox is not supported by the current entitlement set.
- A same-user XPC service inside the app bundle is replaced when the app bundle is replaced. It does not resist a same-user agent.
- Secure Enclave keys created by the app live in the user keychain. A root helper does not automatically receive those keys or the app's keychain access group. Moving the key into a helper is a new key-lifecycle design, not a flag.
- The helper would need its own update, downgrade, and recovery story: a pinned code signature, a version that cannot be rolled back to a helper that skips the check, and a recovery path when the biometric set changes. None of that is specified as an implementation here.
- IPC from the app to a helper must authenticate the caller. A helper that accepts any same-user connection is the app again.

**An App Store binary the user cannot rewrite in place.** The installed Store app is owned by the system install path, but the user can still run another `runspecimen` from a writable location, and the approval directory used by a prototype remains writable. Store distribution alone does not protect state. Whether a future Store version can hold protected state without a helper is part of the decision, not a conclusion.

## Store feasibility

- Do not add a helper, a relay, or a new entitlement in order to try this.
- Do not assume the helper option is compatible with the Mac App Store sandbox.
- Do not overwrite `/Applications/RunSpecimen.app` or the approved **0.1.4 (9)** record while this is undecided.
- The development app used for acceptance is signed with Apple Development and is not a Store package.

## What this document does not decide

Yahor still chooses where the consume check lives before a run may start. Until that choice is explicit, the prototype stays unwired: no lease, no helper, no relay, no Face ID on iOS, and no claim that biometric approval is an execution gate.
