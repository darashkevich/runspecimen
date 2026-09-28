import CryptoKit
import Foundation

/// A software P-256 key used only while developing the carried-package flow.
///
/// This is not a Secure Enclave key and it does not call Face ID. A signature
/// from this key is not a Mac approval and it is not physical presence.
struct DevelopmentPairingRecord: Equatable {
    var keyID: String
    var generation: Int
    var publicKeyX963B64: String
    static let backend = "software-development"
}

enum DevelopmentCompanionSigner {
    static func makeKey() -> P256.Signing.PrivateKey {
        P256.Signing.PrivateKey()
    }

    static func record(keyID: String, generation: Int, key: P256.Signing.PrivateKey) -> DevelopmentPairingRecord {
        DevelopmentPairingRecord(
            keyID: keyID,
            generation: generation,
            publicKeyX963B64: key.publicKey.x963Representation.base64EncodedString()
        )
    }

    /// Signs the shared RSBA2 bytes. Refuses a local-only policy and a package
    /// whose companion key id or generation does not match this development record.
    static func sign(fields: RSBA2Package.Fields, record: DevelopmentPairingRecord, key: P256.Signing.PrivateKey) throws -> Data {
        guard fields.policy == "companion" || fields.policy == "dual" else {
            throw RSBA2Package.ParseFailure.malformed("policy")
        }
        guard fields.companionKeyID == record.keyID, fields.companionGeneration == record.generation else {
            throw RSBA2Package.ParseFailure.malformed("enrollment")
        }
        guard key.publicKey.x963Representation.base64EncodedString() == record.publicKeyX963B64 else {
            throw RSBA2Package.ParseFailure.malformed("enrollment")
        }
        let bytes = try RSBA2Package.canonicalBytes(
            policy: fields.policy,
            macID: fields.macID,
            workspaceID: fields.workspaceID,
            runID: fields.runID,
            contractSHA256: fields.contractSHA256,
            inputsSHA256: fields.inputsSHA256,
            bounds: fields.bounds,
            nonce: fields.nonce,
            expiryUnix: fields.expiryUnix,
            localKeyID: fields.localKeyID,
            companionKeyID: fields.companionKeyID,
            localGeneration: fields.localGeneration,
            companionGeneration: fields.companionGeneration
        )
        return try key.signature(for: bytes).rawRepresentation
    }
}
