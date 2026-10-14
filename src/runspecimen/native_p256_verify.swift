import CryptoKit
import Foundation

// CryptoKit verifies the signature bytes. This is not a handwritten verifier
// and a valid result is not a Secure Enclave, Touch ID, or Face ID approval.
let arguments = CommandLine.arguments
if arguments.count != 4 {
    fputs("usage: native_p256_verify public_x963_b64 signature_raw_b64 message_path\n", stderr)
    exit(2)
}
guard let publicKeyData = Data(base64Encoded: arguments[1]),
      let signatureData = Data(base64Encoded: arguments[2]) else {
    exit(1)
}
let message: Data
do {
    message = try Data(contentsOf: URL(fileURLWithPath: arguments[3]))
} catch {
    exit(1)
}
do {
    let key = try P256.Signing.PublicKey(x963Representation: publicKeyData)
    let signature = try P256.Signing.ECDSASignature(rawRepresentation: signatureData)
    if key.isValidSignature(signature, for: message) {
        exit(0)
    }
} catch {
    exit(1)
}
exit(1)
