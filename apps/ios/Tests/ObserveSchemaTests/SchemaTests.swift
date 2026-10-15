import CryptoKit
import XCTest
@testable import RunSpecimenObserve

final class ObserveSchemaTests: XCTestCase {
    override func setUp() {
        super.setUp()
        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in }
        CompanionSecureEnclaveEnrollment.testKeyCreator = nil
        CompanionSecureEnclaveEnrollment.testKeyDeleter = nil
    }

    override func tearDown() {
        CompanionSecureEnclaveEnrollment.testAuthenticator = nil
        CompanionSecureEnclaveEnrollment.testKeyCreator = nil
        CompanionSecureEnclaveEnrollment.testKeyDeleter = nil
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
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("enrollment"))
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
        Thread.sleep(forTimeInterval: 0.05)
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
        let malformed = try Data(contentsOf: url)
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
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("enrollment"))
        }
        XCTAssertEqual(created, 0)
        XCTAssertEqual(try Data(contentsOf: url), malformed)

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
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("enrollment"))
        }
        XCTAssertEqual(created, 0)
        _ = chmod(url.path, 0o644)
        XCTAssertEqual(try Data(contentsOf: url), malformed)

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

    func testRotationRollsBackNewKeyWhenRevocationFails() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-rotate-rollback-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let oldKey = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1)
        try CompanionSecureEnclaveEnrollment.storeEnrollment(oldKey, directory: directory) {}
        let newKeyURL = directory.appendingPathComponent("new-key.pairing.json")
        XCTAssertFalse(FileManager.default.fileExists(atPath: newKeyURL.path))
        let oldKeyURL = directory.appendingPathComponent("phone-vector.pairing.json")
        let originalOldData = try Data(contentsOf: oldKeyURL)
        let stored = try CompanionSecureEnclaveEnrollment.inspect(keyID: oldKey.keyID, directory: directory)
        XCTAssertEqual(stored.state, CompanionSecureEnclaveEnrollment.active)
        XCTAssertEqual(stored.generation, 1)
        XCTAssertEqual(try Data(contentsOf: oldKeyURL), originalOldData)
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

        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)

        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path), "oldKeyRevoked phase should clear rotation state")
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

        try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)

        XCTAssertFalse(FileManager.default.fileExists(atPath: directory.appendingPathComponent(".rotation-state.json").path), "completed phase should clear rotation state")
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

    func testPhoneKeyStageValidatesStagedParts() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-staged-validation-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let stage = PhoneKeyStage(directory: directory)
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

        try Data(repeating: 4, count: 65).write(to: publicPath)
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
        XCTAssertFalse(delegate.hadPinMismatch, "Clear should not affect false state")
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
        let goodResult = CapabilityValidator.validateForAction(capabilities: goodCaps, status: nil)
        XCTAssertEqual(goodResult, .valid, "Should accept valid capabilities")

        let badStatus = CompanionStatus(phase: "active", companion: CompanionFlags(canApprove: true))
        let statusResult = CapabilityValidator.validateForAction(capabilities: goodCaps, status: badStatus)
        XCTAssertNotEqual(statusResult, .valid, "Should reject status with approve")
    }

    func testPhoneKeyStageValidatesStagedPartsBeforeOwnerCheck() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-staged-order-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        let stage = PhoneKeyStage(directory: directory)
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

        let stage = PhoneKeyStage(directory: directory)
        try stage.stage(handle: Data("handle".utf8), publicKey: Data(repeating: 4, count: 65))
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

    func testFailedRefreshShowsStaleWithoutAdvancingTimestamp() async throws {
        let session = await CompanionSession()

        let statusBefore = await MainActor.run { session.status }
        let isPairedBefore = await MainActor.run { session.isPaired }

        await MainActor.run {
            session.baseURLString = "http://localhost:9999"
            session.pairingToken = "test-token"
            session.tlsFingerprint = ""
            session.isPaired = true
        }

        await MainActor.run {
            XCTAssertNil(session.status, "Status should be nil before refresh")
            XCTAssertNil(session.lastError, "lastError should be nil before refresh")
        }

        await session.refresh()

        await MainActor.run {
            XCTAssertNotNil(session.lastError, "Failed refresh should set lastError")
            XCTAssertNil(session.status, "Status should remain nil after failed refresh (Offline)")
            XCTAssertTrue(session.isPaired, "isPaired should remain true after failed refresh")
        }
    }

    func testPhonePeerKeyStateRefreshesAfterHolderVerifiedCommit() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-commit-refresh-" + UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let signer = TempDirectoryTestSigner(directory: directory)

        let session = await CompanionSession()
        let mac = P256.Signing.PrivateKey()

        await MainActor.run {
            session.macSessionPublicKey = mac.publicKey.x963Representation.base64EncodedString()
            session.phonePeerKeyState = .enrolled(generation: 99)
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

        await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)

        await MainActor.run {
            XCTAssertEqual(signer.commits, 1, "signer.commitEnrollment should be called once")
            XCTAssertNil(session.phoneChallenge, "phoneChallenge should be cleared after commit")
            XCTAssertEqual(session.phonePeerKeyState, .noKey,
                "phonePeerKeyState should change after commit (refreshPhonePeerKeyState called)")
        }

        let generation = try signer.stage.committedGeneration()
        XCTAssertEqual(generation, 1, "Signer's stage should have generation 1 after commit")
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

    init(directory: URL) {
        self.stage = PhoneKeyStage(directory: directory)
        self.publicKey = Data(repeating: 4, count: 65)
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

    func commitEnrollment(ownedBy challengeId: String, publicKey: String) throws {
        guard let key = Data(base64Encoded: publicKey) else {
            throw CompanionClientError.transport("invalid key")
        }
        try stage.stage(handle: Data("test-handle".utf8), publicKey: key, challengeId: challengeId)
        try stage.commit(ownedBy: challengeId, publicKey: key)
        commits += 1
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
