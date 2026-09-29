import CryptoKit
import XCTest
@testable import RunSpecimenObserve

final class ObserveSchemaTests: XCTestCase {
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
        XCTAssertEqual(stored.generation, 2)
        let retried = try CompanionSecureEnclaveEnrollment.persistRevocation(stored, directory: directory) { _ in }
        XCTAssertEqual(retried.generation, 2)
        XCTAssertEqual(retried.state, CompanionSecureEnclaveEnrollment.revoked)
    }

    func testSignatureIsDiscardedWhenTheRecordChangesDuringTheWait() throws {
        let before = sampleRecord(state: CompanionSecureEnclaveEnrollment.active, generation: 1).snapshot
        var revoked = before
        revoked.state = CompanionSecureEnclaveEnrollment.revoked
        revoked.generation = 2
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

    func testRevocationUnderTheEnrollmentLockBumpsOnce() throws {
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
                XCTAssertEqual(live.generation, 2)
                _ = try CompanionSecureEnclaveEnrollment.persistRevocation(live, directory: directory) { _ in }
            }
            second.fulfill()
        }
        Thread.sleep(forTimeInterval: 0.05)
        finishFirst.signal()
        wait(for: [first, second], timeout: 3)
        let stored = try CompanionSecureEnclaveEnrollment.inspect(keyID: record.keyID, directory: directory)
        XCTAssertEqual(stored.state, CompanionSecureEnclaveEnrollment.revoked)
        XCTAssertEqual(stored.generation, 2)
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
            XCTAssertEqual(error as? CompanionHardwareRefusal, .malformed("enrollment"))
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
        XCTAssertEqual(stored.generation, 2)
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

    private func sampleRecord(state: String, generation: Int) -> CompanionPairingRecord {
        CompanionPairingRecord(
            keyID: "phone-vector",
            publicKey: Data(repeating: 4, count: 65),
            role: EnrollmentIdentity.roleCompanion,
            backend: EnrollmentIdentity.backendSecureEnclave,
            provenance: EnrollmentIdentity.provenanceProduction,
            state: state,
            generation: generation
        )
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
