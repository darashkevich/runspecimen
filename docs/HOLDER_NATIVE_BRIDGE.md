# Holder native bridge

This map is the engine interface. It is not installed protection, not a Secure Enclave enrollment, and not a production sign-off.

## Verifier

`native_p256_verify` is a CryptoKit binary the holder loads from `runspecimen/platform/darwin_arm64/`. The pure `py3-none-any` wheel does not carry that Mach-O. `native_p256_verify.provenance.json` beside it pins its SHA-256, the codesign identifier `com.darashkevich.runspecimen.native-p256-verify`, and `not_secure_enclave: true`. `verify_native_p256` checks that pin, runs `codesign --verify --strict`, and executes the binary. It does not invoke `swiftc`. A true result is a signature check, not Touch ID, Face ID, or a Secure Enclave approval. The binary is Darwin arm64. Other platforms fail closed. Trust is a pinned team identifier and designated requirement. A display name that contains "Developer ID" is not that pin. `production_verifier_pin()` is unset.

Ed25519 verification stays on PyNaCl. A missing vetted verifier fails closed. There is no handwritten production verifier.

## Pairing

A P-256 public key is stored only when all of these match:

| Field | Required value |
| --- | --- |
| `key_comparison` | SHA-256 hex of the public key text |
| `provenance.bridge` | `labeled-native-bridge-double-not-hardware` |
| `provenance.public_key` | the same public key |
| `provenance.role` | `mac` or `phone` |
| `provenance.policy` | the policy in force for the pair call |
| `provenance.generation` | the holder generation at pair time |

The stored device record keeps that role, generation, policy, and fingerprint. Later local, companion, and dual challenges include those paired fields plus `holder-device-p256-v1`. Consume and execute label that challenge `device-p256-not-hardware` when every live paired key is P-256. A client `hardware: true` value, or an imported `secure-enclave`, `touch-id`, or `face-id` label, is refused. `installed_protection` refuses the labeled bridge double and a software P-256 key.

The labeled bridge is a test double. The engineering path is `isolated-native-bridge-double-not-hardware`. It enrolls, pairs, and signs for local, companion, and dual when a caller supplies a verifier pin and the binary's team identifier and designated requirement match. `native_signers_connected` reports those paired roles. The isolated double stays `hardware: false` and is refused when installed protection is on. It does not create a Secure Enclave private key and it does not prompt. The production team identifier and designated requirement are not in this tree, so production acceptance stays fail-closed. See [HOLDER_GATE_LEDGER.md](HOLDER_GATE_LEDGER.md).

## Already covered beside this bridge

Cancellation of an uncertain lease, revocation, caller rotation, protocol downgrade, spent-nonce replay, and exact launch binding already fail closed in the holder tests. Those tests do not become hardware acceptance because a P-256 signature verified.

## Human gates this process does not perform

Creating the Secure Enclave private key, Touch ID, Face ID, a paired-phone confirmation, a privileged install, and the final bounded run on the approved path stay with Yahor. The live `/Applications` holder is not repaired from this map.
