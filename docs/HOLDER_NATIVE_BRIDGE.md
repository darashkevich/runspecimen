# Holder native bridge

This map is the engine interface. It is not installed protection, not a Secure Enclave enrollment, and not a production sign-off.

## Verifier

`native_p256_verify` is a CryptoKit binary the holder loads from `runspecimen/platform/darwin_arm64/`. The pure `py3-none-any` wheel does not carry that Mach-O. `native_p256_verify.provenance.json` beside it pins its SHA-256, the codesign identifier `com.darashkevich.runspecimen.native-p256-verify`, and `not_secure_enclave: true`. `verify_native_p256` checks that pin, runs `codesign --verify --strict`, and executes the binary. It does not invoke `swiftc`. A true result is a signature check, not Touch ID, Face ID, or a Secure Enclave approval. The binary is Darwin arm64. Other platforms fail closed. Trust is the confirmed Developer ID holder pin in `production_verifier_pin()`: team `UN6KF8636A` and the exact designated requirement stored there. A display name that contains "Developer ID" is not that pin. The repository binary stays ad-hoc and does not meet the pin. The Store app does not carry it.

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

The stored device record keeps that role, generation, policy, and fingerprint. Later local, companion, and dual challenges include those paired fields plus `holder-device-p256-v1`. Consume and execute label that challenge `device-p256-not-hardware` when every live paired key is P-256. A client `hardware: true` value, or an imported `secure-enclave`, `touch-id`, or `face-id` label, is refused. `installed_protection` refuses the labeled bridge double and a software P-256 key. `begin_human_secure_enclave_enrollment` pairs a role only when the caller passes a `HumanNativeSigner` instance. That class is a software signer, not the native adapter. A dict, environment variable, or config file is not that instance. The no-argument call refuses before any prompt. The software signer stays `hardware: false`, and installed protection refuses it even when the pin matches. `begin_human_operated_native_adapter` is the human-operated adapter. Tests inject a subclass there for local, companion, and dual. Wire JSON, environment, and config cannot select it. A caller hardware label cannot select it. Installed protection does not treat that adapter as the software-key refusal; the pin still authenticates verifier code only. The adapter does not prompt and does not close E2.

The labeled bridge is a test double. The isolated double is a separate unprivileged path. A caller `boundary_double` flag is not the production path. Installed protection refuses that flag even when the verifier pin matches, because a pin checks the verifier binary and does not authorize a software key. Tests that still exercise local, companion, and dual use an in-process `TrustedNativeBoundary`. Wire input, environment, and config cannot construct it. `production_verifier_pin()` is the confirmed Developer ID holder pin. It does not authorize a software key. Signing a copy of the verifier refreshes the provenance beside that copy. The repository binary stays ad-hoc. A display name that contains "Developer ID" is not a pin. See [HOLDER_GATE_LEDGER.md](HOLDER_GATE_LEDGER.md).

## Already covered beside this bridge

Cancellation of an uncertain lease, revocation, caller rotation, protocol downgrade, spent-nonce replay, and exact launch binding already fail closed in the holder tests. Those tests do not become hardware acceptance because a P-256 signature verified.

## Human gates this process does not perform

Creating the Secure Enclave private key, Touch ID, Face ID, a paired-phone confirmation, a privileged install, and the final bounded run on the approved path stay with Yahor. The live `/Applications` holder is not repaired from this map.
