# Holder gate ledger

This ledger separates engineering that is in the tree from actions a person still has to perform. It is not a production sign-off and it is not Store parity. Approved Mac App Store **0.1.4 (9)** is a different package.

## Engineering in this tree

| Gate | What the code does |
| --- | --- |
| Packaged CryptoKit check | `native_p256_verify` is a Darwin arm64 Mach-O inside the `py3-none-any` wheel. Other platforms fail closed. `codesign --verify --strict` checks the ad-hoc signature. The SHA-256 pin is in `native_p256_verify.provenance.json`. |
| Publisher identity | `packaged_verifier_publisher()` reads `codesign -dvvv`. Ad-hoc is not Developer ID. `publisher_trusted` stays false. |
| Production bridge | `native-production-bridge` refuses enrollment while the verifier is ad-hoc and the local and companion signers are disconnected. It does not call Secure Enclave APIs. |
| Labeled test double | `labeled-native-bridge-double-not-hardware` can pair and run local, companion, and dual only when installed protection is off. Those runs stay `hardware: false`. Installed protection does not accept that double. |
| Mac app control | `ProductionNativeBridgeGate` shows that pinning a carried key is not production enrollment. It does not create a key. |

## Human steps, not run by this agent

1. Developer ID-sign and notarize the verifier, then replace the ad-hoc binary. Until that identity is present, production enrollment stays refused.
2. On the signed holder, enroll the Mac key. That call is `SecureEnclave.P256.Signing.PrivateKey` and raises Touch ID or a password prompt. This agent does not make that call.
3. Confirm the displayed public-key fingerprint on the Mac before the holder stores it.
4. Enroll the companion on the paired phone and confirm that fingerprint. This agent does not show a paired-phone prompt.
5. Install the holder only through the privileged path Yahor chooses. The live `/Applications/RunSpecimen Holder.app` is not repaired from this ledger.
6. Run one real bounded contract after those enrollments. This agent does not type APPROVE and does not pass `--human-invoked`.

## Packaging

The wheel is `py3-none-any` and also contains one `darwin-arm64` executable. That combination does not make the binary a universal or a signed update channel. Linux and non-arm64 Darwin fail closed. A hash file next to an ad-hoc signature does not establish a trusted publisher against a writable tree.
