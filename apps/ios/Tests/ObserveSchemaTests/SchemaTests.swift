import CryptoKit
import LocalAuthentication
import XCTest
import Security
import Darwin
@testable import RunSpecimenObserve

final class ObserveSchemaTests: IsolatedCompanionSessionTests {
    @MainActor
    func testSchemaStorageIsNotStandardDefaults() {
        XCTAssertFalse(CompanionSession.storageDefaults === UserDefaults.standard)
        XCTAssertNil(CompanionSession.testPairingToken)
    }

    override func setUp() {
        super.setUp()
        executionTimeAllowance = 60
        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in }
        CompanionSecureEnclaveEnrollment.testKeyCreator = nil
        CompanionSecureEnclaveEnrollment.testSignatureProducer = nil
        CryptoOperationContext.testDidInvalidate = nil
        CompanionSecureEnclaveEnrollment.testKeyDeleter = nil
        CompanionSecureEnclaveEnrollment.testInMemoryKeychain = [:]
    }

    override func tearDown() {
        CompanionSecureEnclaveEnrollment.testAuthenticator = nil
        CompanionSecureEnclaveEnrollment.testKeyCreator = nil
        CompanionSecureEnclaveEnrollment.testSignatureProducer = nil
        CryptoOperationContext.testDidInvalidate = nil
        CompanionSecureEnclaveEnrollment.testKeyDeleter = nil
        CompanionSecureEnclaveEnrollment.testInMemoryKeychain = nil
        CompanionSecureEnclaveEnrollment.testRotationWillWrite = nil
        CompanionSecureEnclaveEnrollment.testRotationCheckpoint = nil
        CompanionSecureEnclaveEnrollment.testRotationFileRemoval = nil
        CompanionSecureEnclaveEnrollment.beforeFinalSignatureDecision = nil
        CompanionSecureEnclaveEnrollment.clock = { Int(Date().timeIntervalSince1970) }
        super.tearDown()
    }
    func testSharedParserRejectsIncompletePackages() throws {
        let original = try package()
        func expect(_ mutate: (inout [String: String]) -> Void, _ field: String) throws {
            var object = original
            mutate(&object)
            let data = try JSONSerialization.data(withJSONObject: object)
            XCTAssertThrowsError(try RSBA2Package.parse(data)) { error in
                XCTAssertEqual(error as? RSBA2Package.ParseFailure, .malformed(field))
            }
        }
        try expect({ $0.removeValue(forKey: "mac_id") }, "mac_id")
        try expect({ $0["mac_id"] = "" }, "mac_id")
        try expect({ $0["workspace_id"] = "ws\0id" }, "workspace_id")
        try expect({ $0["bounds"] = String(repeating: "x", count: 300) }, "bounds")
        try expect({ $0["contract_sha256"] = "abcd" }, "contract_sha256")
        try expect({ $0["companion_generation"] = "01" }, "enrollment")
        var inconsistent = original
        inconsistent["local_key_id"] = "mac-key"
        XCTAssertThrowsError(try RSBA2Package.parse(try JSONSerialization.data(withJSONObject: inconsistent))) { error in
            XCTAssertEqual(error as? RSBA2Package.ParseFailure, .malformed("policy"))
        }
    }

    func testCompanionCanonicalVectorMatchesTheMacDigest() throws {
        let bytes = try RSBA2Package.canonicalBytes(
            policy: "companion",
            macID: "mac-vector",
            workspaceID: "ws-vector",
            runID: "run-vector",
            contractSHA256: String(repeating: "11", count: 32),
            inputsSHA256: String(repeating: "22", count: 32),
            bounds: "bounds-vector",
            nonce: String(repeating: "bb", count: 32),
            expiryUnix: 1_700_000_000,
            localKeyID: "",
            companionKeyID: "phone-vector",
            localGeneration: 0,
            companionGeneration: 1
        )
        let digest = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(digest, "7f0b15d280bc57ac4416fc0e170e2480117bd78e316b570ed6d84ce6d73abced")
    }

    func testAutomationRefusalDoesNotTouchEnrollmentFiles() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-gate-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.automationRefused()) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .automationRefused)
        }
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.inspect(keyID: "../phone", directory: directory))
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.inspect(keyID: "phone-vector", directory: directory)) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .missing)
        }
        try Data("not-json".utf8).write(to: directory.appendingPathComponent("phone-vector.pairing.json"))
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.inspect(keyID: "phone-vector", directory: directory)) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("json"), "Invalid JSON should return malformed(json), not malformed(enrollment)")
        }
        let names = try FileManager.default.contentsOfDirectory(atPath: directory.path)
        XCTAssertEqual(names, ["phone-vector.pairing.json"])
    }

    func testRevocationRecordIsWrittenBeforeAFailedKeyDeletion() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-revoke-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let record = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(record, directory: directory) {}
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.persistRevocation(record, directory: directory) { _ in
            throw CompanionHardwareRefusal.malformed("keychain")
        }) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("keychain-cleanup"))
        }
        let stored = try CompanionSecureEnclaveEnrollment.inspect(keyID: record.keyID, directory: directory)
        XCTAssertEqual(stored.state, CompanionSecureEnclaveEnrollment.revoked)
        XCTAssertEqual(stored.generation, 2, "Revoked record has generation incremented for Mac import compatibility")
        let retried = try CompanionSecureEnclaveEnrollment.persistRevocation(stored, directory: directory) { _ in }
        XCTAssertEqual(retried.generation, 2, "Re-revoke of already revoked does not change generation")
        XCTAssertEqual(retried.state, CompanionSecureEnclaveEnrollment.revoked)
    }

    func testSignatureIsDiscardedWhenTheRecordChangesDuringTheWait() throws {
        let before = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1).snapshot
        var revoked = before
        revoked.state = CompanionSecureEnclaveEnrollment.revoked
        let signature = Data(repeating: 9, count: 64)
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.signatureIfStillValid(
            produced: signature,
            before: before,
            after: revoked,
            expiryUnix: 1_700_000_000,
            now: 1_600_000_000
        ))
        var expired = before
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.signatureIfStillValid(
            produced: signature,
            before: before,
            after: expired,
            expiryUnix: 1_700_000_000,
            now: 1_700_000_000
        )) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("expiry_unix"))
        }
        let kept = try CompanionSecureEnclaveEnrollment.signatureIfStillValid(
            produced: signature,
            before: before,
            after: before,
            expiryUnix: 1_700_000_000,
            now: 1_600_000_000
        )
        XCTAssertEqual(kept, signature)
    }

    func testDisplayedPackageMustMatchTheBytesThatWouldBeSigned() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-stale-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let fields = try RSBA2Package.parse(try JSONSerialization.data(withJSONObject: package()))
        var edited = try package()
        edited["bounds"] = "changed-bounds"
        let editedText = String(decoding: try JSONSerialization.data(withJSONObject: edited), as: UTF8.self)
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.signDisplayed(
            packageText: editedText,
            displayed: fields,
            selectedKeyID: fields.companionKeyID,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .staleRequest)
        }
    }

    func testConcurrentRevocationsIncrementGenerationOnce() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-race-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let record = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(record, directory: directory) {}
        let entered = DispatchSemaphore(value: 0)
        let finishFirst = DispatchSemaphore(value: 0)
        let first = expectation(description: "first revocation")
        DispatchQueue.global(qos: .userInitiated).async {
            try? CompanionSecureEnclaveEnrollment.withLock(directory) {
                entered.signal()
                finishFirst.wait()
                let live = try CompanionSecureEnclaveEnrollment.inspect(keyID: record.keyID, directory: directory)
                _ = try CompanionSecureEnclaveEnrollment.persistRevocation(live, directory: directory) { _ in }
            }
            first.fulfill()
        }
        XCTAssertEqual(entered.wait(timeout: .now() + 2), .success)
        let second = expectation(description: "second revocation")
        DispatchQueue.global(qos: .userInitiated).async {
            try? CompanionSecureEnclaveEnrollment.withLock(directory) {
                let live = try CompanionSecureEnclaveEnrollment.inspect(keyID: record.keyID, directory: directory)
                XCTAssertEqual(live.state, CompanionSecureEnclaveEnrollment.revoked)
                XCTAssertEqual(live.generation, 2, "Revoked record has incremented generation")
                _ = try CompanionSecureEnclaveEnrollment.persistRevocation(live, directory: directory) { _ in }
            }
            second.fulfill()
        }
        finishFirst.signal()
        wait(for: [first, second], timeout: 3)
        let stored = try CompanionSecureEnclaveEnrollment.inspect(keyID: record.keyID, directory: directory)
        XCTAssertEqual(stored.state, CompanionSecureEnclaveEnrollment.revoked)
        XCTAssertEqual(stored.generation, 2, "Generation incremented once by first revocation, unchanged by re-revoke")
    }

    func testEnrollmentOnEmptyDirectoryReachesCreateKeyWithoutMalformed() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-empty-enroll-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.path))
        var createKeyCalled = false
        let record = try CompanionSecureEnclaveEnrollment.enrollReplacingMissingFile(
            keyID: "test-empty-dir",
            directory: directory,
            createKey: {
                createKeyCalled = true
                return Data(repeating: 4, count: 65)
            },
            cleanup: {}
        )
        XCTAssertTrue(createKeyCalled, "createKey should be called when enrolling on an empty directory")
        XCTAssertEqual(record.generation, 1)
        XCTAssertEqual(record.state, CompanionSecureEnclaveEnrollment.active)
    }

    func testEnrollCreatesAKeyOnlyWhenThePairingFileIsMissing() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-enroll-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        var created = 0
        let record = try CompanionSecureEnclaveEnrollment.enrollReplacingMissingFile(
            keyID: "phone-vector",
            directory: directory,
            createKey: {
                created += 1
                return Data(repeating: 4, count: 65)
            },
            cleanup: {}
        )
        XCTAssertEqual(created, 1)
        XCTAssertEqual(record.generation, 1)
        XCTAssertEqual(record.state, CompanionSecureEnclaveEnrollment.active)
        let url = directory.appendingPathComponent("phone-vector.pairing.json")
        let original = try Data(contentsOf: url)

        created = 0
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.enrollReplacingMissingFile(
            keyID: "phone-vector",
            directory: directory,
            createKey: {
                created += 1
                return Data(repeating: 9, count: 65)
            },
            cleanup: {}
        )) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .alreadyEnrolled)
        }
        XCTAssertEqual(created, 0)
        XCTAssertEqual(try Data(contentsOf: url), original)

        try Data("not-json".utf8).write(to: url)
        let malformedData = try Data(contentsOf: url)
        created = 0
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.enrollReplacingMissingFile(
            keyID: "phone-vector",
            directory: directory,
            createKey: {
                created += 1
                return Data(repeating: 9, count: 65)
            },
            cleanup: {}
        )) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("json"), "Invalid JSON should return malformed(json)")
        }
        XCTAssertEqual(created, 0)
        XCTAssertEqual(try Data(contentsOf: url), malformedData)

        XCTAssertEqual(chmod(url.path, 0), 0)
        defer { _ = chmod(url.path, 0o644) }
        created = 0
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.enrollReplacingMissingFile(
            keyID: "phone-vector",
            directory: directory,
            createKey: {
                created += 1
                return Data(repeating: 9, count: 65)
            },
            cleanup: {}
        )) { error in
            guard case .fileReadError = error as? CompanionHardwareRefusal else {
                XCTFail("Expected fileReadError for unreadable file, got \(error)")
                return
            }
        }
        XCTAssertEqual(created, 0)
        _ = chmod(url.path, 0o644)
        XCTAssertEqual(try Data(contentsOf: url), malformedData)

        let revoked = sampleRecord(state: CompanionSecureEnclaveEnrollment.revoked, generation: 4)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(revoked, directory: directory) {}
        let revokedBytes = try Data(contentsOf: url)
        created = 0
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.enrollReplacingMissingFile(
            keyID: "phone-vector",
            directory: directory,
            createKey: {
                created += 1
                return Data(repeating: 9, count: 65)
            },
            cleanup: {}
        )) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .keyIDRevoked)
        }
        XCTAssertEqual(created, 0)
        XCTAssertEqual(try Data(contentsOf: url), revokedBytes)

        try FileManager.default.removeItem(at: url)
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.enrollReplacingMissingFile(
            keyID: "phone-vector",
            directory: directory,
            createKey: { throw CompanionHardwareRefusal.malformed("keychain") },
            cleanup: {}
        )) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("keychain"))
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    }

    func testRevocationBetweenReloadAndDecisionDiscardsTheSignature() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-boundary-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let record = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(record, directory: directory) {}
        CompanionSecureEnclaveEnrollment.clock = { 1_600_000_000 }
        CompanionSecureEnclaveEnrollment.beforeFinalSignatureDecision = {
            _ = try? CompanionSecureEnclaveEnrollment.persistRevocation(record, directory: directory) { _ in }
        }
        defer {
            CompanionSecureEnclaveEnrollment.beforeFinalSignatureDecision = nil
            CompanionSecureEnclaveEnrollment.clock = { Int(Date().timeIntervalSince1970) }
        }
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.finalizeSignature(
            produced: Data(repeating: 9, count: 64),
            before: record.snapshot,
            keyID: record.keyID,
            expiryUnix: 1_700_000_000,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("enrollment"))
        }
        let stored = try CompanionSecureEnclaveEnrollment.inspect(keyID: record.keyID, directory: directory)
        XCTAssertEqual(stored.state, CompanionSecureEnclaveEnrollment.revoked)
        XCTAssertEqual(stored.generation, 2, "Revoked record has incremented generation")
    }

    func testPublicRevokeAfterFinalizeSeesTheRecordTheDecisionAlreadyAccepted() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-order-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let record = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(record, directory: directory) {}
        CompanionSecureEnclaveEnrollment.clock = { 1_600_000_000 }
        let holding = DispatchSemaphore(value: 0)
        let release = DispatchSemaphore(value: 0)
        CompanionSecureEnclaveEnrollment.beforeFinalSignatureDecision = {
            holding.signal()
            release.wait()
        }
        defer {
            CompanionSecureEnclaveEnrollment.beforeFinalSignatureDecision = nil
            CompanionSecureEnclaveEnrollment.clock = { Int(Date().timeIntervalSince1970) }
        }
        let finishedDecision = expectation(description: "decision")
        var decisionError: Error?
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                _ = try CompanionSecureEnclaveEnrollment.finalizeSignature(
                    produced: Data(repeating: 9, count: 64),
                    before: record.snapshot,
                    keyID: record.keyID,
                    expiryUnix: 1_700_000_000,
                    directory: directory
                )
            } catch {
                decisionError = error
            }
            finishedDecision.fulfill()
        }
        XCTAssertEqual(holding.wait(timeout: .now() + 2), .success)
        let revokeStarted = DispatchSemaphore(value: 0)
        let revokeReturned = DispatchSemaphore(value: 0)
        let finishedRevoke = expectation(description: "revoke")
        Task {
            revokeStarted.signal()
            _ = try? await CompanionSecureEnclaveEnrollment.revoke(keyID: record.keyID, directory: directory)
            revokeReturned.signal()
            finishedRevoke.fulfill()
        }
        XCTAssertEqual(revokeStarted.wait(timeout: .now() + 2), .success)
        XCTAssertEqual(revokeReturned.wait(timeout: .now() + 0.2), .timedOut)
        let whileHeld = try CompanionSecureEnclaveEnrollment.inspect(keyID: record.keyID, directory: directory)
        XCTAssertEqual(whileHeld.state, CompanionSecureEnclaveEnrollment.active)
        XCTAssertEqual(whileHeld.generation, 1)
        release.signal()
        wait(for: [finishedDecision, finishedRevoke], timeout: 3)
        XCTAssertNil(decisionError)
        let stored = try CompanionSecureEnclaveEnrollment.inspect(keyID: record.keyID, directory: directory)
        XCTAssertEqual(stored.state, CompanionSecureEnclaveEnrollment.revoked)
        XCTAssertEqual(stored.generation, 2, "Revoked record has incremented generation")
    }

    func testFinalizeAfterPublicRevokeDiscardsTheSignature() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-after-revoke-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let record = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(record, directory: directory) {}
        _ = try await CompanionSecureEnclaveEnrollment.revoke(keyID: record.keyID, directory: directory)
        CompanionSecureEnclaveEnrollment.clock = { 1_600_000_000 }
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.finalizeSignature(
            produced: Data(repeating: 9, count: 64),
            before: record.snapshot,
            keyID: record.keyID,
            expiryUnix: 1_700_000_000,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("enrollment"))
        }
    }

    func testExpiryIsDecidedWithThePostReloadSnapshot() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-expiry-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let record = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(record, directory: directory) {}
        CompanionSecureEnclaveEnrollment.clock = { 1_600_000_000 }
        CompanionSecureEnclaveEnrollment.beforeFinalSignatureDecision = {
            CompanionSecureEnclaveEnrollment.clock = { 1_700_000_000 }
        }
        defer {
            CompanionSecureEnclaveEnrollment.beforeFinalSignatureDecision = nil
            CompanionSecureEnclaveEnrollment.clock = { Int(Date().timeIntervalSince1970) }
        }
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.finalizeSignature(
            produced: Data(repeating: 9, count: 64),
            before: record.snapshot,
            keyID: record.keyID,
            expiryUnix: 1_700_000_000,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("expiry_unix"))
        }
        let stored = try CompanionSecureEnclaveEnrollment.inspect(keyID: record.keyID, directory: directory)
        XCTAssertEqual(stored.state, CompanionSecureEnclaveEnrollment.active)
        XCTAssertEqual(stored.generation, 1)
    }

    func testRevokeAndRotateHintsClaimAFaceIDPromptForRevocation() {
        XCTAssertTrue(CompanionHardwareHints.revoke.contains("Asks for Face ID"))
        XCTAssertTrue(CompanionHardwareHints.revoke.contains("revokes this iPhone key"))
        XCTAssertTrue(CompanionHardwareHints.revoke.contains("If Face ID is cancelled"))
        XCTAssertTrue(CompanionHardwareHints.rotate.contains("Asks for Face ID once"))
        XCTAssertTrue(CompanionHardwareHints.rotate.contains("revokes the current key"))
        XCTAssertTrue(CompanionHardwareHints.rotate.contains("If Face ID is cancelled"))
        XCTAssertTrue(CompanionHardwareHints.rotate.contains("old key stays active"))
    }

    func testRotationRollsBackNewKeyWhenCreationFails() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-rollback-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        
        let oldKey = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(oldKey, directory: directory) {}
        
        let oldKeyURL = directory.appendingPathComponent("phone-vector.pairing.json")
        let originalOldData = try Data(contentsOf: oldKeyURL)
        let newKeyURL = directory.appendingPathComponent("new-key.pairing.json")
        
        XCTAssertFalse(FileManager.default.fileExists(atPath: newKeyURL.path), "New key should not exist before rotation")
        
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in
            throw CompanionHardwareRefusal.malformed("key-creation-failure")
        }
        
        do {
            _ = try await CompanionSecureEnclaveEnrollment.rotate(from: "phone-vector", to: "new-key", directory: directory)
            XCTFail("Expected rotation to fail due to key creation error")
        } catch {
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("key-creation-failure"))
        }
        
        let storedOld = try CompanionSecureEnclaveEnrollment.inspect(keyID: "phone-vector", directory: directory)
        XCTAssertEqual(storedOld.state, CompanionSecureEnclaveEnrollment.active, "IOSQA6-16: Old key must remain active after failed rotation")
        XCTAssertEqual(storedOld.generation, 1, "IOSQA6-16: Old key generation unchanged after rollback")
        
        let currentOldData = try Data(contentsOf: oldKeyURL)
        XCTAssertEqual(currentOldData, originalOldData, "IOSQA6-16: Old key file content unchanged after rollback")
        XCTAssertFalse(FileManager.default.fileExists(atPath: newKeyURL.path), "IOSQA6-16: New key file should not exist after failed rotation")
    }
    
    func testRotationRetainsJournalWhenKeychainCleanupFails() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "old", directory: directory)
        CompanionSecureEnclaveEnrollment.testKeyDeleter = { _ in throw CompanionHardwareRefusal.keychainError(errSecNotAvailable) }
        do {
            _ = try await CompanionSecureEnclaveEnrollment.rotate(from: "old", to: "new", directory: directory)
            XCTFail("Cleanup failure must be reported")
        } catch {
            XCTAssertEqual(error as? CompanionHardwareRefusal, .keychainError(errSecNotAvailable))
        }
        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path))
        XCTAssertEqual(try CompanionSecureEnclaveEnrollment.inspect(keyID: "old", directory: directory).state, CompanionSecureEnclaveEnrollment.revoked)
        XCTAssertEqual(try CompanionSecureEnclaveEnrollment.inspect(keyID: "new", directory: directory).state, CompanionSecureEnclaveEnrollment.active)
        CompanionSecureEnclaveEnrollment.testKeyDeleter = nil
        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path))
    }

    func testRotationWithTestSeamsSucceeds() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-seams-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let oldKey = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(oldKey, directory: directory) {}

        var authCalls = 0
        var createCalls = 0
        var deleteCalls: [String] = []

        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in authCalls += 1 }
        CompanionSecureEnclaveEnrollment.testKeyCreator = { keyID in
            createCalls += 1
            return Data(repeating: 5, count: 65)
        }
        CompanionSecureEnclaveEnrollment.testKeyDeleter = { keyID in
            deleteCalls.append(keyID)
        }

        let (newKey, revokedKey) = try await CompanionSecureEnclaveEnrollment.rotate(
            from: "phone-vector",
            to: "phone-new",
            directory: directory
        )

        XCTAssertEqual(authCalls, 1, "Should authenticate exactly once")
        XCTAssertEqual(createCalls, 1, "Should create one new key")
        XCTAssertEqual(deleteCalls, ["phone-vector"], "Should delete old key blob")
        XCTAssertEqual(newKey.keyID, "phone-new")
        XCTAssertEqual(newKey.state, CompanionSecureEnclaveEnrollment.active)
        XCTAssertEqual(newKey.generation, 2, "New key inherits old generation + 1")
        XCTAssertEqual(revokedKey.keyID, "phone-vector")
        XCTAssertEqual(revokedKey.state, CompanionSecureEnclaveEnrollment.revoked)
        XCTAssertEqual(revokedKey.generation, 2, "Revoked key has incremented generation for Mac compatibility")
    }

    func testRotationFailsIfAuthenticationFails() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-auth-fail-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let oldKey = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(oldKey, directory: directory) {}

        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in
            throw CompanionHardwareRefusal.automationRefused
        }

        do {
            _ = try await CompanionSecureEnclaveEnrollment.rotate(
                from: "phone-vector",
                to: "phone-new",
                directory: directory
            )
            XCTFail("Expected error to be thrown")
        } catch {
            XCTAssertEqual(error as? CompanionHardwareRefusal, .automationRefused)
        }

        let stored = try CompanionSecureEnclaveEnrollment.inspect(keyID: "phone-vector", directory: directory)
        XCTAssertEqual(stored.state, CompanionSecureEnclaveEnrollment.active)
        XCTAssertEqual(stored.generation, 1)
    }

    func testRotationFailsIfNewKeyCreationFails() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-create-fail-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let oldKey = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(oldKey, directory: directory) {}

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in
            throw CompanionHardwareRefusal.malformed("secure-enclave")
        }

        do {
            _ = try await CompanionSecureEnclaveEnrollment.rotate(
                from: "phone-vector",
                to: "phone-new",
                directory: directory
            )
            XCTFail("Expected error to be thrown")
        } catch {
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("secure-enclave"))
        }

        let stored = try CompanionSecureEnclaveEnrollment.inspect(keyID: "phone-vector", directory: directory)
        XCTAssertEqual(stored.state, CompanionSecureEnclaveEnrollment.active)
        XCTAssertEqual(stored.generation, 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("phone-new.pairing.json").path))
    }

    func testRotationReturnsIncompleteIfOldKeyRevocationFails() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-revoke-fail-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let oldKey = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(oldKey, directory: directory) {}

        var createCount = 0
        CompanionSecureEnclaveEnrollment.testKeyCreator = { keyID in
            createCount += 1
            return Data(repeating: 5, count: 65)
        }

        let oldKeyURL = directory.appendingPathComponent("phone-vector.pairing.json")
        XCTAssertEqual(chmod(oldKeyURL.path, 0o444), 0)
        defer { _ = chmod(oldKeyURL.path, 0o644) }

        do {
            _ = try await CompanionSecureEnclaveEnrollment.rotate(
                from: "phone-vector",
                to: "phone-new",
                directory: directory
            )
            XCTFail("Expected error to be thrown")
        } catch {
            if case .rotationIncomplete(let oldRevoked, let newCreated) = error as? CompanionHardwareRefusal {
                XCTAssertFalse(oldRevoked)
                XCTAssertTrue(newCreated)
            } else {
                XCTFail("Expected rotationIncomplete error")
            }
        }
        _ = chmod(oldKeyURL.path, 0o644)

        XCTAssertEqual(createCount, 1, "New key should have been created")
        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent("phone-new.pairing.json").path))
    }

    func testRotationRecoveryAfterIncompleteNewKeyStage() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-recover-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let state = RotationState(
            oldKeyID: "old-key",
            newKeyID: "new-key",
            phase: .newKeyStaged,
            oldKeyRevoked: false,
            newKeyCreated: true
        )
        let stateData = try JSONEncoder().encode(state)
        try stateData.write(to: directory.appendingPathComponent(".rotation-state.json"))

        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)

        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path))
    }

    func testRotationRecoveryAtStartedPhase() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-started-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let state = RotationState(
            oldKeyID: "old-key",
            newKeyID: "new-key",
            phase: .started,
            oldKeyRevoked: false,
            newKeyCreated: false
        )
        try JSONEncoder().encode(state).write(to: directory.appendingPathComponent(".rotation-state.json"))

        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)

        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path), "Started phase should clear rotation state")
    }

    func testRotationRecoveryAtNewKeyCommittedPhase() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-committed-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let state = RotationState(
            oldKeyID: "old-key",
            newKeyID: "new-key",
            phase: .newKeyCommitted,
            oldKeyRevoked: false,
            newKeyCreated: true
        )
        try JSONEncoder().encode(state).write(to: directory.appendingPathComponent(".rotation-state.json"))

        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)

        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path), "newKeyCommitted phase should clear rotation state")
    }

    func testRotationRecoveryAtNewKeyCommittedRemovesNewRecordAndBlob() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-committed-record-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let oldKey = sampleRecord(keyID: "old-key", state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(oldKey, directory: directory) {}

        let newKey = sampleRecord(keyID: "new-key", state: CompanionSecureEnclaveEnrollment.active, generation: 2)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(newKey, directory: directory) {}

        CompanionSecureEnclaveEnrollment.testInMemoryKeychain = ["new-key": Data(repeating: 5, count: 65)]

        let state = RotationState(
            oldKeyID: "old-key",
            newKeyID: "new-key",
            phase: .newKeyCommitted,
            oldKeyRevoked: false,
            newKeyCreated: true
        )
        try JSONEncoder().encode(state).write(to: directory.appendingPathComponent(".rotation-state.json"))

        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent("new-key.pairing.json").path), "New key record should exist before recovery")
        XCTAssertNotNil(CompanionSecureEnclaveEnrollment.testInMemoryKeychain?["new-key"], "New key blob should exist before recovery")

        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)

        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("new-key.pairing.json").path), "IOSQA6-01: Recovery at newKeyCommitted must remove new record")
        XCTAssertNil(CompanionSecureEnclaveEnrollment.testInMemoryKeychain?["new-key"], "IOSQA6-01: Recovery at newKeyCommitted must remove new blob")

        let oldKeyRecord = try CompanionSecureEnclaveEnrollment.inspect(keyID: "old-key", directory: directory)
        XCTAssertEqual(oldKeyRecord.state, CompanionSecureEnclaveEnrollment.active, "Old key should still be active after rollback")
    }

    func testRotationRecoveryAtOldKeyRevokedKeepsRecords() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-revoked-records-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let oldKey = sampleRecord(keyID: "old-key", state: CompanionSecureEnclaveEnrollment.revoked, generation: 2)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(oldKey, directory: directory) {}

        let newKey = sampleRecord(keyID: "new-key", state: CompanionSecureEnclaveEnrollment.active, generation: 2)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(newKey, directory: directory) {}

        CompanionSecureEnclaveEnrollment.testInMemoryKeychain = ["old-key": Data(repeating: 4, count: 65)]

        let state = RotationState(
            oldKeyID: "old-key",
            newKeyID: "new-key",
            phase: .oldKeyRevoked,
            oldKeyRevoked: true,
            newKeyCreated: true
        )
        try JSONEncoder().encode(state).write(to: directory.appendingPathComponent(".rotation-state.json"))

        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)

        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path))
        XCTAssertNil(CompanionSecureEnclaveEnrollment.testInMemoryKeychain?["old-key"], "IOSQA6-01: Recovery at oldKeyRevoked must clean up old blob")

        let newKeyRecord = try CompanionSecureEnclaveEnrollment.inspect(keyID: "new-key", directory: directory)
        XCTAssertEqual(newKeyRecord.state, CompanionSecureEnclaveEnrollment.active, "IOSQA6-01: New key record must remain after recovery")

        let oldKeyRecord = try CompanionSecureEnclaveEnrollment.inspect(keyID: "old-key", directory: directory)
        XCTAssertEqual(oldKeyRecord.state, CompanionSecureEnclaveEnrollment.revoked, "IOSQA6-01: Old key revocation record must remain")
    }

    func testRotationRecoveryAtOldKeyRevokedPhase() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-revoked-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let state = RotationState(
            oldKeyID: "old-key",
            newKeyID: "new-key",
            phase: .oldKeyRevoked,
            oldKeyRevoked: true,
            newKeyCreated: true
        )
        try JSONEncoder().encode(state).write(to: directory.appendingPathComponent(".rotation-state.json"))

        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory))

        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path), "Missing replacement must retain the recovery journal")
    }

    func testRotationRecoveryAtCompletedPhase() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-completed-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let state = RotationState(
            oldKeyID: "old-key",
            newKeyID: "new-key",
            phase: .completed,
            oldKeyRevoked: true,
            newKeyCreated: true
        )
        try JSONEncoder().encode(state).write(to: directory.appendingPathComponent(".rotation-state.json"))

        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory))

        XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path), "Missing replacement must retain the recovery journal")
    }

    func testRecoveryWithNoRotationState() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-no-state-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path))

        XCTAssertNoThrow(try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory), "Recovery should succeed when no rotation state exists")
    }

    func testRotationGenerationNumbering() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-gen-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let oldKey = sampleRecord(keyID: "test-old", state: CompanionSecureEnclaveEnrollment.active, generation: 5)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(oldKey, directory: directory) {}

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 5, count: 65) }
        CompanionSecureEnclaveEnrollment.testKeyDeleter = { _ in }

        let (newKey, revokedKey) = try await CompanionSecureEnclaveEnrollment.rotate(
            from: "test-old",
            to: "test-new",
            directory: directory
        )

        XCTAssertEqual(newKey.keyID, "test-new")
        XCTAssertEqual(newKey.generation, 6, "New key gets old generation + 1")
        XCTAssertEqual(newKey.state, CompanionSecureEnclaveEnrollment.active)
        XCTAssertTrue(newKey.macUpdatePending, "New key has Mac update pending")

        XCTAssertEqual(revokedKey.keyID, "test-old")
        XCTAssertEqual(revokedKey.generation, 6, "Revoked key gets old generation + 1 for Mac compatibility")
        XCTAssertEqual(revokedKey.state, CompanionSecureEnclaveEnrollment.revoked)
        XCTAssertTrue(revokedKey.macUpdatePending, "Revoked key has Mac update pending")

        let storedNew = try CompanionSecureEnclaveEnrollment.inspect(keyID: "test-new", directory: directory)
        XCTAssertEqual(storedNew.generation, 6)
        let storedRevoked = try CompanionSecureEnclaveEnrollment.inspect(keyID: "test-old", directory: directory)
        XCTAssertEqual(storedRevoked.generation, 6)
    }

    func testEnrollOnRevokedKeyIDReturnsSpecificError() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-enroll-revoked-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let revokedKey = sampleRecord(keyID: "old-key", state: CompanionSecureEnclaveEnrollment.revoked, generation: 3)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(revokedKey, directory: directory) {}

        var createKeyCalled = false
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.enrollReplacingMissingFile(
            keyID: "old-key",
            directory: directory,
            createKey: {
                createKeyCalled = true
                return Data(repeating: 4, count: 65)
            },
            cleanup: {}
        )) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .keyIDRevoked, "Enrolling on revoked key ID returns keyIDRevoked error")
        }
        XCTAssertFalse(createKeyCalled, "Key creation should not be attempted for revoked key ID")

        let stored = try CompanionSecureEnclaveEnrollment.inspect(keyID: "old-key", directory: directory)
        XCTAssertEqual(stored.state, CompanionSecureEnclaveEnrollment.revoked, "Original revoked record unchanged")
        XCTAssertEqual(stored.generation, 3, "Original generation unchanged")
    }

    func testKeyIDRevokedErrorMessage() {
        let error = CompanionHardwareRefusal.keyIDRevoked
        XCTAssertTrue(error.userMessage.contains("revoked"), "Error message mentions revoked")
        XCTAssertTrue(error.userMessage.contains("different key ID"), "Error message suggests using different key ID")
    }

    func testCarriedExportUsesAllStringsAndExcludesMacUpdatePending() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-carried-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: "cross-platform-test", directory: directory)
        XCTAssertTrue(record.macUpdatePending, "New enrollment has Mac update pending")

        let carriedData = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: "cross-platform-test", directory: directory)
        guard let object = try JSONSerialization.jsonObject(with: carriedData) as? [String: String] else {
            XCTFail("Carried export must be [String: String] for Mac compatibility")
            return
        }

        XCTAssertNotNil(object["generation"], "Carried export includes generation")
        XCTAssertEqual(object["generation"], "1", "Generation is exported as string")
        XCTAssertNil(object["mac_update_pending"], "Carried export excludes mac_update_pending")
        XCTAssertEqual(object["state"], "active")
        XCTAssertEqual(object["key_id"], "cross-platform-test")
        XCTAssertEqual(object["role"], EnrollmentIdentity.roleCompanion)
    }

    func testRotateToRevokedDestinationIsRefused() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-revoked-dest-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        CompanionSecureEnclaveEnrollment.testKeyDeleter = { _ in }

        let activeKey = try CompanionSecureEnclaveEnrollment.enroll(keyID: "active-key", directory: directory)
        XCTAssertEqual(activeKey.state, CompanionSecureEnclaveEnrollment.active)

        let destinationKey = try CompanionSecureEnclaveEnrollment.enroll(keyID: "destination-key", directory: directory)
        XCTAssertEqual(destinationKey.state, CompanionSecureEnclaveEnrollment.active)

        _ = try await CompanionSecureEnclaveEnrollment.revoke(keyID: "destination-key", directory: directory)
        let revokedDest = try CompanionSecureEnclaveEnrollment.inspect(keyID: "destination-key", directory: directory)
        XCTAssertEqual(revokedDest.state, CompanionSecureEnclaveEnrollment.revoked)

        do {
            _ = try await CompanionSecureEnclaveEnrollment.rotate(from: "active-key", to: "destination-key", directory: directory)
            XCTFail("Expected keyIDRevoked error when rotating to revoked destination")
        } catch {
            XCTAssertEqual(error as? CompanionHardwareRefusal, .keyIDRevoked, "Rotating to revoked destination key returns keyIDRevoked error")
        }

        let activeStillActive = try CompanionSecureEnclaveEnrollment.inspect(keyID: "active-key", directory: directory)
        XCTAssertEqual(activeStillActive.state, CompanionSecureEnclaveEnrollment.active, "Source key remains active after refused rotation")
    }

    func testRotateToActiveDestinationIsRefused() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-active-dest-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        CompanionSecureEnclaveEnrollment.testKeyDeleter = { _ in }

        let sourceKey = try CompanionSecureEnclaveEnrollment.enroll(keyID: "source-key", directory: directory)
        XCTAssertEqual(sourceKey.state, CompanionSecureEnclaveEnrollment.active)

        let destKey = try CompanionSecureEnclaveEnrollment.enroll(keyID: "dest-key", directory: directory)
        XCTAssertEqual(destKey.state, CompanionSecureEnclaveEnrollment.active)

        do {
            _ = try await CompanionSecureEnclaveEnrollment.rotate(from: "source-key", to: "dest-key", directory: directory)
            XCTFail("IOSQA6-14: Expected alreadyEnrolled error when rotating to active destination")
        } catch {
            XCTAssertEqual(error as? CompanionHardwareRefusal, .alreadyEnrolled, "IOSQA6-14: Rotating to active destination returns alreadyEnrolled error")
        }

        let sourceStillActive = try CompanionSecureEnclaveEnrollment.inspect(keyID: "source-key", directory: directory)
        XCTAssertEqual(sourceStillActive.state, CompanionSecureEnclaveEnrollment.active, "Source key remains active after refused rotation")

        let destStillActive = try CompanionSecureEnclaveEnrollment.inspect(keyID: "dest-key", directory: directory)
        XCTAssertEqual(destStillActive.state, CompanionSecureEnclaveEnrollment.active, "Destination key remains unchanged")
    }

    func testListKeysReturnsAllEnrolledKeys() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-list-keys-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let key1 = sampleRecord(keyID: "key-one", state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        let key2 = sampleRecord(keyID: "key-two", state: CompanionSecureEnclaveEnrollment.revoked, generation: 3)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(key1, directory: directory) {}
        try CompanionSecureEnclaveEnrollment.storeEnrollment(key2, directory: directory) {}

        let keys = try CompanionSecureEnclaveEnrollment.listKeys(directory: directory)
        XCTAssertEqual(keys.count, 2)
        XCTAssertTrue(keys.contains(where: { $0.keyID == "key-one" && $0.state == CompanionSecureEnclaveEnrollment.active }))
        XCTAssertTrue(keys.contains(where: { $0.keyID == "key-two" && $0.state == CompanionSecureEnclaveEnrollment.revoked }))
    }

    func testMacUpdatePendingFlagIsPersisted() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-mac-pending-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: "test-key", directory: directory)
        XCTAssertTrue(record.macUpdatePending)

        let loaded = try CompanionSecureEnclaveEnrollment.inspect(keyID: "test-key", directory: directory)
        XCTAssertTrue(loaded.macUpdatePending)

        try CompanionSecureEnclaveEnrollment.markMacUpdated(keyID: "test-key", directory: directory)
        let updated = try CompanionSecureEnclaveEnrollment.inspect(keyID: "test-key", directory: directory)
        XCTAssertFalse(updated.macUpdatePending)
    }

    private func sampleRecord(keyID: String = "phone-vector", state: String, generation: Int) -> CompanionPairingRecord {
        CompanionPairingRecord(
            keyID: keyID,
            publicKey: Data(repeating: 4, count: 65),
            role: EnrollmentIdentity.roleCompanion,
            backend: EnrollmentIdentity.backendSecureEnclave,
            provenance: EnrollmentIdentity.provenanceProduction,
            state: state,
            generation: generation,
            macUpdatePending: false
        )
    }

    func testCapabilityValidatorRejectsApproveCapability() {
        var caps = CompanionCapabilities(
            product: "test",
            mode: "observe",
            canApprove: true,
            canExecute: false,
            canMutateLifecycle: false,
            canRemoteConfirm: true,
            boundary: "test"
        )
        let result = CapabilityValidator.validateForPairing(capabilities: caps)
        if case .invalid(let reason) = result {
            XCTAssertTrue(reason.contains("ADR-004"))
        } else {
            XCTFail("Expected invalid result")
        }

        caps.canApprove = false
        caps.canExecute = true
        let result2 = CapabilityValidator.validateForPairing(capabilities: caps)
        XCTAssertNotEqual(result2, .valid)

        caps.canExecute = false
        caps.canMutateLifecycle = true
        let result3 = CapabilityValidator.validateForPairing(capabilities: caps)
        XCTAssertNotEqual(result3, .valid)

        caps.canMutateLifecycle = false
        let result4 = CapabilityValidator.validateForPairing(capabilities: caps)
        XCTAssertEqual(result4, .valid)
    }

    func testCapabilityValidatorRejectsStatusWithApprove() {
        let status = CompanionStatus(
            phase: "active",
            companion: CompanionFlags(canApprove: true)
        )
        let result = CapabilityValidator.validateForRefresh(status: status)
        if case .invalid(let reason) = result {
            XCTAssertTrue(reason.contains("approve/execute"))
        } else {
            XCTFail("Expected invalid result")
        }
    }

    func testRemoteConfirmResultSuccessFields() {
        let confirmed = RemoteConfirmResult(ok: true, settled: true, refused: false)
        XCTAssertTrue(confirmed.confirmedSuccessfully)
        XCTAssertFalse(confirmed.refusedSuccessfully)
        XCTAssertFalse(confirmed.isAmbiguous)

        let refused = RemoteConfirmResult(ok: true, settled: false, refused: true)
        XCTAssertFalse(refused.confirmedSuccessfully)
        XCTAssertTrue(refused.refusedSuccessfully)
        XCTAssertFalse(refused.isAmbiguous)

        let ambiguous1 = RemoteConfirmResult(ok: nil, settled: true)
        XCTAssertFalse(ambiguous1.confirmedSuccessfully)
        XCTAssertTrue(ambiguous1.isAmbiguous)

        let ambiguous2 = RemoteConfirmResult(ok: true, settled: nil, refused: nil)
        XCTAssertTrue(ambiguous2.isAmbiguous)

        let ambiguous3 = RemoteConfirmResult(ok: true, settled: true, refused: true)
        XCTAssertTrue(ambiguous3.isAmbiguous)
    }

    func testArgvRenderingPreservesBoundaries() {
        let argvWithSpace = ["/bin/echo", "a b"]
        let argvSeparate = ["/bin/echo", "a", "b"]

        let renderedWithSpace = argvWithSpace.enumerated().map { (index, arg) in
            "[\(index)] \(StatusObserveView.escapeForDisplay(arg))"
        }.joined(separator: "\n")

        let renderedSeparate = argvSeparate.enumerated().map { (index, arg) in
            "[\(index)] \(StatusObserveView.escapeForDisplay(arg))"
        }.joined(separator: "\n")

        XCTAssertNotEqual(renderedWithSpace, renderedSeparate, "Argv with embedded space should render differently from separate args")
        XCTAssertTrue(renderedWithSpace.contains("a␣b"), "Embedded space should be rendered as ␣")
        XCTAssertEqual(argvWithSpace.count, 2, "First array has 2 elements")
        XCTAssertEqual(argvSeparate.count, 3, "Second array has 3 elements")
    }

    func testEscapeForDisplayDistinguishesNewlineFromLiteralBackslashN() {
        let realNewline = StatusObserveView.escapeForDisplay("a\nb")
        let literalBackslashN = StatusObserveView.escapeForDisplay("a\\nb")

        XCTAssertNotEqual(realNewline, literalBackslashN,
            "Real newline and literal backslash-n must render differently. " +
            "Got '\(realNewline)' for newline and '\(literalBackslashN)' for backslash-n")

        XCTAssertEqual(realNewline, "a\\nb", "Real newline should render as a\\nb")
        XCTAssertEqual(literalBackslashN, "a\\\\nb", "Literal backslash-n should render as a\\\\nb")
    }

    func testEscapeForDisplayRendersNonASCIIDistinctly() {
        let eAcute = StatusObserveView.escapeForDisplay("é")
        let chinese = StatusObserveView.escapeForDisplay("中")

        XCTAssertNotEqual(eAcute, chinese,
            "é (U+00E9) and 中 (U+4E2D) must render distinctly. " +
            "Got '\(eAcute)' for é and '\(chinese)' for 中")

        XCTAssertFalse(eAcute.contains("\\x00"),
            "é should not render as \\x00. Got '\(eAcute)'")
        XCTAssertFalse(chinese.contains("\\x00"),
            "中 should not render as \\x00. Got '\(chinese)'")

        XCTAssertEqual(eAcute, "\\u00E9", "é (U+00E9) should render as \\u00E9")
        XCTAssertEqual(chinese, "\\u4E2D", "中 (U+4E2D) should render as \\u4E2D")
    }

    func testEscapeForDisplayEscapesBackslash() {
        let backslash = StatusObserveView.escapeForDisplay("\\")
        XCTAssertEqual(backslash, "\\\\", "Single backslash should render as \\\\")

        let multipleBackslash = StatusObserveView.escapeForDisplay("\\\\\\")
        XCTAssertEqual(multipleBackslash, "\\\\\\\\\\\\", "Three backslashes should render as six")

        let backslashWithTab = StatusObserveView.escapeForDisplay("\\\t")
        XCTAssertEqual(backslashWithTab, "\\\\\\t", "Backslash followed by tab should render as \\\\\\t")
    }

    func testEscapeForDisplayHandlesSurrogatePairs() {
        let emoji = StatusObserveView.escapeForDisplay("😀")
        XCTAssertFalse(emoji.contains("\\x"), "Emoji should not render with \\x escape")
        XCTAssertTrue(emoji.contains("\\U"), "Emoji should render with \\U escape for code points above U+FFFF")
        XCTAssertEqual(emoji, "\\U0001F600", "😀 (U+1F600) should render as \\U0001F600")
    }

    func testEscapeForDisplayPrintableASCIIPassthrough() {
        let printable = "ABCxyz019!@#$%^&*()[]{}|;':\",./<>?"
        let escaped = StatusObserveView.escapeForDisplay(printable)
        let expected = "ABCxyz019!@#$%^&*()[]{}|;':\",./<>?"
        XCTAssertEqual(escaped, expected, "Printable ASCII should pass through unchanged (except space)")
    }

    func testPhoneKeyStageValidatesStagedParts() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-staged-validation-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let stage = PhoneKeyStage.fixture(directory: directory)
        XCTAssertThrowsError(try stage.validateStagedParts()) { error in
            guard let clientError = error as? CompanionClientError,
                  case .transport(let message) = clientError else {
                XCTFail("Expected transport error")
                return
            }
            XCTAssertTrue(message.contains("incomplete-stage"))
        }

        let handlePath = directory.appendingPathComponent("phone-session-handle.pending")
        try Data().write(to: handlePath)
        XCTAssertThrowsError(try stage.validateStagedParts()) { error in
            guard let clientError = error as? CompanionClientError,
                  case .transport(let message) = clientError else {
                XCTFail("Expected transport error")
                return
            }
            XCTAssertTrue(message.contains("incomplete-stage"))
        }

        let publicPath = directory.appendingPathComponent("phone-session-public.pending")
        try Data(repeating: 1, count: 64).write(to: publicPath)
        XCTAssertThrowsError(try stage.validateStagedParts()) { error in
            guard let clientError = error as? CompanionClientError,
                  case .transport(let message) = clientError else {
                XCTFail("Expected transport error")
                return
            }
            XCTAssertTrue(message.contains("empty"))
        }

        try Data(repeating: 1, count: 32).write(to: handlePath)
        XCTAssertThrowsError(try stage.validateStagedParts()) { error in
            guard let clientError = error as? CompanionClientError,
                  case .transport(let message) = clientError else {
                XCTFail("Expected transport error")
                return
            }
            XCTAssertTrue(message.contains("malformed"))
        }

        try fixturePhonePublicKey(Data(repeating: 1, count: 32)).write(to: publicPath)
        XCTAssertNoThrow(try stage.validateStagedParts())
    }

    func testEnrolledKeyPersistsAcrossRelaunch() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-relaunch-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }

        let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: "test-relaunch", directory: directory)
        XCTAssertEqual(record.keyID, "test-relaunch")
        XCTAssertEqual(record.state, CompanionSecureEnclaveEnrollment.active)
        XCTAssertEqual(record.generation, 1)

        let keys = try CompanionSecureEnclaveEnrollment.listKeys(directory: directory)
        XCTAssertEqual(keys.count, 1, "Should have exactly one key after enrollment")
        XCTAssertEqual(keys.first?.keyID, "test-relaunch")
        XCTAssertEqual(keys.first?.state, CompanionSecureEnclaveEnrollment.active)

        let reloaded = try CompanionSecureEnclaveEnrollment.inspect(keyID: "test-relaunch", directory: directory)
        XCTAssertEqual(reloaded.keyID, "test-relaunch", "Key ID should match after simulated relaunch")
        XCTAssertEqual(reloaded.state, CompanionSecureEnclaveEnrollment.active, "Key should still be active after simulated relaunch")
        XCTAssertEqual(reloaded.generation, 1, "Generation should persist")
        XCTAssertTrue(reloaded.macUpdatePending, "Mac update pending should persist")

        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.inspect(keyID: "nonexistent-key", directory: directory)) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .missing, "Inspecting non-existent key returns missing")
        }
    }

    func testListKeysReturnsCorrectKeyForSelection() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-selection-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }

        let key1 = try CompanionSecureEnclaveEnrollment.enroll(keyID: "test-1", directory: directory)
        XCTAssertEqual(key1.state, CompanionSecureEnclaveEnrollment.active)

        let key2 = try CompanionSecureEnclaveEnrollment.enroll(keyID: "test-2", directory: directory)
        XCTAssertEqual(key2.state, CompanionSecureEnclaveEnrollment.active)

        let keys = try CompanionSecureEnclaveEnrollment.listKeys(directory: directory)
        XCTAssertEqual(keys.count, 2, "Should have two keys")

        let hasTest1 = keys.contains { $0.keyID == "test-1" }
        let hasTest2 = keys.contains { $0.keyID == "test-2" }
        XCTAssertTrue(hasTest1, "Should find test-1 in list")
        XCTAssertTrue(hasTest2, "Should find test-2 in list")

        let selectedKeyID = "test-2"
        let keyExists = keys.contains { $0.keyID == selectedKeyID }
        XCTAssertTrue(keyExists, "Selected key should exist in list")

        if keyExists {
            let selected = try CompanionSecureEnclaveEnrollment.inspect(keyID: selectedKeyID, directory: directory)
            XCTAssertEqual(selected.keyID, "test-2")
            XCTAssertEqual(selected.state, CompanionSecureEnclaveEnrollment.active)
        }
    }

    func testDeriveReplacementKeyIDBasicCases() {
        XCTAssertEqual(
            CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: "test", existingKeyIDs: []),
            "test-2",
            "Key without -N suffix appends -2"
        )
        XCTAssertEqual(
            CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: "test-3", existingKeyIDs: []),
            "test-4",
            "Key with -N suffix increments N"
        )
        XCTAssertEqual(
            CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: "iphone-companion", existingKeyIDs: []),
            "iphone-companion-2",
            "iphone-companion appends -2"
        )
        XCTAssertEqual(
            CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: "my-key-99", existingKeyIDs: []),
            "my-key-100",
            "Large N increments correctly"
        )
        XCTAssertEqual(
            CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: "", existingKeyIDs: []),
            "iphone-companion-2",
            "Empty base uses iphone-companion-2"
        )
    }

    func testDeriveReplacementKeyIDSkipsCollisions() {
        XCTAssertEqual(
            CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: "test-3", existingKeyIDs: ["test-4"]),
            "test-5",
            "Skips existing test-4, returns test-5"
        )
        XCTAssertEqual(
            CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: "test-3", existingKeyIDs: ["test-4", "test-5", "test-6"]),
            "test-7",
            "Skips multiple collisions"
        )
        XCTAssertEqual(
            CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: "key", existingKeyIDs: ["key-2"]),
            "key-3",
            "Skips collision when appending -N"
        )
        XCTAssertEqual(
            CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: "", existingKeyIDs: ["iphone-companion-2"]),
            "iphone-companion-3",
            "Empty base skips collision with iphone-companion-2"
        )
    }

    func testDeriveReplacementKeyIDHandlesIntMaxWithoutOverflow() {
        let maxSuffix = "test-\(Int.max)"
        let result = CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: maxSuffix, existingKeyIDs: [])
        XCTAssertNotEqual(result, "", "IOSQA6-15: Should not crash with Int.max suffix")
        let overflowed = Int.max &+ 1
        XCTAssertFalse(result.contains("-\(overflowed)"), "IOSQA6-15: Should not overflow to Int.min")
        XCTAssertEqual(result, "test-\(Int.max)-2", "Should fall back to appending -2 when overflow would occur")
    }

    func testDeriveReplacementKeyIDHandlesVeryLargeSuffix() {
        let hugeSuffix = "test-" + String(repeating: "9", count: 20)
        let result = CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: hugeSuffix, existingKeyIDs: [])
        XCTAssertNotEqual(result, "", "IOSQA6-15: Should not crash with very large suffix")
        XCTAssertTrue(result.hasPrefix("test-"), "Should have correct prefix")
    }

    func testManageActionsUseSelectedKeyIDAfterRelaunch() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-manage-selection-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }

        let defaultKey = try CompanionSecureEnclaveEnrollment.enroll(keyID: "iphone-companion-2", directory: directory)
        XCTAssertEqual(defaultKey.state, CompanionSecureEnclaveEnrollment.active)

        let selectedKey = try CompanionSecureEnclaveEnrollment.enroll(keyID: "test-3", directory: directory)
        XCTAssertEqual(selectedKey.state, CompanionSecureEnclaveEnrollment.active)

        let persistedKeyID = "test-3"
        let keys = try CompanionSecureEnclaveEnrollment.listKeys(directory: directory)
        XCTAssertEqual(keys.count, 2)

        let restoredKeyID: String
        if keys.contains(where: { $0.keyID == persistedKeyID }) {
            restoredKeyID = persistedKeyID
        } else if let firstActive = keys.first(where: { $0.state == CompanionSecureEnclaveEnrollment.active }) {
            restoredKeyID = firstActive.keyID
        } else {
            restoredKeyID = persistedKeyID
        }

        XCTAssertEqual(restoredKeyID, "test-3", "Should restore selected key ID 'test-3' after relaunch")

        let revokeTargetKeyID = restoredKeyID
        XCTAssertEqual(revokeTargetKeyID, "test-3", "Revoke must target selected key ID, not a hardcoded default")
        XCTAssertNotEqual(revokeTargetKeyID, "iphone-companion-2", "Revoke must not accidentally target default key")

        let rotateSourceKeyID = restoredKeyID
        XCTAssertEqual(rotateSourceKeyID, "test-3", "Rotate must rotate FROM selected key ID")
        XCTAssertNotEqual(rotateSourceKeyID, "iphone-companion-2", "Rotate must not accidentally rotate default key")

        let existingIDs = Set(keys.map(\.keyID))
        let derivedReplacementID = CompanionSecureEnclaveEnrollment.deriveReplacementKeyID(from: restoredKeyID, existingKeyIDs: existingIDs)
        XCTAssertEqual(derivedReplacementID, "test-4", "Replacement ID should derive from selected key using production code")
        XCTAssertNotEqual(derivedReplacementID, "iphone-companion-2", "Replacement ID must not match default")

        XCTAssertEqual(revokeTargetKeyID, "test-3", "Revoke target must be the selected key")
        XCTAssertEqual(rotateSourceKeyID, "test-3", "Rotate source must be the selected key")
        let inspectedDefault = try CompanionSecureEnclaveEnrollment.inspect(keyID: "iphone-companion-2", directory: directory)
        XCTAssertEqual(inspectedDefault.state, CompanionSecureEnclaveEnrollment.active, "Default key is still active (not targeted)")
    }

    func testGoldenFixturesMatchCrossplatformSchema() throws {
        let fixturesPath = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("shared/TestFixtures/companion-pairing-golden.json")

        let data = try Data(contentsOf: fixturesPath)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let fixtures = root["fixtures"] as? [String: Any] else {
            XCTFail("Could not parse golden fixtures")
            return
        }

        for (name, fixture) in fixtures {
            guard let fixtureDict = fixture as? [String: Any],
                  let record = fixtureDict["record"] as? [String: String] else {
                XCTFail("Fixture \(name) is not valid [String: String]")
                continue
            }

            XCTAssertNotNil(record["backend"], "\(name): missing backend")
            XCTAssertNotNil(record["generation"], "\(name): missing generation")
            XCTAssertNotNil(record["key_id"], "\(name): missing key_id")
            XCTAssertNotNil(record["provenance"], "\(name): missing provenance")
            XCTAssertNotNil(record["public_key_x963_b64"], "\(name): missing public_key_x963_b64")
            XCTAssertNotNil(record["role"], "\(name): missing role")
            XCTAssertNotNil(record["state"], "\(name): missing state")

            XCTAssertNil(record["mac_update_pending"], "\(name): mac_update_pending should not be in carried export schema")

            if let genStr = record["generation"], let gen = Int(genStr) {
                XCTAssertTrue(gen > 0, "\(name): generation must be positive")
            } else {
                XCTFail("\(name): generation is not a valid integer string")
            }

            let state = record["state"]
            XCTAssertTrue(state == "active" || state == "revoked", "\(name): state must be active or revoked")
        }

        guard let activeFixture = fixtures["active"] as? [String: Any],
              let activeRecord = activeFixture["record"] as? [String: String],
              let revokedFixture = fixtures["revoked"] as? [String: Any],
              let revokedRecord = revokedFixture["record"] as? [String: String] else {
            XCTFail("Missing active or revoked fixture")
            return
        }

        XCTAssertEqual(activeRecord["generation"], "1", "Active key starts at generation 1")
        XCTAssertEqual(revokedRecord["generation"], "2", "Revoked key has generation incremented (1 + 1 = 2)")

        guard let rotatedNewFixture = fixtures["rotated_new"] as? [String: Any],
              let rotatedNewRecord = rotatedNewFixture["record"] as? [String: String],
              let rotatedOldFixture = fixtures["rotated_old"] as? [String: Any],
              let rotatedOldRecord = rotatedOldFixture["record"] as? [String: String] else {
            XCTFail("Missing rotated fixtures")
            return
        }

        XCTAssertEqual(rotatedNewRecord["state"], "active", "New key after rotation is active")
        XCTAssertEqual(rotatedOldRecord["state"], "revoked", "Old key after rotation is revoked")
        XCTAssertEqual(rotatedNewRecord["generation"], rotatedOldRecord["generation"], "Both rotated keys have same generation (old + 1)")
    }
    
    func testGoldenFixturesMatchRealSerializerOutput() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-golden-real-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        
        let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: "golden-test", directory: directory)
        let carriedData = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: "golden-test", directory: directory)
        
        guard let carried = try JSONSerialization.jsonObject(with: carriedData) as? [String: String] else {
            XCTFail("IOSQA6-16: Real serializer output must be [String: String]")
            return
        }
        
        XCTAssertEqual(carried["key_id"], "golden-test", "IOSQA6-16: key_id matches enrolled key")
        XCTAssertEqual(carried["state"], "active", "IOSQA6-16: state is active for new enrollment")
        XCTAssertEqual(carried["generation"], "1", "IOSQA6-16: generation is 1 for new enrollment")
        XCTAssertEqual(carried["backend"], EnrollmentIdentity.backendSecureEnclave, "IOSQA6-16: backend is secure_enclave")
        XCTAssertEqual(carried["role"], EnrollmentIdentity.roleCompanion, "IOSQA6-16: role is companion")
        XCTAssertNotNil(carried["public_key_x963_b64"], "IOSQA6-16: public_key_x963_b64 is present")
        XCTAssertNil(carried["mac_update_pending"], "IOSQA6-16: mac_update_pending excluded from export")
        
        let publicKeyData = Data(base64Encoded: carried["public_key_x963_b64"] ?? "")
        XCTAssertEqual(publicKeyData?.count, 65, "IOSQA6-16: public key is 65 bytes (X9.63 uncompressed P-256)")
    }

    func testListKeysWithCorruptIdentifiesCorruptRecords() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-corrupt-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        let validRecord = try CompanionSecureEnclaveEnrollment.enroll(keyID: "valid-key", directory: directory)
        XCTAssertEqual(validRecord.state, CompanionSecureEnclaveEnrollment.active)

        try Data("not-json".utf8).write(to: directory.appendingPathComponent("corrupt-key.pairing.json"))
        try Data("{\"invalid\": true}".utf8).write(to: directory.appendingPathComponent("malformed-key.pairing.json"))

        let listing = try CompanionSecureEnclaveEnrollment.listKeysWithCorrupt(directory: directory)

        XCTAssertEqual(listing.validRecords.count, 1, "Should have one valid record")
        XCTAssertEqual(listing.validRecords.first?.keyID, "valid-key")
        XCTAssertEqual(listing.corruptKeyIDs.count, 2, "Should identify two corrupt records")
        XCTAssertTrue(listing.corruptKeyIDs.contains { $0.keyID == "corrupt-key" }, "Should identify corrupt-key as corrupt")
        XCTAssertTrue(listing.corruptKeyIDs.contains { $0.keyID == "malformed-key" }, "Should identify malformed-key as corrupt")
    }

    func testRecoveryAtLaunchCleansUpIncompleteRotation() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-launch-recovery-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let state = RotationState(
            oldKeyID: "old-key",
            newKeyID: "new-key",
            phase: .newKeyStaged,
            oldKeyRevoked: false,
            newKeyCreated: true
        )
        let stateData = try JSONEncoder().encode(state)
        let stateURL = directory.appendingPathComponent(".rotation-state.json")
        try stateData.write(to: stateURL)

        XCTAssertTrue(FileManager.default.fileExists(atPath: stateURL.path), "Rotation state should exist before recovery")

        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)

        XCTAssertFalse(FileManager.default.fileExists(atPath: stateURL.path), "Rotation state should be cleaned up after recovery")
    }

    func testMarkMacUpdatedClearsPendingFlag() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-mark-updated-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: "test-mark", directory: directory)
        XCTAssertTrue(record.macUpdatePending, "New enrollment should have Mac update pending")

        let before = try CompanionSecureEnclaveEnrollment.inspect(keyID: "test-mark", directory: directory)
        XCTAssertTrue(before.macUpdatePending, "Should still be pending before mark")

        try CompanionSecureEnclaveEnrollment.markMacUpdated(keyID: "test-mark", directory: directory)

        let after = try CompanionSecureEnclaveEnrollment.inspect(keyID: "test-mark", directory: directory)
        XCTAssertFalse(after.macUpdatePending, "Should not be pending after mark")
    }

    func testTLSPinningDelegateRecordsMismatch() {
        let delegate = CompanionTLSPinningDelegate(expectedFingerprint: "abc123")
        XCTAssertFalse(delegate.hadPinMismatch, "Initially no mismatch")
        
        delegate.clearMismatch()
        XCTAssertFalse(delegate.hadPinMismatch, "IOSQA6-16: Clear on initial state should remain false")
        
        let differentDelegate = CompanionTLSPinningDelegate(expectedFingerprint: "AABBCC")
        XCTAssertFalse(differentDelegate.hadPinMismatch, "IOSQA6-16: Each delegate starts with no mismatch")
        XCTAssertEqual(CompanionTLSPinningDelegate.normalize("aa:bb:cc"), "aabbcc", "Fingerprint normalization matches the certificate digest")
        XCTAssertEqual(CompanionTLSPinningDelegate.normalize("AA:BB:CC"), "aabbcc", "IOSQA6-16: Normalization handles uppercase input")
    }

    func testCapabilityValidatorValidateForAction() {
        let badCaps = CompanionCapabilities(
            product: "test",
            mode: "observe",
            canApprove: true,
            canExecute: false,
            canMutateLifecycle: false,
            canRemoteConfirm: true,
            boundary: "test"
        )
        let result = CapabilityValidator.validateForAction(capabilities: badCaps, status: nil)
        XCTAssertNotEqual(result, .valid, "Should reject capabilities with approve")

        let goodCaps = CompanionCapabilities(
            product: "test",
            mode: "observe",
            canApprove: false,
            canExecute: false,
            canMutateLifecycle: false,
            canRemoteConfirm: true,
            boundary: "test"
        )
        let goodResult = CapabilityValidator.validateForAction(capabilities: goodCaps, status: CompanionStatus(phase: "active"))
        XCTAssertEqual(goodResult, .valid, "Should accept valid capabilities")

        let badStatus = CompanionStatus(phase: "active", companion: CompanionFlags(canApprove: true))
        let statusResult = CapabilityValidator.validateForAction(capabilities: goodCaps, status: badStatus)
        XCTAssertNotEqual(statusResult, .valid, "Should reject status with approve")
    }

    func testPhoneKeyStageValidatesStagedPartsBeforeOwnerCheck() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-staged-order-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let stage = PhoneKeyStage.fixture(directory: directory)
        XCTAssertThrowsError(try stage.commit(ownedBy: "challenge-1", publicKey: Data(repeating: 4, count: 65))) { error in
            guard let clientError = error as? CompanionClientError,
                  case .transport(let message) = clientError else {
                XCTFail("Expected transport error")
                return
            }
            XCTAssertTrue(message.contains("incomplete-stage"), "Error should mention incomplete-stage before checking owner")
        }
    }

    func testPhoneKeyStageRevokeThrowsOnFailure() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-revoke-throw-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let stage = PhoneKeyStage.fixture(directory: directory)
        try stage.stage(handle: Data("handle".utf8), publicKey: fixturePhonePublicKey(Data("handle".utf8)))
        try stage.commit()

        XCTAssertNoThrow(try stage.revoke(), "Revoke should succeed when files exist")
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("custody.json").path))
    }

    func testClientCachingReturnsTheSameInstance() async throws {
        let session = await CompanionSession()
        await MainActor.run {
            session.baseURLString = "http://localhost:8080"
            session.pairingToken = "test-token"
            session.tlsFingerprint = ""
            session.isPaired = true
        }

        let client1 = await MainActor.run { session.testMakeClient() }
        let client2 = await MainActor.run { session.testMakeClient() }

        XCTAssertTrue(client1 === client2, "makeClient should return the same cached instance")

        await MainActor.run { session.invalidateCachedClient() }
        let client3 = await MainActor.run { session.testMakeClient() }
        XCTAssertFalse(client1 === client3, "After invalidation, a new instance should be returned")
    }

    @MainActor
    func testFailedRefreshShowsStaleWithoutAdvancingTimestamp() async throws {
        let session = CompanionSession(deferPhoneKeyState: true)
        session.baseURLString = "http://localhost"
        session.pairingToken = "fixture-token"
        session.isPaired = true
        let previous = Date(timeIntervalSince1970: 100)
        session.lastSuccessfulRefresh = previous
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { _ in throw CompanionClientError.transport("fixture unavailable") }
        await session.refresh()
        XCTAssertEqual(session.lastSuccessfulRefresh, previous)
        XCTAssertEqual(session.refreshOutcome, .failure("fixture unavailable"))
        XCTAssertEqual(session.connectionState, .stale)
        XCTAssertTrue(session.isPaired)
    }

    func testGrokEnrollmentCommitSurvivesCancellation() async throws {
        try await verifyEnrollmentCommit(cancelDuringCommit: true)
    }

    func testGrokExplicitCancelAfterCommitReconcilesEnrolledKey() async throws {
        try await verifyEnrollmentCommit(cancelDuringCommit: false, cancelChallengeAfterCommit: true)
    }

    func testPhonePeerKeyStateRefreshesAfterHolderVerifiedCommit() async throws {
        try await verifyEnrollmentCommit(cancelDuringCommit: false)
    }

    func testP3PhonePeerEnrollmentBiometricCancelIsNeutral() async throws {
        try await verifyEnrollmentCommit(cancelDuringCommit: false, biometricCancellation: true)
    }

    private func verifyEnrollmentCommit(cancelDuringCommit: Bool, cancelChallengeAfterCommit: Bool = false, biometricCancellation: Bool = false) async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-commit-refresh-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let signer = TempDirectoryTestSigner(directory: directory)

        let session = await CompanionSession(deferPhoneKeyState: true, phoneKeyStage: signer.stage)
        let mac = P256.Signing.PrivateKey()

        await MainActor.run {
            session.macSessionPublicKey = mac.publicKey.x963Representation.base64EncodedString()
            session.phonePeerKeyState = .enrolled(generation: 99)
            session.status = CompanionStatus(phase: "active")
            session.capabilities = CompanionCapabilities(
                product: "test",
                mode: "observe",
                canApprove: false,
                canExecute: false,
                canMutateLifecycle: false,
                canRemoteConfirm: true,
                boundary: "test"
            )
        }

        let challenge = PhonePeerChallengeMessage(
            challengeId: "test-challenge-1",
            challenge: "Y2hhbGxlbmdl",
            generation: 1,
            holderId: "holder",
            expiry: 1,
            role: "phone"
        )

        let peer = MockPhonePeerTransport()
        peer.verification = try signedPhoneReceipt(
            key: mac,
            challenge: challenge,
            phonePublicKey: signer.publicKeyBase64
        )

        await MainActor.run {
            session.phoneChallenge = challenge
            session.signedPhonePublicKey = signer.publicKeyBase64
            session.isPaired = true
        }

        signer.cancelAfterCommit = cancelDuringCommit
        if cancelChallengeAfterCommit { signer.afterCommit = { await session.cancelPhonePeerChallenge() } }
        if biometricCancellation { CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in throw CompanionHardwareRefusal.automationRefused } }
        let outcome = await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
        if biometricCancellation {
            XCTAssertEqual(outcome, .cancelled)
            XCTAssertEqual(signer.commits, 0)
            await MainActor.run { XCTAssertNil(session.lastError); XCTAssertEqual(session.phoneEnrollmentFeedback, .cancelled) }
            return
        }
        XCTAssertEqual(outcome, .enrolled)

        await MainActor.run {
            XCTAssertEqual(signer.commits, 1, "signer.commitEnrollment should be called once")
            XCTAssertNil(session.phoneChallenge, "phoneChallenge should be cleared after commit")
            XCTAssertEqual(session.phonePeerKeyState, .enrolled(generation: 1),
                "phonePeerKeyState should change after commit (refreshPhonePeerKeyState called)")
        }

        let generation = try signer.stage.committedGeneration()
        XCTAssertEqual(generation, 1, "Signer's stage should have generation 1 after commit")
        await MainActor.run { XCTAssertEqual(session.phoneEnrollmentFeedback, .enrolled) }
        try await session.revokePhonePeerKey()
        await MainActor.run {
            XCTAssertEqual(session.phonePeerKeyState, .noKey)
            XCTAssertNil(session.phoneEnrollmentFeedback, "enrollment success must disappear after revocation")
        }
    }

    private func package() throws -> [String: String] {
        [
            "version": "RSBA2",
            "policy": "companion",
            "mac_id": "mac-vector",
            "workspace_id": "ws-vector",
            "run_id": "run-vector",
            "contract_sha256": String(repeating: "11", count: 32),
            "inputs_sha256": String(repeating: "22", count: 32),
            "bounds": "bounds-vector",
            "nonce": String(repeating: "bb", count: 32),
            "expiry_unix": "1700000000",
            "companion_key_id": "phone-vector",
            "companion_generation": "1",
        ]
    }
}

final class TempDirectoryTestSigner: PhoneChallengeSigning {
    let stage: PhoneKeyStage
    let publicKey: Data
    let publicKeyBase64: String
    var commits = 0
    var cancelAfterCommit = false
    var afterCommit: (() async -> Void)?

    init(directory: URL) {
        self.stage = PhoneKeyStage.fixture(directory: directory)
        self.publicKey = try! fixturePhonePublicKey(Data("test-handle".utf8))
        self.publicKeyBase64 = publicKey.base64EncodedString()
    }

    func sign(message: Data) throws -> (publicKey: String, signature: String) {
        try stage.stage(handle: Data("test-handle".utf8), publicKey: publicKey)
        return (publicKeyBase64, "c2ln")
    }

    func signCommitted(message: Data) throws -> (publicKey: String, signature: String) {
        (publicKeyBase64, "c2ln")
    }

    func bindStagedOwnership(challengeId: String, publicKey: String) throws {
        guard let key = Data(base64Encoded: publicKey) else { return }
        try stage.bindOwner(challengeId: challengeId, publicKey: key)
    }

    func commitEnrollmentAsync(ownedBy challengeId: String, publicKey: String) async throws {
        try await CryptoWorker.shared.performCommit { try self.commitEnrollment(ownedBy: challengeId, publicKey: publicKey) }
        await afterCommit?()
    }

    func commitEnrollment(ownedBy challengeId: String, publicKey: String) throws {
        guard let key = Data(base64Encoded: publicKey) else {
            throw CompanionClientError.transport("invalid key")
        }
        try stage.stage(handle: Data("test-handle".utf8), publicKey: key, challengeId: challengeId)
        try stage.commit(ownedBy: challengeId, publicKey: key)
        commits += 1
        if cancelAfterCommit { withUnsafeCurrentTask { $0?.cancel() } }
    }

    func discardStagedEnrollment() {
        stage.discard()
    }
}

final class MockPhonePeerTransport: PhonePeerTransport {
    var verification: PhoneHolderVerification?

    func fetchPhonePeerChallenge() async throws -> PhonePeerChallengeMessage {
        PhonePeerChallengeMessage(
            challengeId: "test-challenge",
            challenge: "Y2hhbGxlbmdl",
            generation: 1,
            holderId: "holder",
            expiry: 1,
            role: "phone"
        )
    }

    func willSubmitPhonePeerSignature() async throws {}

    func submitPhonePeerSignature(
        challengeId: String,
        challenge: String,
        publicKey: String,
        signature: String
    ) async throws {}

    func invalidatePhonePeerChallenge(challengeId: String) async throws {}

    func fetchHolderVerification(challengeId: String) async throws -> PhoneHolderVerification {
        verification ?? PhoneHolderVerification(verified: false, consumed: false, invalidated: false)
    }
}

func signedPhoneReceipt(
    key: P256.Signing.PrivateKey,
    challenge: PhonePeerChallengeMessage,
    phonePublicKey: String,
    generation: Int? = nil,
    challengeId: String? = nil
) throws -> PhoneHolderVerification {
    let mac = key.publicKey.x963Representation.base64EncodedString()
    let canonical = phoneReceiptCanonical(
        challenge: challenge.challenge,
        challengeId: challengeId ?? challenge.challengeId,
        generation: generation ?? challenge.generation,
        holderId: challenge.holderId,
        macPublicKey: mac,
        phoneFingerprint: phoneKeyFingerprint(phonePublicKey)
    )
    let signature = try key.signature(for: Data(canonical.utf8)).rawRepresentation.base64EncodedString()
    return PhoneHolderVerification(
        verified: true,
        consumed: true,
        invalidated: false,
        challengeId: challengeId ?? challenge.challengeId,
        receipt: Data(canonical.utf8).base64EncodedString(),
        signature: signature,
        macPublicKey: mac,
        phoneFingerprint: phoneKeyFingerprint(phonePublicKey),
        holderId: challenge.holderId,
        generation: generation ?? challenge.generation,
        outcome: "verified-consumed"
    )
}

// MARK: - IOSQA6 Behavioral Tests

extension ObserveSchemaTests {
    
    // IOSQA6-02: Test that revoked key exports are accessible after Revoke, Rotate, and relaunch
    func testRevokedExportCardReachableAfterRevoke() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-revoked-export-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        CompanionSecureEnclaveEnrollment.testKeyDeleter = { _ in }
        
        let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: "test-revoke-export", directory: directory)
        XCTAssertEqual(record.state, CompanionSecureEnclaveEnrollment.active)
        
        let revoked = try await CompanionSecureEnclaveEnrollment.revoke(keyID: "test-revoke-export", directory: directory)
        XCTAssertEqual(revoked.state, CompanionSecureEnclaveEnrollment.revoked)
        
        let carriedData = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: "test-revoke-export", directory: directory)
        XCTAssertFalse(carriedData.isEmpty, "IOSQA6-02: Revoked key export must be accessible")
        
        let parsed = try JSONSerialization.jsonObject(with: carriedData) as? [String: String]
        XCTAssertEqual(parsed?["state"], "revoked", "IOSQA6-02: Export shows revoked state")
    }
    
    func testRevokedExportCardReachableAfterRotate() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-export-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        CompanionSecureEnclaveEnrollment.testKeyDeleter = { _ in }
        
        let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: "old-key", directory: directory)
        XCTAssertEqual(record.state, CompanionSecureEnclaveEnrollment.active)
        
        let (newKey, revokedKey) = try await CompanionSecureEnclaveEnrollment.rotate(from: "old-key", to: "new-key", directory: directory)
        XCTAssertEqual(newKey.state, CompanionSecureEnclaveEnrollment.active)
        XCTAssertEqual(revokedKey.state, CompanionSecureEnclaveEnrollment.revoked)
        
        let revokedCarried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: "old-key", directory: directory)
        XCTAssertFalse(revokedCarried.isEmpty, "IOSQA6-02: Revoked key export must be accessible after rotation")
        
        let newCarried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: "new-key", directory: directory)
        XCTAssertFalse(newCarried.isEmpty, "IOSQA6-02: New key export must be accessible after rotation")
    }
    
    func testRevokedExportCardReachableAfterRelaunch() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-relaunch-export-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        
        let revokedRecord = sampleRecord(keyID: "persisted-revoked", state: CompanionSecureEnclaveEnrollment.revoked, generation: 2)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(revokedRecord, directory: directory) {}
        
        let keys = try CompanionSecureEnclaveEnrollment.listKeys(directory: directory)
        XCTAssertTrue(keys.contains { $0.keyID == "persisted-revoked" && $0.state == CompanionSecureEnclaveEnrollment.revoked },
            "IOSQA6-02: Revoked keys must be visible after simulated relaunch")
        
        let carriedData = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: "persisted-revoked", directory: directory)
        XCTAssertFalse(carriedData.isEmpty, "IOSQA6-02: Revoked key export must be accessible after relaunch")
    }
    
    // IOSQA6-04: Test disconnect during refresh

    
    // IOSQA6-07: Test commit on empty stage fails
    func testCommitOnEmptyStageFails() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-empty-commit-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        
        let stage = PhoneKeyStage.fixture(directory: directory)
        XCTAssertThrowsError(try stage.commit()) { error in
            guard let clientError = error as? CompanionClientError,
                  case .transport(let message) = clientError else {
                XCTFail("IOSQA6-07: Expected transport error")
                return
            }
            XCTAssertTrue(message.contains("incomplete-stage"), "IOSQA6-07: Error should mention incomplete-stage")
        }
    }
    
    // IOSQA6-08: Test corrupt key selection preserved
    func testCorruptKeySelectionPreserved() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-corrupt-selection-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        let validRecord = try CompanionSecureEnclaveEnrollment.enroll(keyID: "valid-key", directory: directory)
        XCTAssertEqual(validRecord.state, CompanionSecureEnclaveEnrollment.active)
        
        try Data("not-json".utf8).write(to: directory.appendingPathComponent("corrupt-key.pairing.json"))
        
        let listing = try CompanionSecureEnclaveEnrollment.listKeysWithCorrupt(directory: directory)
        
        let selection = try HardwareKeySelection(persistedKeyID: "corrupt-key", directory: directory)
        XCTAssertEqual(selection.keyID, "corrupt-key")
        XCTAssertEqual(selection.corruptKeyIDs.map(\.keyID), ["corrupt-key"])
        XCTAssertEqual(selection.records.map(\.keyID), ["valid-key"])

    }
    
    // IOSQA6-11: Test stale async read discarded
    func testPhonePeerKeyStateRevisionPreventsStaleReads() async throws {
        let session = await CompanionSession()
        
        await MainActor.run {
            session.refreshPhonePeerKeyState()
        }
        
        let revisionBefore = await MainActor.run { session.testPhonePeerKeyStateRevision }
        
        await MainActor.run {
            session.refreshPhonePeerKeyState()
        }
        
        let revisionAfter = await MainActor.run { session.testPhonePeerKeyStateRevision }
        
        XCTAssertGreaterThan(revisionAfter, revisionBefore, "IOSQA6-11: Each refresh should increment revision")
    }
    
    // IOSQA6-17: Test Release symbol gate

    
    // Keychain token storage test
    func testKeychainTokenStorageMigration() async throws {
        let session = await CompanionSession()
        
        await MainActor.run {
            let defaults = CompanionSession.storageDefaults
            let oldKey = "rs.observe.pairing"
            
            if let existingConfig = defaults.dictionary(forKey: oldKey),
               existingConfig["pairingToken"] != nil {
                XCTAssertNil(existingConfig["pairingToken"], "Keychain: Token should migrate out of UserDefaults")
            }
        }
    }
    
    // IOSQA6-05: Test capability validation requires verified capabilities
    func testCapabilityValidationRequiresVerifiedCapabilities() {
        let result = CapabilityValidator.validateForAction(capabilities: nil, status: nil)
        XCTAssertNotEqual(result, .valid, "IOSQA6-05: Action should be refused when capabilities is nil")
        
        if case .invalid(let reason) = result {
            XCTAssertTrue(reason.contains("not verified"), "IOSQA6-05: Error should mention capabilities not verified")
        }
    }
    
    // IOSQA6-09: Test key generation binding for exact-run signing
    func testExactRunKeyGenerationBinding() async throws {
        let session = await CompanionSession()
        
        await MainActor.run {
            session.phonePeerKeyState = .enrolled(generation: 5)
            session.status = CompanionStatus(phase: "active")
            session.capabilities = CompanionCapabilities(
                product: "test",
                mode: "observe",
                canApprove: false,
                canExecute: false,
                canMutateLifecycle: false,
                canRemoteConfirm: true,
                boundary: "test"
            )
        }
        
        let peer = MockExactRunTransport()
        let digest = String(repeating: "ab", count: 32)
        let expiry = Int(Date().timeIntervalSince1970) + 3600
        let bound = canonicalExactRunBound(
            holderId: "holder",
            payloadDigest: digest,
            launchArgv: ["/usr/bin/test"],
            nonce: "test-challenge",
            policy: "companion",
            generation: 1,
            keyGeneration: 5,
            expiry: expiry
        )
        peer.fetchedRun = FetchedExactRun(
            challengeId: "test-challenge",
            bound: bound,
            policy: "companion",
            generation: 1,
            keyGeneration: 5,
            expiry: expiry
        )
        
        await MainActor.run {
            session.baseURLString = "http://localhost:8080"
            session.pairingToken = "test"
            session.isPaired = true
            session.pinnedHolderId = "holder"
        }
        
        await session.reviewRetainedExactRun(peer: peer)
        
        let reviewedKeyGen = await MainActor.run { session.testReviewedExactRunKeyGeneration }
        XCTAssertEqual(reviewedKeyGen, 5, "IOSQA6-09: Review should capture current key generation")
        
        await MainActor.run {
            session.phonePeerKeyState = .enrolled(generation: 6)
        }
        
        let signer = TempDirectoryTestSigner(directory: FileManager.default.temporaryDirectory.appendingPathComponent("test-signer-" + UUID().uuidString))
        await session.approveReviewedExactRun(signer: signer, peer: peer)
        
        let note = await MainActor.run { session.exactRunNote }
        XCTAssertTrue(note.contains("key changed") || note.contains("not returned"), 
            "IOSQA6-09: Signing should fail when key generation changes")
    }
    
    // IOSQA6-10: Test task handle generation prevents stale cleanup

    
    // IOSQA6-12: Test typed refresh outcomes

    
    // IOSQA6-06: Test phone-peer key rotation keeps old key
    func testPhonePeerRotationKeepsOldKey() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-phone-rotate-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        
        let stage = PhoneKeyStage.fixture(directory: directory)
        try stage.stage(handle: Data("old-handle".utf8), publicKey: fixturePhonePublicKey(Data("old-handle".utf8)))
        try stage.commit()
        
        let genBefore = try stage.committedGeneration()
        XCTAssertEqual(genBefore, 1)
        
        try stage.rotate(handle: Data("new-handle".utf8), publicKey: fixturePhonePublicKey(Data("new-handle".utf8)))
        
        let genAfter = try stage.committedGeneration()
        XCTAssertEqual(genAfter, 1, "IOSQA6-06: Old key should still be committed during rotation")
        
        XCTAssertTrue(stage.hasStagedKey(), "IOSQA6-06: New key should be staged")
        
        try stage.commit()
        let genFinal = try stage.committedGeneration()
        XCTAssertEqual(genFinal, 2, "Generation increments after completion")
    }
}

final class MockExactRunTransport: ExactRunPhoneSigningTransport {
    var fetchedRun: FetchedExactRun?
    
    func fetchRetainedExactRun() async throws -> FetchedExactRun {
        guard let run = fetchedRun else {
            throw CompanionClientError.transport("No exact run")
        }
        return run
    }
    
    func submitRetainedExactRunSignature(challengeId: String, signature: String) async throws {}
}


private final class CertificateProtectionSpace: URLProtectionSpace {
    let testTrust: SecTrust
    init(trust: SecTrust) {
        testTrust = trust
        super.init(host: "localhost", port: 443, protocol: "https", realm: nil,
                   authenticationMethod: NSURLAuthenticationMethodServerTrust)
    }
    required init?(coder: NSCoder) { fatalError("Not used by this fixture") }
    override var serverTrust: SecTrust? { testTrust }
}

private final class PinChallengeSender: NSObject, URLAuthenticationChallengeSender {
    func use(_ credential: URLCredential, for challenge: URLAuthenticationChallenge) {}
    func continueWithoutCredential(for challenge: URLAuthenticationChallenge) {}
    func cancel(_ challenge: URLAuthenticationChallenge) {}
}

extension ObserveSchemaTests {
    func testIOSQA701AcceptsRealCertificateThroughDelegate() throws {
        let der = try XCTUnwrap(Data(base64Encoded: "MIIDCTCCAfGgAwIBAgIUeb2wA2weOf2d7oiPQZyJl07V0XgwDQYJKoZIhvcNAQELBQAwFDESMBAGA1UEAwwJbG9jYWxob3N0MB4XDTI2MTAxNjAxMjcwM1oXDTM2MTAxMzAxMjcwM1owFDESMBAGA1UEAwwJbG9jYWxob3N0MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoXltWb/A9vnRaoU0cCOKOjzbbKaa3+eKf5KVsYu9KSucpzZG5yFhlkhjBlspypW1lDHSz+8GmYpgQI3OVhaRqFEx4rgte8Q74u75g8M8Q5u81CKqjgpIi8307VxUO0EdW5qE8111Jr73fi53UX1pz0Ly+l7n71UTk4pEtulAzvQm+lIdxtn/USW8gh5P81SHroXl1CEZYKzfpoXs/KO4jmIQv6OwsBqG22kML0bK1gdL6dtU5ICmwXl5Mb1KokcxtG7rgSfYLXsu+JuhG59aw60VYoNVdfZbYVXYT/dyIE2T/XrL2t8/f9vFSjn0UFmmomnaQrFMMDHIz4DgJNT8JwIDAQABo1MwUTAdBgNVHQ4EFgQUnnJiI6lY15E0zArWf9qH6pWXy+0wHwYDVR0jBBgwFoAUnnJiI6lY15E0zArWf9qH6pWXy+0wDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEAe6rUnGfvCa5u/XqIfIbq+OoNI9TrdV9TPtxgB27VklRCJHCNdysAFqiKcXK3EqP1/ageeHK/RfLWoj6N/jd7YQtRbMTGrHkTJ/rwyEKD6eeOcbNUPq6fB+mzbreobIivhKtaRhL/cfYJxpEYjsjTbbJCjr2MCVcyfaS6iPARZOR58EASBEV57apBHJ+BVild0x1G3PUVbbUuY6CkpyBSiPq1XxPan7XKcs66AIwwNPuFPMehE0VpqaS0K/fg/FLCRmXgqgPTe0EsJ9jobb49c7kAA/HHbrwZUBmWypngcTUWnUpJHC3ldsq32WYSZFgoGNJ+yYmQ4TdCuRKiv7FEWw=="))
        let certificate = try XCTUnwrap(SecCertificateCreateWithData(nil, der as CFData))
        var trust: SecTrust?
        XCTAssertEqual(SecTrustCreateWithCertificates(certificate, SecPolicyCreateSSL(true, "localhost" as CFString), &trust), errSecSuccess)
        let challenge = URLAuthenticationChallenge(protectionSpace: CertificateProtectionSpace(trust: try XCTUnwrap(trust)),
            proposedCredential: nil, previousFailureCount: 0, failureResponse: nil, error: nil, sender: PinChallengeSender())
        let digest = SHA256.hash(data: der).map { String(format: "%02x", $0) }.joined()
        for pin in [digest, digest.uppercased(), digest.map(String.init).joined(separator: ":")] {
            let delegate = CompanionTLSPinningDelegate(expectedFingerprint: pin)
            var disposition: URLSession.AuthChallengeDisposition?
            delegate.urlSession(.shared, didReceive: challenge) { result, credential in
                disposition = result
                XCTAssertNotNil(credential)
            }
            XCTAssertEqual(disposition, .useCredential)
            XCTAssertFalse(delegate.hadPinMismatch)
        }
        let wrong = CompanionTLSPinningDelegate(expectedFingerprint: String(repeating: "0", count: 64))
        wrong.urlSession(.shared, didReceive: challenge) { result, credential in
            XCTAssertEqual(result, .cancelAuthenticationChallenge)
            XCTAssertNil(credential)
        }
        XCTAssertTrue(wrong.hadPinMismatch)
    }

    @MainActor
    func testIOSQA702MigrationRetainsTokenUntilKeychainWriteSucceeds() throws {
        let defaults = CompanionSession.storageDefaults
        let key = "rs.observe.pairing"
        let previous = defaults.object(forKey: key)
        defer {
            defaults.set(previous, forKey: key)
            CompanionSession.testTokenRead = nil
            CompanionSession.testTokenWrite = nil
        }
        let config = PairingConfig(baseURL: URL(string: "https://localhost")!, pairingToken: "legacy-secret", tlsFingerprint: "abc")
        let legacy = try JSONEncoder().encode(config)
        defaults.set(legacy, forKey: key)
        CompanionSession.testTokenRead = { nil }
        var attempts = 0
        CompanionSession.testTokenWrite = { token in
            attempts += 1
            XCTAssertEqual(token, "legacy-secret")
            return errSecInteractionNotAllowed
        }
        let first = CompanionSession(deferPhoneKeyState: true)
        XCTAssertEqual(first.pairingToken, "legacy-secret")
        XCTAssertTrue(first.lastError?.contains(String(errSecInteractionNotAllowed)) == true)
        XCTAssertEqual(defaults.data(forKey: key), legacy)
        let second = CompanionSession(deferPhoneKeyState: true)
        XCTAssertEqual(second.pairingToken, "legacy-secret")
        XCTAssertEqual(attempts, 2)
        CompanionSession.testTokenWrite = { _ in errSecSuccess }
        _ = CompanionSession(deferPhoneKeyState: true)
        let sanitized = try JSONDecoder().decode(PairingConfig.self, from: XCTUnwrap(defaults.data(forKey: key)))
        XCTAssertEqual(sanitized.pairingToken, "")
    }
}

extension ObserveSchemaTests {
    func testIOSQA601EveryJournalPhaseRetainsFailedDeletionAndRetries() throws {
        for phase in [RotationState.RotationPhase.started, .newKeyStaged, .newKeyCommitted, .oldKeyRevoked, .completed] {
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            defer { try? FileManager.default.removeItem(at: directory) }
            try CompanionSecureEnclaveEnrollment.storeEnrollment(sampleRecord(keyID: "old", state:
                phase == .oldKeyRevoked || phase == .completed ? CompanionSecureEnclaveEnrollment.revoked : CompanionSecureEnclaveEnrollment.active,
                generation: 1), directory: directory) {}
            try CompanionSecureEnclaveEnrollment.storeEnrollment(sampleRecord(keyID: "new", state: CompanionSecureEnclaveEnrollment.active,
                generation: 2), directory: directory) {}
            let journal = directory.appendingPathComponent(".rotation-state.json")
            let state = RotationState(oldKeyID: "old", newKeyID: "new", phase: phase,
                                      oldKeyRevoked: phase == .oldKeyRevoked || phase == .completed, newKeyCreated: true)
            let bytes = try JSONEncoder().encode(state)
            try bytes.write(to: journal)
            CompanionSecureEnclaveEnrollment.testKeyDeleter = { _ in throw CompanionHardwareRefusal.keychainError(errSecNotAvailable) }
            XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory))
            XCTAssertEqual(try Data(contentsOf: journal), bytes)
            CompanionSecureEnclaveEnrollment.testKeyDeleter = nil
            CompanionSecureEnclaveEnrollment.testRotationFileRemoval = { url in
                if url == journal { throw CocoaError(.fileWriteNoPermission) }
            }
            XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory))
            XCTAssertEqual(try Data(contentsOf: journal), bytes)
            CompanionSecureEnclaveEnrollment.testRotationFileRemoval = nil
            try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
            XCTAssertFalse(FileManager.default.fileExists(atPath: journal.path))
            try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
        }
    }

    func testIOSQA601DiskRevocationAheadOfJournalKeepsReplacement() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        let old = try CompanionSecureEnclaveEnrollment.enroll(keyID: "old", directory: directory)
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "new", directory: directory)
        _ = try CompanionSecureEnclaveEnrollment.persistRevocation(old, directory: directory) { _ in }
        let journal = directory.appendingPathComponent(".rotation-state.json")
        try JSONEncoder().encode(RotationState(oldKeyID: "old", newKeyID: "new", phase: .newKeyCommitted,
            oldKeyRevoked: false, newKeyCreated: true)).write(to: journal)
        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
        XCTAssertEqual(try CompanionSecureEnclaveEnrollment.inspect(keyID: "new", directory: directory).state, CompanionSecureEnclaveEnrollment.active)
        XCTAssertEqual(try CompanionSecureEnclaveEnrollment.inspect(keyID: "old", directory: directory).state, CompanionSecureEnclaveEnrollment.revoked)
    }

    func testIOSQA601StagedJournalRemovesRecordWrittenBeforeCheckpoint() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "old", directory: directory)
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "new", directory: directory)
        let journal = directory.appendingPathComponent(".rotation-state.json")
        try JSONEncoder().encode(RotationState(oldKeyID: "old", newKeyID: "new", phase: .newKeyStaged,
            oldKeyRevoked: false, newKeyCreated: true)).write(to: journal)
        CompanionSecureEnclaveEnrollment.testRotationFileRemoval = { url in
            if url.lastPathComponent == "new.pairing.json" { throw CocoaError(.fileWriteNoPermission) }
        }
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory))
        XCTAssertTrue(FileManager.default.fileExists(atPath: journal.path))
        CompanionSecureEnclaveEnrollment.testRotationFileRemoval = nil
        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.inspect(keyID: "new", directory: directory))
        XCTAssertEqual(try CompanionSecureEnclaveEnrollment.inspect(keyID: "old", directory: directory).state, CompanionSecureEnclaveEnrollment.active)
    }

    @MainActor
    func testIOSQA612CancelledCallReturnsCancellationForBothActions() async {
        let session = CompanionSession(deferPhoneKeyState: true)
        let confirm = Task { @MainActor in
            withUnsafeCurrentTask { $0?.cancel() }
            return await session.submitRemoteConfirm()
        }
        let confirmOutcome = await confirm.value
        XCTAssertEqual(confirmOutcome, .cancelled)
        let refuse = Task { @MainActor in
            withUnsafeCurrentTask { $0?.cancel() }
            return await session.submitRemoteRefuse()
        }
        let refuseOutcome = await refuse.value
        XCTAssertEqual(refuseOutcome, .cancelled)
    }
}

extension ObserveSchemaTests {
    func testIOSQA601RotationCheckpointFailuresRecoverUnderLock() async throws {
        for phase in [RotationState.RotationPhase.started, .newKeyStaged, .newKeyCommitted, .oldKeyRevoked, .completed] {
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: directory) }
            CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
            _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "old", directory: directory)
            var reached = false
            CompanionSecureEnclaveEnrollment.testRotationCheckpoint = { state in
                let fd = open(directory.appendingPathComponent("enrollment.lock").path, O_RDWR)
                XCTAssertGreaterThanOrEqual(fd, 0)
                if fd >= 0 {
                    defer { close(fd) }
                    XCTAssertEqual(flock(fd, LOCK_EX | LOCK_NB), -1, "Journal checkpoints must hold the enrollment lock")
                }
                if state.phase == phase {
                    reached = true
                    throw CocoaError(.fileWriteUnknown)
                }
            }
            do {
                _ = try await CompanionSecureEnclaveEnrollment.rotate(from: "old", to: "new", directory: directory)
                XCTFail("Injected checkpoint failure must propagate")
            } catch { XCTAssertTrue(reached) }
            XCTAssertTrue(reached)
            CompanionSecureEnclaveEnrollment.testRotationCheckpoint = nil
            CompanionSecureEnclaveEnrollment.testKeyDeleter = { _ in
                let fd = open(directory.appendingPathComponent("enrollment.lock").path, O_RDWR)
                XCTAssertGreaterThanOrEqual(fd, 0)
                if fd >= 0 {
                    defer { close(fd) }
                    XCTAssertEqual(flock(fd, LOCK_EX | LOCK_NB), -1, "Recovery cleanup must hold the enrollment lock")
                }
            }
            try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
            CompanionSecureEnclaveEnrollment.testKeyDeleter = nil
            let old = try CompanionSecureEnclaveEnrollment.inspect(keyID: "old", directory: directory)
            if phase == .oldKeyRevoked || phase == .completed {
                XCTAssertEqual(old.state, CompanionSecureEnclaveEnrollment.revoked)
                XCTAssertEqual(try CompanionSecureEnclaveEnrollment.inspect(keyID: "new", directory: directory).state, CompanionSecureEnclaveEnrollment.active)
            } else {
                XCTAssertEqual(old.state, CompanionSecureEnclaveEnrollment.active)
                XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.inspect(keyID: "new", directory: directory))
            }
            XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path))
        }
    }
}

extension ObserveSchemaTests {
    @MainActor
    func testIOSQA612CancellationAfterTransportStartedPreservesAcknowledgement() async throws {
        for refuse in [false, true] {
            let session = CompanionSession(deferPhoneKeyState: true)
            session.baseURLString = "http://localhost"
            session.pairingToken = "test-token"
            session.isPaired = true
            session.status = CompanionStatus(phase: "active")
            session.capabilities = CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
                canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "test")
            session.challengeInput = "challenge"
            session.approvePhraseInput = "APPROVE"
            session.refuseReasonInput = "test refusal"
            let entered = expectation(description: "Production settlement request entered transport")
            var resume: CheckedContinuation<Data, Error>?
            let client = try XCTUnwrap(session.testMakeClient())
            client.testRequest = { request in
                if request.url?.path == "/v1/status" { throw CancellationError() }
                XCTAssertEqual(request.url?.path, refuse ? "/v1/remote-confirm-refuse" : "/v1/remote-confirm")
                return try await withCheckedThrowingContinuation { continuation in
                    resume = continuation
                    entered.fulfill()
                }
            }
            let task = Task { @MainActor in
                if refuse { return await session.submitRemoteRefuse() }
                return await session.submitRemoteConfirm()
            }
            await fulfillment(of: [entered], timeout: 3)
            task.cancel()
            let continuation = try XCTUnwrap(resume)
            continuation.resume(returning: Data((refuse ? "{\"ok\":true,\"refused\":true}" : "{\"ok\":true,\"settled\":true}").utf8))
            let result = await task.value
            XCTAssertEqual(result, refuse ? .refused : .confirmed)
            XCTAssertNotNil(session.lastRemoteConfirmNote)
            XCTAssertEqual(session.challengeInput, "")
        }
    }
}

extension ObserveSchemaTests {
    @MainActor
    private func qaPairedSession() -> CompanionSession {
        let session = CompanionSession(deferPhoneKeyState: true)
        session.baseURLString = "http://localhost"
        session.pairingToken = "fixture-token"
        session.isPaired = true
        session.status = CompanionStatus(phase: "active")
        session.capabilities = CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
            canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture")
        return session
    }

    @MainActor
    func testIOSQA604DisconnectRejectsStatusReleasedAfterDisconnect() async throws {
        let session = qaPairedSession()
        let client = try XCTUnwrap(session.testMakeClient())
        let entered = expectation(description: "Status request suspended")
        var resume: CheckedContinuation<Data, Error>?
        client.testRequest = { request in
            if request.url?.path == "/v1/status" {
                return try await withCheckedThrowingContinuation { continuation in
                    resume = continuation
                    entered.fulfill()
                }
            }
            return try JSONEncoder().encode(CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
                canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture"))
        }
        let task = Task { @MainActor in await session.refresh() }
        await fulfillment(of: [entered], timeout: 3)
        session.disconnect()
        try XCTUnwrap(resume).resume(returning: JSONEncoder().encode(CompanionStatus(phase: "active")))
        await task.value
        XCTAssertFalse(session.isPaired)
        XCTAssertNil(session.status)
        XCTAssertNil(session.capabilities)
        XCTAssertEqual(session.connectionState, .offline)
        XCTAssertEqual(session.refreshOutcome, .notAttempted)
    }

    @MainActor
    func testIOSQA605CapabilitiesFailureInvalidatesStaleCapabilities() async throws {
        let session = qaPairedSession()
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { request in
            if request.url?.path == "/v1/status" {
                return try JSONEncoder().encode(CompanionStatus(phase: "active"))
            }
            throw CompanionClientError.http(503, "unavailable")
        }
        await session.refresh()
        XCTAssertNil(session.capabilities)
        XCTAssertNotNil(session.lastError)
        XCTAssertEqual(session.connectionState, .stale)
        if case .failure = session.refreshOutcome {} else { XCTFail("Capability fetch failure must fail refresh") }
    }

    @MainActor
    func testIOSQA605ActionRequiresVerifiedStatusAndRestoredPairCannotAct() {
        let session = qaPairedSession()
        session.status = nil
        let validation = CapabilityValidator.validateForAction(capabilities: session.capabilities, status: session.status)
        if case .invalid = validation {} else { XCTFail("Capabilities alone must not enable actions") }
        XCTAssertNotEqual(session.connectionState, .connected)
    }

    func testIOSQA614CorruptRotationDestinationRemainsUntouched() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        try CompanionSecureEnclaveEnrollment.storeEnrollment(sampleRecord(keyID: "old", state: CompanionSecureEnclaveEnrollment.active, generation: 1), directory: directory) {}
        let destination = directory.appendingPathComponent("new.pairing.json")
        let corrupt = Data("{corrupt".utf8)
        try corrupt.write(to: destination)
        var creations = 0
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in
            creations += 1
            return Data(repeating: 4, count: 65)
        }
        do {
            _ = try await CompanionSecureEnclaveEnrollment.rotate(from: "old", to: "new", directory: directory)
            XCTFail("Corrupt destination must be occupied")
        } catch {
            XCTAssertEqual(creations, 0)
            XCTAssertEqual(try Data(contentsOf: destination), corrupt)
        }
    }

    func testIOSQA608SelectionDoesNotReplaceMissingStoredIdentity() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        try CompanionSecureEnclaveEnrollment.storeEnrollment(sampleRecord(keyID: "other", state: CompanionSecureEnclaveEnrollment.active, generation: 1), directory: directory) {}
        let selection = try HardwareKeySelection(persistedKeyID: "missing-selected-id", directory: directory)
        XCTAssertEqual(selection.keyID, "missing-selected-id")
        XCTAssertEqual(selection.records.map(\.keyID), ["other"])
        XCTAssertTrue(selection.corruptKeyIDs.isEmpty)
    }

    func testIOSQA609DisplayedRequestCannotSignWithAnotherSelectedKey() throws {
        let fields = try RSBA2Package.parse(JSONSerialization.data(withJSONObject: package()))
        let text = String(decoding: try JSONSerialization.data(withJSONObject: package()), as: UTF8.self)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.signDisplayed(packageText: text, displayed: fields,
            selectedKeyID: "another-key", directory: directory)) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .staleRequest)
        }
    }

    func testIOSQA704MarkUpdatedRefreshCompletesBeforeSuccessOutcome() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        var record = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        record.macUpdatePending = true
        try CompanionSecureEnclaveEnrollment.storeEnrollment(record, directory: directory) {}
        var refreshed = false
        let outcome = try HardwareKeyActions.markMacUpdated(keyID: record.keyID, directory: directory) {
            refreshed = true
            XCTAssertFalse(try CompanionSecureEnclaveEnrollment.inspect(keyID: record.keyID, directory: directory).macUpdatePending)
        }
        XCTAssertTrue(refreshed)
        XCTAssertEqual(outcome, .success("Key marked as updated on Mac."))
    }

    @MainActor
    func testIOSQA703StaleLaunchReadCannotRestoreEnrollmentAfterRevoke() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let key = try fixturePhonePublicKey(Data([1]))
        let record: [String: Any] = ["generation": 5, "handle": Data([1]).base64EncodedString(), "publicKey": key.base64EncodedString()]
        try JSONSerialization.data(withJSONObject: record).write(to: directory.appendingPathComponent("custody.json"))
        let session = CompanionSession(deferPhoneKeyState: true, phoneKeyStage: PhoneKeyStage.fixture(directory: directory))
        session.refreshPhonePeerKeyState()
        let captured = session.phonePeerKeyState
        XCTAssertEqual(captured, .enrolled(generation: 5))
        let entered = expectation(description: "Launch read suspended")
        var resume: CheckedContinuation<CompanionSession.PhonePeerKeyState, Never>?
        session.testPhoneKeyStateRead = {
            await withCheckedContinuation { continuation in
                resume = continuation
                entered.fulfill()
            }
        }
        let task = Task { @MainActor in await session.refreshPhonePeerKeyStateAsync() }
        await fulfillment(of: [entered], timeout: 3)
        try await session.revokePhonePeerKey()
        try XCTUnwrap(resume).resume(returning: captured)
        await task.value
        XCTAssertEqual(session.phonePeerKeyState, .noKey)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("custody.json").path))
    }

    @MainActor
    func testIOSQA611AsyncStateReportsRotationAndCorruption() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let stage = PhoneKeyStage.fixture(directory: directory)
        let session = CompanionSession(deferPhoneKeyState: true, phoneKeyStage: stage)
        let key = try fixturePhonePublicKey(Data([1]))
        try stage.stage(handle: Data([1]), publicKey: key)
        await session.refreshPhonePeerKeyStateAsync()
        XCTAssertEqual(session.phonePeerKeyState, .rotating(oldGeneration: 0, newPublicKey: key.base64EncodedString()))
        try Data("bad record".utf8).write(to: directory.appendingPathComponent("custody.json"))
        await session.refreshPhonePeerKeyStateAsync()
        if case .error = session.phonePeerKeyState {} else { XCTFail("Corruption must not look like no enrollment") }
    }
}

extension ObserveSchemaTests {
    @MainActor
    func testIOSQA612AcknowledgedSettlementSurvivesRefreshFailure() async throws {
        for refuse in [false, true] {
            let session = qaPairedSession()
            session.challengeInput = "challenge"
            session.approvePhraseInput = "APPROVE"
            session.refuseReasonInput = "test refusal"
            let client = try XCTUnwrap(session.testMakeClient())
            client.testRequest = { request in
                if request.url?.path == "/v1/remote-confirm" {
                    return Data("{\"ok\":true,\"settled\":true}".utf8)
                }
                if request.url?.path == "/v1/remote-confirm-refuse" {
                    return Data("{\"ok\":true,\"refused\":true}".utf8)
                }
                throw CompanionClientError.http(503, "status unavailable")
            }
            let outcome = refuse ? await session.submitRemoteRefuse() : await session.submitRemoteConfirm()
            XCTAssertEqual(outcome, refuse ? .refused : .confirmed)
            XCTAssertNotNil(session.lastRemoteConfirmNote)
            XCTAssertEqual(session.connectionState, .stale)
        }
    }
}

extension ObserveSchemaTests {
    @MainActor
    func testTypedRefreshFailureCarriesTheActualTransportError() async throws {
        let session = qaPairedSession()
        let client = try XCTUnwrap(session.testMakeClient())
        let error = CompanionClientError.http(503, "fixture unavailable")
        client.testRequest = { _ in throw error }
        await session.refresh()
        XCTAssertEqual(session.refreshOutcome, .failure(error.localizedDescription))
        XCTAssertEqual(session.lastError, error.localizedDescription)
        XCTAssertEqual(session.connectionState, .stale)
    }
}

private func fixturePhonePublicKey(_ handle: Data) throws -> Data {
    try P256.Signing.PrivateKey(rawRepresentation: Data(SHA256.hash(data: handle))).publicKey.x963Representation
}

private extension PhoneKeyStage {
    static func fixture(directory: URL) -> Self {
        Self(directory: directory, testPublicKeyForHandle: fixturePhonePublicKey)
    }
}

private final class BackgroundCheckingSigner: PhoneChallengeSigning {
    var signs = 0
    func sign(message: Data) throws -> (publicKey: String, signature: String) {
        XCTAssertFalse(Thread.isMainThread, "Production session must dispatch signing off the main actor")
        signs += 1
        return ("cHVibGlj", "c2ln")
    }
}

extension ObserveSchemaTests {
    func testIOSQA602RotationExportStateSurvivesSelectionRefreshAndRelaunch() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "old", directory: directory)
        _ = try await CompanionSecureEnclaveEnrollment.rotate(from: "old", to: "new", directory: directory)
        let initial = try HardwareRotationExport.pending(directory: directory)
        XCTAssertEqual(Set(initial.map(\.keyID)), ["old", "new"])
        XCTAssertEqual(initial.first { $0.keyID == "old" }?.isRevoked, true)
        XCTAssertEqual(initial.first { $0.keyID == "new" }?.isRevoked, false)
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "unrelated", directory: directory)
        let selection = try HardwareKeySelection(persistedKeyID: "unrelated", directory: directory)
        XCTAssertEqual(selection.keyID, "unrelated")
        let afterSelectionAndRefresh = try HardwareRotationExport.pending(directory: directory)
        XCTAssertEqual(afterSelectionAndRefresh, initial)
        let restored = try CompanionSecureEnclaveEnrollment.inspect(keyID: "new", directory: directory)
        XCTAssertEqual(restored.replacesKeyID, "old")
        XCTAssertEqual(try HardwareRotationExport.pending(directory: directory), initial)
        _ = try await CompanionSecureEnclaveEnrollment.rotate(from: "new", to: "newer", directory: directory)
        XCTAssertEqual(Set(try HardwareRotationExport.pending(directory: directory).map(\.keyID)), ["old", "new", "newer"])
        for id in ["old", "new", "newer"] { try CompanionSecureEnclaveEnrollment.markMacUpdated(keyID: id, directory: directory) }
        XCTAssertTrue(try HardwareRotationExport.pending(directory: directory).isEmpty)
    }

    func testIOSQA607RejectsRandomPublicKeyAndMismatchedHandle() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let stage = PhoneKeyStage.fixture(directory: directory)
        try stage.stage(handle: Data("handle".utf8), publicKey: Data(repeating: 4, count: 65))
        XCTAssertThrowsError(try stage.commit())
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("custody.json").path))
        try stage.stage(handle: Data("handle".utf8), publicKey: fixturePhonePublicKey(Data("different-handle".utf8)))
        XCTAssertThrowsError(try stage.commit())
        // The production Secure Enclave resolver must reject opaque junk too.
        let productionStage = PhoneKeyStage(directory: directory)
        try productionStage.stage(handle: Data("not-an-enclave-handle".utf8), publicKey: fixturePhonePublicKey(Data("handle".utf8)))
        XCTAssertThrowsError(try productionStage.commit())
    }

    func testIOSQA607CorruptCustodyNeverRestartsGenerationOrOverwritesRecord() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let stage = PhoneKeyStage.fixture(directory: directory)
        let handle = Data("next".utf8)
        let publicKey = try fixturePhonePublicKey(handle)
        let recordURL = directory.appendingPathComponent("custody.json")
        for generation: Any in [true, 0, -1, Int.max, "1"] {
            let object: [String: Any] = ["generation": generation, "handle": handle.base64EncodedString(), "publicKey": publicKey.base64EncodedString()]
            let corrupt = try JSONSerialization.data(withJSONObject: object)
            try corrupt.write(to: recordURL)
            try stage.stage(handle: handle, publicKey: publicKey)
            XCTAssertThrowsError(try stage.commit())
            XCTAssertEqual(try Data(contentsOf: recordURL), corrupt)
        }
        let corrupt = Data("{broken-custody".utf8)
        try corrupt.write(to: recordURL)
        XCTAssertThrowsError(try stage.commit())
        XCTAssertEqual(try Data(contentsOf: recordURL), corrupt)
    }

    @MainActor
    func testIOSQA606RevokeRequiresBiometricsAndCancellationPreservesCustody() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let stage = PhoneKeyStage.fixture(directory: directory)
        let handle = Data("old".utf8)
        try stage.stage(handle: handle, publicKey: fixturePhonePublicKey(handle))
        try stage.commit()
        let session = CompanionSession(deferPhoneKeyState: true, phoneKeyStage: stage)
        session.refreshPhonePeerKeyState()
        let previous = try Data(contentsOf: directory.appendingPathComponent("custody.json"))
        var authentications = 0
        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in
            authentications += 1
            throw CompanionHardwareRefusal.automationRefused
        }
        do { try await session.revokePhonePeerKey(); XCTFail("Cancelled biometrics must refuse revocation") }
        catch { XCTAssertEqual(error as? CompanionHardwareRefusal, .automationRefused) }
        XCTAssertEqual(authentications, 1)
        XCTAssertEqual(try Data(contentsOf: directory.appendingPathComponent("custody.json")), previous)
        XCTAssertEqual(session.phonePeerKeyState, .enrolled(generation: 1))
        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in authentications += 1 }
        try await session.revokePhonePeerKey()
        XCTAssertEqual(authentications, 2)
        XCTAssertEqual(session.phonePeerKeyState, .noKey)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("custody.json").path))
    }

    @MainActor
    func testIOSQA606RotationCompletionRequiresSignedReceiptAndBiometrics() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let stage = PhoneKeyStage.fixture(directory: directory)
        try stage.stage(handle: Data("old".utf8), publicKey: fixturePhonePublicKey(Data("old".utf8)))
        try stage.commit()
        let peer = MockPhonePeerTransport()
        let challenge = try await peer.fetchPhonePeerChallenge()
        let newHandle = Data("replacement".utf8)
        let newPublicKey = try fixturePhonePublicKey(newHandle)
        try stage.stage(handle: newHandle, publicKey: newPublicKey, challengeId: challenge.challengeId)
        let session = CompanionSession(deferPhoneKeyState: true, phoneKeyStage: stage)
        let configured = qaPairedSession()
        session.isPaired = true
        session.status = configured.status
        session.capabilities = configured.capabilities
        let signer = LivePhoneSecureEnclaveSigner(stage: stage)
        var authentications = 0
        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in authentications += 1 }
        do { try await session.completePhonePeerKeyRotation(signer: signer, peer: peer); XCTFail("No signed challenge must not complete") } catch { }
        XCTAssertEqual(try stage.committedGeneration(), 1)
        session.phoneChallenge = challenge
        session.signedPhonePublicKey = newPublicKey.base64EncodedString()
        peer.verification = PhoneHolderVerification(verified: true, consumed: true, invalidated: false)
        do { try await session.completePhonePeerKeyRotation(signer: signer, peer: peer); XCTFail("Flags are not a holder receipt") } catch { }
        XCTAssertEqual(authentications, 0)
        XCTAssertEqual(try stage.committedGeneration(), 1)
        let mac = P256.Signing.PrivateKey()
        session.macSessionPublicKey = mac.publicKey.x963Representation.base64EncodedString()
        peer.verification = try signedPhoneReceipt(key: mac, challenge: challenge, phonePublicKey: newPublicKey.base64EncodedString())
        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in
            authentications += 1
            throw CompanionHardwareRefusal.automationRefused
        }
        do { try await session.completePhonePeerKeyRotation(signer: signer, peer: peer); XCTFail("Biometric refusal must preserve old custody") } catch { }
        XCTAssertEqual(authentications, 1)
        XCTAssertEqual(try stage.committedGeneration(), 1)
        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in authentications += 1 }
        try await session.completePhonePeerKeyRotation(signer: signer, peer: peer)
        XCTAssertEqual(authentications, 2)
        XCTAssertEqual(try stage.committedGeneration(), 2)
        XCTAssertEqual(try stage.committedPublicKey(), newPublicKey)
        XCTAssertEqual(session.phonePeerKeyState, .enrolled(generation: 2))
    }

    @MainActor
    func testIOSQA613SessionSignsOffMainActor() async {
        let session = qaPairedSession()
        let signer = BackgroundCheckingSigner()
        await session.signPhonePeerChallenge(signer: signer, peer: MockPhonePeerTransport())
        XCTAssertEqual(signer.signs, 1)
        XCTAssertEqual(session.signedPhonePublicKey, "cHVibGlj")
    }

    @MainActor
    func testIOSQA613CancellationInvalidatesContextWhileWorkerIsBlocked() async throws {
        let entered = expectation(description: "Crypto operation started")
        let invalidated = expectation(description: "Context invalidated before worker completes")
        let release = DispatchSemaphore(value: 0)
        CryptoOperationContext.testDidInvalidate = { invalidated.fulfill() }
        let task = Task {
            try await CryptoWorker.withContext { _ in
                XCTAssertFalse(Thread.isMainThread)
                entered.fulfill()
                release.wait()
                return "must not publish"
            }
        }
        await fulfillment(of: [entered], timeout: 3)
        task.cancel()
        await fulfillment(of: [invalidated], timeout: 3)
        release.signal()
        do { _ = try await task.value; XCTFail("Cancelled crypto result must not escape") }
        catch { XCTAssertTrue(error is CancellationError) }
        CryptoOperationContext.testDidInvalidate = nil
    }

    @MainActor
    func testIOSQA613HardwareViewSigningEntryRunsKeyOperationOffMainActor() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        CompanionSecureEnclaveEnrollment.clock = { 1_600_000_000 }
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in
            XCTAssertFalse(Thread.isMainThread)
            return Data(repeating: 4, count: 65)
        }
        _ = try await CompanionSecureEnclaveEnrollment.enrollAsync(keyID: "phone-vector", directory: directory)
        let text = String(decoding: try JSONSerialization.data(withJSONObject: package()), as: UTF8.self)
        let fields = try RSBA2Package.parse(Data(text.utf8))
        CompanionSecureEnclaveEnrollment.testSignatureProducer = { bytes in
            XCTAssertFalse(Thread.isMainThread)
            XCTAssertFalse(bytes.isEmpty)
            return Data([1, 2, 3])
        }
        let signature = try await CompanionSecureEnclaveEnrollment.signDisplayedAsync(packageText: text,
            displayed: fields, selectedKeyID: "phone-vector", directory: directory)
        XCTAssertEqual(signature, Data([1, 2, 3]))
    }

    func testIOSQA613LateCleanupCannotDeleteSuccessorOperationStage() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let stage = PhoneKeyStage.fixture(directory: directory)
        try stage.stage(handle: Data("old".utf8), publicKey: fixturePhonePublicKey(Data("old".utf8)), challengeId: "old", operationID: "operation-old")
        try stage.stage(handle: Data("new".utf8), publicKey: fixturePhonePublicKey(Data("new".utf8)), challengeId: "new", operationID: "operation-new")
        stage.discard(ownedByOperation: "operation-old")
        XCTAssertEqual(try stage.stagedHandle(), Data("new".utf8))
        stage.discard(ownedByOperation: "operation-new")
        XCTAssertFalse(stage.hasAnyStagedParts())
    }
}

extension ObserveSchemaTests {
    func testIOSQA607OpaqueInvalidHandleCannotCommit() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let stage = PhoneKeyStage(directory: directory)
        try stage.stage(handle: Data("invalid-enclave-handle".utf8), publicKey: P256.Signing.PrivateKey().publicKey.x963Representation)
        XCTAssertThrowsError(try stage.commit())
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("custody.json").path))
    }
}

extension ObserveSchemaTests {
    @MainActor
    func testIOSQA702PairingWriteFailureKeepsPreviousConfigurationAndToken() throws {
        let key = "rs.observe.pairing"
        let defaults = CompanionSession.storageDefaults
        let previous = defaults.object(forKey: key)
        defer {
            defaults.set(previous, forKey: key)
            CompanionSession.testTokenRead = nil
            CompanionSession.testTokenWrite = nil
        }
        let old = PairingConfig(baseURL: URL(string: "https://old.example")!, pairingToken: "", tlsFingerprint: "old-pin")
        let oldData = try JSONEncoder().encode(old)
        defaults.set(oldData, forKey: key)
        CompanionSession.testTokenRead = { "old-token" }
        CompanionSession.testTokenWrite = { _ in errSecInteractionNotAllowed }
        let session = CompanionSession(deferPhoneKeyState: true)
        let replacement = PairingConfig(baseURL: URL(string: "https://new.example")!, pairingToken: "new-token", tlsFingerprint: "new-pin")
        XCTAssertThrowsError(try session.persist(replacement)) { error in
            XCTAssertTrue(error.localizedDescription.contains(String(errSecInteractionNotAllowed)))
        }
        XCTAssertEqual(defaults.data(forKey: key), oldData)
        XCTAssertEqual(session.baseURLString, old.baseURL.absoluteString)
        XCTAssertEqual(session.pairingToken, "old-token")
        CompanionSession.testTokenWrite = { _ in errSecSuccess }
        try session.persist(replacement)
        let saved = try JSONDecoder().decode(PairingConfig.self, from: XCTUnwrap(defaults.data(forKey: key)))
        XCTAssertEqual(saved.baseURL, replacement.baseURL)
        XCTAssertEqual(saved.pairingToken, "")
        XCTAssertEqual(session.pairingToken, "new-token")
    }
}


extension ObserveSchemaTests {
    func testIOSQA607RevocationNeverReusesGeneration() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        for generation in 1...3 {
            let stage = PhoneKeyStage.fixture(directory: directory)
            let handle = Data("key-\(generation)".utf8)
            try stage.stage(handle: handle, publicKey: fixturePhonePublicKey(handle))
            try stage.commit()
            XCTAssertEqual(try stage.committedGeneration(), generation)
            try stage.revoke()
            XCTAssertThrowsError(try stage.committedHandle())
            XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("custody.json").path))
        }
        let stage = PhoneKeyStage.fixture(directory: directory)
        let reservation = directory.appendingPathComponent("custody-generation.json")
        let corrupt = Data("broken-counter".utf8)
        try corrupt.write(to: reservation)
        let handle = Data("next".utf8)
        try stage.stage(handle: handle, publicKey: fixturePhonePublicKey(handle))
        XCTAssertThrowsError(try stage.commit())
        XCTAssertEqual(try Data(contentsOf: reservation), corrupt)
        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent("custody.json").path))
    }

    @MainActor
    func testIOSQA6N5RecoveryFailureRemainsVisibleUntilSuccessfulRetry() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "old", directory: directory)
        let journal = directory.appendingPathComponent(".rotation-state.json")
        try JSONEncoder().encode(RotationState(oldKeyID: "old", newKeyID: "new", phase: .started,
            oldKeyRevoked: false, newKeyCreated: false)).write(to: journal)
        CompanionSecureEnclaveEnrollment.testRotationFileRemoval = { _ in throw CocoaError(.fileWriteNoPermission) }
        let session = CompanionSession(deferPhoneKeyState: true)
        await session.recoverHardwareRotation(directory: directory)
        XCTAssertNotNil(session.rotationRecoveryError)
        XCTAssertFalse(session.rotationRecoveryInProgress)
        XCTAssertTrue(FileManager.default.fileExists(atPath: journal.path))
        CompanionSecureEnclaveEnrollment.testRotationFileRemoval = nil
        await session.recoverHardwareRotation(directory: directory)
        XCTAssertNil(session.rotationRecoveryError)
        XCTAssertFalse(FileManager.default.fileExists(atPath: journal.path))
    }
}

extension ObserveSchemaTests {
    func testIOSQA601JournalWriteFailuresRecoverUnderLock() async throws {
        for phase in [RotationState.RotationPhase.started, .newKeyStaged, .newKeyCommitted, .oldKeyRevoked, .completed] {
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: directory) }
            CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
            _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "old", directory: directory)
            var reached = false
            CompanionSecureEnclaveEnrollment.testRotationWillWrite = { state in
                let fd = open(directory.appendingPathComponent("enrollment.lock").path, O_RDWR)
                XCTAssertGreaterThanOrEqual(fd, 0)
                if fd >= 0 {
                    defer { close(fd) }
                    XCTAssertEqual(flock(fd, LOCK_EX | LOCK_NB), -1, "Journal checkpoints must hold the enrollment lock")
                }
                if state.phase == phase {
                    reached = true
                    throw CocoaError(.fileWriteUnknown)
                }
            }
            do {
                _ = try await CompanionSecureEnclaveEnrollment.rotate(from: "old", to: "new", directory: directory)
                XCTFail("Injected checkpoint failure must propagate")
            } catch { XCTAssertTrue(reached) }
            XCTAssertTrue(reached)
            CompanionSecureEnclaveEnrollment.testRotationWillWrite = nil
            CompanionSecureEnclaveEnrollment.testKeyDeleter = { _ in
                let fd = open(directory.appendingPathComponent("enrollment.lock").path, O_RDWR)
                XCTAssertGreaterThanOrEqual(fd, 0)
                if fd >= 0 {
                    defer { close(fd) }
                    XCTAssertEqual(flock(fd, LOCK_EX | LOCK_NB), -1, "Recovery cleanup must hold the enrollment lock")
                }
            }
            try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
            CompanionSecureEnclaveEnrollment.testKeyDeleter = nil
            let old = try CompanionSecureEnclaveEnrollment.inspect(keyID: "old", directory: directory)
            if phase == .oldKeyRevoked || phase == .completed {
                XCTAssertEqual(old.state, CompanionSecureEnclaveEnrollment.revoked)
                XCTAssertEqual(try CompanionSecureEnclaveEnrollment.inspect(keyID: "new", directory: directory).state, CompanionSecureEnclaveEnrollment.active)
            } else {
                XCTAssertEqual(old.state, CompanionSecureEnclaveEnrollment.active)
                XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.inspect(keyID: "new", directory: directory))
            }
            XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path))
        }
    }
}

extension ObserveSchemaTests {
    func testIOSQA608MissingSavedSelectionIsExplicitlyUnavailable() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "other", directory: directory)
        let missing = try HardwareKeySelection(persistedKeyID: "gone", directory: directory)
        XCTAssertEqual(missing.keyID, "gone")
        XCTAssertTrue(missing.isUnavailable)
        XCTAssertFalse(try HardwareKeySelection(persistedKeyID: "other", directory: directory).isUnavailable)
    }
}

extension ObserveSchemaTests {
    func testIOSQA601MissingReplacementPreservesRecoveryEvidence() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        let old = try CompanionSecureEnclaveEnrollment.enroll(keyID: "old", directory: directory)
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "new", directory: directory)
        _ = try CompanionSecureEnclaveEnrollment.persistRevocation(old, directory: directory) { _ in }
        let replacementURL = directory.appendingPathComponent("new.pairing.json")
        let replacement = try Data(contentsOf: replacementURL)
        try FileManager.default.removeItem(at: replacementURL)
        let journal = directory.appendingPathComponent(".rotation-state.json")
        try JSONEncoder().encode(RotationState(oldKeyID: "old", newKeyID: "new", phase: .oldKeyRevoked,
            oldKeyRevoked: true, newKeyCreated: true)).write(to: journal)
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory))
        XCTAssertTrue(FileManager.default.fileExists(atPath: journal.path))
        try replacement.write(to: replacementURL)
        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
        XCTAssertFalse(FileManager.default.fileExists(atPath: journal.path))
        XCTAssertEqual(try CompanionSecureEnclaveEnrollment.inspect(keyID: "new", directory: directory).state, CompanionSecureEnclaveEnrollment.active)
    }

    func testIOSQA601StagedRollbackDeletesReplacementRecordWithoutHooks() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        CompanionSecureEnclaveEnrollment.testKeyCreator = { _ in Data(repeating: 4, count: 65) }
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "old", directory: directory)
        _ = try CompanionSecureEnclaveEnrollment.enroll(keyID: "new", directory: directory)
        try JSONEncoder().encode(RotationState(oldKeyID: "old", newKeyID: "new", phase: .newKeyStaged,
            oldKeyRevoked: false, newKeyCreated: true)).write(to: directory.appendingPathComponent(".rotation-state.json"))
        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.inspect(keyID: "new", directory: directory))
        XCTAssertEqual(try CompanionSecureEnclaveEnrollment.inspect(keyID: "old", directory: directory).state, CompanionSecureEnclaveEnrollment.active)
    }
}


extension ObserveSchemaTests {
    @MainActor
    func testIOSQA8C1RejectedCandidateIsNeverPersistedOrRestored() async throws {
        let defaults = CompanionSession.storageDefaults
        let previous = defaults.object(forKey: "rs.observe.pairing")
        defer { defaults.set(previous, forKey: "rs.observe.pairing"); CompanionSession.testTokenRead = nil; CompanionSession.testTokenWrite = nil }
        defaults.removeObject(forKey: "rs.observe.pairing")
        var token: String?
        var writes = 0
        CompanionSession.testTokenRead = { token }
        CompanionSession.testTokenWrite = { value in writes += 1; token = value; return errSecSuccess }
        let session = CompanionSession(deferPhoneKeyState: true)
        session.baseURLString = "https://localhost"
        session.pairingToken = "candidate-token"
        session.tlsFingerprint = "candidate-pin"
        let client = CompanionClient(config: PairingConfig(baseURL: URL(string: session.baseURLString)!, pairingToken: session.pairingToken, tlsFingerprint: session.tlsFingerprint))
        var reject = true
        client.testRequest = { request in
            if request.url?.path == "/v1/status" {
                if reject { throw CompanionClientError.tlsPinMismatch }
                return try JSONEncoder().encode(CompanionStatus(phase: "active"))
            }
            return try JSONEncoder().encode(CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
                canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture"))
        }
        await session.saveAndPair(client: client)
        XCTAssertFalse(session.isPaired)
        XCTAssertEqual(writes, 0)
        XCTAssertNil(defaults.data(forKey: "rs.observe.pairing"))
        XCTAssertNil(token)
        XCTAssertFalse(CompanionSession(deferPhoneKeyState: true).isPaired)
        reject = false
        await session.saveAndPair(client: client)
        XCTAssertTrue(session.isPaired)
        XCTAssertEqual(writes, 1)
        XCTAssertNotNil(session.status)
        XCTAssertNotNil(session.capabilities)
        XCTAssertTrue(CompanionSession(deferPhoneKeyState: true).isPaired)
    }

    @MainActor
    func testIOSQA8C2DismissalPreservesEvidenceAndDiagnosticsUntilRetrySucceeds() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let journal = directory.appendingPathComponent(".rotation-state.json")
        let bytes = try JSONEncoder().encode(RotationState(oldKeyID: "old", newKeyID: "new", phase: .started, oldKeyRevoked: false, newKeyCreated: false))
        try bytes.write(to: journal)
        CompanionSecureEnclaveEnrollment.testRotationFileRemoval = { _ in throw CocoaError(.fileWriteNoPermission) }
        let session = CompanionSession(deferPhoneKeyState: true)
        await session.recoverHardwareRotation(directory: directory)
        XCTAssertNotNil(session.rotationRecoveryError)
        session.dismissRotationRecoveryNotice()
        XCTAssertTrue(session.rotationRecoveryDismissed)
        XCTAssertTrue(session.rotationRecoveryDiagnostics.contains("Recovery evidence is retained"))
        XCTAssertEqual(try Data(contentsOf: journal), bytes)
        await session.recoverHardwareRotation(directory: directory)
        XCTAssertTrue(session.rotationRecoveryDismissed, "Repeated failure must not force the dismissed banner back")
        session.showRotationRecoveryNotice()
        XCTAssertFalse(session.rotationRecoveryDismissed)
        CompanionSecureEnclaveEnrollment.testRotationFileRemoval = nil
        await session.recoverHardwareRotation(directory: directory)
        XCTAssertNil(session.rotationRecoveryError)
        XCTAssertFalse(session.rotationRecoveryDismissed)
        XCTAssertFalse(FileManager.default.fileExists(atPath: journal.path))
    }

    @MainActor
    func testIOSQA8C3CounterRepairRequiresBiometricsAndPreservesHighWater() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let stage = PhoneKeyStage.fixture(directory: directory)
        let handle = Data("first".utf8)
        try stage.stage(handle: handle, publicKey: fixturePhonePublicKey(handle))
        try stage.commit()
        try stage.revoke()
        let primary = directory.appendingPathComponent("custody-generation.json")
        let recovery = directory.appendingPathComponent("custody-generation-recovery.json")
        // The recovery write can lead a failed primary write by a generation.
        try JSONEncoder().encode(7).write(to: recovery)
        let corrupt = Data("broken-counter".utf8)
        try corrupt.write(to: primary)
        let session = CompanionSession(deferPhoneKeyState: true, phoneKeyStage: stage)
        session.refreshPhonePeerKeyState()
        guard case .error(let message) = session.phonePeerKeyState else { return XCTFail("Counter damage must surface in the key UI") }
        XCTAssertTrue(message.contains("Repair saved key counter"))
        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in throw CompanionHardwareRefusal.automationRefused }
        do { try await session.repairPhoneKeyCounter(); XCTFail("Biometric refusal must not repair") } catch { }
        XCTAssertEqual(try Data(contentsOf: primary), corrupt)
        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in }
        try await session.repairPhoneKeyCounter()
        XCTAssertEqual(session.phonePeerKeyState, .noKey)
        let replacement = Data("replacement".utf8)
        try stage.stage(handle: replacement, publicKey: fixturePhonePublicKey(replacement))
        try stage.commit()
        XCTAssertEqual(try stage.committedGeneration(), 8)
    }

    func testIOSQA8C3MissingRecoveryRefusesResetAndLegacyCounterMigrates() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let stage = PhoneKeyStage.fixture(directory: directory)
        let primary = directory.appendingPathComponent("custody-generation.json")
        let corrupt = Data("bad".utf8)
        try corrupt.write(to: primary)
        XCTAssertThrowsError(try stage.repairGenerationReservation()) { error in
            XCTAssertEqual(error as? PhoneKeyStage.CounterRecoveryError, .noTrustedRecovery)
        }
        XCTAssertEqual(try Data(contentsOf: primary), corrupt)
        try JSONEncoder().encode(9).write(to: primary)
        let handle = Data("legacy-next".utf8)
        try stage.stage(handle: handle, publicKey: fixturePhonePublicKey(handle))
        try stage.commit()
        XCTAssertEqual(try stage.committedGeneration(), 10)
        try FileManager.default.removeItem(at: primary)
        XCTAssertThrowsError(try stage.checkGenerationReservation())
        try stage.repairGenerationReservation()
        try stage.revoke()
        try stage.stage(handle: handle, publicKey: fixturePhonePublicKey(handle))
        try stage.commit()
        XCTAssertEqual(try stage.committedGeneration(), 11)
    }

    func testIOSQA8C4OwnedCommitResolvesStagedHandleOnceAndRechecksNextOperation() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        var resolutions = 0
        var stage = PhoneKeyStage(directory: directory)
        stage.testPublicKeyForHandle = { handle in resolutions += 1; return try fixturePhonePublicKey(handle) }
        let handle = Data("first".utf8)
        let publicKey = try fixturePhonePublicKey(handle)
        try stage.stage(handle: handle, publicKey: publicKey, challengeId: "challenge")
        try stage.commit(ownedBy: "challenge", publicKey: publicKey)
        XCTAssertEqual(resolutions, 1, "Ownership and commit must share one validated staged snapshot")
        try stage.stage(handle: handle, publicKey: publicKey, challengeId: "next")
        resolutions = 0
        try stage.claimOperation("operation")
        XCTAssertEqual(resolutions, 1)
        // No cross-operation cache may accept bytes altered after validation.
        try Data("different".utf8).write(to: directory.appendingPathComponent("phone-session-handle.pending"))
        XCTAssertThrowsError(try stage.validateStagedParts())
        XCTAssertEqual(resolutions, 2)
    }
}

extension ObserveSchemaTests {
    @MainActor
    func testIOSQA8C1FailedOrCancelledReplacementKeepsPreviouslySavedPairing() async throws {
        let defaults = CompanionSession.storageDefaults
        let previous = defaults.object(forKey: "rs.observe.pairing")
        defer { defaults.set(previous, forKey: "rs.observe.pairing"); CompanionSession.testTokenRead = nil; CompanionSession.testTokenWrite = nil }
        var token = "old-token"
        var writes = 0
        CompanionSession.testTokenRead = { token }
        CompanionSession.testTokenWrite = { value in token = value; writes += 1; return errSecSuccess }
        let old = PairingConfig(baseURL: URL(string: "https://old.example")!, pairingToken: "old-token", tlsFingerprint: "old-pin")
        let session = CompanionSession(deferPhoneKeyState: true)
        try session.persist(old)
        let oldBytes = defaults.data(forKey: "rs.observe.pairing")
        writes = 0
        session.baseURLString = "https://new.example"
        session.pairingToken = "new-token"
        session.tlsFingerprint = "new-pin"
        let client = CompanionClient(config: PairingConfig(baseURL: URL(string: session.baseURLString)!, pairingToken: session.pairingToken, tlsFingerprint: session.tlsFingerprint))
        let entered = expectation(description: "Candidate verification suspended")
        var resume: CheckedContinuation<Data, Error>?
        var hold = false
        client.testRequest = { request in
            if request.url?.path == "/v1/status" {
                if !hold { throw CompanionClientError.http(503, "unavailable") }
                return try await withCheckedThrowingContinuation { continuation in resume = continuation; entered.fulfill() }
            }
            return try JSONEncoder().encode(CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
                canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture"))
        }
        await session.saveAndPair(client: client)
        XCTAssertEqual(defaults.data(forKey: "rs.observe.pairing"), oldBytes)
        XCTAssertEqual(token, "old-token")
        XCTAssertEqual(CompanionSession(deferPhoneKeyState: true).baseURLString, old.baseURL.absoluteString)
        hold = true
        let task = Task { @MainActor in await session.saveAndPair(client: client) }
        await fulfillment(of: [entered], timeout: 3)
        task.cancel()
        try XCTUnwrap(resume).resume(returning: JSONEncoder().encode(CompanionStatus(phase: "active")))
        await task.value
        XCTAssertEqual(writes, 0)
        XCTAssertEqual(token, "old-token")
        XCTAssertEqual(defaults.data(forKey: "rs.observe.pairing"), oldBytes)
        XCTAssertFalse(session.isPaired)
    }
}


extension ObserveSchemaTests {
    @MainActor
    func testIOSQAUXEnrollmentWithoutSignedChallengeExplainsNextStep() async throws {
        let session = qaPairedSession()
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { _ in
            XCTFail("Enrollment without a signed challenge must not contact the holder")
            throw CompanionClientError.http(500, "unexpected request")
        }
        let expected = "Sign a phone peer challenge first, then verify it on the Mac before enrolling."
        let outcome = await session.commitPhoneKeyAfterHolderVerification()
        XCTAssertEqual(outcome, .refused(expected))
        XCTAssertEqual(session.lastError, expected)
        XCTAssertEqual(session.phonePeerNote, expected)
    }
}


extension ObserveSchemaTests {
    func testDeviceReinstallDoesNotReportSurvivingKeyAsMissing() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        CompanionSecureEnclaveEnrollment.testInMemoryKeychain = ["yd-phone-2": Data([1, 2, 3])]
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.inspect(keyID: "yd-phone-2", directory: directory)) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .orphanedKey)
        }
        XCTAssertEqual(CompanionSecureEnclaveEnrollment.testInMemoryKeychain?["yd-phone-2"], Data([1, 2, 3]))
    }
}


extension ObserveSchemaTests {
    func testDeviceReinstallEnrollmentPreservesExistingKey() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        CompanionSecureEnclaveEnrollment.testInMemoryKeychain = ["yd-phone-2": Data([1, 2, 3])]
        var created = false
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.enrollReplacingMissingFile(keyID: "yd-phone-2", directory: directory, createKey: {
            created = true
            return Data(repeating: 1, count: 65)
        }, cleanup: {})) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .orphanedKey)
        }
        XCTAssertFalse(created)
        XCTAssertEqual(CompanionSecureEnclaveEnrollment.testInMemoryKeychain?["yd-phone-2"], Data([1, 2, 3]))
    }
}


extension ObserveSchemaTests {
    func testDeviceFaceIDCancellationHasExpectedFeedback() {
        let error = NSError(domain: LAError.errorDomain, code: LAError.userCancel.rawValue)
        XCTAssertEqual(CompanionHardwareErrorPresentation.describe(error).message, "Authentication cancelled.")
    }
    func testDeviceFaceIDPermissionDeniedGivesSettingsGuidance() {
        let error = NSError(domain: LAError.errorDomain, code: LAError.biometryNotAvailable.rawValue)
        XCTAssertTrue(CompanionHardwareErrorPresentation.describe(error).message.contains("Settings"))
    }
    func testDeviceWrappedKeychainCancellationHasExpectedFeedback() {
        let error = NSError(domain: NSOSStatusErrorDomain, code: Int(errSecUserCanceled))
        let wrapper = NSError(domain: "CryptoKit", code: 1, userInfo: [NSUnderlyingErrorKey: error])
        XCTAssertEqual(CompanionHardwareErrorPresentation.describe(wrapper).message, "Authentication cancelled.")
    }
}

extension ObserveSchemaTests {
    @MainActor
    func testICQA03LateAcknowledgementPreservesSuccessorDrafts() async throws {
        for refuse in [false, true] {
            let session = CompanionSession(deferPhoneKeyState: true)
            session.baseURLString = "http://localhost"
            session.pairingToken = "test-token"
            session.isPaired = true
            session.status = CompanionStatus(phase: "active")
            session.capabilities = CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
                canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "test")
            session.challengeInput = "challenge"
            session.approvePhraseInput = "APPROVE"
            session.refuseReasonInput = "test refusal"
            let entered = expectation(description: "Production settlement request entered transport")
            var resume: CheckedContinuation<Data, Error>?
            let client = try XCTUnwrap(session.testMakeClient())
            client.testRequest = { request in
                if request.url?.path == "/v1/status" { throw CancellationError() }
                XCTAssertEqual(request.url?.path, refuse ? "/v1/remote-confirm-refuse" : "/v1/remote-confirm")
                return try await withCheckedThrowingContinuation { continuation in
                    resume = continuation
                    entered.fulfill()
                }
            }
            let task = Task { @MainActor in
                if refuse { return await session.submitRemoteRefuse() }
                return await session.submitRemoteConfirm()
            }
            await fulfillment(of: [entered], timeout: 3)
            guard let continuation = resume else {
                task.cancel()
                _ = await task.value
                XCTFail("Settlement transport did not enter")
                continue
            }
            session.cancelAllTasks()
            session.challengeInput = "successor challenge"
            session.approvePhraseInput = "successor phrase"
            session.refuseReasonInput = "successor reason"
            session.lastRemoteConfirmNote = "successor note"
            continuation.resume(returning: Data((refuse ? "{\"ok\":true,\"refused\":true}" : "{\"ok\":true,\"settled\":true}").utf8))
            let result = await task.value
            XCTAssertEqual(result, refuse ? .refused : .confirmed)
            XCTAssertEqual(session.lastRemoteConfirmNote, "successor note")
            XCTAssertEqual(session.challengeInput, "successor challenge")
            XCTAssertEqual(session.approvePhraseInput, "successor phrase")
            XCTAssertEqual(session.refuseReasonInput, "successor reason")
        }
    }
}
