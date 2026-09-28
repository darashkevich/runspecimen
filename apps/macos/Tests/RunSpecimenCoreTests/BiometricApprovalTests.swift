import CryptoKit
import XCTest
@testable import RunSpecimenCore

final class BiometricApprovalTests: XCTestCase {
    private var directory: URL!
    private var frozenNow = 1_500

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("rs-bio-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        frozenNow = 1_500
        BiometricApprovalStore.clock = { self.frozenNow }
    }

    override func tearDownWithError() throws {
        BiometricApprovalStore.clock = { Int(Date().timeIntervalSince1970) }
        BiometricApprovalStore.beforeExclusiveAccess = nil
        BiometricApprovalStore.beforeConsumptionDecision = nil
        try? FileManager.default.removeItem(at: directory)
    }

    func testConsumeOnceThenRejectsReplay() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 2_000)
        try submit(request, key: key, now: 1_000)
        try BiometricApprovalStore.consume(
            request: request,
            pinnedPublicKey: key.publicKey.x963Representation,
            directory: directory
        )
        XCTAssertTrue(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: request,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .replay)
        }
    }

    func testValidJSONWithACorruptedSignatureIsTamper() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 2_000)
        try submit(request, key: key, now: 1_000)
        let url = pending(request.nonce)
        var object = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: String]
        var signature = Data(base64Encoded: object["signature_b64"]!)!
        signature[0] ^= 0xff
        object["signature_b64"] = signature.base64EncodedString()
        try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]).write(to: url)
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: request,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .tampered)
        }
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
    }

    func testMalformedApprovalAndRequestInputsAreRejected() throws {
        var empty = sample(nonce: nonce(), expiry: 2_000)
        empty.macID = ""
        XCTAssertThrowsError(try empty.canonicalBytes())
        empty = sample(nonce: "not-hex", expiry: 2_000)
        XCTAssertThrowsError(try empty.canonicalBytes())
        empty = sample(nonce: nonce(), expiry: 2_000)
        empty.keyID = "../escape"
        XCTAssertThrowsError(try empty.canonicalBytes())

        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce("b"), expiry: 2_000)
        try Data("not-json".utf8).write(to: pending(request.nonce))
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: request,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .tampered)
        }
        try Data("{\"canonical_b64\":\"YQ==\"}".utf8).write(to: pending(request.nonce))
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: request,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .tampered)
        }
    }

    func testEachSignedFieldIsBound() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 2_000)
        let signature = try signature(request, key: key)
        let publicKey = key.publicKey.x963Representation
        var variants = [request]
        variants[0].macID = "other-mac"
        var workspace = request
        workspace.workspaceID = "other-ws"
        var run = request
        run.runID = "other-run"
        var contract = request
        contract.contractSHA256 = String(repeating: "ab", count: 32)
        var inputs = request
        inputs.inputsSHA256 = String(repeating: "cd", count: 32)
        var bounds = request
        bounds.bounds = "timeout_seconds=1"
        var otherNonce = request
        otherNonce.nonce = nonce("c")
        var expiry = request
        expiry.expiryUnix = 2_001
        var keyID = request
        keyID.keyID = "other-key"
        for changed in [variants[0], workspace, run, contract, inputs, bounds, otherNonce, expiry, keyID] {
            XCTAssertFalse(
                BiometricApprovalStore.verify(
                    canonical: try changed.canonicalBytes(),
                    signature: signature,
                    publicKey: publicKey
                ),
                "field change still verified"
            )
        }
    }

    func testEnrollmentSignsLaterRequestsWithTheSameKey() throws {
        let keyID = "local-test"
        let enrolled = try SoftwareApprovalKeyEnrollment.enroll(keyID: keyID, directory: enrollmentDirectory)
        let reloaded = try BiometricEnrollmentDirectory.load(keyID: keyID, directory: enrollmentDirectory)
        XCTAssertEqual(reloaded.publicKey, enrolled)
        XCTAssertEqual(reloaded.state, BiometricEnrollmentRecord.active)
        let mode = try FileManager.default.attributesOfItem(
            atPath: SoftwareApprovalKeyEnrollment.privateURL(enrollmentDirectory, keyID).path
        )[.posixPermissions] as? NSNumber
        XCTAssertEqual(mode?.int16Value, 0o600)

        let first = sample(nonce: nonce(), expiry: 2_000)
        let second = sample(nonce: nonce("d"), expiry: 2_000)
        let firstSignature = try SoftwareApprovalKeyEnrollment.sign(first, directory: enrollmentDirectory)
        let secondSignature = try SoftwareApprovalKeyEnrollment.sign(second, directory: enrollmentDirectory)
        XCTAssertTrue(BiometricApprovalStore.verify(canonical: try first.canonicalBytes(), signature: firstSignature, publicKey: enrolled))
        XCTAssertTrue(BiometricApprovalStore.verify(canonical: try second.canonicalBytes(), signature: secondSignature, publicKey: enrolled))

        try BiometricApprovalStore.submitEnrolled(
            request: first,
            signature: firstSignature,
            enrollmentDirectory: enrollmentDirectory,
            approvalDirectory: directory
        )
        try BiometricApprovalStore.consumeEnrolled(
            request: first,
            enrollmentDirectory: enrollmentDirectory,
            approvalDirectory: directory
        )
        XCTAssertThrowsError(
            try BiometricApprovalStore.consumeEnrolled(
                request: first,
                enrollmentDirectory: enrollmentDirectory,
                approvalDirectory: directory
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .replay)
        }
    }

    func testRevokeAndRotateStopTheOldKey() throws {
        let oldID = "local-old"
        _ = try SoftwareApprovalKeyEnrollment.enroll(keyID: oldID, directory: enrollmentDirectory)
        let oldRequest = sample(nonce: nonce(), expiry: 2_000)
        var oldKeyed = oldRequest
        oldKeyed.keyID = oldID
        _ = try SoftwareApprovalKeyEnrollment.sign(oldKeyed, directory: enrollmentDirectory)
        let rotated = try SoftwareApprovalKeyEnrollment.rotate(from: oldID, to: "local-new", directory: enrollmentDirectory)
        XCTAssertThrowsError(try SoftwareApprovalKeyEnrollment.sign(oldKeyed, directory: enrollmentDirectory)) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .revoked)
        }
        let retired = try BiometricEnrollmentDirectory.load(keyID: oldID, directory: enrollmentDirectory)
        XCTAssertEqual(retired.state, BiometricEnrollmentRecord.revoked)
        XCTAssertFalse(FileManager.default.fileExists(
            atPath: SoftwareApprovalKeyEnrollment.privateURL(enrollmentDirectory, oldID).path
        ))
        var next = sample(nonce: nonce("e"), expiry: 2_000)
        next.keyID = "local-new"
        let signature = try SoftwareApprovalKeyEnrollment.sign(next, directory: enrollmentDirectory)
        XCTAssertTrue(
            BiometricApprovalStore.verify(
                canonical: try next.canonicalBytes(),
                signature: signature,
                publicKey: rotated
            )
        )
    }

    func testRevokeWhileConsumeIsBlockedRejectsTheStaleActiveRecord() throws {
        let keyID = "local-test"
        _ = try SoftwareApprovalKeyEnrollment.enroll(keyID: keyID, directory: enrollmentDirectory)
        let request = sample(nonce: nonce("1"), expiry: 2_000)
        let signature = try SoftwareApprovalKeyEnrollment.sign(request, directory: enrollmentDirectory)
        try BiometricApprovalStore.submitEnrolled(
            request: request,
            signature: signature,
            enrollmentDirectory: enrollmentDirectory,
            approvalDirectory: directory
        )
        let entered = DispatchSemaphore(value: 0)
        let release = DispatchSemaphore(value: 0)
        BiometricApprovalStore.beforeExclusiveAccess = {
            entered.signal()
            _ = release.wait(timeout: .now() + 2)
        }
        defer {
            BiometricApprovalStore.beforeExclusiveAccess = nil
            release.signal()
        }
        var outcome: BiometricApprovalError?
        let finished = DispatchGroup()
        finished.enter()
        DispatchQueue.global().async {
            do {
                try BiometricApprovalStore.consumeEnrolled(
                    request: request,
                    enrollmentDirectory: self.enrollmentDirectory,
                    approvalDirectory: self.directory
                )
            } catch let error as BiometricApprovalError {
                outcome = error
            } catch {
                outcome = .tampered
            }
            finished.leave()
        }
        XCTAssertEqual(entered.wait(timeout: .now() + 2), .success)
        try SoftwareApprovalKeyEnrollment.revoke(keyID: keyID, directory: enrollmentDirectory)
        release.signal()
        XCTAssertEqual(finished.wait(timeout: .now() + 2), .success)
        XCTAssertEqual(outcome, .revoked)
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
    }

    func testKeychainDeleteFailureIsNotReportedAsRemoval() {
        XCTAssertNil(LocalSecureEnclaveEnrollment.keychainDeletionError(status: errSecSuccess))
        XCTAssertNil(LocalSecureEnclaveEnrollment.keychainDeletionError(status: errSecItemNotFound))
        XCTAssertEqual(
            LocalSecureEnclaveEnrollment.keychainDeletionError(status: errSecAuthFailed),
            .malformed("keychain")
        )
    }

    func testUserWritableConsumedMarkerCanBeRolledBack() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce("f"), expiry: 2_000)
        try submit(request, key: key, now: 1_000)
        let savedApproval = try Data(contentsOf: pending(request.nonce))
        try BiometricApprovalStore.consume(
            request: request,
            pinnedPublicKey: key.publicKey.x963Representation,
            directory: directory
        )
        try savedApproval.write(to: pending(request.nonce))
        try FileManager.default.removeItem(at: directory.appendingPathComponent("\(request.nonce).consumed"))
        // Restoring these files is enough to consume again. The directory is user-writable.
        try BiometricApprovalStore.consume(
            request: request,
            pinnedPublicKey: key.publicKey.x963Representation,
            directory: directory
        )
    }

    func testDifferentContractIsNotConsumed() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 2_000)
        try submit(request, key: key, now: 1_000)
        var other = request
        other.contractSHA256 = String(repeating: "ab", count: 32)
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: other,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .mismatch)
        }
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        try BiometricApprovalStore.consume(
            request: request,
            pinnedPublicKey: key.publicKey.x963Representation,
            directory: directory
        )
    }

    func testExpiredApprovalIsSpentSoAClockChangeCannotReuseIt() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 1_200)
        try submit(request, key: key, now: 1_000)
        frozenNow = 1_200
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: request,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .expired)
        }
        XCTAssertTrue(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        frozenNow = 1_000
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: request,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .replay)
        }
    }

    func testExpiryDuringLockWaitSpendsTheNonce() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce("8"), expiry: 2_000)
        try submit(request, key: key, now: 1_000)
        let entered = DispatchSemaphore(value: 0)
        let release = DispatchSemaphore(value: 0)
        BiometricApprovalStore.beforeConsumptionDecision = {
            entered.signal()
            _ = release.wait(timeout: .now() + 2)
        }
        defer {
            BiometricApprovalStore.beforeConsumptionDecision = nil
            release.signal()
        }
        var outcome: BiometricApprovalError?
        let finished = DispatchGroup()
        finished.enter()
        DispatchQueue.global().async {
            do {
                try BiometricApprovalStore.consume(
                    request: request,
                    pinnedPublicKey: key.publicKey.x963Representation,
                    directory: self.directory
                )
            } catch let error as BiometricApprovalError {
                outcome = error
            } catch {
                outcome = .tampered
            }
            finished.leave()
        }
        XCTAssertEqual(entered.wait(timeout: .now() + 2), .success)
        self.frozenNow = 2_500
        release.signal()
        XCTAssertEqual(finished.wait(timeout: .now() + 2), .success)
        XCTAssertEqual(outcome, .expired)
        XCTAssertTrue(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
    }

    func testConcurrentConsumeSpendsTheNonceOnce() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 2_000)
        try submit(request, key: key, now: 1_000)
        let group = DispatchGroup()
        let results = NSLock()
        var outcomes: [BiometricApprovalError?] = []
        for _ in 0..<8 {
            group.enter()
            DispatchQueue.global().async {
                do {
                    try BiometricApprovalStore.consume(
                        request: request,
                        pinnedPublicKey: key.publicKey.x963Representation,
                        directory: self.directory
                    )
                    results.lock()
                    outcomes.append(nil)
                    results.unlock()
                } catch let error as BiometricApprovalError {
                    results.lock()
                    outcomes.append(error)
                    results.unlock()
                } catch {
                    results.lock()
                    outcomes.append(.tampered)
                    results.unlock()
                }
                group.leave()
            }
        }
        XCTAssertEqual(group.wait(timeout: .now() + 2), .success)
        XCTAssertEqual(outcomes.filter { $0 == nil }.count, 1)
        XCTAssertEqual(outcomes.filter { $0 == .replay }.count, 7)
    }

    func testUnpinnedKeyIsRejected() throws {
        let key = P256.Signing.PrivateKey()
        let other = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 2_000)
        XCTAssertThrowsError(
            try BiometricApprovalStore.submit(
                request: request,
                signature: try signature(request, key: key),
                publicKey: key.publicKey.x963Representation,
                pinnedPublicKey: other.publicKey.x963Representation,
                directory: directory
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .tampered)
        }
        XCTAssertFalse(FileManager.default.fileExists(atPath: pending(request.nonce).path))
    }

    func testBoundsAndInputChangesDoNotVerify() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 2_000)
        let signature = try signature(request, key: key)
        var changed = request
        changed.bounds = "timeout_seconds=1"
        XCTAssertFalse(
            BiometricApprovalStore.verify(
                canonical: try changed.canonicalBytes(),
                signature: signature,
                publicKey: key.publicKey.x963Representation
            )
        )
        changed = request
        changed.inputsSHA256 = String(repeating: "cd", count: 32)
        XCTAssertFalse(
            BiometricApprovalStore.verify(
                canonical: try changed.canonicalBytes(),
                signature: signature,
                publicKey: key.publicKey.x963Representation
            )
        )
    }

    func testSoftwareDoubleIsNotTheProductionPolicy() {
        XCTAssertFalse(LocalSecureEnclaveEnrollment.ProductionPolicy.accepts(
            backend: BiometricEnrollmentRecord.softwareBackend
        ))
        XCTAssertTrue(LocalSecureEnclaveEnrollment.ProductionPolicy.accepts(
            backend: BiometricEnrollmentRecord.secureEnclaveBackend
        ))
    }

    func testRSBA1CanonicalBytesStayLocal() throws {
        let request = sample(nonce: nonce(), expiry: 2_000)
        let digest = SHA256.hash(data: try request.canonicalBytes())
        let hex = digest.map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(hex, "58f4faea64f3a77289cc1f9016c84b4c58850f195e2b95c859f86d635b79b476")
    }

    func testTouchIDDiagnosticRefusesUnlessAHumanInvokesIt() {
        let refused = TouchIDDiagnosticGate.refusal(arguments: ["diag"])
        XCTAssertNotNil(refused)
        let outside = TouchIDDiagnosticGate.refusal(arguments: [
            "diag", "--human-invoked", "--directory", "/Users/yahor", "--key-id", "diag-a", "enroll"
        ])
        XCTAssertNotNil(outside)
        let accepted = TouchIDDiagnosticGate.refusal(arguments: [
            "diag", "--human-invoked", "--directory", "/private/tmp/rs-touchid-diag", "--key-id", "diag-a", "enroll"
        ])
        XCTAssertNil(accepted)
        XCTAssertNil(TouchIDDiagnosticGate.refusal(arguments: ["diag", "preview"]))
    }

    func testSecureEnclaveHumanHarnessIsNotRunByAutomation() throws {
        throw XCTSkip("Yahor runs Secure Enclave enroll, sign, reload, cancel, and revoke. This test does not call that path.")
    }

    private func submit(_ request: BiometricApprovalRequest, key: P256.Signing.PrivateKey, now: Int) throws {
        let previous = frozenNow
        frozenNow = now
        defer { frozenNow = previous }
        try BiometricApprovalStore.submit(
            request: request,
            signature: try signature(request, key: key),
            publicKey: key.publicKey.x963Representation,
            pinnedPublicKey: key.publicKey.x963Representation,
            directory: directory
        )
    }

    private func signature(_ request: BiometricApprovalRequest, key: P256.Signing.PrivateKey) throws -> Data {
        try key.signature(for: try request.canonicalBytes()).rawRepresentation
    }

    private func pending(_ nonce: String) -> URL {
        directory.appendingPathComponent("\(nonce).approval")
    }

    private var enrollmentDirectory: URL {
        directory.appendingPathComponent("enrollment", isDirectory: true)
    }

    private func nonce(_ mark: String = "a") -> String {
        String(repeating: mark, count: 64)
    }

    private func sample(nonce: String, expiry: Int) -> BiometricApprovalRequest {
        BiometricApprovalRequest(
            macID: "mac-1",
            workspaceID: "ws-1",
            runID: "run-1",
            contractSHA256: String(repeating: "11", count: 32),
            inputsSHA256: String(repeating: "22", count: 32),
            bounds: "timeout_seconds=30",
            nonce: nonce,
            expiryUnix: expiry,
            keyID: "local-test"
        )
    }
}

final class PolicyBoundApprovalTests: XCTestCase {
    private var directory: URL!
    private var frozenNow = 1_500

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("rs-policy-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        frozenNow = 1_500
        BiometricApprovalStore.clock = { self.frozenNow }
    }

    override func tearDownWithError() throws {
        BiometricApprovalStore.clock = { Int(Date().timeIntervalSince1970) }
        BiometricApprovalStore.beforeConsumptionDecision = nil
        try? FileManager.default.removeItem(at: directory)
    }

    func testLocalRejectsACompanionSignature() throws {
        let local = P256.Signing.PrivateKey()
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .local, localKeyID: "mac-key")
        XCTAssertThrowsError(try submit(request, local: local, companion: phone)) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .unsupportedPolicy)
        }
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
    }

    func testCompanionRejectsALocalOnlySignature() throws {
        let local = P256.Signing.PrivateKey()
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        XCTAssertThrowsError(try submit(request, local: local, companion: nil)) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .tampered)
        }
        XCTAssertThrowsError(try submit(request, local: local, companion: phone)) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .unsupportedPolicy)
        }
    }

    func testDualRequiresBothSignaturesOverTheSameRequest() throws {
        let local = P256.Signing.PrivateKey()
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .dual, localKeyID: "mac-key", companionKeyID: "phone-key")
        XCTAssertThrowsError(try submit(request, local: local, companion: nil)) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .tampered)
        }
        try submit(request, local: local, companion: phone)
        try PolicyBoundApprovalStore.consume(
            request: request,
            pinnedLocalKey: local.publicKey.x963Representation,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            localGeneration: 1,
            companionGeneration: 1,
            directory: directory
        )
        XCTAssertTrue(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        let lines = BiometricRequestPresentation.lines(for: request)
        XCTAssertTrue(lines.contains { $0.contains("not physical presence at the Mac") })
    }

    func testChangedInputsDoNotSpendTheNonce() throws {
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        try submit(request, local: nil, companion: phone)
        var changed = request
        changed.inputsSHA256 = String(repeating: "ee", count: 32)
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consume(
            request: changed,
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            localGeneration: nil,
            companionGeneration: 1,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .mismatch)
        }
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
    }

    func testWrongKeyExpiredRevokedAndReplay() throws {
        let phone = P256.Signing.PrivateKey()
        let other = P256.Signing.PrivateKey()
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        try submit(request, local: nil, companion: phone)
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consume(
            request: request,
            pinnedLocalKey: nil,
            pinnedCompanionKey: other.publicKey.x963Representation,
            localGeneration: nil,
            companionGeneration: 1,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .tampered)
        }
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consume(
            request: request,
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            localGeneration: nil,
            companionGeneration: 2,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .revoked)
        }
        frozenNow = 5_000
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consume(
            request: request,
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            localGeneration: nil,
            companionGeneration: 1,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .expired)
        }
        XCTAssertTrue(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consume(
            request: request,
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            localGeneration: nil,
            companionGeneration: 1,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .replay)
        }
    }

    func testUserMediatedPackageRejectsAMacPresenceClaim() throws {
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        var package = try JSONSerialization.jsonObject(with: try PolicyBoundApprovalStore.package(
            request: request,
            local: nil,
            companion: try signed(request, key: phone)
        )) as! [String: String]
        package["present_at_mac"] = "true"
        let data = try JSONSerialization.data(withJSONObject: package, options: [.sortedKeys])
        XCTAssertThrowsError(try PolicyBoundApprovalStore.importUserMediatedPackage(
            data,
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .malformed("presence"))
        }
    }

    func testUserMediatedPackageImportsACompanionSignature() throws {
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        let data = try PolicyBoundApprovalStore.package(
            request: request,
            local: nil,
            companion: try signed(request, key: phone)
        )
        let imported = try PolicyBoundApprovalStore.importUserMediatedPackage(
            data,
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            directory: directory
        )
        XCTAssertEqual(imported, request)
        try PolicyBoundApprovalStore.consume(
            request: imported,
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            localGeneration: nil,
            companionGeneration: 1,
            directory: directory
        )
    }

    func testDualConsumeIsSingleUseUnderContention() throws {
        let local = P256.Signing.PrivateKey()
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .dual, localKeyID: "mac-key", companionKeyID: "phone-key")
        try submit(request, local: local, companion: phone)
        let group = DispatchGroup()
        let results = NSLock()
        var outcomes: [BiometricApprovalError?] = []
        for _ in 0..<8 {
            group.enter()
            DispatchQueue.global().async {
                do {
                    try PolicyBoundApprovalStore.consume(
                        request: request,
                        pinnedLocalKey: local.publicKey.x963Representation,
                        pinnedCompanionKey: phone.publicKey.x963Representation,
                        localGeneration: 1,
                        companionGeneration: 1,
                        directory: self.directory
                    )
                    results.lock()
                    outcomes.append(nil)
                    results.unlock()
                } catch let error as BiometricApprovalError {
                    results.lock()
                    outcomes.append(error)
                    results.unlock()
                } catch {
                    results.lock()
                    outcomes.append(.tampered)
                    results.unlock()
                }
                group.leave()
            }
        }
        XCTAssertEqual(group.wait(timeout: .now() + 2), .success)
        XCTAssertEqual(outcomes.filter { $0 == nil }.count, 1)
        XCTAssertEqual(outcomes.filter { $0 == .replay }.count, 7)
    }

    func testPolicyDowngradeDoesNotVerify() throws {
        let local = P256.Signing.PrivateKey()
        let dual = sample(policy: .dual, localKeyID: "mac-key", companionKeyID: "phone-key")
        let signature = try signed(dual, key: local)
        var localOnly = dual
        localOnly.policy = .local
        localOnly.companionKeyID = ""
        XCTAssertFalse(BiometricApprovalStore.verify(
            canonical: try localOnly.canonicalBytes(),
            signature: signature.signature,
            publicKey: local.publicKey.x963Representation
        ))
    }

    private func submit(
        _ request: PolicyBoundApprovalRequest,
        local: P256.Signing.PrivateKey?,
        companion: P256.Signing.PrivateKey?
    ) throws {
        try PolicyBoundApprovalStore.submit(
            request: request,
            local: try signature(local, request),
            companion: try signature(companion, request),
            pinnedLocalKey: local?.publicKey.x963Representation,
            pinnedCompanionKey: companion?.publicKey.x963Representation,
            directory: directory
        )
    }

    private func signature(_ key: P256.Signing.PrivateKey?, _ request: PolicyBoundApprovalRequest) throws -> PolicyApprovalSignature? {
        guard let key else { return nil }
        return try signed(request, key: key)
    }

    private func signed(_ request: PolicyBoundApprovalRequest, key: P256.Signing.PrivateKey) throws -> PolicyApprovalSignature {
        PolicyApprovalSignature(
            publicKey: key.publicKey.x963Representation,
            signature: try key.signature(for: try request.canonicalBytes()).rawRepresentation,
            enrollmentGeneration: 1
        )
    }

    private func sample(
        policy: BiometricApprovalPolicy,
        localKeyID: String = "",
        companionKeyID: String = ""
    ) -> PolicyBoundApprovalRequest {
        PolicyBoundApprovalRequest(
            policy: policy,
            macID: "mac-1",
            workspaceID: "ws-1",
            runID: "run-1",
            contractSHA256: String(repeating: "11", count: 32),
            inputsSHA256: String(repeating: "22", count: 32),
            bounds: "timeout_seconds=30",
            nonce: String(repeating: "b", count: 64),
            expiryUnix: 2_000,
            localKeyID: localKeyID,
            companionKeyID: companionKeyID
        )
    }
}
