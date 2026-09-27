# Biometric approval — decision required

Status: **not implemented**. This note is the threat model and the choice that has to be made before any signing code, entitlement, or companion transport is added. It is not an approval feature.

## What a signature would mean

A local biometric approval is evidence that a key stored in the Mac Secure Enclave signed one canonical request, and that using the key required a fresh biometric check. A companion approval is evidence that a different key, stored in the paired iPhone Secure Enclave, signed that same request after the phone showed the request and the person approved it there.

Neither signature proves that no model was involved, that the person understood the command, or that the person was at the Mac when the phone signed.

## Request

Each signature is over one versioned byte string, not over an authentication-success Boolean. The request includes a version, the Mac and workspace identity, campaign and run IDs, the contract and input fingerprints, the execution bounds, the policy (`local`, `companion`, or `dual`), a nonce, an expiry, and the key identifier. Local-only policy rejects a companion signature. Dual policy requires both signatures over that same request. A relay that carries bytes does not get a key and cannot approve.

The executor rechecks the request against the live contract immediately before execution and consumes the approval in the same state transition as the workspace lease. A restart, a second entry point, or a signature after expiry does not run the command again.

## What this Mac can enforce today

TTY `approve` checks that stdin and stdout are terminals and that the line is exactly `APPROVE`. That does not identify a person. The Mac app does not type that phrase. Store builds do not include `com.apple.security.network.server`. The existing remote-confirm channel is not biometric approval and must not be reused as one.

An agent that can replace the user-writable CLI, or that runs inside the same user session as the executor, can still skip a check that lives only in that CLI. A Secure Enclave signature does not fix a replaced executor. Putting the check in a privileged helper, or in an App Store binary the agent cannot rewrite, is a different product boundary.

## Decision

Companion approval needs a path from the iPhone to the Mac. The rejected Mac App Store entitlement was a listening server. The choices are:

1. **Local biometric only.** Mac Secure Enclave key, fresh biometrics, no phone and no new network entitlement. Companion and dual policies stay unavailable. This can be built later without a relay.
2. **User-mediated transfer.** The phone signs, and the person moves the signature onto the Mac (share sheet or a file). No listening socket. Easy to mishandle, and it is not an automatic pairing.
3. **Outbound relay.** The Mac uses the existing outbound client entitlement to reach a service the phone also reaches. That service must not hold approval keys. It is new infrastructure, a privacy disclosure, and an outage dependency.
4. **Privileged local helper.** A helper the agent cannot replace enforces the signature. That is a privileged component and a material change to the sandbox story.

No option is selected. Do not add a network server entitlement, a relay, or a privileged helper until one of these is chosen. Do not describe biometric approval as shipped.
