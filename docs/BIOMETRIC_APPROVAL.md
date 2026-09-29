# Biometric approval

Status: **local prototype, not an execution gate, not shipped**.

`BiometricApprovalStore` canonicalizes one RSBA1 local request and consumes it once. The bytes cover the policy (`local`), Mac id, workspace id, run id, contract fingerprint, input fingerprint, execution bounds, nonce, expiry, and key id. Consume checks the public key in the enrollment record, not a public key that arrived with the signature. A second consume is a replay. A changed signature or a different key is tamper and does not spend the nonce. Each signed field is bound. A different contract, input fingerprint, or bound is a mismatch and does not spend the nonce. Expiry spends the nonce so a later clock change cannot reuse it.

`PolicyBoundApprovalStore` is the RSBA2 request. Its policy is `local`, `companion`, or `dual`, and that policy is inside the signed bytes. So are the enrollment generations for the keys that policy requires. A signature made under generation 1 does not verify after the package generation is rewritten. Import accepts only the exact version `RSBA2`, rejects unknown keys, and rejects a missing or non-canonical generation. Local rejects a companion signature. Companion rejects a local-only signature. Dual requires two different public keys over the same bytes, including at consume of a crafted pending file. A policy downgrade does not verify. A package that claims `present_at_mac` is rejected. The person can carry that package onto the Mac; the import does not open a socket. A companion signature is the phone. It is not physical presence at the Mac.

Enrollment is separate from an approval. Each record stores a role (`local` or `companion`), a backend, and a provenance. `consumeEnrolled` accepts a software test double only when the role matches the policy and the provenance is the software-test provenance. A swapped role, a `software-development` key, and a diagnostic key fail closed and do not spend the nonce. `consumeForExecution` accepts only an active Secure Enclave key with production provenance. No run path calls it. Two distinct software keys are not Mac-plus-phone authentication, and a passing software consume is not biometric completion.

`SoftwareApprovalKeyEnrollment` is a test double: it stores a software P-256 key and signs later requests with that same key. `LocalSecureEnclaveEnrollment` creates one non-exportable Secure Enclave key (`biometryCurrentSet` and `privateKeyUsage`), stores the key blob in the keychain, and later signs by loading that blob. It does not call `LAContext.evaluatePolicy` and it does not take an authentication-success Boolean. Revoke and rotate drop the old key. If the biometric set changes, recovery is `retireUnusableKey` and a new enrollment, not an exported private key. Unit tests do not call the Secure Enclave path. Yahor still has to complete a real Touch ID prompt before that path can be treated as exercised.

The iPhone companion key is `CompanionSecureEnclaveEnrollment` in the Observe app. The buttons call Secure Enclave enroll, sign, revoke, and rotate directly. `automationRefused()` is the entry tests call; it does not touch the enclave or the keychain, and it is not proof of a person. Sign reloads the enrollment record after the Face ID wait and discards the signature if the key was revoked, the generation or public key changed, or the request expired. Revoke writes the revoked record before deleting the keychain item. A failed delete leaves the revoked record, and a retry deletes the item without bumping the generation again. The public pairing file may say `secure-enclave`. `pinCarriedCompanion` stores that public key as `unverified` / `carried-pin` and does not copy the label. The development software signer is compiled only into `RunSpecimenObserveDev`. A software signature from that target is not biometric completion. No agent enrolls or authenticates on Yahor's behalf.

Revoke and `consumeEnrolled` take the same enrollment lock. `consumeEnrolled` reloads the live active record, key role, public key, and generation after that lock is acquired, so a revocation that finished while the consumer was waiting is not accepted. A missing generation fails closed. `consume` itself does not take a caller-supplied generation: the generation inside the signed request must match the stored signature, and a mismatch is tamper. Expiry is read from the clock inside the approval lock, at the consume decision, after that wait. A keychain delete that returns anything other than success or "not found" is a failure and does not count as removal. The diagnostic keychain service is `com.darashkevich.runspecimen.biometric.diagnostic`, separate from the production service. The diagnostic directory walk resolves each symlink before applying `..`, stops after 16 hops, and writes through a descriptor opened with `O_NOFOLLOW` on a directory the user owns. A path that leaves `/private/tmp/rs-touchid-diag` is refused. A short write, a failed `fsync`, or an interrupted write removes the new file instead of leaving a partial one.

`LocalSecureEnclaveEnrollment.ProductionPolicy.accepts` compares a backend string. Tests call it. Enroll, sign, consume, and every run path do not. It is not an execution policy and it does not reject a software key at runtime. The software double is not hardware-backed approval. The approval directory is user-writable, so restoring an approval file and deleting the consumed marker spends the nonce again. That is a prototype limit, not protection against a same-user agent.

This store does not start a run. The existing PTY `APPROVE` path is unchanged. No run entry point calls the store. The approval directory is user-writable: restoring the approval file and deleting the consumed marker consumes the nonce again. That is a limit of this prototype, not a shipped bypass. An agent that can replace the user-writable CLI, or that runs in the same user session as the executor, still bypasses a check that lives only in the app. A Secure Enclave signature does not fix a replaced executor.

## What a signature would mean

A local biometric approval is evidence that a key stored in the Mac Secure Enclave signed one canonical request, and that using the key required a fresh biometric check. A companion approval is evidence that a different key, stored in the paired iPhone Secure Enclave, signed that same request after the phone showed the request and the person approved it there.

Neither signature proves that no model was involved, that the person understood the command, or that the person was at the Mac when the phone signed.

## Request

Each signature is over one versioned byte string, not over an authentication-success Boolean. The request includes the exact version `RSBA2`, the Mac and workspace identity, campaign and run IDs, the contract and input fingerprints, the execution bounds, the policy (`local`, `companion`, or `dual`), a nonce, an expiry, the key identifier, and the enrollment generation for each required role. Local-only policy rejects a companion signature. Dual policy requires both signatures over that same request. A relay that carries bytes does not get a key and cannot approve.

The store can consume an RSBA2 approval once. It does not recheck a live contract, and it does not take the workspace lease. That execution-boundary wiring is waiting on where the check is allowed to live. A restart of the store process still sees the consumed marker on disk. A signature after expiry spends the nonce. Neither of those facts is a protected execution boundary.

## What this Mac can enforce today

TTY `approve` checks that stdin and stdout are terminals and that the line is exactly `APPROVE`. That does not identify a person. The Mac app does not type that phrase. Store builds do not include `com.apple.security.network.server`. The existing remote-confirm channel is not biometric approval and must not be reused as one.

An agent that can replace the user-writable CLI, or that runs inside the same user session as the executor, can still skip a check that lives only in that CLI. A Secure Enclave signature does not fix a replaced executor. Putting the check in a privileged helper, or in an App Store binary the agent cannot rewrite, is a different product boundary.

## Decisions still required

These are separate. Choosing one does not choose the other. Neither is implemented.

**Executor protection.** Owning a marker or a lease does not stop another process from running the command. The recommended design is the sandboxed Store app, with that limit left unfinished. Endpoint Security could deny other execs only with a restricted entitlement this team does not have, and it is not requested. Details are in `docs/EXECUTOR_PROTECTION.md`. Nothing there is built.

Mac and iPhone Secure Enclave enroll, sign, revoke, and rotate are implemented and are not human-tested. Unit tests do not call the Secure Enclave. A passing software test is not that hardware path.

**Companion transport.** How an iPhone signature would reach the Mac. Local enrollment does not need this.

1. User-mediated transfer. The person moves the signature onto the Mac. No listening socket. Easy to mishandle, and it is not automatic pairing.
2. Outbound relay. The Mac uses the existing outbound client entitlement. The relay holds no approval keys. That is new infrastructure, a privacy disclosure, and an outage dependency.

A listening server was the rejected Mac App Store entitlement. Do not add `com.apple.security.network.server`, a relay, or a privileged helper until the matching decision is explicit. Do not connect consumption to the lease before the executor decision is accepted. Do not describe biometric approval as shipped.

## Real-device steps, for Yahor

An agent must not run these. Do not pass `--human-invoked`. Do not tap Touch ID or Face ID. Do not grant a permission dialog. Do not type `APPROVE`.

1. Mac diagnostic, after the candidate is built: `RunSpecimenTouchIDDiagnostic preview` with no `--human-invoked` should exit 0 and must not prompt. The binary exercised here was `apps/macos/.build/out/Products/Debug/RunSpecimenTouchIDDiagnostic`: `preview` exited 0, and `enroll` without `--human-invoked` exited 2. Then run `enroll`, `sign`, and `revoke` yourself with `--human-invoked`, `--directory` under `/private/tmp/rs-touchid-diag`, and a `diag-` key id. Confirm the printed request matches the bytes you intend to sign before you authenticate. Cancel one prompt and confirm no signature is printed. There is no rotate command in this diagnostic.
2. iPhone, on a device build of the shipping Observe app, not `RunSpecimenObserveDev`. An unsigned Release iphoneos build is at `/tmp/rs-device-builds/ios-unsigned/Build/Products/Release-iphoneos/RunSpecimenObserve.app` (`com.darashkevich.runspecimen.observe`, version 0.1.0 (1), not signed, not installed). This Mac has no local provisioning profiles, and the agent did not pass `-allowProvisioningUpdates` or register a device. Sign that target for your iPhone in Xcode yourself, then tap Enroll, then Rotate, then Sign with Face ID on a package whose on-screen lines you have read. Edit the package after Show request and confirm Sign stays disabled until you show it again. Revoke and confirm a later sign does not produce a signature. Carry the pairing JSON to the Mac and pin it in Workflows. The status must say the Secure Enclave label was not accepted.
3. A signature from either device is evidence the hardware key signed those bytes after a biometric check. It is not evidence you understood the command, and it does not start a run. Starting a run still requires you to type `APPROVE` yourself, and only after the executor decision is explicit.
