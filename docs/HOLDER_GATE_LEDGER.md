# Holder gate ledger

This ledger separates engineering that is in the tree from actions a person still has to perform. The bridge implementation is engineering. It is not a wait on Yahor. This note is not a production sign-off and it is not Store parity. Approved Mac App Store **0.1.4 (9)** is a different package. The Store app stays guarantee (1), a typed phrase. The Developer ID holder is guarantee (2). The Store app does not have guarantee (2).

## Engineering in this tree

| Gate | What the code does |
| --- | --- |
| Verifier placement | The Darwin arm64 `native_p256_verify` binary is loaded from `runspecimen/platform/darwin_arm64/`. The `py3-none-any` wheel does not carry that Mach-O. Other platforms fail closed. |
| Verifier identity | A signature is accepted only when the binary's `TeamIdentifier` is `UN6KF8636A` and the designated requirement equals the confirmed string in `production_verifier_pin()`, and `codesign --verify --strict` succeeds. A display name that contains "Developer ID" is not that pin. The repository ad-hoc binary does not meet it. The Store app does not carry this pin. |
| Isolated double | `isolated-native-bridge-double-not-hardware` enrolls, pairs, and signs for local, companion, and dual when the test pin matches and installed protection is off. Those runs stay `hardware: false`. Installed protection refuses the double. |
| Production boundary | A caller `boundary_double` flag is refused under installed protection, including when the verifier pin matches. The software double runs only through an in-process `TrustedNativeBoundary` that wire input, environment, and config cannot set. That record stays `hardware: false` and is not production enrollment. |
| Labeled test double | `labeled-native-bridge-double-not-hardware` remains a separate unprivileged double. It is not the isolated path and it is not installed protection. |
| Production hardware | `allowsProductionEnrollment` is false for a caller label and for the software double, including under installed protection with a pin and a verifier. It is true only for the Secure Enclave human-step origin when a pin and verifier are connected. `beginHumanSecureEnclaveEnrollment` does not call `SecureEnclave.P256.Signing.PrivateKey` and does not prompt. Yahor confirmed the holder pin. That confirmation is not a biometric and not a production sign-off. |
| Mac app control | `IsolatedNativeEnrollment.complete` records a local or companion engineering signer. `ProductionNativeBridgeGate` reports those signers and keeps hardware enrollment closed. |

Yahor confirmed the Developer ID holder pin: team `UN6KF8636A` and designated requirement `identifier "com.darashkevich.runspecimen.native-p256-verify" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ and certificate leaf[field.1.2.840.113635.100.6.1.13] /* exists */ and certificate leaf[subject.OU] = UN6KF8636A`. The repository verifier stays ad-hoc and does not satisfy that requirement. This confirmation is not a production sign-off.

## Human acceptance steps, not run by this agent

1. Biometric enrollment. On the signed holder, create the Mac key with `SecureEnclave.P256.Signing.PrivateKey`. That raises Touch ID, Face ID, or a password prompt.
2. Fingerprint confirmation. Compare the Mac public-key fingerprint, then the paired phone's fingerprint, before the holder stores either key.
3. Privileged install. Install the holder only through the privileged path. The live `/Applications/RunSpecimen Holder.app` is not repaired from this ledger.
4. One real bounded run after those enrollments. Do not type APPROVE and do not pass `--human-invoked` from automation.

## Packaging

The pure wheel stays `py3-none-any` and must not contain `native_p256_verify`. The holder loads the helper from `platform/darwin_arm64/` in the runtime tree. A hash file next to an ad-hoc signature does not establish a trusted publisher. Trust is the pinned team identifier plus the designated requirement.
