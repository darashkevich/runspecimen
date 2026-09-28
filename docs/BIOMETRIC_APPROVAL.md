# Biometric approval

Status: **local prototype, not an execution gate, not shipped**.

`BiometricApprovalStore` canonicalizes one local request and consumes it once. The bytes cover the policy (`local`), Mac id, workspace id, run id, contract fingerprint, input fingerprint, execution bounds, nonce, expiry, and key id. Consume checks the public key in the enrollment record, not a public key that arrived with the signature. A second consume is a replay. A changed signature or a different key is tamper and does not spend the nonce. Each signed field is bound. A different contract, input fingerprint, or bound is a mismatch and does not spend the nonce. Expiry spends the nonce so a later clock change cannot reuse it. Companion and dual policies cannot be constructed or consumed.

Enrollment is separate from an approval. `SoftwareApprovalKeyEnrollment` is a test double: it stores a software P-256 key and signs later requests with that same key. `LocalSecureEnclaveEnrollment` creates one non-exportable Secure Enclave key (`biometryCurrentSet` and `privateKeyUsage`), stores the key blob in the keychain, and later signs by loading that blob. It does not call `LAContext.evaluatePolicy` and it does not take an authentication-success Boolean. Revoke and rotate drop the old key. If the biometric set changes, recovery is `retireUnusableKey` and a new enrollment, not an exported private key. Unit tests do not call the Secure Enclave path. Yahor still has to complete a real Touch ID prompt before that path can be treated as exercised.

Revoke and consume take the same enrollment lock. Consume reloads the key state and generation after that lock is acquired, so a revocation that finished while the consumer was waiting is not accepted. Expiry is read from the clock inside the approval lock, at the consume decision, after that wait. A keychain delete that returns anything other than success or "not found" is a failure and does not count as removal.

`LocalSecureEnclaveEnrollment.ProductionPolicy.accepts` compares a backend string. Tests call it. Enroll, sign, consume, and every run path do not. It is not an execution policy and it does not reject a software key at runtime. The software double is not hardware-backed approval. The approval directory is user-writable, so restoring an approval file and deleting the consumed marker spends the nonce again. That is a prototype limit, not protection against a same-user agent.

This store does not start a run. The existing PTY `APPROVE` path is unchanged. No run entry point calls the store. The approval directory is user-writable: restoring the approval file and deleting the consumed marker consumes the nonce again. That is a limit of this prototype, not a shipped bypass. An agent that can replace the user-writable CLI, or that runs in the same user session as the executor, still bypasses a check that lives only in the app. A Secure Enclave signature does not fix a replaced executor.

## What a signature would mean

A local biometric approval is evidence that a key stored in the Mac Secure Enclave signed one canonical request, and that using the key required a fresh biometric check. A companion approval is evidence that a different key, stored in the paired iPhone Secure Enclave, signed that same request after the phone showed the request and the person approved it there.

Neither signature proves that no model was involved, that the person understood the command, or that the person was at the Mac when the phone signed.

## Request

Each signature is over one versioned byte string, not over an authentication-success Boolean. The request includes a version, the Mac and workspace identity, campaign and run IDs, the contract and input fingerprints, the execution bounds, the policy (`local`, `companion`, or `dual`), a nonce, an expiry, and the key identifier. Local-only policy rejects a companion signature. Dual policy requires both signatures over that same request. A relay that carries bytes does not get a key and cannot approve.

The executor must recheck the request against the live contract immediately before execution and consume the approval in the same state transition as the workspace lease. That wiring is not in this increment. A restart, a second entry point, or a signature after expiry must not run the command again.

## What this Mac can enforce today

TTY `approve` checks that stdin and stdout are terminals and that the line is exactly `APPROVE`. That does not identify a person. The Mac app does not type that phrase. Store builds do not include `com.apple.security.network.server`. The existing remote-confirm channel is not biometric approval and must not be reused as one.

An agent that can replace the user-writable CLI, or that runs inside the same user session as the executor, can still skip a check that lives only in that CLI. A Secure Enclave signature does not fix a replaced executor. Putting the check in a privileged helper, or in an App Store binary the agent cannot rewrite, is a different product boundary.

## Decisions still required

These are separate. Choosing one does not choose the other. Neither is implemented.

**Executor protection.** Where the check has to live before it can refuse a same-user agent.

1. Leave enforcement in the app and the user-writable CLI. No new entitlement. A replaced binary or a restored approval directory still wins. This is the current prototype.
2. A privileged helper that holds enrollment and the workspace lease. That is a privileged component and a material sandbox change.

**Companion transport.** How an iPhone signature would reach the Mac. Local enrollment does not need this.

1. User-mediated transfer. The person moves the signature onto the Mac. No listening socket. Easy to mishandle, and it is not automatic pairing.
2. Outbound relay. The Mac uses the existing outbound client entitlement. The relay holds no approval keys. That is new infrastructure, a privacy disclosure, and an outage dependency.

A listening server was the rejected Mac App Store entitlement. Do not add `com.apple.security.network.server`, a relay, or a privileged helper until the matching decision is explicit. Do not connect consumption to the lease before the executor decision is accepted. Do not describe biometric approval as shipped.
