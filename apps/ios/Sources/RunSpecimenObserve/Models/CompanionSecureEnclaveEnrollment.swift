import CryptoKit
import Foundation
import LocalAuthentication
import Security

public enum CompanionHardwareRefusal: Error, Equatable {
    case humanTapRequired
    case missing
    case malformed(String)
}

/// Public pairing material for one iPhone Secure Enclave key.
///
/// The private key stays in the Secure Enclave. This record is what a person
/// can carry to the Mac. It does not open a socket.
public struct CompanionPairingRecord: Equatable {
    public var keyID: String
    public var publicKey: Data
    public var role: String
    public var backend: String
    public var provenance: String
    public var state: String
    public var generation: Int

    public var allowsExecution: Bool {
        EnrollmentIdentity.allowsExecution(
            role: role,
            backend: backend,
            provenance: provenance,
            state: state
        )
    }
}

/// Face ID signing for a carried RSBA2 request.
///
/// `humanTap` false returns before any Secure Enclave, LocalAuthentication, or
/// keychain call. Unit tests and agents must pass false. A person taps the
/// button in the app, which is the only caller that passes true.
public enum CompanionSecureEnclaveEnrollment {
    public static let keychainService = "com.darashkevich.runspecimen.observe.biometric"
    public static let active = "active"
    public static let revoked = "revoked"

    public static func enroll(keyID: String, directory: URL, humanTap: Bool) throws -> CompanionPairingRecord {
        guard humanTap else { throw CompanionHardwareRefusal.humanTapRequired }
        return try createEnclaveKey(keyID: keyID, directory: directory)
    }

    public static func sign(fields: RSBA2Package.Fields, directory: URL, humanTap: Bool) throws -> Data {
        guard humanTap else { throw CompanionHardwareRefusal.humanTapRequired }
        return try signWithEnclave(fields: fields, directory: directory)
    }

    public static func revoke(keyID: String, directory: URL, humanTap: Bool) throws {
        guard humanTap else { throw CompanionHardwareRefusal.humanTapRequired }
        try revokeEnclaveKey(keyID: keyID, directory: directory)
    }

    /// Reads the public pairing file. It does not call the Secure Enclave.
    public static func carriedPairing(keyID: String, directory: URL) throws -> Data {
        try json(load(keyID: keyID, directory: directory))
    }

    private static func createEnclaveKey(keyID: String, directory: URL) throws -> CompanionPairingRecord {
        try validateKeyID(keyID)
        if (try? load(keyID: keyID, directory: directory)) != nil {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        let context = LAContext()
        context.localizedFallbackTitle = ""
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            accessControl: try accessControl(),
            authenticationContext: context
        )
        try saveBlob(key.dataRepresentation, keyID: keyID)
        let record = CompanionPairingRecord(
            keyID: keyID,
            publicKey: key.publicKey.x963Representation,
            role: EnrollmentIdentity.roleCompanion,
            backend: EnrollmentIdentity.backendSecureEnclave,
            provenance: EnrollmentIdentity.provenanceProduction,
            state: active,
            generation: 1
        )
        do {
            try save(record, directory: directory)
        } catch {
            try? deleteBlob(keyID: keyID)
            throw error
        }
        return record
    }

    private static func signWithEnclave(fields: RSBA2Package.Fields, directory: URL) throws -> Data {
        let record = try load(keyID: fields.companionKeyID, directory: directory)
        guard record.state == active, record.allowsExecution else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        guard record.generation == fields.companionGeneration else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        guard fields.policy == "companion" || fields.policy == "dual" else {
            throw CompanionHardwareRefusal.malformed("policy")
        }
        let blob = try loadBlob(keyID: record.keyID)
        let context = LAContext()
        context.localizedFallbackTitle = ""
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            dataRepresentation: blob,
            authenticationContext: context
        )
        guard key.publicKey.x963Representation == record.publicKey else {
            throw CompanionHardwareRefusal.malformed("enrollment")
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

    private static func revokeEnclaveKey(keyID: String, directory: URL) throws {
        var record = try load(keyID: keyID, directory: directory)
        guard record.backend == EnrollmentIdentity.backendSecureEnclave else {
            throw CompanionHardwareRefusal.malformed("backend")
        }
        guard record.state == active else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        try deleteBlob(keyID: keyID)
        record.state = revoked
        record.generation += 1
        try save(record, directory: directory)
    }

    private static func validateKeyID(_ keyID: String) throws {
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
        guard (1...64).contains(keyID.count), keyID.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
    }

    private static func fileURL(keyID: String, directory: URL) -> URL {
        directory.appendingPathComponent(keyID + ".pairing.json")
    }

    private static func save(_ record: CompanionPairingRecord, directory: URL) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let data = try json(record)
        let destination = fileURL(keyID: record.keyID, directory: directory)
        let temporary = directory.appendingPathComponent("." + record.keyID + ".pairing.json.tmp")
        try data.write(to: temporary, options: .atomic)
        if FileManager.default.fileExists(atPath: destination.path) {
            _ = try FileManager.default.replaceItemAt(destination, withItemAt: temporary)
        } else {
            try FileManager.default.moveItem(at: temporary, to: destination)
        }
    }

    private static func load(keyID: String, directory: URL) throws -> CompanionPairingRecord {
        let url = fileURL(keyID: keyID, directory: directory)
        guard let data = try? Data(contentsOf: url),
              let object = try JSONSerialization.jsonObject(with: data) as? [String: String] else {
            throw CompanionHardwareRefusal.missing
        }
        guard object["key_id"] == keyID,
              let publicKey = object["public_key_x963_b64"].flatMap({ Data(base64Encoded: $0) }),
              publicKey.count == 65,
              let role = object["role"],
              let backend = object["backend"],
              let provenance = object["provenance"],
              let state = object["state"],
              let generationText = object["generation"],
              let generation = Int(generationText),
              generation > 0,
              String(generation) == generationText,
              state == active || state == revoked else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        let record = CompanionPairingRecord(
            keyID: keyID,
            publicKey: publicKey,
            role: role,
            backend: backend,
            provenance: provenance,
            state: state,
            generation: generation
        )
        guard EnrollmentIdentity.isRecognized(role: role, backend: backend, provenance: provenance) else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        return record
    }

    private static func json(_ record: CompanionPairingRecord) throws -> Data {
        let object: [String: String] = [
            "key_id": record.keyID,
            "public_key_x963_b64": record.publicKey.base64EncodedString(),
            "role": record.role,
            "backend": record.backend,
            "provenance": record.provenance,
            "state": record.state,
            "generation": String(record.generation),
        ]
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    private static func accessControl() throws -> SecAccessControl {
        var cfError: Unmanaged<CFError>?
        guard let access = SecAccessControlCreateWithFlags(
            nil,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            [.privateKeyUsage, .biometryCurrentSet],
            &cfError
        ) else {
            throw CompanionHardwareRefusal.malformed("access control")
        }
        return access
    }

    private static func saveBlob(_ data: Data, keyID: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keyID,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        ]
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw CompanionHardwareRefusal.malformed("keychain")
        }
    }

    private static func loadBlob(keyID: String) throws -> Data {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keyID,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else {
            throw CompanionHardwareRefusal.malformed("keychain")
        }
        return data
    }

    private static func deleteBlob(keyID: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keyID,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw CompanionHardwareRefusal.malformed("keychain")
        }
    }
}
