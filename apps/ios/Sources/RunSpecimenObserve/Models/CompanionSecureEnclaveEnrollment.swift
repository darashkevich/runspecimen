import CryptoKit
import Foundation
import LocalAuthentication
import os
import Security

private let enrollmentLogger = Logger(subsystem: "com.darashkevich.runspecimen.observe", category: "enrollment")

public enum CompanionHardwareRefusal: Error, Equatable {
    case automationRefused
    case missing
    case malformed(String)
    case staleRequest
    case alreadyEnrolled
    case keyIDRevoked
    case duplicateKeychainItem(OSStatus)
    case keychainError(OSStatus)
    case biometryUnavailable
    case biometryChanged
    case biometryLockout
    case incompleteStage
    case fileReadError(String)
    case fileWriteError(String)
    case rotationIncomplete(oldKeyRevoked: Bool, newKeyCreated: Bool)
}

public extension CompanionHardwareRefusal {
    var userMessage: String {
        switch self {
        case .automationRefused:
            return "Cancelled by user or system."
        case .missing:
            return "No enrollment found for this key."
        case .malformed(let detail):
            return "Invalid state: \(detail)."
        case .staleRequest:
            return "The request has changed since it was displayed."
        case .alreadyEnrolled:
            return "A key with this ID already exists."
        case .keyIDRevoked:
            return "This key ID was revoked. Use a different key ID to enroll a new key."
        case .duplicateKeychainItem:
            return "A keychain item already exists. Delete it manually or use a different key ID."
        case .keychainError(let status):
            return "Keychain operation failed (code \(status))."
        case .biometryUnavailable:
            return "Face ID or Touch ID is not available on this device."
        case .biometryChanged:
            return "Your biometric enrollment has changed. Re-enroll the key."
        case .biometryLockout:
            return "Too many failed attempts. Unlock your device first."
        case .incompleteStage:
            return "Key enrollment was incomplete. Try again."
        case .fileReadError(let path):
            return "Could not read enrollment file at \(path)."
        case .fileWriteError(let path):
            return "Could not write enrollment file at \(path)."
        case .rotationIncomplete(let oldRevoked, let newCreated):
            if oldRevoked && newCreated {
                return "Rotation completed but cleanup failed. Both keys are valid."
            } else if oldRevoked {
                return "Old key was revoked but new key creation failed."
            } else if newCreated {
                return "New key was created but old key revocation failed."
            }
            return "Rotation was interrupted."
        }
    }

    var technicalDetail: String? {
        switch self {
        case .keychainError(let status):
            return "OSStatus: \(status)"
        case .duplicateKeychainItem(let status):
            return "errSecDuplicateItem, OSStatus: \(status)"
        case .malformed(let detail):
            return detail
        case .fileReadError(let path), .fileWriteError(let path):
            return path
        default:
            return nil
        }
    }
}

public struct CompanionPairingRecord: Equatable, Codable {
    public var keyID: String
    public var publicKey: Data
    public var role: String
    public var backend: String
    public var provenance: String
    public var state: String
    public var generation: Int
    public var macUpdatePending: Bool = false

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

struct RotationState: Codable {
    var oldKeyID: String
    var newKeyID: String
    var phase: RotationPhase
    var oldKeyRevoked: Bool
    var newKeyCreated: Bool

    enum RotationPhase: String, Codable {
        case started
        case newKeyStaged
        case newKeyCommitted
        case oldKeyRevoked
        case completed
    }
}

#if RUNSPECIMEN_TEST_HOOKS
@used
@_cdecl("beforeFinalSignatureDecision")
func beforeFinalSignatureDecisionHook() {
    CompanionSecureEnclaveEnrollment.beforeFinalSignatureDecision?()
}
#endif

public enum CompanionSecureEnclaveEnrollment {
    public static let keychainService = "com.darashkevich.runspecimen.observe.biometric"
    public static let active = "active"
    public static let revoked = "revoked"
    static var clock: () -> Int = { Int(Date().timeIntervalSince1970) }

    #if RUNSPECIMEN_TEST_HOOKS
    static var beforeFinalSignatureDecision: (() -> Void)?
    static var testAuthenticator: ((String) throws -> Void)?
    static var testKeyCreator: ((String) throws -> Data)?
    static var testKeyDeleter: ((String) throws -> Void)?
    static var testInMemoryKeychain: [String: Data]?
    #endif

    public static func automationRefused() throws -> Never {
        throw CompanionHardwareRefusal.automationRefused
    }

    public static func enroll(keyID: String, directory: URL) throws -> CompanionPairingRecord {
        try enrollReplacingMissingFile(keyID: keyID, directory: directory) {
            try createEnclaveKey(keyID: keyID)
        } cleanup: {
            try? deleteBlob(keyID: keyID)
        }
    }

    static func enrollReplacingMissingFile(
        keyID: String,
        directory: URL,
        createKey: () throws -> Data,
        cleanup: () -> Void
    ) throws -> CompanionPairingRecord {
        try validateKeyID(keyID)
        return try withLock(directory) {
            do {
                let existing = try load(keyID: keyID, directory: directory)
                if existing.state == active {
                    throw CompanionHardwareRefusal.alreadyEnrolled
                }
                if existing.state == revoked {
                    throw CompanionHardwareRefusal.keyIDRevoked
                }
                throw CompanionHardwareRefusal.malformed("enrollment")
            } catch CompanionHardwareRefusal.missing {
                let publicKey = try createKey()
                let record = CompanionPairingRecord(
                    keyID: keyID,
                    publicKey: publicKey,
                    role: EnrollmentIdentity.roleCompanion,
                    backend: EnrollmentIdentity.backendSecureEnclave,
                    provenance: EnrollmentIdentity.provenanceProduction,
                    state: active,
                    generation: 1,
                    macUpdatePending: true
                )
                try storeEnrollment(record, directory: directory, cleanup: cleanup)
                return record
            }
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

    public static func revoke(keyID: String, directory: URL) async throws -> CompanionPairingRecord {
        try validateKeyID(keyID)
        try await authenticateWithBiometrics(reason: "Authenticate to revoke this iPhone key")
        return try withLock(directory) {
            let record = try load(keyID: keyID, directory: directory)
            return try persistRevocation(record, directory: directory) { _ in
                try deleteBlob(keyID: keyID)
            }
        }
    }

    public static func rotate(from oldKeyID: String, to newKeyID: String, directory: URL) async throws -> (newKey: CompanionPairingRecord, revokedKey: CompanionPairingRecord) {
        try validateKeyID(oldKeyID)
        try validateKeyID(newKeyID)
        guard oldKeyID != newKeyID else {
            throw CompanionHardwareRefusal.malformed("same-key-id")
        }

        try await authenticateWithBiometrics(reason: "Authenticate to rotate this iPhone key")

        return try withLock(directory) {
            try recoverIncompleteRotation(directory: directory)

            let oldRecord = try load(keyID: oldKeyID, directory: directory)
            guard oldRecord.state == active else {
                throw CompanionHardwareRefusal.malformed("enrollment")
            }

            if let existingNew = try? load(keyID: newKeyID, directory: directory),
               existingNew.state == revoked {
                throw CompanionHardwareRefusal.keyIDRevoked
            }

            var state = RotationState(
                oldKeyID: oldKeyID,
                newKeyID: newKeyID,
                phase: .started,
                oldKeyRevoked: false,
                newKeyCreated: false
            )
            try saveRotationState(state, directory: directory)

            let newPublicKey: Data
            do {
                newPublicKey = try createEnclaveKey(keyID: newKeyID)
                state.newKeyCreated = true
                state.phase = .newKeyStaged
                try saveRotationState(state, directory: directory)
            } catch {
                enrollmentLogger.error("Rotation: new key creation failed: \(error.localizedDescription, privacy: .public)")
                try? clearRotationState(directory: directory)
                throw error
            }

            let newRecord = CompanionPairingRecord(
                keyID: newKeyID,
                publicKey: newPublicKey,
                role: EnrollmentIdentity.roleCompanion,
                backend: EnrollmentIdentity.backendSecureEnclave,
                provenance: EnrollmentIdentity.provenanceProduction,
                state: active,
                generation: oldRecord.generation + 1,
                macUpdatePending: true
            )

            do {
                try save(newRecord, directory: directory)
                state.phase = .newKeyCommitted
                try saveRotationState(state, directory: directory)
            } catch {
                enrollmentLogger.error("Rotation: new key save failed: \(error.localizedDescription, privacy: .public)")
                try? deleteBlob(keyID: newKeyID)
                try? clearRotationState(directory: directory)
                throw CompanionHardwareRefusal.fileWriteError(newKeyID)
            }
            let revokedRecord: CompanionPairingRecord
            do {
                revokedRecord = try persistRevocationWithoutCleanup(oldRecord, directory: directory)
                state.oldKeyRevoked = true
                state.phase = .oldKeyRevoked
                try saveRotationState(state, directory: directory)
            } catch {
                enrollmentLogger.error("Rotation: old key revocation failed: \(error.localizedDescription, privacy: .public)")
                throw CompanionHardwareRefusal.rotationIncomplete(oldKeyRevoked: false, newKeyCreated: true)
            }

            do {
                try deleteBlob(keyID: oldKeyID)
            } catch {
                enrollmentLogger.warning("Rotation: old key blob cleanup failed (non-fatal): \(error.localizedDescription, privacy: .public)")
            }

            state.phase = .completed
            try? clearRotationState(directory: directory)

            return (newRecord, revokedRecord)
        }
    }

    public static func recoverIncompleteRotation(directory: URL) throws {
        guard let state = try loadRotationState(directory: directory) else { return }

        enrollmentLogger.info("Recovering incomplete rotation: \(state.phase.rawValue, privacy: .public)")

        switch state.phase {
        case .started:
            try? clearRotationState(directory: directory)
        case .newKeyStaged:
            try? deleteBlob(keyID: state.newKeyID)
            try? clearRotationState(directory: directory)
        case .newKeyCommitted, .oldKeyRevoked:
            try? deleteBlob(keyID: state.oldKeyID)
            try? clearRotationState(directory: directory)
        case .completed:
            try? clearRotationState(directory: directory)
        }
    }

    private static func saveRotationState(_ state: RotationState, directory: URL) throws {
        let url = directory.appendingPathComponent(".rotation-state.json")
        let data = try JSONEncoder().encode(state)
        try data.write(to: url, options: .atomic)
    }

    private static func loadRotationState(directory: URL) throws -> RotationState? {
        let url = directory.appendingPathComponent(".rotation-state.json")
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(RotationState.self, from: data)
    }

    private static func clearRotationState(directory: URL) throws {
        let url = directory.appendingPathComponent(".rotation-state.json")
        try? FileManager.default.removeItem(at: url)
    }

    public static func carriedPairing(keyID: String, directory: URL) throws -> Data {
        try validateKeyID(keyID)
        return try carriedJson(load(keyID: keyID, directory: directory))
    }

    public static func inspect(keyID: String, directory: URL) throws -> CompanionPairingRecord {
        try validateKeyID(keyID)
        return try load(keyID: keyID, directory: directory)
    }

    public static func listKeys(directory: URL) throws -> [CompanionPairingRecord] {
        guard FileManager.default.fileExists(atPath: directory.path) else { return [] }
        let files = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        return files.compactMap { url -> CompanionPairingRecord? in
            guard url.pathExtension == "json", url.lastPathComponent.hasSuffix(".pairing.json") else { return nil }
            let keyID = String(url.lastPathComponent.dropLast(".pairing.json".count))
            return try? load(keyID: keyID, directory: directory)
        }
    }

    public struct KeyListingResult {
        public var validRecords: [CompanionPairingRecord]
        public var corruptKeyIDs: [(keyID: String, error: String)]
    }

    public static func listKeysWithCorrupt(directory: URL) throws -> KeyListingResult {
        guard FileManager.default.fileExists(atPath: directory.path) else {
            return KeyListingResult(validRecords: [], corruptKeyIDs: [])
        }
        let files = try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        var validRecords: [CompanionPairingRecord] = []
        var corruptKeyIDs: [(keyID: String, error: String)] = []

        for url in files {
            guard url.pathExtension == "json", url.lastPathComponent.hasSuffix(".pairing.json") else { continue }
            let keyID = String(url.lastPathComponent.dropLast(".pairing.json".count))
            do {
                let record = try load(keyID: keyID, directory: directory)
                validRecords.append(record)
            } catch let error as CompanionHardwareRefusal {
                corruptKeyIDs.append((keyID: keyID, error: error.userMessage))
            } catch {
                corruptKeyIDs.append((keyID: keyID, error: error.localizedDescription))
            }
        }

        return KeyListingResult(validRecords: validRecords, corruptKeyIDs: corruptKeyIDs)
    }

    public static func markMacUpdated(keyID: String, directory: URL) throws {
        try validateKeyID(keyID)
        try withLock(directory) {
            var record = try load(keyID: keyID, directory: directory)
            record.macUpdatePending = false
            try save(record, directory: directory)
        }
    }

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
        revokedRecord.generation = record.generation + 1
        revokedRecord.macUpdatePending = true
        try save(revokedRecord, directory: directory)
        do {
            try deleteKey(record.publicKey)
        } catch {
            throw CompanionHardwareRefusal.malformed("keychain-cleanup")
        }
        return revokedRecord
    }

    private static func persistRevocationWithoutCleanup(
        _ record: CompanionPairingRecord,
        directory: URL
    ) throws -> CompanionPairingRecord {
        guard record.state == active else {
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        var revokedRecord = record
        revokedRecord.state = revoked
        revokedRecord.generation = record.generation + 1
        revokedRecord.macUpdatePending = true
        try save(revokedRecord, directory: directory)
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
        return try finalizeSignature(
            produced: produced,
            before: before.snapshot,
            keyID: fields.companionKeyID,
            expiryUnix: fields.expiryUnix,
            directory: directory
        )
    }

    static func finalizeSignature(
        produced: Data,
        before: CompanionEnrollmentSnapshot,
        keyID: String,
        expiryUnix: Int,
        directory: URL
    ) throws -> Data {
        try withLock(directory) {
            let readableBeforeWait = try load(keyID: keyID, directory: directory)
            #if RUNSPECIMEN_TEST_HOOKS
            beforeFinalSignatureDecision?()
            #endif
            let after = try load(keyID: keyID, directory: directory)
            guard readableBeforeWait.keyID == after.keyID else {
                throw CompanionHardwareRefusal.malformed("enrollment")
            }
            return try signatureIfStillValid(
                produced: produced,
                before: before,
                after: after.snapshot,
                expiryUnix: expiryUnix,
                now: clock()
            )
        }
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

    private static let processLock = NSLock()

    static func withLock<T>(_ directory: URL, _ body: () throws -> T) throws -> T {
        processLock.lock()
        defer { processLock.unlock() }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let fd = open(directory.appendingPathComponent("enrollment.lock").path, O_CREAT | O_RDWR, 0o600)
        guard fd >= 0 else { throw CompanionHardwareRefusal.malformed("lock") }
        defer { close(fd) }
        guard flock(fd, LOCK_EX) == 0 else { throw CompanionHardwareRefusal.malformed("lock") }
        defer { _ = flock(fd, LOCK_UN) }
        return try body()
    }

    public static func authenticateWithBiometrics(reason: String) async throws {
        #if RUNSPECIMEN_TEST_HOOKS
        if let testAuth = testAuthenticator {
            try testAuth(reason)
            return
        }
        #endif

        let context = LAContext()
        context.localizedFallbackTitle = ""

        var biometryError: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &biometryError) else {
            if let error = biometryError {
                enrollmentLogger.error("Biometry unavailable: \(error.localizedDescription, privacy: .public)")
                switch error.code {
                case LAError.biometryNotAvailable.rawValue:
                    throw CompanionHardwareRefusal.biometryUnavailable
                case LAError.biometryNotEnrolled.rawValue:
                    throw CompanionHardwareRefusal.biometryUnavailable
                case LAError.biometryLockout.rawValue:
                    throw CompanionHardwareRefusal.biometryLockout
                default:
                    throw CompanionHardwareRefusal.biometryUnavailable
                }
            }
            throw CompanionHardwareRefusal.biometryUnavailable
        }

        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: reason) { success, error in
                if success {
                    continuation.resume()
                } else if let error = error as? LAError {
                    enrollmentLogger.info("Face ID result: code=\(error.code.rawValue, privacy: .public)")
                    switch error.code {
                    case .userCancel, .appCancel, .systemCancel:
                        continuation.resume(throwing: CompanionHardwareRefusal.automationRefused)
                    case .biometryLockout:
                        continuation.resume(throwing: CompanionHardwareRefusal.biometryLockout)
                    case .biometryNotEnrolled, .biometryNotAvailable:
                        continuation.resume(throwing: CompanionHardwareRefusal.biometryUnavailable)
                    default:
                        continuation.resume(throwing: CompanionHardwareRefusal.malformed("biometric-\(error.code.rawValue)"))
                    }
                } else if let error {
                    enrollmentLogger.error("Face ID failed: \(error.localizedDescription, privacy: .public)")
                    continuation.resume(throwing: CompanionHardwareRefusal.malformed("biometric"))
                } else {
                    continuation.resume(throwing: CompanionHardwareRefusal.malformed("biometric"))
                }
            }
        }
    }

    private static func createEnclaveKey(keyID: String) throws -> Data {
        #if RUNSPECIMEN_TEST_HOOKS
        if let testCreator = testKeyCreator {
            return try testCreator(keyID)
        }
        #endif

        let context = LAContext()
        context.localizedFallbackTitle = ""
        let key: SecureEnclave.P256.Signing.PrivateKey
        do {
            key = try SecureEnclave.P256.Signing.PrivateKey(
                accessControl: try accessControl(),
                authenticationContext: context
            )
        } catch {
            enrollmentLogger.error("Secure Enclave key creation failed: \(error.localizedDescription, privacy: .public)")
            throw CompanionHardwareRefusal.malformed("secure-enclave")
        }
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
            throw CompanionHardwareRefusal.malformed("key-id")
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
        do {
            try data.write(to: temporary, options: .atomic)
        } catch {
            enrollmentLogger.error("Failed to write temp file: \(error.localizedDescription, privacy: .public)")
            throw CompanionHardwareRefusal.fileWriteError(temporary.path)
        }
        if FileManager.default.fileExists(atPath: destination.path) {
            _ = try FileManager.default.replaceItemAt(destination, withItemAt: temporary)
        } else {
            try FileManager.default.moveItem(at: temporary, to: destination)
        }
    }

    private static func load(keyID: String, directory: URL) throws -> CompanionPairingRecord {
        try validateKeyID(keyID)
        let url = fileURL(keyID: keyID, directory: directory)
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw CompanionHardwareRefusal.missing
        }
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            enrollmentLogger.error("Failed to read enrollment file: \(error.localizedDescription, privacy: .public)")
            throw CompanionHardwareRefusal.fileReadError(url.path)
        }
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            enrollmentLogger.error("Enrollment file is not valid JSON")
            throw CompanionHardwareRefusal.malformed("json")
        }
        guard object["key_id"] as? String == keyID,
              let publicKeyB64 = object["public_key_x963_b64"] as? String,
              let publicKey = Data(base64Encoded: publicKeyB64),
              publicKey.count == 65,
              let role = object["role"] as? String,
              let backend = object["backend"] as? String,
              let provenance = object["provenance"] as? String,
              let state = object["state"] as? String,
              let generation = (object["generation"] as? Int) ?? Int(object["generation"] as? String ?? ""),
              generation > 0,
              state == active || state == revoked else {
            enrollmentLogger.error("Enrollment file has invalid structure for keyID: \(keyID, privacy: .public)")
            throw CompanionHardwareRefusal.malformed("enrollment")
        }
        guard EnrollmentIdentity.isRecognized(role: role, backend: backend, provenance: provenance) else {
            enrollmentLogger.error("Enrollment identity not recognized for keyID: \(keyID, privacy: .public)")
            throw CompanionHardwareRefusal.malformed("identity")
        }
        let macUpdatePending = object["mac_update_pending"] as? Bool ?? false
        return CompanionPairingRecord(
            keyID: keyID,
            publicKey: publicKey,
            role: role,
            backend: backend,
            provenance: provenance,
            state: state,
            generation: generation,
            macUpdatePending: macUpdatePending
        )
    }

    private static func json(_ record: CompanionPairingRecord) throws -> Data {
        var object: [String: Any] = [
            "backend": record.backend,
            "generation": record.generation,
            "key_id": record.keyID,
            "provenance": record.provenance,
            "public_key_x963_b64": record.publicKey.base64EncodedString(),
            "role": record.role,
            "state": record.state,
        ]
        if record.macUpdatePending {
            object["mac_update_pending"] = true
        }
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    private static func carriedJson(_ record: CompanionPairingRecord) throws -> Data {
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
            throw CompanionHardwareRefusal.malformed("access-control")
        }
        return access
    }

    private static func saveBlob(_ data: Data, keyID: String) throws {
        #if RUNSPECIMEN_TEST_HOOKS
        if testKeyCreator != nil { return }
        if testInMemoryKeychain != nil {
            testInMemoryKeychain?[keyID] = data
            return
        }
        #endif

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keyID,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        ]
        let status = SecItemAdd(query as CFDictionary, nil)
        if status == errSecDuplicateItem {
            enrollmentLogger.error("Keychain duplicate for keyID \(keyID, privacy: .public)")
            throw CompanionHardwareRefusal.duplicateKeychainItem(status)
        }
        guard status == errSecSuccess else {
            enrollmentLogger.error("Keychain save failed for keyID \(keyID, privacy: .public): OSStatus \(status)")
            throw CompanionHardwareRefusal.keychainError(status)
        }
    }

    private static func loadBlob(keyID: String) throws -> Data {
        #if RUNSPECIMEN_TEST_HOOKS
        if let inMemory = testInMemoryKeychain {
            guard let data = inMemory[keyID] else {
                throw CompanionHardwareRefusal.keychainError(errSecItemNotFound)
            }
            return data
        }
        #endif

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
            enrollmentLogger.error("Keychain load failed for keyID \(keyID, privacy: .public): OSStatus \(status)")
            throw CompanionHardwareRefusal.keychainError(status)
        }
        return data
    }

    static func deleteBlob(keyID: String) throws {
        #if RUNSPECIMEN_TEST_HOOKS
        if let testDeleter = testKeyDeleter {
            try testDeleter(keyID)
            return
        }
        if testInMemoryKeychain != nil {
            testInMemoryKeychain?.removeValue(forKey: keyID)
            return
        }
        #endif

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keyID,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            enrollmentLogger.error("Keychain delete failed for keyID \(keyID, privacy: .public): OSStatus \(status)")
            throw CompanionHardwareRefusal.keychainError(status)
        }
    }

    public static func deleteOrphanedBlob(keyID: String) throws {
        try validateKeyID(keyID)
        try deleteBlob(keyID: keyID)
    }

    public static func deriveReplacementKeyID(from baseKeyID: String, existingKeyIDs: Set<String>) -> String {
        guard !baseKeyID.isEmpty else {
            return findAvailableID(prefix: "iphone-companion", startN: 2, existingKeyIDs: existingKeyIDs)
        }

        if let match = baseKeyID.range(of: #"-(\d+)$"#, options: .regularExpression),
           let n = Int(baseKeyID[match].dropFirst()) {
            let prefix = String(baseKeyID[..<match.lowerBound])
            return findAvailableID(prefix: prefix, startN: n + 1, existingKeyIDs: existingKeyIDs)
        } else {
            return findAvailableID(prefix: baseKeyID, startN: 2, existingKeyIDs: existingKeyIDs)
        }
    }

    private static func findAvailableID(prefix: String, startN: Int, existingKeyIDs: Set<String>) -> String {
        var n = startN
        while true {
            let candidate = "\(prefix)-\(n)"
            if !existingKeyIDs.contains(candidate) {
                return candidate
            }
            n += 1
            if n > 9999 {
                return "\(prefix)-\(startN)-overflow"
            }
        }
    }
}
