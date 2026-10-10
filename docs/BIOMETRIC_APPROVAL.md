# Biometric approval

Status: **local prototype, not an execution gate, not shipped**.

`BiometricApprovalStore` canonicalizes one RSBA1 local request and consumes it once. The bytes cover the policy (`local`), Mac id, workspace id, run id, contract fingerprint, input fingerprint, execution bounds, nonce, expiry, and key id. Consume checks the public key in the enrollment record, not a public key that arrived with the signature. A second consume is a replay. A changed signature or a different key is tamper and does not spend the nonce. Each signed field is bound. A different contract, input fingerprint, or bound is a mismatch and does not spend the nonce. Expiry spends the nonce so a later clock change cannot reuse it.

`PolicyBoundApprovalStore` is the RSBA2 request. Its policy is `local`, `companion`, or `dual`, and that policy is inside the signed bytes. So are the enrollment generations for the keys that policy requires. A signature made under generation 1 does not verify after the package generation is rewritten. Import accepts only the exact version `RSBA2`, rejects unknown keys, and rejects a missing or non-canonical generation. Local rejects a companion signature. Companion rejects a local-only signature. Dual requires two different public keys over the same bytes, including at consume of a crafted pending file. A policy downgrade does not verify. A package that claims `present_at_mac` is rejected. The person can carry that package onto the Mac; the import does not open a socket. A companion signature is the phone. It is not physical presence at the Mac.

Enrollment is separate from an approval. Each record stores a role (`local` or `companion`), a backend, and a provenance. `consumeEnrolled` accepts a software test double only when the role matches the policy and the provenance is the software-test provenance. A swapped role, a `software-development` key, and a diagnostic key fail closed and do not spend the nonce. `consumeForExecution` accepts only an active Secure Enclave key with production provenance. No run path calls it. Two distinct software keys are not Mac-plus-phone authentication, and a passing software consume is not biometric completion.

`SoftwareApprovalKeyEnrollment` is a test double: it stores a software P-256 key and signs later requests with that same key. `LocalSecureEnclaveEnrollment` creates one non-exportable Secure Enclave key (`biometryCurrentSet` and `privateKeyUsage`), stores the key blob in the keychain, and later signs by loading that blob. It does not call `LAContext.evaluatePolicy` and it does not take an authentication-success Boolean. Revoke and rotate drop the old key. If the biometric set changes, recovery is `retireUnusableKey` and a new enrollment, not an exported private key. Unit tests do not call the Secure Enclave path. Yahor still has to complete a real Touch ID prompt before that path can be treated as exercised.

The iPhone companion key is `CompanionSecureEnclaveEnrollment` in the Observe app. The buttons call Secure Enclave enroll, sign, revoke, and rotate directly. `automationRefused()` is the entry tests call; it does not touch the enclave or the keychain, and it is not proof of a person. Enroll creates a key only when the pairing file is missing. A malformed, unreadable, active, or revoked file is an error, and the file is not replaced. That is not a recovery flow. Sign's linearization point is the enrollment lock after Face ID: the reload, the decision, and the clock happen together there. A revocation at that boundary discards the signature that has not been returned. A signature already returned is not revoked by that check; a later run still has to re-read the live record. Revoke writes the revoked record before deleting the keychain item. A failed delete leaves the revoked record, and a retry deletes the item without bumping the generation again. The public pairing file may say `secure-enclave`. `pinCarriedCompanion` stores an `active` public key as `unverified` / `carried-pin` and does not copy the label. A missing, revoked, or other `state` is refused, and no active enrollment file is written. A later import does not replace a locally revoked record or a different generation. That refusal is a carried-import check. It is not installed Secure Enclave admission. The development software signer is compiled only into `RunSpecimenObserveDev`. A software signature from that target is not biometric completion. No agent enrolls or authenticates on Yahor's behalf.

Revoke and `consumeEnrolled` take the same enrollment lock. `consumeEnrolled` reloads the live active record, key role, public key, and generation after that lock is acquired, so a revocation that finished while the consumer was waiting is not accepted. A missing generation fails closed. `consume` itself does not take a caller-supplied generation: the generation inside the signed request must match the stored signature, and a mismatch is tamper. Expiry is read from the clock inside the approval lock, at the consume decision, after that wait. A keychain delete that returns anything other than success or "not found" is a failure and does not count as removal. The diagnostic keychain service is `com.darashkevich.runspecimen.biometric.diagnostic`, separate from the production service. The diagnostic directory walk resolves each symlink before applying `..`, stops after 16 hops, and writes through a descriptor opened with `O_NOFOLLOW` on a directory the user owns. A path that leaves `/private/tmp/rs-touchid-diag` is refused. A short write, a failed `fsync`, or an interrupted write removes the new file instead of leaving a partial one.

`LocalSecureEnclaveEnrollment.ProductionPolicy.accepts` compares a backend string. Tests call it. Enroll, sign, consume, and every run path do not. It is not an execution policy and it does not reject a software key at runtime. The software double is not hardware-backed approval. The approval directory is user-writable, so restoring an approval file and deleting the consumed marker spends the nonce again. That is a prototype limit, not protection against a same-user agent.

This store does not start a run. The existing PTY `APPROVE` path is unchanged. No run entry point calls the store. The approval directory is user-writable: restoring the approval file and deleting the consumed marker consumes the nonce again. That is a limit of this prototype, not a shipped bypass. An agent that can replace the user-writable CLI, or that runs in the same user session as the executor, still bypasses a check that lives only in the app. A Secure Enclave signature does not fix a replaced executor.

## What a signature would mean

A local biometric approval is evidence that a key stored in the Mac Secure Enclave signed one canonical request, and that using the key required a fresh biometric check. A companion approval is evidence that a different key, stored in the paired iPhone Secure Enclave, signed that same request after the phone showed the request and the person approved it there.

Neither signature proves that no model was involved, that the person understood the command, or that the person was at the Mac when the phone signed.

## Request

Each signature is over one versioned byte string, not over an authentication-success Boolean. The request includes the exact version `RSBA2`, the Mac and workspace identity, campaign and run IDs, the contract and input fingerprints, the execution bounds, the policy (`local`, `companion`, or `dual`), a nonce, an expiry, the key identifier, and the enrollment generation for each required role. Local-only policy rejects a companion signature. Dual policy requires both signatures over that same request. A relay that carries bytes does not get a key and cannot approve.

The store can consume an RSBA2 approval once. It does not recheck a live contract, and it does not take the workspace lease. Connecting consume to the execution lease is still not done; that is not a request to reopen D1 or D2. A restart of the store process still sees the consumed marker on disk. A signature after expiry spends the nonce. Neither of those facts is a protected execution boundary.

## What this Mac can enforce today

TTY `approve` checks that stdin and stdout are terminals and that the line is exactly `APPROVE`. That does not identify a person. The Mac app does not type that phrase. Store builds do not include `com.apple.security.network.server`. The existing remote-confirm channel is not biometric approval and must not be reused as one.

An agent that can replace the user-writable CLI, or that runs inside the same user session as the executor, can still skip a check that lives only in that CLI. A Secure Enclave signature does not fix a replaced executor. Putting the check in a privileged helper, or in an App Store binary the agent cannot rewrite, is a different product boundary.

## Current state (locked D1/D2; E2 remains open)

Do not read the historical section below as the live product record.

- **D1 locked:** installed Secure Enclave / biometric admission stays fail-closed. `run_integration_complete` and `e2_closed` stay false.
- **D2 locked:** bundle id `com.darashkevich.runspecimen.holder` is accepted for Developer ID packaging and is not `production_verifier_pin()`. Guarantee (3) is excluded. The Store app stays guarantee (1).
- **Holder source exists, and it is not the Store app.** Yahor authorized a separate Developer ID holder. Its source is in this repository (`apps/holder`, `src/runspecimen/execution_holder.py`). A prior session observed `/Applications/RunSpecimen Holder.app` with `SMAppService.daemon`. That is a separate product. "Not in the Store app" is not "no separate holder source exists." It is not Store parity and is not installed admission.
- **E2 stays open.** Mac and iPhone Secure Enclave enroll, sign, revoke, and rotate are implemented in source and are not human-accepted on this candidate. Unit tests do not call the Secure Enclave. A passing software test is not that hardware path. A biometric press does not close E2.
- **Store app:** do not add `com.apple.security.network.server`, a relay, or a privileged helper to the Store binary. The Developer ID holder is not a Store privileged helper.

Details of the three guarantees remain in `docs/EXECUTOR_PROTECTION.md`. Do not describe biometric approval as shipped.

## Historical decision text (2026-09; do not reopen D1/D2)

The next paragraphs are the original decision record. They are not current identity. "Three different guarantees are open" and "Nothing beyond the sandboxed app is built" were true of that draft. D1 and D2 are now locked as above. Holder source exists outside the Store app. E2 is the item that remains open.

**Executor protection (historical wording).** Three different guarantees were distinguished: RunSpecimen refusing its own transition, protecting RunSpecimen's lease and enrollment files from other same-user writers, and blocking every equivalent command on the Mac. The candidate does the first. The lease still lives in the user-writable workspace, so the second is unfinished and does not require Endpoint Security. The third is global command blocking and is not this product.

**Companion transport (historical wording).** How an iPhone signature would reach the Mac. Local enrollment does not need this.

1. User-mediated transfer. The person moves the signature onto the Mac. No listening socket. Easy to mishandle, and it is not automatic pairing.
2. Outbound relay. The Mac uses the existing outbound client entitlement. The relay holds no approval keys. That is new infrastructure, a privacy disclosure, and an outage dependency.

A listening server was the rejected Mac App Store entitlement. That Store prohibition still holds. It does not mean the separate Developer ID holder source is absent.

## Real-device steps, for Yahor

The steps, the provisioning actions, and the kit layout are in `docs/HUMAN_DEVICE_KIT.md`. An agent must not run them, must not pass `--human-invoked`, and must not create a provisioning profile. Preview without that flag, and enroll without that flag, are the only diagnostic commands an agent may run. They do not call Secure Enclave.
