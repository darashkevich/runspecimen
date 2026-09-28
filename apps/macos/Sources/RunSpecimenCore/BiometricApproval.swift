import CryptoKit
import Darwin
import Foundation
import LocalAuthentication
import Security

/// Failure of a local biometric approval check.
///
/// A software signature in tests is not a biometric grant. Nothing in this
/// type treats an authentication-success Boolean as permission to run.
public enum BiometricApprovalError: Error, Equatable, CustomStringConvertible, Sendable {
    case malformed(String)
    case expired
    case tampered
    case replay
    case mismatch
    case revoked
    case unsupportedPolicy

    public var description: String {
        switch self {
        case .malformed(let field):
            return "The biometric approval request is malformed (\(field))."
        case .expired:
            return "The biometric approval expired."
        case .tampered:
            return "The biometric approval signature does not match the pinned key."
        case .replay:
            return "The biometric approval was already consumed."
        case .mismatch:
            return "The biometric approval is not for this run."
        case .revoked:
            return "The biometric key is revoked. A new enrollment is required."
        case .unsupportedPolicy:
            return "Only a local biometric policy can be consumed. Companion and dual approval are not available."
        }
    }
}

/// One versioned request. The signature covers these fields and nothing else.
public struct BiometricApprovalRequest: Equatable, Sendable {
    public static let localPolicy = "local"
    public static let version = "RSBA1"

    public var macID: String
    public var workspaceID: String
    public var runID: String
    public var contractSHA256: String
    public var inputsSHA256: String
    public var bounds: String
    public var nonce: String
    public var expiryUnix: Int
    public var keyID: String

    public init(
        macID: String,
        workspaceID: String,
        runID: String,
        contractSHA256: String,
        inputsSHA256: String,
        bounds: String,
        nonce: String,
        expiryUnix: Int,
        keyID: String
    ) {
        self.macID = macID
        self.workspaceID = workspaceID
        self.runID = runID
        self.contractSHA256 = contractSHA256
        self.inputsSHA256 = inputsSHA256
        self.bounds = bounds
        self.nonce = nonce
        self.expiryUnix = expiryUnix
        self.keyID = keyID
    }

    /// Bytes that a key must sign. Field order is fixed. Policy is always local.
    public func canonicalBytes() throws -> Data {
        let fields: [(String, String)] = [
            ("policy", Self.localPolicy),
            ("mac_id", macID),
            ("workspace_id", workspaceID),
            ("run_id", runID),
            ("contract_sha256", contractSHA256),
            ("inputs_sha256", inputsSHA256),
            ("bounds", bounds),
            ("nonce", nonce),
            ("expiry_unix", String(expiryUnix)),
            ("key_id", keyID),
        ]
        var out = Data(Self.version.utf8)
        for (name, value) in fields {
            try Self.validate(name: name, value: value)
            out.append(Self.lengthPrefixed(name))
            out.append(Self.lengthPrefixed(value))
        }
        return out
    }

    private static func validate(name: String, value: String) throws {
        guard !value.isEmpty, !value.contains("\0") else {
            throw BiometricApprovalError.malformed(name)
        }
        if name == "nonce" {
            let hex = CharacterSet(charactersIn: "0123456789abcdef")
            guard (32...64).contains(value.count), value.unicodeScalars.allSatisfy({ hex.contains($0) }) else {
                throw BiometricApprovalError.malformed("nonce")
            }
        }
        if name == "key_id" {
            let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
            guard (1...64).contains(value.count), value.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
                throw BiometricApprovalError.malformed("key_id")
            }
        }
    }

    private static func lengthPrefixed(_ text: String) -> Data {
        let bytes = Data(text.utf8)
        var length = UInt32(bytes.count).bigEndian
        var out = Data(bytes: &length, count: 4)
        out.append(bytes)
        return out
    }
}

struct StoredBiometricApproval: Equatable {
    var canonical: Data
    var signature: Data
    var publicKey: Data
    var enrollmentGeneration: Int?
}

/// Stores one signed approval and consumes it once under an exclusive lock.
///
/// The pinned public key is an argument. A record that names a different key
/// is rejected. This store does not start a run.
public enum BiometricApprovalStore {
    public static func submit(
        request: BiometricApprovalRequest,
        signature: Data,
        publicKey: Data,
        pinnedPublicKey: Data,
        directory: URL,
        now: Int,
        enrollmentGeneration: Int? = nil
    ) throws {
        guard request.expiryUnix > now else {
            throw BiometricApprovalError.expired
        }
        let canonical = try request.canonicalBytes()
        guard publicKey == pinnedPublicKey, verify(canonical: canonical, signature: signature, publicKey: pinnedPublicKey) else {
            throw BiometricApprovalError.tampered
        }
        try withLock(directory) {
            let consumed = consumedURL(directory, request.nonce)
            let pending = pendingURL(directory, request.nonce)
            if FileManager.default.fileExists(atPath: consumed.path) || FileManager.default.fileExists(atPath: pending.path) {
                throw BiometricApprovalError.replay
            }
            let payload = try encode(StoredBiometricApproval(
                canonical: canonical,
                signature: signature,
                publicKey: publicKey,
                enrollmentGeneration: enrollmentGeneration
            ))
            try payload.write(to: pending, options: .atomic)
        }
    }

    /// Verifies the live request, then spends the nonce.
    ///
    /// Expiry spends the nonce so a later clock change cannot reuse it.
    /// A mismatch or a bad signature does not spend it.
    public static func consume(
        request: BiometricApprovalRequest,
        pinnedPublicKey: Data,
        directory: URL,
        now: Int,
        enrollmentGeneration: Int? = nil
    ) throws {
        let canonical = try request.canonicalBytes()
        try withLock(directory) {
            let consumed = consumedURL(directory, request.nonce)
            if FileManager.default.fileExists(atPath: consumed.path) {
                throw BiometricApprovalError.replay
            }
            let pending = pendingURL(directory, request.nonce)
            let stored: StoredBiometricApproval
            do {
                stored = try decode(Data(contentsOf: pending))
            } catch let error as BiometricApprovalError {
                throw error
            } catch {
                throw BiometricApprovalError.tampered
            }
            guard stored.publicKey == pinnedPublicKey else {
                throw BiometricApprovalError.tampered
            }
            guard verify(canonical: stored.canonical, signature: stored.signature, publicKey: pinnedPublicKey) else {
                throw BiometricApprovalError.tampered
            }
            guard stored.canonical == canonical else {
                throw BiometricApprovalError.mismatch
            }
            if let enrollmentGeneration, stored.enrollmentGeneration != enrollmentGeneration {
                throw BiometricApprovalError.revoked
            }
            if request.expiryUnix <= now {
                try Data("expired\n".utf8).write(to: consumed, options: .atomic)
                throw BiometricApprovalError.expired
            }
            try Data("consumed\n".utf8).write(to: consumed, options: .atomic)
            try? FileManager.default.removeItem(at: pending)
        }
    }

    public static func isConsumed(nonce: String, directory: URL) -> Bool {
        FileManager.default.fileExists(atPath: consumedURL(directory, nonce).path)
    }

    static func verify(canonical: Data, signature: Data, publicKey: Data) -> Bool {
        guard let parsedSignature = try? P256.Signing.ECDSASignature(rawRepresentation: signature),
              let key = try? P256.Signing.PublicKey(x963Representation: publicKey) else {
            return false
        }
        return key.isValidSignature(parsedSignature, for: canonical)
    }

    private static func pendingURL(_ directory: URL, _ nonce: String) -> URL {
        directory.appendingPathComponent("\(nonce).approval")
    }

    private static func consumedURL(_ directory: URL, _ nonce: String) -> URL {
        directory.appendingPathComponent("\(nonce).consumed")
    }

    private static func encode(_ stored: StoredBiometricApproval) throws -> Data {
        var object: [String: String] = [
            "canonical_b64": stored.canonical.base64EncodedString(),
            "public_key_b64": stored.publicKey.base64EncodedString(),
            "signature_b64": stored.signature.base64EncodedString(),
        ]
        if let generation = stored.enrollmentGeneration {
            object["enrollment_generation"] = String(generation)
        }
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    private static func decode(_ data: Data) throws -> StoredBiometricApproval {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: String],
              let canonical = object["canonical_b64"].flatMap({ Data(base64Encoded: $0) }),
              let signature = object["signature_b64"].flatMap({ Data(base64Encoded: $0) }),
              let publicKey = object["public_key_b64"].flatMap({ Data(base64Encoded: $0) }) else {
            throw BiometricApprovalError.tampered
        }
        let generation = object["enrollment_generation"].flatMap { Int($0) }
        if object["enrollment_generation"] != nil && (generation ?? 0) <= 0 {
            throw BiometricApprovalError.tampered
        }
        return StoredBiometricApproval(
            canonical: canonical,
            signature: signature,
            publicKey: publicKey,
            enrollmentGeneration: generation
        )
    }

    private static func withLock<T>(_ directory: URL, _ body: () throws -> T) throws -> T {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let lockURL = directory.appendingPathComponent("consume.lock")
        let fd = open(lockURL.path, O_CREAT | O_RDWR, 0o600)
        guard fd >= 0 else {
            throw BiometricApprovalError.malformed("lock")
        }
        defer { close(fd) }
        guard flock(fd, LOCK_EX) == 0 else {
            throw BiometricApprovalError.malformed("lock")
        }
        defer { _ = flock(fd, LOCK_UN) }
        return try body()
    }
}

/// A pinned public key stored apart from any approval.
///
/// The private key is not in this record. A public key that arrives beside a
/// signature is not enrollment.
public struct BiometricEnrollmentRecord: Equatable, Sendable {
    public static let active = "active"
    public static let revoked = "revoked"
    public static let softwareBackend = "software-test-double"
    public static let secureEnclaveBackend = "secure-enclave"

    public var keyID: String
    public var publicKey: Data
    public var state: String
    public var backend: String
    /// Increases when the key is revoked. Consumers recheck it under the enrollment lock.
    public var generation: Int = 1
}

/// Writes and reads enrollment records. It does not sign and it does not start a run.
public enum BiometricEnrollmentDirectory {
    public static func save(_ record: BiometricEnrollmentRecord, directory: URL) throws {
        try validateKeyID(record.keyID)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let object: [String: String] = [
            "backend": record.backend,
            "generation": String(record.generation),
            "key_id": record.keyID,
            "public_key_b64": record.publicKey.base64EncodedString(),
            "state": record.state,
        ]
        let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        try data.write(to: recordURL(directory, record.keyID), options: .atomic)
    }

    public static func load(keyID: String, directory: URL) throws -> BiometricEnrollmentRecord {
        try validateKeyID(keyID)
        let data: Data
        do {
            data = try Data(contentsOf: recordURL(directory, keyID))
        } catch {
            throw BiometricApprovalError.malformed("enrollment")
        }
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: String],
              object["key_id"] == keyID,
              let state = object["state"],
              let backend = object["backend"],
              let publicKey = object["public_key_b64"].flatMap({ Data(base64Encoded: $0) }),
              !publicKey.isEmpty,
              state == BiometricEnrollmentRecord.active || state == BiometricEnrollmentRecord.revoked else {
            throw BiometricApprovalError.tampered
        }
        let generation = Int(object["generation"] ?? "1") ?? 0
        guard generation > 0 else {
            throw BiometricApprovalError.tampered
        }
        return BiometricEnrollmentRecord(
            keyID: keyID,
            publicKey: publicKey,
            state: state,
            backend: backend,
            generation: generation
        )
    }

    /// In-process lock plus a directory file lock. Revoke and consume share it.
    public static func withExclusiveAccess<T>(_ directory: URL, _ body: () throws -> T) throws -> T {
        processLock.lock()
        defer { processLock.unlock() }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let lockURL = directory.appendingPathComponent("enrollment.lock")
        let fd = open(lockURL.path, O_CREAT | O_RDWR, 0o600)
        guard fd >= 0 else {
            throw BiometricApprovalError.malformed("lock")
        }
        defer { close(fd) }
        guard flock(fd, LOCK_EX) == 0 else {
            throw BiometricApprovalError.malformed("lock")
        }
        defer { _ = flock(fd, LOCK_UN) }
        return try body()
    }

    public static func revoke(keyID: String, directory: URL) throws {
        try withExclusiveAccess(directory) {
            var record = try load(keyID: keyID, directory: directory)
            guard record.state == BiometricEnrollmentRecord.active else {
                throw BiometricApprovalError.revoked
            }
            record.state = BiometricEnrollmentRecord.revoked
            record.generation += 1
            try save(record, directory: directory)
        }
    }

    private static let processLock = NSLock()

    static func recordURL(_ directory: URL, _ keyID: String) -> URL {
        directory.appendingPathComponent("\(keyID).enrollment")
    }

    private static func validateKeyID(_ keyID: String) throws {
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
        guard (1...64).contains(keyID.count), keyID.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
            throw BiometricApprovalError.malformed("key_id")
        }
    }
}

/// Test-double keys on disk. This is not a Secure Enclave and not biometric approval.
///
/// The private file is loaded on every sign, so a later sign uses the enrolled key.
public enum SoftwareApprovalKeyEnrollment {
    public static func enroll(keyID: String, directory: URL) throws -> Data {
        if (try? BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)) != nil {
            throw BiometricApprovalError.replay
        }
        let key = P256.Signing.PrivateKey()
        try writePrivate(key.rawRepresentation, keyID: keyID, directory: directory)
        let record = BiometricEnrollmentRecord(
            keyID: keyID,
            publicKey: key.publicKey.x963Representation,
            state: BiometricEnrollmentRecord.active,
            backend: BiometricEnrollmentRecord.softwareBackend
        )
        try BiometricEnrollmentDirectory.save(record, directory: directory)
        return record.publicKey
    }

    public static func sign(_ request: BiometricApprovalRequest, directory: URL) throws -> Data {
        try BiometricEnrollmentDirectory.withExclusiveAccess(directory) {
            let record = try activeRecord(request.keyID, directory: directory, backend: BiometricEnrollmentRecord.softwareBackend)
            let raw = try Data(contentsOf: privateURL(directory, request.keyID))
            let key = try P256.Signing.PrivateKey(rawRepresentation: raw)
            guard key.publicKey.x963Representation == record.publicKey else {
                throw BiometricApprovalError.tampered
            }
            return try key.signature(for: try request.canonicalBytes()).rawRepresentation
        }
    }

    public static func revoke(keyID: String, directory: URL) throws {
        let record = try BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)
        guard record.backend == BiometricEnrollmentRecord.softwareBackend else {
            throw BiometricApprovalError.malformed("backend")
        }
        try BiometricEnrollmentDirectory.revoke(keyID: keyID, directory: directory)
        try? FileManager.default.removeItem(at: privateURL(directory, keyID))
    }

    /// Enrolls `newKeyID`, then revokes `oldKeyID`. The new public key is a different key.
    public static func rotate(from oldKeyID: String, to newKeyID: String, directory: URL) throws -> Data {
        let publicKey = try enroll(keyID: newKeyID, directory: directory)
        try revoke(keyID: oldKeyID, directory: directory)
        return publicKey
    }

    static func privateURL(_ directory: URL, _ keyID: String) -> URL {
        directory.appendingPathComponent("\(keyID).software-key")
    }

    private static func activeRecord(_ keyID: String, directory: URL, backend: String) throws -> BiometricEnrollmentRecord {
        let record = try BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)
        guard record.backend == backend else {
            throw BiometricApprovalError.malformed("backend")
        }
        guard record.state == BiometricEnrollmentRecord.active else {
            throw BiometricApprovalError.revoked
        }
        return record
    }

    private static func writePrivate(_ data: Data, keyID: String, directory: URL) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = privateURL(directory, keyID)
        let fd = open(url.path, O_CREAT | O_EXCL | O_WRONLY, 0o600)
        guard fd >= 0 else {
            throw BiometricApprovalError.malformed("private key")
        }
        defer { close(fd) }
        let wrote = data.withUnsafeBytes { raw -> Int in
            guard let base = raw.baseAddress else { return -1 }
            return Darwin.write(fd, base, raw.count)
        }
        guard wrote == data.count else {
            throw BiometricApprovalError.malformed("private key")
        }
    }
}

extension BiometricApprovalStore {
    /// Test seam. Runs before the enrollment lock so a revoke can finish first.
    /// Production leaves this nil.
    static var beforeExclusiveAccess: (() -> Void)?

    /// Pins the key from the enrollment record. The signature's accompanying public key is not consulted.
    public static func submitEnrolled(
        request: BiometricApprovalRequest,
        signature: Data,
        enrollmentDirectory: URL,
        approvalDirectory: URL,
        now: Int
    ) throws {
        try BiometricEnrollmentDirectory.withExclusiveAccess(enrollmentDirectory) {
            let record = try BiometricEnrollmentDirectory.load(keyID: request.keyID, directory: enrollmentDirectory)
            guard record.state == BiometricEnrollmentRecord.active else {
                throw BiometricApprovalError.revoked
            }
            try submit(
                request: request,
                signature: signature,
                publicKey: record.publicKey,
                pinnedPublicKey: record.publicKey,
                directory: approvalDirectory,
                now: now,
                enrollmentGeneration: record.generation
            )
        }
    }

    public static func consumeEnrolled(
        request: BiometricApprovalRequest,
        enrollmentDirectory: URL,
        approvalDirectory: URL,
        now: Int
    ) throws {
        beforeExclusiveAccess?()
        try BiometricEnrollmentDirectory.withExclusiveAccess(enrollmentDirectory) {
            let record = try BiometricEnrollmentDirectory.load(keyID: request.keyID, directory: enrollmentDirectory)
            guard record.state == BiometricEnrollmentRecord.active else {
                throw BiometricApprovalError.revoked
            }
            try consume(
                request: request,
                pinnedPublicKey: record.publicKey,
                directory: approvalDirectory,
                now: now,
                enrollmentGeneration: record.generation
            )
        }
    }
}

/// Enrolls one Secure Enclave key and signs later requests with that same key.
///
/// Each private-key operation requires the current biometric set. These
/// functions do not call `LAContext.evaluatePolicy` and do not accept a
/// Boolean in its place. Unit tests must not call them.
///
/// The key blob is stored in the keychain. The enrollment record stores only
/// the public key. Losing the biometric set makes the key unusable; recovery
/// is `retireUnusableKey` followed by a new `enroll`, not an exported copy.
public enum LocalSecureEnclaveEnrollment {
    private static let service = "com.darashkevich.runspecimen.biometric"

    public static func enroll(keyID: String, directory: URL) throws -> Data {
        if (try? BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)) != nil {
            throw BiometricApprovalError.replay
        }
        let context = biometricContext()
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            accessControl: try accessControl(),
            authenticationContext: context
        )
        try saveBlob(key.dataRepresentation, keyID: keyID)
        let record = BiometricEnrollmentRecord(
            keyID: keyID,
            publicKey: key.publicKey.x963Representation,
            state: BiometricEnrollmentRecord.active,
            backend: BiometricEnrollmentRecord.secureEnclaveBackend
        )
        do {
            try BiometricEnrollmentDirectory.save(record, directory: directory)
        } catch let saveError {
            do {
                try deleteBlob(keyID: keyID)
            } catch {
                throw error
            }
            throw saveError
        }
        return record.publicKey
    }

    public static func sign(_ request: BiometricApprovalRequest, directory: URL) throws -> Data {
        let record = try BiometricEnrollmentDirectory.load(keyID: request.keyID, directory: directory)
        guard record.backend == BiometricEnrollmentRecord.secureEnclaveBackend else {
            throw BiometricApprovalError.malformed("backend")
        }
        guard record.state == BiometricEnrollmentRecord.active else {
            throw BiometricApprovalError.revoked
        }
        let blob = try loadBlob(keyID: request.keyID)
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            dataRepresentation: blob,
            authenticationContext: biometricContext()
        )
        guard key.publicKey.x963Representation == record.publicKey else {
            throw BiometricApprovalError.tampered
        }
        return try key.signature(for: try request.canonicalBytes()).rawRepresentation
    }

    public static func revoke(keyID: String, directory: URL) throws {
        try BiometricEnrollmentDirectory.withExclusiveAccess(directory) {
            let record = try BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)
            guard record.backend == BiometricEnrollmentRecord.secureEnclaveBackend else {
                throw BiometricApprovalError.malformed("backend")
            }
            guard record.state == BiometricEnrollmentRecord.active else {
                throw BiometricApprovalError.revoked
            }
            try deleteBlob(keyID: keyID)
            var revoked = record
            revoked.state = BiometricEnrollmentRecord.revoked
            revoked.generation += 1
            try BiometricEnrollmentDirectory.save(revoked, directory: directory)
        }
    }

    public static func rotate(from oldKeyID: String, to newKeyID: String, directory: URL) throws -> Data {
        let publicKey = try enroll(keyID: newKeyID, directory: directory)
        try revoke(keyID: oldKeyID, directory: directory)
        return publicKey
    }

    /// Drops a key that can no longer be used. It does not create a replacement key.
    public static func retireUnusableKey(keyID: String, directory: URL) throws {
        try BiometricEnrollmentDirectory.withExclusiveAccess(directory) {
            try deleteBlob(keyID: keyID)
            guard (try? BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)) != nil else {
                return
            }
            var record = try BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)
            record.state = BiometricEnrollmentRecord.revoked
            record.generation += 1
            try BiometricEnrollmentDirectory.save(record, directory: directory)
        }
    }

    /// `nil` means the keychain item is gone or was never there.
    /// Any other status is a failure and must not be treated as removal.
    public static func keychainDeletionError(status: OSStatus) -> BiometricApprovalError? {
        if status == errSecSuccess || status == errSecItemNotFound {
            return nil
        }
        return .malformed("keychain")
    }

    private static func biometricContext() -> LAContext {
        let context = LAContext()
        context.localizedFallbackTitle = ""
        return context
    }

    private static func accessControl() throws -> SecAccessControl {
        var cfError: Unmanaged<CFError>?
        guard let access = SecAccessControlCreateWithFlags(
            nil,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            [.privateKeyUsage, .biometryCurrentSet],
            &cfError
        ) else {
            throw BiometricApprovalError.malformed("access control")
        }
        return access
    }

    private static func saveBlob(_ data: Data, keyID: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: keyID,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        ]
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw BiometricApprovalError.malformed("keychain")
        }
    }

    private static func loadBlob(keyID: String) throws -> Data {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: keyID,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else {
            throw BiometricApprovalError.malformed("keychain")
        }
        return data
    }

    private static func deleteBlob(keyID: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: keyID,
        ]
        let status = SecItemDelete(query as CFDictionary)
        if let error = keychainDeletionError(status: status) {
            throw error
        }
    }
}
