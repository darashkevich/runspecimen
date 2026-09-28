# Biometric approval

Status: **local binding only, not an execution gate, not shipped**.

`BiometricApprovalStore` canonicalizes one local request and consumes it once. The bytes cover the policy (`local`), Mac id, workspace id, run id, contract fingerprint, input fingerprint, execution bounds, nonce, expiry, and key id. Consume checks a pinned P-256 public key, the signature, and the live request. A second consume is a replay. A changed signature or a different key is tamper and does not spend the nonce. A different contract, input fingerprint, or bound is a mismatch and does not spend the nonce. Expiry spends the nonce so a later clock change cannot reuse it. Companion and dual policies cannot be constructed or consumed.

`LocalSecureEnclaveSigner` builds a non-exportable Secure Enclave key with `biometryCurrentSet` and `privateKeyUsage`, then signs those bytes. It does not call `LAContext.evaluatePolicy` and it does not take an authentication-success Boolean. Unit tests do not call it. A software P-256 key in tests is a test double, not biometric approval. Yahor still has to complete a real Touch ID prompt before that signer can be treated as exercised.

This store does not start a run. The existing PTY `APPROVE` path is unchanged. An agent that can replace the user-writable CLI, or that runs in the same user session as the executor, still bypasses a check that lives only in the app. A Secure Enclave signature does not fix a replaced executor.

## What a signature would mean

A local biometric approval is evidence that a key stored in the Mac Secure Enclave signed one canonical request, and that using the key required a fresh biometric check. A companion approval is evidence that a different key, stored in the paired iPhone Secure Enclave, signed that same request after the phone showed the request and the person approved it there.

Neither signature proves that no model was involved, that the person understood the command, or that the person was at the Mac when the phone signed.

## Request

Each signature is over one versioned byte string, not over an authentication-success Boolean. The request includes a version, the Mac and workspace identity, campaign and run IDs, the contract and input fingerprints, the execution bounds, the policy (`local`, `companion`, or `dual`), a nonce, an expiry, and the key identifier. Local-only policy rejects a companion signature. Dual policy requires both signatures over that same request. A relay that carries bytes does not get a key and cannot approve.

The executor must recheck the request against the live contract immediately before execution and consume the approval in the same state transition as the workspace lease. That wiring is not in this increment. A restart, a second entry point, or a signature after expiry must not run the command again.

## What this Mac can enforce today

TTY `approve` checks that stdin and stdout are terminals and that the line is exactly `APPROVE`. That does not identify a person. The Mac app does not type that phrase. Store builds do not include `com.apple.security.network.server`. The existing remote-confirm channel is not biometric approval and must not be reused as one.

An agent that can replace the user-writable CLI, or that runs inside the same user session as the executor, can still skip a check that lives only in that CLI. A Secure Enclave signature does not fix a replaced executor. Putting the check in a privileged helper, or in an App Store binary the agent cannot rewrite, is a different product boundary.

## Decision

The first increment is local Mac signing only. Companion approval still needs a path from the iPhone to the Mac, and that path is not chosen. The rejected Mac App Store entitlement was a listening server. The remaining choices are:

1. **User-mediated transfer.** The phone signs, and the person moves the signature onto the Mac (share sheet or a file). No listening socket. Easy to mishandle, and it is not an automatic pairing.
2. **Outbound relay.** The Mac uses the existing outbound client entitlement to reach a service the phone also reaches. That service must not hold approval keys. It is new infrastructure, a privacy disclosure, and an outage dependency.
3. **Privileged local helper.** A helper the agent cannot replace enforces the signature. That is a privileged component and a material change to the sandbox story.

Do not add a network server entitlement, a relay, or a privileged helper until one of these is chosen. Do not describe biometric approval as shipped.
