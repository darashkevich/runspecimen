# Executor protection decision

Status: **not decided and not built.** No privileged helper, setuid binary, XPC service, or new entitlement is in this candidate. `consumeForExecution` is not called by a run. `evaluateExecution` only calls a consume function a test supplies, and its `started` field stays false.

The earlier note recommended keeping enforcement in the sandboxed Mac App Store app and accepting same-user binary replacement and container restore. That option does **not** meet the stronger requirement: a same-user agent must not be able to start the bounded command by replacing the CLI or rolling approval state back.

## Option A — sandboxed Store app

The check and the approval files stay in the Mac App Store app and its container.

What it can do: sandbox the app, omit `com.apple.security.network.server`, keep the browser dashboard out of the Store binary, and require a person to carry a package instead of opening a socket.

What it cannot do: stop a same-user agent. That agent can run another `runspecimen`, replace a user-owned binary, or restore the container. Guideline 2.4.5(v) forbids a Mac App Store app from escalating to root or using setuid. Guideline 2.4.5(ii) and (iv) require one self-contained bundle and forbid installing code or resources in shared locations. Guideline 2.5.2 keeps the app inside its container. An XPC service inside `Contents/XPCServices` is replaced when the bundle is replaced.

This option is the only one that can ship as the current Mac App Store app. It is not the stronger requirement.

## Option B — protected executor, outside the Store app

A separate Developer ID product, not the Mac App Store app, whose helper is the only process that may spawn the bounded command. The helper owns the consumed-approval marker and the workspace lease as root, mode `0700` or `0600`, so a same-user process cannot rewrite or restore them.

The helper has to be the spawner. A helper that only returns “allowed” to a user-writable CLI does not meet the requirement, because that CLI can ignore the answer. An alternate CLI meets the requirement only when it cannot read the lease, cannot write the consumed marker, and cannot spawn the bounded command itself. Those resources have to be exclusively the helper’s.

Distribution: this cannot be the Mac App Store app. Apple’s archived EvenBetterAuthorizationSample says `SMJobBless` helpers are for outside the Mac App Store, and that Mac App Store apps may not use elevated privileges. A third-party daemon is not itself sandboxed. The Store app can stay the sandboxed 0.1.x product. The protected executor would be a different download, a different update channel, and a privileged install a person has to approve.

What a privileged helper does **not** solve by itself:

- It does not receive the user-keychain Secure Enclave private key. Face ID and Touch ID stay in the user session. The helper can receive signature bytes and a pinned public key. It cannot sign as the person.
- It does not stop an administrator or root. Root can replace the helper, delete its state, or spawn the command directly. Same-user automation and administrator or root compromise are different threats. Option B is aimed at the first. It does not claim the second.
- A signature still does not prove the person understood the command. Hardware authentication protects the signing operation. It is not a reading of intent.

IPC, if this option is authorized later: the user session sends the canonical request and the signatures over an XPC connection the helper accepts only from a binary whose code signature and launch constraint match the Developer ID product (WWDC 2023 session 10266). The helper reloads enrollment, checks generation, role, backend, and provenance, consumes the nonce, and takes the lease in one critical section before it spawns. A crash before the marker is durable must leave the nonce unconsumed. A crash after the marker is durable must leave the nonce consumed. An update replaces the helper only through the signed installer. A downgrade of the helper or of the enrollment generation fails closed.

None of that IPC or helper exists in this tree.

## Resources the executor would have to own

| Resource | Option A | Option B |
| --- | --- | --- |
| Process that spawns the bounded command | The Store app or any other binary the user can launch | Only the helper |
| Consumed-approval marker and workspace lease | App container, restorable by the same user | Root-owned files the user cannot restore |
| Enrollment and policy records used at spawn | Container, same limitation | Helper-owned copies. A carried file’s “Secure Enclave” label is not enrollment |
| Secure Enclave private key | User keychain | Still the user keychain. The helper does not get it |
| Companion transport | A file a person carries | The same. No relay and no listening socket |

## Recommendation

Do not treat option A as satisfying the stronger requirement. Keep the Mac App Store app on option A so it can remain sandboxed and free of a root helper. Meet the stronger requirement only with option B, as a separate Developer ID product, and only after the helper is specified as the sole spawner of the bounded command.

The candidate does not enable a production run path for either option. `evaluateExecution` is the integration seam, tested with a double. It does not take the workspace lease and it does not spawn.

## Authorization question

Authorize a separate Developer ID product, not a change to the Mac App Store app, whose privileged helper is the only process allowed to spawn a bounded run and the only owner of the consumed-approval marker and workspace lease, knowing that this helper still does not hold the Secure Enclave key and does not stop an administrator or root?
