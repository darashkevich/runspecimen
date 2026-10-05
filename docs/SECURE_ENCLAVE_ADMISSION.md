# Secure Enclave admission design

This design is not authorized and is not implemented. `run_integration_complete` stays false. A biometric press does not close this engineering. A pin match authenticates verifier code only. Software doubles stay non-hardware and are refused under installed protection even when the pin matches.

A holder-signed assertion is not enough. The holder can assert a fingerprint only when the holder process itself created that Secure Enclave key and recorded the public key before any caller could supply it. A Mac-session signature proves possession of the pinned key. It does not prove that protected holder state committed that key. An origin string, a mailbox token, a caller flag, and the D1 pin are not that proof.

## Trusted component

The only component that may create a key for installed admission is the root-owned Developer ID holder daemon, not the Mac App Store app and not a same-user GUI. The daemon must create `SecureEnclave.P256.Signing.PrivateKey` inside its own process. It must refuse a caller-supplied public key, key blob, origin label, or hardware flag on that path.

## Privileges and code identity

The daemon binary and its state directory are root-owned. The state directory is mode 0700. Before creating a key, the daemon checks its own code signature against designated requirement `identifier "com.darashkevich.runspecimen.native-p256-verify" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ and certificate leaf[field.1.2.840.113635.100.6.1.13] /* exists */ and certificate leaf[subject.OU] = UN6KF8636A`. Team `UN6KF8636A`. Identifier `com.darashkevich.runspecimen.native-p256-verify`. A same-user process talks to that daemon only over the authenticated holder socket. The socket checks the response MAC, protocol, and caller id. It does not accept a key for admission.

## Binding

Key creation, fingerprint, generation, and access policy `biometry-current-set-on-each-signature` are one atomic state commit inside the daemon. The public key is the one the Secure Enclave call returned. The receipt is that state record, bound to the fingerprint. It is not a signature over a caller-supplied origin. If the commit fails, the previous usable key stays. Rotation and revocation bump generation in the same transaction and drop pending receipts. There is no export of the private key. Recovery is a new enrollment and a new generation. Old signatures do not authorize the new generation.

## What this still does not prove

A same-user process can create its own Secure Enclave key. That key is not admitted, because the daemon did not create it. Administrator or root can replace the daemon or its state directory. This design is not a defense against root. A biometric prompt proves the person authenticated to the key the daemon created. It does not prove the daemon binary is the reviewed one if root replaced it.

## Decision, unconfirmed

Yes or no: authorize that root-owned Developer ID holder daemon, and only that daemon, as the component that may create the Secure Enclave key for installed admission. Until that daemon exists and creates the key itself, installed protection keeps refusing exact-run admission. This document does not grant that authorization.
