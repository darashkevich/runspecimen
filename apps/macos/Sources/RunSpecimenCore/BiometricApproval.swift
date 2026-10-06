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
            return "The signatures do not match the biometric policy. Local, companion, and dual each require their own keys."
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
        enrollmentGeneration: Int? = nil
    ) throws {
        let canonical = try request.canonicalBytes()
        guard publicKey == pinnedPublicKey, verify(canonical: canonical, signature: signature, publicKey: pinnedPublicKey) else {
            throw BiometricApprovalError.tampered
        }
        try withLock(directory) {
            guard request.expiryUnix > clock() else {
                throw BiometricApprovalError.expired
            }
            let consumed = consumedURL(directory, request.nonce)
            let pending = pendingURL(directory, request.nonce)
            let policyPending = PolicyBoundApprovalStore.pendingURL(directory, request.nonce)
            if FileManager.default.fileExists(atPath: consumed.path)
                || FileManager.default.fileExists(atPath: pending.path)
                || FileManager.default.fileExists(atPath: policyPending.path) {
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
            #if RUNSPECIMEN_TEST_HOOKS
            beforeConsumptionDecision?()
            #endif
            let observedNow = clock()
            if request.expiryUnix <= observedNow {
                try Data("expired\n".utf8).write(to: consumed, options: .atomic)
                throw BiometricApprovalError.expired
            }
            try Data("consumed\n".utf8).write(to: consumed, options: .atomic)
            try? FileManager.default.removeItem(at: pending)
        }
    }

    /// Read at the submit and consume decision, after the approval lock is held.
    /// A timestamp captured before a wait is not used.
    /// Internal so another module cannot replace the production clock.
    static var clock: () -> Int = { Int(Date().timeIntervalSince1970) }

    #if RUNSPECIMEN_TEST_HOOKS
    /// Test seam. Runs inside the approval lock, immediately before the expiry decision.
    static var beforeConsumptionDecision: (() -> Void)?
    #endif

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

    static func consumedMarker(_ directory: URL, _ nonce: String) -> URL {
        consumedURL(directory, nonce)
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
    public static let softwareBackend = EnrollmentIdentity.backendSoftwareTest
    public static let secureEnclaveBackend = EnrollmentIdentity.backendSecureEnclave

    public var keyID: String
    public var publicKey: Data
    public var state: String
    public var backend: String
    /// `local` or `companion`. A swapped role does not satisfy the other slot.
    public var role: String
    /// `production`, `software-test`, `software-development`, or `diagnostic`.
    public var provenance: String
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
            "provenance": record.provenance,
            "public_key_b64": record.publicKey.base64EncodedString(),
            "role": record.role,
            "state": record.state,
        ]
        let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        try data.write(to: recordURL(directory, record.keyID), options: .atomic)
    }

    /// Stores an active public key from a file a person carried.
    ///
    /// The pairing schema accepts `active` or `revoked`. This pin accepts only
    /// `active`. A missing, revoked, or other state is refused before any
    /// enrollment file is written. A locally revoked record is not replaced by
    /// a later active import, including one with another generation. The file's
    /// backend and provenance strings are ignored. A label of `secure-enclave`
    /// does not make the key production enrollment. This is not installed
    /// admission.
    public static func pinCarriedCompanion(_ data: Data, directory: URL) throws -> BiometricEnrollmentRecord {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: String] else {
            throw BiometricApprovalError.malformed("enrollment")
        }
        guard let keyID = object["key_id"] else {
            throw BiometricApprovalError.malformed("enrollment")
        }
        try validateKeyID(keyID)
        if let role = object["role"], role != EnrollmentIdentity.roleCompanion {
            throw BiometricApprovalError.unsupportedPolicy
        }
        guard let publicKey = object["public_key_x963_b64"].flatMap({ Data(base64Encoded: $0) }),
              publicKey.count == 65 else {
            throw BiometricApprovalError.malformed("public_key")
        }
        guard let generationText = object["generation"],
              let generation = Int(generationText),
              generation > 0,
              String(generation) == generationText else {
            throw BiometricApprovalError.malformed("enrollment")
        }
        guard let state = object["state"] else {
            throw BiometricApprovalError.malformed("state")
        }
        if state == BiometricEnrollmentRecord.revoked {
            throw BiometricApprovalError.revoked
        }
        guard state == BiometricEnrollmentRecord.active else {
            throw BiometricApprovalError.malformed("state")
        }
        let record = BiometricEnrollmentRecord(
            keyID: keyID,
            publicKey: publicKey,
            state: state,
            backend: EnrollmentIdentity.backendUnverified,
            role: EnrollmentIdentity.roleCompanion,
            provenance: EnrollmentIdentity.provenanceCarriedPin,
            generation: generation
        )
        return try withExclusiveAccess(directory) {
            let url = recordURL(directory, keyID)
            if FileManager.default.fileExists(atPath: url.path) {
                let existing = try load(keyID: keyID, directory: directory)
                guard existing.state == BiometricEnrollmentRecord.active else {
                    throw BiometricApprovalError.revoked
                }
                guard existing.publicKey == publicKey else {
                    throw BiometricApprovalError.malformed("public_key")
                }
                guard existing.generation == generation else {
                    throw BiometricApprovalError.malformed("generation")
                }
                return existing
            }
            try save(record, directory: directory)
            return record
        }
    }

    public static func save(_ record: BiometricEnrollmentRecord, directoryFD: Int32) throws {
        try validateKeyID(record.keyID)
        let data = try JSONSerialization.data(withJSONObject: json(record), options: [.sortedKeys])
        let temporary = ".\(record.keyID).enrollment.tmp"
        let finalName = "\(record.keyID).enrollment"
        let fd = openat(directoryFD, temporary, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw BiometricApprovalError.malformed("enrollment") }
        do {
            try DescriptorIO.writeAll(fd, data)
        } catch {
            close(fd)
            _ = unlinkat(directoryFD, temporary, 0)
            throw error
        }
        close(fd)
        if renameat(directoryFD, temporary, directoryFD, finalName) != 0 {
            _ = unlinkat(directoryFD, temporary, 0)
            throw BiometricApprovalError.malformed("enrollment")
        }
    }

    public static func load(keyID: String, directoryFD: Int32) throws -> BiometricEnrollmentRecord {
        try validateKeyID(keyID)
        let fd = openat(directoryFD, "\(keyID).enrollment", O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw BiometricApprovalError.malformed("enrollment") }
        defer { close(fd) }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while true {
            let count = buffer.withUnsafeMutableBytes { Darwin.read(fd, $0.baseAddress, $0.count) }
            if count == 0 { break }
            if count < 0 { throw BiometricApprovalError.malformed("enrollment") }
            data.append(buffer, count: count)
        }
        return try record(from: data, keyID: keyID)
    }

    public static func load(keyID: String, directory: URL) throws -> BiometricEnrollmentRecord {
        try validateKeyID(keyID)
        let data: Data
        do {
            data = try Data(contentsOf: recordURL(directory, keyID))
        } catch {
            throw BiometricApprovalError.malformed("enrollment")
        }
        return try record(from: data, keyID: keyID)
    }

    private static func json(_ record: BiometricEnrollmentRecord) -> [String: String] {
        [
            "backend": record.backend,
            "generation": String(record.generation),
            "key_id": record.keyID,
            "provenance": record.provenance,
            "public_key_b64": record.publicKey.base64EncodedString(),
            "role": record.role,
            "state": record.state,
        ]
    }

    private static func record(from data: Data, keyID: String) throws -> BiometricEnrollmentRecord {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: String],
              object["key_id"] == keyID,
              let state = object["state"],
              let backend = object["backend"],
              let role = object["role"],
              let provenance = object["provenance"],
              let publicKey = object["public_key_b64"].flatMap({ Data(base64Encoded: $0) }),
              !publicKey.isEmpty,
              state == BiometricEnrollmentRecord.active || state == BiometricEnrollmentRecord.revoked,
              EnrollmentIdentity.isRecognized(role: role, backend: backend, provenance: provenance) else {
            throw BiometricApprovalError.tampered
        }
        let generationText = object["generation"] ?? ""
        guard let generation = Int(generationText), generation > 0, String(generation) == generationText else {
            throw BiometricApprovalError.tampered
        }
        return BiometricEnrollmentRecord(
            keyID: keyID,
            publicKey: publicKey,
            state: state,
            backend: backend,
            role: role,
            provenance: provenance,
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
            try revokeWhileLocked(keyID: keyID, directory: directory)
        }
    }

    static func revokeWhileLocked(keyID: String, directory: URL) throws {
        var record = try load(keyID: keyID, directory: directory)
        guard record.state == BiometricEnrollmentRecord.active else {
            throw BiometricApprovalError.revoked
        }
        record.state = BiometricEnrollmentRecord.revoked
        record.generation += 1
        try save(record, directory: directory)
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
            backend: BiometricEnrollmentRecord.softwareBackend,
            role: EnrollmentIdentity.roleLocal,
            provenance: EnrollmentIdentity.provenanceSoftwareTest
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
        try BiometricEnrollmentDirectory.withExclusiveAccess(directory) {
            let record = try BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)
            guard record.backend == BiometricEnrollmentRecord.softwareBackend else {
                throw BiometricApprovalError.malformed("backend")
            }
            try BiometricEnrollmentDirectory.revokeWhileLocked(keyID: keyID, directory: directory)
            try? FileManager.default.removeItem(at: privateURL(directory, keyID))
        }
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
    #if RUNSPECIMEN_TEST_HOOKS
    /// Test seam. Runs before the enrollment lock so a revoke can finish first.
    /// Production leaves this nil.
    static var beforeExclusiveAccess: (() -> Void)?
    #endif

    /// Pins the key from the enrollment record. The signature's accompanying public key is not consulted.
    public static func submitEnrolled(
        request: BiometricApprovalRequest,
        signature: Data,
        enrollmentDirectory: URL,
        approvalDirectory: URL
    ) throws {
        try BiometricEnrollmentDirectory.withExclusiveAccess(enrollmentDirectory) {
            let record = try BiometricEnrollmentDirectory.load(keyID: request.keyID, directory: enrollmentDirectory)
            guard record.state == BiometricEnrollmentRecord.active else {
                throw BiometricApprovalError.revoked
            }
            guard record.role == EnrollmentIdentity.roleLocal,
                  EnrollmentIdentity.acceptsPrototype(role: record.role, backend: record.backend, provenance: record.provenance) else {
                throw BiometricApprovalError.unsupportedPolicy
            }
            try submit(
                request: request,
                signature: signature,
                publicKey: record.publicKey,
                pinnedPublicKey: record.publicKey,
                directory: approvalDirectory,
                enrollmentGeneration: record.generation
            )
        }
    }

    public static func consumeEnrolled(
        request: BiometricApprovalRequest,
        enrollmentDirectory: URL,
        approvalDirectory: URL
    ) throws {
        #if RUNSPECIMEN_TEST_HOOKS
        beforeExclusiveAccess?()
        #endif
        try BiometricEnrollmentDirectory.withExclusiveAccess(enrollmentDirectory) {
            let record = try BiometricEnrollmentDirectory.load(keyID: request.keyID, directory: enrollmentDirectory)
            guard record.state == BiometricEnrollmentRecord.active else {
                throw BiometricApprovalError.revoked
            }
            guard record.role == EnrollmentIdentity.roleLocal,
                  EnrollmentIdentity.acceptsPrototype(role: record.role, backend: record.backend, provenance: record.provenance) else {
                throw BiometricApprovalError.unsupportedPolicy
            }
            try consume(
                request: request,
                pinnedPublicKey: record.publicKey,
                directory: approvalDirectory,
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
    public static let productionKeychainService = "com.darashkevich.runspecimen.biometric"
    public static let diagnosticKeychainService = "com.darashkevich.runspecimen.biometric.diagnostic"
    private static let service = productionKeychainService

    public static func enroll(keyID: String, directory: URL, directoryFD: Int32? = nil, keychainService: String = productionKeychainService) throws -> Data {
        let existing: BiometricEnrollmentRecord?
        if let directoryFD {
            existing = try? BiometricEnrollmentDirectory.load(keyID: keyID, directoryFD: directoryFD)
        } else {
            existing = try? BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)
        }
        if existing != nil {
            throw BiometricApprovalError.replay
        }
        let context = biometricContext()
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            accessControl: try accessControl(),
            authenticationContext: context
        )
        try saveBlob(key.dataRepresentation, keyID: keyID, service: keychainService)
        let provenance = keychainService == Self.diagnosticKeychainService
            ? EnrollmentIdentity.provenanceDiagnostic
            : EnrollmentIdentity.provenanceProduction
        let record = BiometricEnrollmentRecord(
            keyID: keyID,
            publicKey: key.publicKey.x963Representation,
            state: BiometricEnrollmentRecord.active,
            backend: BiometricEnrollmentRecord.secureEnclaveBackend,
            role: EnrollmentIdentity.roleLocal,
            provenance: provenance
        )
        do {
            if let directoryFD {
                try BiometricEnrollmentDirectory.save(record, directoryFD: directoryFD)
            } else {
                try BiometricEnrollmentDirectory.save(record, directory: directory)
            }
        } catch let saveError {
            try? deleteBlob(keyID: keyID, service: keychainService)
            throw saveError
        }
        return record.publicKey
    }

    public static func sign(_ request: BiometricApprovalRequest, directory: URL, directoryFD: Int32? = nil, keychainService: String = productionKeychainService) throws -> Data {
        let record: BiometricEnrollmentRecord
        if let directoryFD {
            record = try BiometricEnrollmentDirectory.load(keyID: request.keyID, directoryFD: directoryFD)
        } else {
            record = try BiometricEnrollmentDirectory.load(keyID: request.keyID, directory: directory)
        }
        guard record.backend == BiometricEnrollmentRecord.secureEnclaveBackend else {
            throw BiometricApprovalError.malformed("backend")
        }
        guard record.state == BiometricEnrollmentRecord.active else {
            throw BiometricApprovalError.revoked
        }
        let blob = try loadBlob(keyID: request.keyID, service: keychainService)
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            dataRepresentation: blob,
            authenticationContext: biometricContext()
        )
        guard key.publicKey.x963Representation == record.publicKey else {
            throw BiometricApprovalError.tampered
        }
        return try key.signature(for: try request.canonicalBytes()).rawRepresentation
    }

    public static func revoke(keyID: String, directory: URL, directoryFD: Int32? = nil, keychainService: String = productionKeychainService) throws {
        if let directoryFD {
            let record = try BiometricEnrollmentDirectory.load(keyID: keyID, directoryFD: directoryFD)
            guard record.backend == BiometricEnrollmentRecord.secureEnclaveBackend else {
                throw BiometricApprovalError.malformed("backend")
            }
            guard record.state == BiometricEnrollmentRecord.active else {
                throw BiometricApprovalError.revoked
            }
            try deleteBlob(keyID: keyID, service: keychainService)
            var revoked = record
            revoked.state = BiometricEnrollmentRecord.revoked
            revoked.generation += 1
            try BiometricEnrollmentDirectory.save(revoked, directoryFD: directoryFD)
            return
        }
        try BiometricEnrollmentDirectory.withExclusiveAccess(directory) {
            let record = try BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)
            guard record.backend == BiometricEnrollmentRecord.secureEnclaveBackend else {
                throw BiometricApprovalError.malformed("backend")
            }
            guard record.state == BiometricEnrollmentRecord.active else {
                throw BiometricApprovalError.revoked
            }
            try deleteBlob(keyID: keyID, service: keychainService)
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
            try deleteBlob(keyID: keyID, service: service)
            guard var record = try? BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory) else {
                return
            }
            record.state = BiometricEnrollmentRecord.revoked
            record.generation += 1
            try BiometricEnrollmentDirectory.save(record, directory: directory)
        }
    }

    /// Backend-string classifier for tests. No enroll, sign, consume, or run path calls it.
    public enum ProductionPolicy {
        public static func accepts(backend: String) -> Bool {
            backend == BiometricEnrollmentRecord.secureEnclaveBackend
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

    private static func saveBlob(_ data: Data, keyID: String, service: String) throws {
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

    private static func loadBlob(keyID: String, service: String) throws -> Data {
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

    private static func deleteBlob(keyID: String, service: String) throws {
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

/// Who must sign. The policy is inside the signed bytes, so changing it invalidates the signature.
public enum BiometricApprovalPolicy: String, Equatable, Sendable {
    case local = "local"
    case companion = "companion"
    case dual = "dual"
}

/// One signature over an RSBA2 request. The public key is the enrolled key, not a key that arrived only with the signature.
public struct PolicyApprovalSignature: Equatable, Sendable {
    public var publicKey: Data
    public var signature: Data
    public var enrollmentGeneration: Int

    public init(publicKey: Data, signature: Data, enrollmentGeneration: Int) {
        self.publicKey = publicKey
        self.signature = signature
        self.enrollmentGeneration = enrollmentGeneration
    }
}

/// RSBA2 request. RSBA1 local bytes stay unchanged.
///
/// A companion signature is evidence from the phone. It is not evidence that the person is at the Mac.
public struct PolicyBoundApprovalRequest: Equatable, Sendable {
    public static let version = "RSBA2"

    public var policy: BiometricApprovalPolicy
    public var macID: String
    public var workspaceID: String
    public var runID: String
    public var contractSHA256: String
    public var inputsSHA256: String
    public var bounds: String
    public var nonce: String
    public var expiryUnix: Int
    public var localKeyID: String
    public var companionKeyID: String
    /// Enrollment epoch covered by the signature. Zero means that role is absent.
    public var localGeneration: Int
    public var companionGeneration: Int

    public init(
        policy: BiometricApprovalPolicy,
        macID: String,
        workspaceID: String,
        runID: String,
        contractSHA256: String,
        inputsSHA256: String,
        bounds: String,
        nonce: String,
        expiryUnix: Int,
        localKeyID: String = "",
        companionKeyID: String = "",
        localGeneration: Int = 0,
        companionGeneration: Int = 0
    ) {
        self.policy = policy
        self.macID = macID
        self.workspaceID = workspaceID
        self.runID = runID
        self.contractSHA256 = contractSHA256
        self.inputsSHA256 = inputsSHA256
        self.bounds = bounds
        self.nonce = nonce
        self.expiryUnix = expiryUnix
        self.localKeyID = localKeyID
        self.companionKeyID = companionKeyID
        self.localGeneration = localGeneration
        self.companionGeneration = companionGeneration
    }

    public func canonicalBytes() throws -> Data {
        do {
            return try RSBA2Package.canonicalBytes(
                policy: policy.rawValue,
                macID: macID,
                workspaceID: workspaceID,
                runID: runID,
                contractSHA256: contractSHA256,
                inputsSHA256: inputsSHA256,
                bounds: bounds,
                nonce: nonce,
                expiryUnix: expiryUnix,
                localKeyID: localKeyID,
                companionKeyID: companionKeyID,
                localGeneration: localGeneration,
                companionGeneration: companionGeneration
            )
        } catch let error as RSBA2Package.ParseFailure {
            switch error {
            case .malformed("policy"):
                throw BiometricApprovalError.unsupportedPolicy
            case .malformed(let field):
                throw BiometricApprovalError.malformed(field)
            }
        }
    }
}

/// Sentences a person must be able to read before any biometric prompt.
public enum BiometricRequestPresentation {
    public static func lines(for request: PolicyBoundApprovalRequest) -> [String] {
        RSBA2Package.lines(for: RSBA2Package.Fields(
            policy: request.policy.rawValue,
            macID: request.macID,
            workspaceID: request.workspaceID,
            runID: request.runID,
            contractSHA256: request.contractSHA256,
            inputsSHA256: request.inputsSHA256,
            bounds: request.bounds,
            nonce: request.nonce,
            expiryUnix: request.expiryUnix,
            localKeyID: request.localKeyID,
            companionKeyID: request.companionKeyID,
            localGeneration: request.localGeneration,
            companionGeneration: request.companionGeneration,
            localPublicKeyB64: nil,
            localSignatureB64: nil,
            companionPublicKeyB64: nil,
            companionSignatureB64: nil
        ))
    }
}

/// Verifies local, companion, and dual signatures and consumes the nonce once.
///
/// This store does not start a run and does not hold the workspace lease.
/// A software key used in tests is not a Secure Enclave key.
public enum PolicyBoundApprovalStore {
    public static func submit(
        request: PolicyBoundApprovalRequest,
        local: PolicyApprovalSignature?,
        companion: PolicyApprovalSignature?,
        pinnedLocalKey: Data?,
        pinnedCompanionKey: Data?,
        directory: URL
    ) throws {
        let canonical = try request.canonicalBytes()
        let localSignature = try requiredSignature(
            request.policy == .companion ? nil : local,
            pinned: pinnedLocalKey,
            canonical: canonical,
            required: request.policy != .companion,
            expectedGeneration: request.localGeneration
        )
        let companionSignature = try requiredSignature(
            request.policy == .local ? nil : companion,
            pinned: pinnedCompanionKey,
            canonical: canonical,
            required: request.policy != .local,
            expectedGeneration: request.companionGeneration
        )
        if request.policy == .local, companion != nil { throw BiometricApprovalError.unsupportedPolicy }
        if request.policy == .companion, local != nil { throw BiometricApprovalError.unsupportedPolicy }
        if request.policy == .dual, let localSignature, let companionSignature, localSignature.publicKey == companionSignature.publicKey {
            throw BiometricApprovalError.unsupportedPolicy
        }
        try withLock(directory) {
            guard request.expiryUnix > BiometricApprovalStore.clock() else {
                throw BiometricApprovalError.expired
            }
            let consumed = BiometricApprovalStore.consumedMarker(directory, request.nonce)
            let legacy = directory.appendingPathComponent("\(request.nonce).approval")
            let pending = pendingURL(directory, request.nonce)
            if FileManager.default.fileExists(atPath: consumed.path)
                || FileManager.default.fileExists(atPath: legacy.path)
                || FileManager.default.fileExists(atPath: pending.path) {
                throw BiometricApprovalError.replay
            }
            let payload = try encode(
                canonical: canonical,
                local: localSignature,
                companion: companionSignature
            )
            try payload.write(to: pending, options: .atomic)
        }
    }

    public static func consume(
        request: PolicyBoundApprovalRequest,
        pinnedLocalKey: Data?,
        pinnedCompanionKey: Data?,
        directory: URL
    ) throws {
        let canonical = try request.canonicalBytes()
        try withLock(directory) {
            let consumed = BiometricApprovalStore.consumedMarker(directory, request.nonce)
            if FileManager.default.fileExists(atPath: consumed.path) {
                throw BiometricApprovalError.replay
            }
            let stored: StoredPolicyApproval
            do {
                stored = try decode(Data(contentsOf: pendingURL(directory, request.nonce)))
            } catch let error as BiometricApprovalError {
                throw error
            } catch {
                throw BiometricApprovalError.tampered
            }
            guard stored.canonical == canonical else {
                throw BiometricApprovalError.mismatch
            }
            if request.policy == .dual {
                guard let localSignature = stored.local, let companionSignature = stored.companion,
                      localSignature.publicKey != companionSignature.publicKey,
                      request.localKeyID != request.companionKeyID else {
                    throw BiometricApprovalError.unsupportedPolicy
                }
            }
            try match(
                stored.local,
                pinned: pinnedLocalKey,
                generation: request.localGeneration,
                canonical: canonical,
                required: request.policy != .companion
            )
            try match(
                stored.companion,
                pinned: pinnedCompanionKey,
                generation: request.companionGeneration,
                canonical: canonical,
                required: request.policy != .local
            )
            #if RUNSPECIMEN_TEST_HOOKS
            BiometricApprovalStore.beforeConsumptionDecision?()
            #endif
            if request.expiryUnix <= BiometricApprovalStore.clock() {
                try Data("expired\n".utf8).write(to: consumed, options: .atomic)
                throw BiometricApprovalError.expired
            }
            try Data("consumed\n".utf8).write(to: consumed, options: .atomic)
            try? FileManager.default.removeItem(at: pendingURL(directory, request.nonce))
        }
    }

    /// Reloads live enrollment under the same lock revoke uses. A missing generation fails closed.
    public static func consumeEnrolled(
        request: PolicyBoundApprovalRequest,
        enrollmentDirectory: URL,
        approvalDirectory: URL
    ) throws {
        #if RUNSPECIMEN_TEST_HOOKS
        BiometricApprovalStore.beforeExclusiveAccess?()
        #endif
        try BiometricEnrollmentDirectory.withExclusiveAccess(enrollmentDirectory) {
            let local = try liveRecord(
                keyID: request.localKeyID,
                generation: request.localGeneration,
                expectedRole: EnrollmentIdentity.roleLocal,
                required: request.policy != .companion,
                directory: enrollmentDirectory,
                forExecution: false
            )
            let companion = try liveRecord(
                keyID: request.companionKeyID,
                generation: request.companionGeneration,
                expectedRole: EnrollmentIdentity.roleCompanion,
                required: request.policy != .local,
                directory: enrollmentDirectory,
                forExecution: false
            )
            if request.policy == .dual, let local, let companion, local.publicKey == companion.publicKey {
                throw BiometricApprovalError.unsupportedPolicy
            }
            try consume(
                request: request,
                pinnedLocalKey: local?.publicKey,
                pinnedCompanionKey: companion?.publicKey,
                directory: approvalDirectory
            )
        }
    }

    /// Execution-shaped consume. Software, development, and diagnostic keys fail closed.
    /// Nothing in the app calls this before a run. A passing software test is not this function.
    public static func consumeForExecution(
        request: PolicyBoundApprovalRequest,
        enrollmentDirectory: URL,
        approvalDirectory: URL
    ) throws {
        #if RUNSPECIMEN_TEST_HOOKS
        BiometricApprovalStore.beforeExclusiveAccess?()
        #endif
        try BiometricEnrollmentDirectory.withExclusiveAccess(enrollmentDirectory) {
            let local = try liveRecord(
                keyID: request.localKeyID,
                generation: request.localGeneration,
                expectedRole: EnrollmentIdentity.roleLocal,
                required: request.policy != .companion,
                directory: enrollmentDirectory,
                forExecution: true
            )
            let companion = try liveRecord(
                keyID: request.companionKeyID,
                generation: request.companionGeneration,
                expectedRole: EnrollmentIdentity.roleCompanion,
                required: request.policy != .local,
                directory: enrollmentDirectory,
                forExecution: true
            )
            if request.policy == .dual, let local, let companion, local.publicKey == companion.publicKey {
                throw BiometricApprovalError.unsupportedPolicy
            }
            try consume(
                request: request,
                pinnedLocalKey: local?.publicKey,
                pinnedCompanionKey: companion?.publicKey,
                directory: approvalDirectory
            )
        }
    }

    /// Asks a consume function whether a request would be allowed, and does not start a run.
    ///
    /// The app and the CLI do not call this. A test double can stand in for consume.
    public struct ExecutionEvaluation: Equatable, Sendable {
        public var started: Bool
        public var consumeSucceeded: Bool
        public var reason: String
    }

    public static func evaluateExecution(
        request: PolicyBoundApprovalRequest,
        enrollmentDirectory: URL,
        approvalDirectory: URL,
        consume: (PolicyBoundApprovalRequest, URL, URL) throws -> Void
    ) -> ExecutionEvaluation {
        do {
            try consume(request, enrollmentDirectory, approvalDirectory)
            return ExecutionEvaluation(started: false, consumeSucceeded: true, reason: "consumed")
        } catch let error as BiometricApprovalError {
            return ExecutionEvaluation(started: false, consumeSucceeded: false, reason: "\(error)")
        } catch {
            return ExecutionEvaluation(started: false, consumeSucceeded: false, reason: "malformed")
        }
    }

    /// Accepts a file a person carried from the phone. It does not open a socket.
    public static func importUserMediatedPackage(
        _ data: Data,
        pinnedLocalKey: Data?,
        pinnedCompanionKey: Data?,
        directory: URL
    ) throws -> PolicyBoundApprovalRequest {
        let fields: RSBA2Package.Fields
        do {
            fields = try RSBA2Package.parse(data)
        } catch let error as RSBA2Package.ParseFailure {
            switch error {
            case .malformed("policy"):
                throw BiometricApprovalError.unsupportedPolicy
            case .malformed(let field):
                throw BiometricApprovalError.malformed(field)
            }
        }
        guard let policy = BiometricApprovalPolicy(rawValue: fields.policy) else {
            throw BiometricApprovalError.unsupportedPolicy
        }
        let request = PolicyBoundApprovalRequest(
            policy: policy,
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
        let local = signature(publicKeyB64: fields.localPublicKeyB64, signatureB64: fields.localSignatureB64, generation: fields.localGeneration)
        let companion = signature(publicKeyB64: fields.companionPublicKeyB64, signatureB64: fields.companionSignatureB64, generation: fields.companionGeneration)
        try submit(
            request: request,
            local: local,
            companion: companion,
            pinnedLocalKey: pinnedLocalKey,
            pinnedCompanionKey: pinnedCompanionKey,
            directory: directory
        )
        return request
    }

    public static func package(
        request: PolicyBoundApprovalRequest,
        local: PolicyApprovalSignature?,
        companion: PolicyApprovalSignature?
    ) throws -> Data {
        var object: [String: String] = [
            "bounds": request.bounds,
            "contract_sha256": request.contractSHA256,
            "expiry_unix": String(request.expiryUnix),
            "inputs_sha256": request.inputsSHA256,
            "mac_id": request.macID,
            "nonce": request.nonce,
            "policy": request.policy.rawValue,
            "run_id": request.runID,
            "version": PolicyBoundApprovalRequest.version,
            "workspace_id": request.workspaceID,
        ]
        if !request.localKeyID.isEmpty { object["local_key_id"] = request.localKeyID }
        if !request.companionKeyID.isEmpty { object["companion_key_id"] = request.companionKeyID }
        if request.localGeneration > 0 { object["local_generation"] = String(request.localGeneration) }
        if request.companionGeneration > 0 { object["companion_generation"] = String(request.companionGeneration) }
        if let local {
            guard local.enrollmentGeneration == request.localGeneration else {
                throw BiometricApprovalError.tampered
            }
            object["local_public_key_b64"] = local.publicKey.base64EncodedString()
            object["local_signature_b64"] = local.signature.base64EncodedString()
        }
        if let companion {
            guard companion.enrollmentGeneration == request.companionGeneration else {
                throw BiometricApprovalError.tampered
            }
            object["companion_public_key_b64"] = companion.publicKey.base64EncodedString()
            object["companion_signature_b64"] = companion.signature.base64EncodedString()
        }
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    static func pendingURL(_ directory: URL, _ nonce: String) -> URL {
        directory.appendingPathComponent("\(nonce).policy-approval")
    }

    private static func liveRecord(
        keyID: String,
        generation: Int,
        expectedRole: String,
        required: Bool,
        directory: URL,
        forExecution: Bool
    ) throws -> BiometricEnrollmentRecord? {
        guard required else { return nil }
        guard generation > 0 else { throw BiometricApprovalError.malformed("enrollment") }
        let record = try BiometricEnrollmentDirectory.load(keyID: keyID, directory: directory)
        guard record.state == BiometricEnrollmentRecord.active else {
            throw BiometricApprovalError.revoked
        }
        guard record.generation == generation else {
            throw BiometricApprovalError.revoked
        }
        guard record.role == expectedRole else {
            throw BiometricApprovalError.unsupportedPolicy
        }
        if forExecution {
            guard EnrollmentIdentity.allowsExecution(
                role: record.role,
                backend: record.backend,
                provenance: record.provenance,
                state: record.state
            ) else {
                throw BiometricApprovalError.unsupportedPolicy
            }
        } else if !EnrollmentIdentity.acceptsPrototype(role: record.role, backend: record.backend, provenance: record.provenance) {
            throw BiometricApprovalError.unsupportedPolicy
        }
        return record
    }

    private static func requiredSignature(
        _ signature: PolicyApprovalSignature?,
        pinned: Data?,
        canonical: Data,
        required: Bool,
        expectedGeneration: Int
    ) throws -> PolicyApprovalSignature? {
        guard required else { return nil }
        guard expectedGeneration > 0 else { throw BiometricApprovalError.malformed("enrollment") }
        guard let signature, let pinned, signature.publicKey == pinned,
              signature.enrollmentGeneration == expectedGeneration,
              BiometricApprovalStore.verify(canonical: canonical, signature: signature.signature, publicKey: pinned) else {
            throw BiometricApprovalError.tampered
        }
        return signature
    }

    private static func match(
        _ stored: PolicyApprovalSignature?,
        pinned: Data?,
        generation: Int,
        canonical: Data,
        required: Bool
    ) throws {
        guard required else {
            if stored != nil { throw BiometricApprovalError.unsupportedPolicy }
            return
        }
        guard generation > 0 else { throw BiometricApprovalError.malformed("enrollment") }
        guard let stored, let pinned, stored.publicKey == pinned,
              stored.enrollmentGeneration == generation,
              BiometricApprovalStore.verify(canonical: canonical, signature: stored.signature, publicKey: pinned) else {
            throw BiometricApprovalError.tampered
        }
    }

    private static func signature(publicKeyB64: String?, signatureB64: String?, generation: Int) -> PolicyApprovalSignature? {
        guard let publicKey = publicKeyB64.flatMap({ Data(base64Encoded: $0) }),
              let signature = signatureB64.flatMap({ Data(base64Encoded: $0) }),
              generation > 0 else {
            return nil
        }
        return PolicyApprovalSignature(publicKey: publicKey, signature: signature, enrollmentGeneration: generation)
    }

    private static func encode(
        canonical: Data,
        local: PolicyApprovalSignature?,
        companion: PolicyApprovalSignature?
    ) throws -> Data {
        var object: [String: String] = [
            "canonical_b64": canonical.base64EncodedString(),
        ]
        if let local {
            object["local_generation"] = String(local.enrollmentGeneration)
            object["local_public_key_b64"] = local.publicKey.base64EncodedString()
            object["local_signature_b64"] = local.signature.base64EncodedString()
        }
        if let companion {
            object["companion_generation"] = String(companion.enrollmentGeneration)
            object["companion_public_key_b64"] = companion.publicKey.base64EncodedString()
            object["companion_signature_b64"] = companion.signature.base64EncodedString()
        }
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    private static func decode(_ data: Data) throws -> StoredPolicyApproval {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: String],
              let canonical = object["canonical_b64"].flatMap({ Data(base64Encoded: $0) }) else {
            throw BiometricApprovalError.tampered
        }
        return StoredPolicyApproval(
            canonical: canonical,
            local: signature(
                publicKeyB64: object["local_public_key_b64"],
                signatureB64: object["local_signature_b64"],
                generation: Int(object["local_generation"] ?? "") ?? 0
            ),
            companion: signature(
                publicKeyB64: object["companion_public_key_b64"],
                signatureB64: object["companion_signature_b64"],
                generation: Int(object["companion_generation"] ?? "") ?? 0
            )
        )
    }

    private static func withLock<T>(_ directory: URL, _ body: () throws -> T) throws -> T {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let lockURL = directory.appendingPathComponent("consume.lock")
        let fd = open(lockURL.path, O_CREAT | O_RDWR, 0o600)
        guard fd >= 0 else { throw BiometricApprovalError.malformed("lock") }
        defer { close(fd) }
        guard flock(fd, LOCK_EX) == 0 else { throw BiometricApprovalError.malformed("lock") }
        defer { _ = flock(fd, LOCK_UN) }
        return try body()
    }
}

private struct StoredPolicyApproval {
    var canonical: Data
    var local: PolicyApprovalSignature?
    var companion: PolicyApprovalSignature?
}

/// Argument gate for the development Touch ID diagnostic.
///
/// A refusal returns before any Secure Enclave call. Passing the gate is not
/// authentication and does not approve a run.
enum DescriptorIO {
    static var writeChunk: (Int32, UnsafeRawPointer, Int) -> Int = { fd, buffer, count in
        Darwin.write(fd, buffer, count)
    }
    static var readChunk: (Int32, UnsafeMutableRawPointer, Int) -> Int = { fd, buffer, count in
        Darwin.read(fd, buffer, count)
    }
    static var syncFile: (Int32) -> Int32 = { fd in
        fsync(fd)
    }

    static func writeAll(_ fd: Int32, _ data: Data) throws {
        if !data.isEmpty {
            try data.withUnsafeBytes { raw in
                guard let base = raw.baseAddress else {
                    throw BiometricApprovalError.malformed("directory")
                }
                var offset = 0
                while offset < raw.count {
                    let wrote = writeChunk(fd, base.advanced(by: offset), raw.count - offset)
                    if wrote < 0 {
                        if errno == EINTR { continue }
                        throw BiometricApprovalError.malformed("directory")
                    }
                    if wrote == 0 {
                        throw BiometricApprovalError.malformed("directory")
                    }
                    offset += wrote
                }
            }
        }
        if syncFile(fd) != 0 {
            throw BiometricApprovalError.malformed("directory")
        }
    }

    static func readAll(_ fd: Int32, count expected: Int) throws -> Data {
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while data.count < expected {
            let remaining = expected - data.count
            let count = buffer.withUnsafeMutableBytes { raw -> Int in
                guard let base = raw.baseAddress else { return -1 }
                return readChunk(fd, base, min(remaining, raw.count))
            }
            if count < 0 {
                if errno == EINTR { continue }
                throw BiometricApprovalError.malformed("directory")
            }
            if count == 0 { break }
            data.append(contentsOf: buffer.prefix(count))
        }
        guard data.count == expected else {
            throw BiometricApprovalError.malformed("directory")
        }
        return data
    }
}

public enum TouchIDDiagnosticGate {
    public static func refusal(arguments: [String]) -> String? {
        if arguments.last == "preview" {
            return nil
        }
        if !arguments.contains("--human-invoked") {
            return "Refusing to call Secure Enclave. Re-run only when you will answer the Touch ID prompt yourself, and pass --human-invoked."
        }
        guard let directory = value(after: "--directory", in: arguments) else {
            return "Pass --directory /private/tmp/rs-touchid-diag. The diagnostic will not use the app container."
        }
        if !isIsolated(directory) {
            return "The diagnostic directory must be /private/tmp/rs-touchid-diag or a directory inside it."
        }
        guard let keyID = value(after: "--key-id", in: arguments) else {
            return "Pass --key-id diag-... so this diagnostic cannot select another enrollment."
        }
        if !keyID.hasPrefix("diag-") || keyID.count > 64 {
            return "The key id must start with diag- and stay within 64 characters."
        }
        guard let command = arguments.last else {
            return "Pass one command: preview, enroll, sign, reload, cancel, or revoke."
        }
        if command == "preview" {
            return nil
        }
        guard ["enroll", "sign", "reload", "cancel", "revoke"].contains(command) else {
            return "Pass one command: preview, enroll, sign, reload, cancel, or revoke."
        }
        _ = command
        return nil
    }

    private static func value(after flag: String, in arguments: [String]) -> String? {
        guard let index = arguments.firstIndex(of: flag), arguments.index(after: index) < arguments.endIndex else {
            return nil
        }
        let value = arguments[arguments.index(after: index)]
        if value.hasPrefix("-") || value.isEmpty {
            return nil
        }
        return value
    }

    /// Canonical containment. A `..` segment or a symlink that leaves the diagnostic root is rejected.
    /// `/tmp` is a symlink to `/private/tmp`, including when the leaf directory does not exist yet.
    static let rootPath = "/private/tmp/rs-touchid-diag"
    static let hopLimit = 16

    static func isIsolated(_ path: String) -> Bool {
        guard let resolved = canonicalPath(path) else { return false }
        return contains(resolved)
    }

    /// Opens a directory the caller owns inside the diagnostic root.
    ///
    /// The walk uses `openat` and `AT_SYMLINK_NOFOLLOW`. A symlink is followed only
    /// by reading its target and continuing in filesystem order. Hop exhaustion,
    /// a path that leaves the root, and a directory someone else can write are refusals.
    public static func openOwnedDirectory(_ path: String) throws -> Int32 {
        guard isIsolated(path) else { throw BiometricApprovalError.malformed("directory") }
        let fd = try walk(path)
        var info = stat()
        guard fstat(fd, &info) == 0 else {
            close(fd)
            throw BiometricApprovalError.malformed("directory")
        }
        let type = info.st_mode & S_IFMT
        guard type == S_IFDIR, info.st_uid == getuid(), (info.st_mode & 0o022) == 0 else {
            close(fd)
            throw BiometricApprovalError.malformed("directory")
        }
        guard let opened = openedPath(of: fd), contains(opened) else {
            close(fd)
            throw BiometricApprovalError.malformed("directory")
        }
        return fd
    }

    static func writeExclusive(directoryFD: Int32, name: String, data: Data) throws {
        try validateComponent(name)
        let fd = openat(directoryFD, name, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw BiometricApprovalError.malformed("directory") }
        do {
            try DescriptorIO.writeAll(fd, data)
            close(fd)
        } catch {
            close(fd)
            _ = unlinkat(directoryFD, name, 0)
            throw error
        }
    }

    static func readExclusive(directoryFD: Int32, name: String) throws -> Data {
        try validateComponent(name)
        let fd = openat(directoryFD, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw BiometricApprovalError.malformed("directory") }
        defer { close(fd) }
        var st = stat()
        guard fstat(fd, &st) == 0, (st.st_mode & S_IFMT) == S_IFREG else {
            throw BiometricApprovalError.malformed("directory")
        }
        guard st.st_size >= 0, st.st_size <= 65_536 else {
            throw BiometricApprovalError.malformed("directory")
        }
        return try DescriptorIO.readAll(fd, count: Int(st.st_size))
    }

    public static func openedPath(of fd: Int32) -> String? {
        var buffer = [CChar](repeating: 0, count: Int(PATH_MAX))
        let result = buffer.withUnsafeMutableBufferPointer { pointer -> Int32 in
            guard let base = pointer.baseAddress else { return -1 }
            return fcntl(fd, F_GETPATH, base)
        }
        guard result == 0 else { return nil }
        return String(cString: buffer)
    }

    /// Resolves in filesystem order. Returns nil on hop exhaustion, a missing
    /// intermediate, or an unreadable symlink. A missing final component is kept.
    static func canonicalPath(_ path: String) -> String? {
        guard path.hasPrefix("/"), !path.contains("\0") else { return nil }
        var components = path.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
        var resolved: [String] = []
        var index = 0
        var hops = 0
        while index < components.count {
            let part = components[index]
            if part == "." {
                index += 1
                continue
            }
            if part == ".." {
                guard !resolved.isEmpty else { return nil }
                resolved.removeLast()
                index += 1
                continue
            }
            let next = "/" + (resolved + [part]).joined(separator: "/")
            var info = stat()
            if lstat(next, &info) != 0 {
                guard index == components.count - 1 else { return nil }
                resolved.append(part)
                break
            }
            if (info.st_mode & S_IFMT) == S_IFLNK {
                hops += 1
                guard hops <= hopLimit else { return nil }
                guard let dest = readLink(at: next) else { return nil }
                let rest = Array(components[(index + 1)...])
                let destParts = dest.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
                if dest.hasPrefix("/") {
                    resolved.removeAll()
                }
                components = destParts + rest
                index = 0
                continue
            }
            resolved.append(part)
            index += 1
        }
        if resolved.isEmpty { return "/" }
        return "/" + resolved.joined(separator: "/")
    }

    private static func contains(_ resolved: String) -> Bool {
        if resolved == "/tmp" || resolved == "/private/tmp" || resolved == "/" {
            return false
        }
        return resolved == rootPath || resolved.hasPrefix(rootPath + "/")
    }

    private static func walk(_ path: String) throws -> Int32 {
        var components = path.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
        var fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC)
        guard fd >= 0 else { throw BiometricApprovalError.malformed("directory") }
        var index = 0
        var hops = 0
        while index < components.count {
            let part = components[index]
            if part == "." {
                index += 1
                continue
            }
            if part == ".." {
                let parent = openat(fd, "..", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
                guard parent >= 0 else {
                    close(fd)
                    throw BiometricApprovalError.malformed("directory")
                }
                close(fd)
                fd = parent
                index += 1
                continue
            }
            var info = stat()
            if fstatat(fd, part, &info, AT_SYMLINK_NOFOLLOW) != 0 {
                guard errno == ENOENT, index == components.count - 1, mkdirat(fd, part, 0o700) == 0 else {
                    close(fd)
                    throw BiometricApprovalError.malformed("directory")
                }
                guard let child = openChild(fd, part) else {
                    close(fd)
                    throw BiometricApprovalError.malformed("directory")
                }
                close(fd)
                return child
            }
            if (info.st_mode & S_IFMT) == S_IFLNK {
                hops += 1
                guard hops <= hopLimit else {
                    close(fd)
                    throw BiometricApprovalError.malformed("directory")
                }
                guard let dest = readLink(atDirectory: fd, name: part) else {
                    close(fd)
                    throw BiometricApprovalError.malformed("directory")
                }
                let rest = Array(components[(index + 1)...])
                let destParts = dest.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
                if dest.hasPrefix("/") {
                    close(fd)
                    fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC)
                    guard fd >= 0 else { throw BiometricApprovalError.malformed("directory") }
                }
                components = destParts + rest
                index = 0
                continue
            }
            guard (info.st_mode & S_IFMT) == S_IFDIR, let child = openChild(fd, part) else {
                close(fd)
                throw BiometricApprovalError.malformed("directory")
            }
            close(fd)
            fd = child
            index += 1
        }
        return fd
    }

    private static func openChild(_ directory: Int32, _ name: String) -> Int32? {
        let fd = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        return fd >= 0 ? fd : nil
    }

    private static func readLink(at path: String) -> String? {
        var buffer = [CChar](repeating: 0, count: Int(PATH_MAX))
        let count = buffer.withUnsafeMutableBufferPointer { pointer -> Int in
            guard let base = pointer.baseAddress else { return -1 }
            return readlink(path, base, pointer.count - 1)
        }
        guard count > 0 else { return nil }
        return String(decoding: buffer.prefix(count).map { UInt8(bitPattern: $0) }, as: UTF8.self)
    }

    private static func readLink(atDirectory directory: Int32, name: String) -> String? {
        var buffer = [CChar](repeating: 0, count: Int(PATH_MAX))
        let count = buffer.withUnsafeMutableBufferPointer { pointer -> Int in
            guard let base = pointer.baseAddress else { return -1 }
            return readlinkat(directory, name, base, pointer.count - 1)
        }
        guard count > 0 else { return nil }
        return String(decoding: buffer.prefix(count).map { UInt8(bitPattern: $0) }, as: UTF8.self)
    }

    private static func validateComponent(_ name: String) throws {
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
        guard (1...64).contains(name.count), !name.contains("/"), name.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
            throw BiometricApprovalError.malformed("directory")
        }
    }
}
