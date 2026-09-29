import CryptoKit
import Foundation
import LocalAuthentication
import Security

public enum CompanionHardwareRefusal: Error, Equatable {
    /// Automation called the refusal entry. This is not evidence of a person.
    case automationRefused
    case missing
    case malformed(String)
    case staleRequest
    case alreadyEnrolled
}

/// Public pairing material for one iPhone Secure Enclave key.
///
/// The private key stays in the Secure Enclave. This record is what a person
/// can carry to the Mac. It does not open a socket, and its backend string is
/// not proof on the Mac.
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

    var snapshot: CompanionEnrollmentSnapshot {
        CompanionEnrollmentSnapshot(
            keyID: keyID,
            publicKey: publicKey,
            role: role,
            backend: backend,
            provenance: provenance,
            state: state,
            generation: generation
        )
    }
}

/// Face ID signing for a carried RSBA2 request.
///
/// The button in the app calls the Secure Enclave methods directly. Tests call
/// `automationRefused()` and the file-only helpers. A Boolean at the call site
/// is not hardware authentication.
public enum CompanionSecureEnclaveEnrollment {
    public static let keychainService = "com.darashkevich.runspecimen.observe.biometric"
    public static let active = "active"
    public static let revoked = "revoked"
    static var clock: () -> Int = { Int(Date().timeIntervalSince1970) }

    public static func automationRefused() throws -> Never {
        throw CompanionHardwareRefusal.automationRefused
    }

    public static func enroll(keyID: String, directory: URL) throws -> CompanionPairingRecord {
        try validateKeyID(keyID)
        return try withLock(directory) {
            if let existing = try? load(keyID: keyID, directory: directory), existing.state == active {
                throw CompanionHardwareRefusal.alreadyEnrolled
            }
            let existing = try? load(keyID: keyID, directory: directory)
            let publicKey = try createEnclaveKey(keyID: keyID)
            let record = CompanionPairingRecord(
                keyID: keyID,
                publicKey: publicKey,
                role: EnrollmentIdentity.roleCompanion,
                backend: EnrollmentIdentity.backendSecureEnclave,
                provenance: EnrollmentIdentity.provenanceProduction,
                state: active,
                generation: existing?.generation ?? 1
            )
            try storeEnrollment(record, directory: directory) {
                try? deleteBlob(keyID: keyID)
            }
            return record
        }
    }

    public static func signDisplayed(
        packageText: String,
        displayed: RSBA2Package.Fields,
        directory: URL
    ) throws -> Data {
        guard let data = packageText.data(using: .utf8) else {
            throw CompanionHardwareRefusal.malformed("package")
        }
        let fresh: RSBA2Package.Fields
        do {
            fresh = try RSBA2Package.parse(data)
        } catch {
            throw CompanionHardwareRefusal.malformed("package")
        }
        guard fresh == displayed else {
            throw CompanionHardwareRefusal.staleRequest
        }
        let bytes = try canonical(fresh)
        return try sign(fields: fresh, displayedCanonical: bytes, directory: directory)
    }

    public static func revoke(keyID: String, directory: URL) throws {
        try validateKeyID(keyID)
        try withLock(directory) {
            let record = try load(keyID: keyID, directory: directory)
            _ = try persistRevocation(record, directory: directory) { _ in
                try deleteBlob(keyID: keyID)
            }
        }
    }

    /// Enrolls the new key first. If that fails, the old key stays. If revoking
    /// the old key fails, the new key is left in place and the error says so.
    public static func rotate(from oldKeyID: String, to newKeyID: String, directory: URL) throws -> CompanionPairingRecord {
        try validateKeyID(oldKeyID)
        try validateKeyID(newKeyID)
        guard oldKeyID != newKeyID else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        let created = try enroll(keyID: newKeyID, directory: directory)
        do {
            try revoke(keyID: oldKeyID, directory: directory)
        } catch {
            throw CompanionHardwareRefusal.malformed("rotation-incomplete")
        }
        return created
    }

    public static func carriedPairing(keyID: String, directory: URL) throws -> Data {
        try validateKeyID(keyID)
        return try json(load(keyID: keyID, directory: directory))
    }

    public static func inspect(keyID: String, directory: URL) throws -> CompanionPairingRecord {
        try validateKeyID(keyID)
        return try load(keyID: keyID, directory: directory)
    }

    /// Writes the revoked record before deleting the key. A failed delete leaves
    /// a revoked record so a later sign fails closed, and a retry deletes the
    /// key without increasing the generation again.
    static func persistRevocation(
        _ record: CompanionPairingRecord,
        directory: URL,
        deleteKey: (Data) throws -> Void
    ) throws -> CompanionPairingRecord {
        if record.state == revoked {
            do {
                try deleteKey(record.publicKey)
            } catch {
                throw CompanionHardwareRefusal.malformed("keychain-cleanup")
            }
            return record
        }
        guard record.state == active else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        var revokedRecord = record
        revokedRecord.state = revoked
        revokedRecord.generation += 1
        try save(revokedRecord, directory: directory)
        do {
            try deleteKey(record.publicKey)
        } catch {
            throw CompanionHardwareRefusal.malformed("keychain-cleanup")
        }
        return revokedRecord
    }

    static func storeEnrollment(
        _ record: CompanionPairingRecord,
        directory: URL,
        cleanup: () -> Void
    ) throws {
        do {
            try save(record, directory: directory)
        } catch {
            cleanup()
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
    }

    static func signatureIfStillValid(
        produced: Data,
        before: CompanionEnrollmentSnapshot,
        after: CompanionEnrollmentSnapshot,
        expiryUnix: Int,
        now: Int
    ) throws -> Data {
        do {
            try CompanionPostAuthentication.accept(
                before: before,
                after: after,
                expiryUnix: expiryUnix,
                now: now
            )
        } catch let error as RSBA2Package.ParseFailure {
            if case .malformed("expiry_unix") = error {
                throw CompanionHardwareRefusal.malformed("expiry_unix")
            }
            throw CompanionHardwareRefusal.malformed("enrollment")
        } catch {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        return produced
    }

    private static func sign(
        fields: RSBA2Package.Fields,
        displayedCanonical: Data,
        directory: URL
    ) throws -> Data {
        try validateKeyID(fields.companionKeyID)
        guard fields.policy == "companion" || fields.policy == "dual" else {
            throw CompanionHardwareRefusal.malformed("policy")
        }
        let bytes = try canonical(fields)
        guard bytes == displayedCanonical else {
            throw CompanionHardwareRefusal.staleRequest
        }
        let before = try withLock(directory) {
            let record = try load(keyID: fields.companionKeyID, directory: directory)
            guard record.allowsExecution else {
                throw CompanionHardwareRefusal.malformed("enrollment")
            }
            guard record.generation == fields.companionGeneration else {
                throw CompanionHardwareRefusal.malformed("enrollment")
            }
            guard fields.expiryUnix > clock() else {
                throw CompanionHardwareRefusal.malformed("expiry_unix")
            }
            return record
        }
        let produced = try signWithEnclave(keyID: before.keyID, publicKey: before.publicKey, bytes: bytes)
        let after = try withLock(directory) {
            try load(keyID: fields.companionKeyID, directory: directory)
        }
        return try signatureIfStillValid(
            produced: produced,
            before: before.snapshot,
            after: after.snapshot,
            expiryUnix: fields.expiryUnix,
            now: clock()
        )
    }

    private static func canonical(_ fields: RSBA2Package.Fields) throws -> Data {
        try RSBA2Package.canonicalBytes(
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
    }

    static func withLock<T>(_ directory: URL, _ body: () throws -> T) throws -> T {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let fd = open(directory.appendingPathComponent("enrollment.lock").path, O_CREAT | O_RDWR, 0o600)
        guard fd >= 0 else { throw CompanionHardwareRefusal.malformed("lock") }
        defer { close(fd) }
        guard flock(fd, LOCK_EX) == 0 else { throw CompanionHardwareRefusal.malformed("lock") }
        defer { _ = flock(fd, LOCK_UN) }
        return try body()
    }

    private static func createEnclaveKey(keyID: String) throws -> Data {
        let context = LAContext()
        context.localizedFallbackTitle = ""
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            accessControl: try accessControl(),
            authenticationContext: context
        )
        try saveBlob(key.dataRepresentation, keyID: keyID)
        return key.publicKey.x963Representation
    }

    private static func signWithEnclave(keyID: String, publicKey: Data, bytes: Data) throws -> Data {
        let blob = try loadBlob(keyID: keyID)
        let context = LAContext()
        context.localizedFallbackTitle = ""
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            dataRepresentation: blob,
            authenticationContext: context
        )
        guard key.publicKey.x963Representation == publicKey else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        return try key.signature(for: bytes).rawRepresentation
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
        try validateKeyID(record.keyID)
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
        try validateKeyID(keyID)
        let url = fileURL(keyID: keyID, directory: directory)
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch let error as NSError {
            if error.domain == NSCocoaErrorDomain && error.code == NSFileReadNoSuchFileError {
                throw CompanionHardwareRefusal.missing
            }
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: String] else {
            throw CompanionHardwareRefusal.malformed("enrollment")
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
        guard EnrollmentIdentity.isRecognized(role: role, backend: backend, provenance: provenance) else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        return CompanionPairingRecord(
            keyID: keyID,
            publicKey: publicKey,
            role: role,
            backend: backend,
            provenance: provenance,
            state: state,
            generation: generation
        )
    }

    private static func json(_ record: CompanionPairingRecord) throws -> Data {
        let object: [String: String] = [
            "backend": record.backend,
            "generation": String(record.generation),
            "key_id": record.keyID,
            "provenance": record.provenance,
            "public_key_x963_b64": record.publicKey.base64EncodedString(),
            "role": record.role,
            "state": record.state,
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
