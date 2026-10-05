# Secure Enclave admission

This is not a production sign-off. `run_integration_complete` stays false. Installed protection stays fail-closed. A biometric press does not close this engineering. A pin match authenticates verifier code only. Software doubles stay non-hardware and are refused under installed protection even when the pin matches.

Read on 2026-10-05. The finding for root-daemon Secure Enclave creation is **unsupported**. Compile success and software doubles are not that finding.

## What Apple documents

- [TN3137: On Mac keychain APIs and implementations](https://developer.apple.com/documentation/technotes/tn3137-on-mac-keychains), read 2026-10-05. A `launchd` daemon runs outside a user context and must use the file-based keychain. The data protection keychain is available only to a program in a user context, such as an app or an app extension, and only in a user login context. TN3137 points Secure Enclave protection at the article below.
- [Protecting keys with the Secure Enclave](https://developer.apple.com/documentation/security/protecting-keys-with-the-secure-enclave), read 2026-10-05. Creation uses `kSecAttrTokenIDSecureEnclave` with an access-control object. The documented protection `kSecAttrAccessibleWhenUnlockedThisDeviceOnly` makes the key usable on the device that created it, and only while that device is unlocked. `biometryCurrentSet` adds the current Touch ID or Face ID enrollment.
- [biometryCurrentSet](https://developer.apple.com/documentation/security/secaccesscontrolcreateflags/biometrycurrentset), read 2026-10-05. Touch ID or Face ID must already be enrolled. The item is invalidated when that enrollment changes.
- [Using CryptoKit.SecureEnclave API from a launch daemon](https://developer.apple.com/forums/thread/799625). Apple Developer Technical Support: using the Secure Enclave from a `launchd` daemon is not supported, and Apple does not support access to the data protection keychain or the Secure Enclave from a `launchd` daemon. Storing `dataRepresentation` in the system keychain is not the supported path.
- [Secure Enclave from a daemon, OSStatus -26276](https://developer.apple.com/forums/thread/739462), Apple Developer Technical Support, October 2023. Third-party daemons cannot access the Secure Enclave. The same note points at TN3137 for the data protection keychain.
- [Using Secure Enclave from a Daemon](https://developer.apple.com/forums/thread/115833). `SecKeyGeneratePair` returned an internal error from `launchd` and from a root login session. `com.apple.CoreAuthentication.agent` is a user agent limited to Aqua, LoginWindow, and Background. It is not a daemon.
- [Secure Enclave from an authorization plug-in](https://developer.apple.com/forums/thread/719342). Secure Enclave integration is associated with the data protection keychain. A process outside a user context cannot use that keychain.

No hardware key was created while reading this, and the feasibility harness was not run as root.

## Session questions

| Question | Result from the documents above |
| --- | --- |
| Root `launchd` daemon creates a Secure Enclave key | Unsupported. Third-party daemons cannot access the Secure Enclave. |
| Custody and reload of that key | Unsupported in the daemon. The data protection keychain is the Secure Enclave's context, and a daemon cannot use it. A system-keychain copy of the key bytes is the path DTS told developers not to take. |
| Human biometric prompt from that daemon | Unsupported. Biometry is an access-control constraint evaluated for a user, through a user authentication agent, while the device is unlocked. |
| Cancellation | A user-session authentication context can be cancelled. A root daemon has no such session, so there is no supported prompt to cancel. |
| Locked session | The documented access class refuses the key while the device is locked. |
| No console session | The data protection keychain follows the caller's user login context. A daemon has none. |
| Fast user switching | The keychain is the logged-in user's. A daemon does not join the switched-in user's session. |
| Rotation, revocation, and restart | Not available, because the daemon cannot create the key whose generation it would rotate. Software custody remains non-hardware and is refused under installed protection. |

## Bounded alternatives

1. Keep installed admission fail-closed. This matches the platform limit. It is the behavior of this tree.
2. A later product decision could move creation into a per-user Aqua app or agent, where TN3137 allows the data protection keychain. That is not a root daemon, it does not qualify Developer ID guarantee (2), and a same-user process can still create its own key. It needs its own explicit decision.
3. Do not store a Secure Enclave data representation in the system keychain to imitate daemon custody.

## Identities

Verifier, confirmed. Team `UN6KF8636A`. Identifier `com.darashkevich.runspecimen.native-p256-verify`. Designated requirement `identifier "com.darashkevich.runspecimen.native-p256-verify" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ and certificate leaf[field.1.2.840.113635.100.6.1.13] /* exists */ and certificate leaf[subject.OU] = UN6KF8636A`. `production_verifier_pin()` returns that pair and nothing else. A pin match authenticates verifier code only.

Daemon, unconfirmed. The holder app plist at `apps/holder/Resources/Info.plist` already uses `com.darashkevich.runspecimen.holder`. `apps/holder/Scripts/build_install_holder.sh` signs that binary and `RunSpecimenHolderDaemon` with `codesign --force --sign -`, which is ad-hoc. There is no confirmed Developer ID designated requirement for the daemon. That plist identifier is not D1 and is not authorized as an admission identity. It is not written into `production_verifier_pin()`.

## Why a same-user software key cannot be substituted

A same-user process can create a software P-256 key, or its own Secure Enclave key, and hand the public key to the holder. Possession of the private key lets that process produce a signature the verifier accepts for that public key. The signature proves possession. It does not prove that protected holder state created the key, and it does not prove the key is hardware.

The holder could attest creation only by being the process that called the Secure Enclave, checking its own code identity before the call, and atomically storing the public key that call returned, together with the fingerprint, generation, and access policy. A holder signature over a caller-supplied public key, origin, mailbox token, or hardware flag attests only that the holder signed what it was given. That is not creation.

Because a root daemon cannot make the Secure Enclave call, this holder cannot attest that creation. Installed protection therefore keeps refusing exact-run admission, including when the verifier pin matches. `run_integration_complete` stays false.

## Feasibility harness

`apps/holder/Sources/DaemonKeyFeasibility/DaemonKeyFeasibility.swift` is an isolated target. It is not installed, not registered with `SMAppService` or `launchd`, and not executed as root. `unattendedAssessment()` returns `unsupported` and does not call `SecureEnclave.P256.Signing.PrivateKey` or `SecAccessControlCreateWithFlags`. Those calls sit in `createKeyForExplicitHumanHandoff` and run only after `acknowledgePrivilegedHardwareTrial` is true. The unit test calls the unattended path and the refused handoff and checks that the callsite counter stays at zero.

## Human handoff, not performed

Do not run these steps under the current approval. A privileged or hardware trial needs a separate explicit handoff. This prototype does not install, register, or repair a daemon.

1. Stay in an unlocked Aqua session as the ordinary user. Do not use `sudo`, `launchd`, `SMAppService`, or a root shell.
2. Build only the feasibility target from this tree into a temporary directory. Do not copy it to `/Applications`.
3. Call `DaemonKeyCreationHarness.unattendedAssessment()` and record that the finding is `unsupported` and the callsite counter is zero.
4. Only if the separate handoff says to create a key, call `createKeyForExplicitHumanHandoff(acknowledgePrivilegedHardwareTrial: true)` from that user session. Record whether a Touch ID, Face ID, or password prompt appeared, the thrown error, and that no daemon was registered.
5. Repeat the same call, still only under that handoff, with the screen locked, with no console session, and during fast user switching. Record each refusal. Do not treat a prompt in the Aqua session as proof that a root daemon can do the same.
6. Do not point the daemon's code signature at the verifier designated requirement. Do not admit the resulting public key into installed protection.

## Decision

Do not authorize a root-owned daemon as the Secure Enclave creator. Apple's current documents say that process cannot create or reload the key or present the biometric prompt. Installed admission stays closed. A different per-user design is a new decision, not this prototype.
