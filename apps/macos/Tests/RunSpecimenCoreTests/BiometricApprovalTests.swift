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

    func testTouchIDDiagnosticRefusesUnlessAHumanInvokesIt() throws {
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
        XCTAssertNotNil(TouchIDDiagnosticGate.refusal(arguments: [
            "diag", "--human-invoked", "--directory", "/tmp/../Users/yahor/not-isolated", "--key-id", "diag-a", "enroll"
        ]))
        XCTAssertNotNil(TouchIDDiagnosticGate.refusal(arguments: [
            "diag", "--human-invoked", "--directory", "/private/tmp", "--key-id", "diag-a", "enroll"
        ]))
        XCTAssertNotNil(TouchIDDiagnosticGate.refusal(arguments: [
            "diag", "--human-invoked", "--directory", "/tmp", "--key-id", "diag-a", "enroll"
        ]))
        XCTAssertNil(TouchIDDiagnosticGate.refusal(arguments: [
            "diag", "--human-invoked", "--directory", "/tmp/rs-touchid-diag", "--key-id", "diag-a", "enroll"
        ]))
        let root = "/private/tmp/rs-touchid-diag"
        try FileManager.default.createDirectory(atPath: root, withIntermediateDirectories: true)
        let link = root + "/escape-probe"
        try? FileManager.default.removeItem(atPath: link)
        try FileManager.default.createSymbolicLink(atPath: link, withDestinationPath: "/Users")
        defer { try? FileManager.default.removeItem(atPath: link) }
        XCTAssertNotNil(TouchIDDiagnosticGate.refusal(arguments: [
            "diag", "--human-invoked", "--directory", link, "--key-id", "diag-a", "enroll"
        ]))
        XCTAssertNotEqual(
            LocalSecureEnclaveEnrollment.diagnosticKeychainService,
            LocalSecureEnclaveEnrollment.productionKeychainService
        )
    }

    func testSymlinkParentHopLimitAndDirectoryReplacementStayInsideTheDiagnosticRoot() throws {
        let root = TouchIDDiagnosticGate.rootPath
        try FileManager.default.createDirectory(atPath: root, withIntermediateDirectories: true)
        let fixture = root + "/order-" + UUID().uuidString
        let outside = FileManager.default.temporaryDirectory.appendingPathComponent("codex-out-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(atPath: fixture, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outside.appendingPathComponent("child"), withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(atPath: fixture)
            try? FileManager.default.removeItem(at: outside)
        }
        try FileManager.default.createSymbolicLink(
            atPath: fixture + "/link",
            withDestinationPath: outside.appendingPathComponent("child").path
        )
        let raw = fixture + "/link/../probe"
        XCTAssertFalse(TouchIDDiagnosticGate.isIsolated(raw))
        let actualParent = (fixture + "/link/..").withCString { realpath($0, nil) }
        XCTAssertNotNil(actualParent)
        if let actualParent {
            defer { free(actualParent) }
            XCTAssertFalse(String(cString: actualParent).hasPrefix(root + "/"))
        }
        XCTAssertTrue(TouchIDDiagnosticGate.isIsolated(fixture + "/missing-leaf"))
        XCTAssertNil(TouchIDDiagnosticGate.canonicalPath(fixture + "/missing/deeper"))

        var previous = fixture
        for hop in 0..<17 {
            let name = fixture + "/hop\(hop)"
            try FileManager.default.createSymbolicLink(atPath: name, withDestinationPath: previous)
            previous = name
        }
        XCTAssertFalse(TouchIDDiagnosticGate.isIsolated(fixture + "/hop16"))

        let owned = root + "/owned-" + UUID().uuidString
        let fd = try TouchIDDiagnosticGate.openOwnedDirectory(owned)
        defer { close(fd) }
        try TouchIDDiagnosticGate.writeExclusive(directoryFD: fd, name: "marker", data: Data("in".utf8))
        let aside = owned + "-aside"
        try FileManager.default.moveItem(atPath: owned, toPath: aside)
        try FileManager.default.createSymbolicLink(atPath: owned, withDestinationPath: outside.path)
        defer {
            try? FileManager.default.removeItem(atPath: owned)
            try? FileManager.default.removeItem(atPath: aside)
        }
        XCTAssertThrowsError(try TouchIDDiagnosticGate.openOwnedDirectory(owned))
        XCTAssertEqual(try TouchIDDiagnosticGate.readExclusive(directoryFD: fd, name: "marker"), Data("in".utf8))
        XCTAssertFalse(FileManager.default.fileExists(atPath: outside.appendingPathComponent("marker").path))

        let modeName = root + "/mode-" + UUID().uuidString
        let writable = try TouchIDDiagnosticGate.openOwnedDirectory(modeName)
        let modePath = TouchIDDiagnosticGate.openedPath(of: writable)
        close(writable)
        if let modePath {
            chmod(modePath, 0o777)
            XCTAssertThrowsError(try TouchIDDiagnosticGate.openOwnedDirectory(modePath))
            chmod(modePath, 0o700)
        }

        let hold = "/private/tmp/rs-touchid-diag-hold-" + UUID().uuidString
        try FileManager.default.moveItem(atPath: root, toPath: hold)
        defer {
            try? FileManager.default.removeItem(atPath: root)
            try? FileManager.default.moveItem(atPath: hold, toPath: root)
        }
        try FileManager.default.createSymbolicLink(atPath: root, withDestinationPath: outside.path)
        XCTAssertFalse(TouchIDDiagnosticGate.isIsolated(root))
        XCTAssertFalse(TouchIDDiagnosticGate.isIsolated(root + "/probe"))
    }

    func testCompanionCanonicalVectorDigestIsStable() throws {
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

    func testShippingObserveTargetExcludesTheSoftwareSigner() throws {
        let ios = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("ios")
        let project = try String(contentsOf: ios.appendingPathComponent("RunSpecimenObserve.xcodeproj/project.pbxproj"), encoding: .utf8)
        let shipping = try sourcesPhase(named: "RunSpecimenObserve", in: project)
        XCTAssertFalse(shipping.contains("DevelopmentCompanionSigner.swift"))
        XCTAssertFalse(shipping.contains("DevelopmentCompanionSignView.swift"))
        XCTAssertTrue(shipping.contains("CompanionSecureEnclaveEnrollment.swift"))
        let development = try sourcesPhase(named: "RunSpecimenObserveDev", in: project)
        XCTAssertTrue(development.contains("DevelopmentCompanionSigner.swift"))
        XCTAssertFalse(try configurationText(named: "RunSpecimenObserve", in: project).contains("RS_OBSERVE_DEV_SIGNER"))
        XCTAssertTrue(try configurationText(named: "RunSpecimenObserveDev", in: project).contains("RS_OBSERVE_DEV_SIGNER"))
        let scheme = try String(contentsOf: ios.appendingPathComponent("RunSpecimenObserve.xcodeproj/xcshareddata/xcschemes/RunSpecimenObserve.xcscheme"), encoding: .utf8)
        XCTAssertFalse(scheme.contains("RunSpecimenObserveDev"))
        let preview = try String(
            contentsOf: ios.appendingPathComponent("Sources/RunSpecimenObserve/Views/CompanionApprovalPreviewView.swift"),
            encoding: .utf8
        )
        XCTAssertFalse(preview.contains("DevelopmentCompanionSigner"))
        XCTAssertTrue(preview.contains("onChange(of: packageText)"))
    }

    private func sourcesPhase(named target: String, in text: String) throws -> String {
        guard let name = text.range(of: "\t\t\tname = \(target);\n"),
              let native = text[..<name.lowerBound].range(of: "isa = PBXNativeTarget;", options: .backwards),
              let sources = text[native.lowerBound..<name.upperBound].range(of: #"([A-F0-9]+) /\* Sources \*/"#, options: .regularExpression)
        else {
            throw BiometricApprovalError.malformed("target")
        }
        let identifier = String(text[sources]).split(separator: " ").first.map(String.init) ?? ""
        guard let start = text.range(of: "\t\t\(identifier) /* Sources */ = {"),
              let end = text[start.upperBound...].range(of: "\t\t};")
        else {
            throw BiometricApprovalError.malformed("sources")
        }
        return String(text[start.lowerBound..<end.upperBound])
    }

    private func configurationText(named target: String, in text: String) throws -> String {
        let marker = "/* Build configuration list for PBXNativeTarget \"\(target)\" */ = {"
        guard let listName = text.range(of: marker),
              let listStart = text[..<listName.lowerBound].range(of: "\t\t", options: .backwards),
              let listEnd = text[listName.upperBound...].range(of: "\t\t};")
        else {
            throw BiometricApprovalError.malformed("configuration")
        }
        let list = String(text[listStart.lowerBound..<listEnd.upperBound])
        var collected = list
        let pattern = #"[A-F0-9]{24}"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return collected }
        let nsList = list as NSString
        for match in regex.matches(in: list, range: NSRange(location: 0, length: nsList.length)) {
            let identifier = nsList.substring(with: match.range)
            guard let start = text.range(of: "\t\t\(identifier) /* "),
                  let end = text[start.upperBound...].range(of: "\t\t};")
            else { continue }
            collected += String(text[start.lowerBound..<end.upperBound])
        }
        return collected
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

    func testInterruptedOrPartialWritesLeaveNoFile() throws {
        // Isolation refuses a missing intermediate. Create the root here so this
        // test does not depend on testTouchIDDiagnostic / testSymlink running first.
        let root = TouchIDDiagnosticGate.rootPath
        try FileManager.default.createDirectory(atPath: root, withIntermediateDirectories: true)
        let owned = root + "/partial-" + UUID().uuidString
        let fd = try TouchIDDiagnosticGate.openOwnedDirectory(owned)
        defer {
            close(fd)
            DescriptorIO.writeChunk = { Darwin.write($0, $1, $2) }
            DescriptorIO.readChunk = { Darwin.read($0, $1, $2) }
            DescriptorIO.syncFile = { fsync($0) }
            try? FileManager.default.removeItem(atPath: owned)
        }
        var attempts = 0
        DescriptorIO.writeChunk = { file, buffer, count in
            attempts += 1
            if attempts == 1 {
                errno = EINTR
                return -1
            }
            return Darwin.write(file, buffer, count)
        }
        try TouchIDDiagnosticGate.writeExclusive(directoryFD: fd, name: "retried", data: Data("abcdef".utf8))
        attempts = 0
        DescriptorIO.writeChunk = { file, buffer, count in
            attempts += 1
            if attempts == 1 {
                _ = Darwin.write(file, buffer, 1)
                errno = EIO
                return -1
            }
            return Darwin.write(file, buffer, count)
        }
        XCTAssertThrowsError(try TouchIDDiagnosticGate.writeExclusive(directoryFD: fd, name: "partial", data: Data("abcdef".utf8)))
        XCTAssertFalse(FileManager.default.fileExists(atPath: owned + "/partial"))
        DescriptorIO.writeChunk = { Darwin.write($0, $1, $2) }
        DescriptorIO.syncFile = { _ in
            errno = EIO
            return -1
        }
        XCTAssertThrowsError(try TouchIDDiagnosticGate.writeExclusive(directoryFD: fd, name: "unsynced", data: Data("abcdef".utf8)))
        XCTAssertFalse(FileManager.default.fileExists(atPath: owned + "/unsynced"))
        DescriptorIO.syncFile = { fsync($0) }
        var reads = 0
        DescriptorIO.readChunk = { file, buffer, count in
            reads += 1
            if reads == 1 {
                errno = EINTR
                return -1
            }
            return Darwin.read(file, buffer, count)
        }
        XCTAssertEqual(try TouchIDDiagnosticGate.readExclusive(directoryFD: fd, name: "retried"), Data("abcdef".utf8))
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
        BiometricApprovalStore.beforeExclusiveAccess = nil
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
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .tampered)
        }
        frozenNow = 5_000
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consume(
            request: request,
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .expired)
        }
        XCTAssertTrue(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consume(
            request: request,
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
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
        localOnly.companionGeneration = 0
        XCTAssertFalse(BiometricApprovalStore.verify(
            canonical: try localOnly.canonicalBytes(),
            signature: signature.signature,
            publicKey: local.publicKey.x963Representation
        ))
    }

    func testRewrittenGenerationAndUnknownVersionAreRejected() throws {
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        var object = try JSONSerialization.jsonObject(with: try PolicyBoundApprovalStore.package(
            request: request,
            local: nil,
            companion: try signed(request, key: phone)
        )) as! [String: String]
        object["companion_generation"] = "2"
        object["version"] = "UNKNOWN-FUTURE-VERSION"
        XCTAssertThrowsError(try PolicyBoundApprovalStore.importUserMediatedPackage(
            JSONSerialization.data(withJSONObject: object),
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .malformed("version"))
        }
        object["version"] = "RSBA2"
        XCTAssertThrowsError(try PolicyBoundApprovalStore.importUserMediatedPackage(
            JSONSerialization.data(withJSONObject: object),
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .tampered)
        }
        object.removeValue(forKey: "version")
        XCTAssertThrowsError(try PolicyBoundApprovalStore.importUserMediatedPackage(
            JSONSerialization.data(withJSONObject: object),
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .malformed("version"))
        }
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        var extra = try JSONSerialization.jsonObject(with: try PolicyBoundApprovalStore.package(
            request: request,
            local: nil,
            companion: try signed(request, key: phone)
        )) as! [String: String]
        extra["future_field"] = "1"
        XCTAssertThrowsError(try PolicyBoundApprovalStore.importUserMediatedPackage(
            JSONSerialization.data(withJSONObject: extra),
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .malformed("package"))
        }
        extra.removeValue(forKey: "future_field")
        extra["companion_generation"] = "01"
        XCTAssertThrowsError(try PolicyBoundApprovalStore.importUserMediatedPackage(
            JSONSerialization.data(withJSONObject: extra),
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .malformed("enrollment"))
        }
    }

    func testConsumeReloadsLiveEnrollmentAndRejectsARevokedEpoch() throws {
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        let enroll = directory.appendingPathComponent("enroll", isDirectory: true)
        try BiometricEnrollmentDirectory.save(BiometricEnrollmentRecord(
            keyID: "phone-key",
            publicKey: phone.publicKey.x963Representation,
            state: BiometricEnrollmentRecord.active,
            backend: BiometricEnrollmentRecord.softwareBackend,
            role: EnrollmentIdentity.roleCompanion,
            provenance: EnrollmentIdentity.provenanceSoftwareTest,
            generation: 1
        ), directory: enroll)
        try submit(request, local: nil, companion: phone)
        try BiometricEnrollmentDirectory.revoke(keyID: "phone-key", directory: enroll)
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consumeEnrolled(
            request: request,
            enrollmentDirectory: enroll,
            approvalDirectory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .revoked)
        }
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
    }

    func testRevokeWhilePolicyConsumeIsBlockedRejectsTheStaleRecord() throws {
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        let enroll = directory.appendingPathComponent("enroll-race", isDirectory: true)
        try BiometricEnrollmentDirectory.save(BiometricEnrollmentRecord(
            keyID: "phone-key",
            publicKey: phone.publicKey.x963Representation,
            state: BiometricEnrollmentRecord.active,
            backend: BiometricEnrollmentRecord.softwareBackend,
            role: EnrollmentIdentity.roleCompanion,
            provenance: EnrollmentIdentity.provenanceSoftwareTest,
            generation: 1
        ), directory: enroll)
        try submit(request, local: nil, companion: phone)
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
                try PolicyBoundApprovalStore.consumeEnrolled(
                    request: request,
                    enrollmentDirectory: enroll,
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
        try BiometricEnrollmentDirectory.revoke(keyID: "phone-key", directory: enroll)
        release.signal()
        XCTAssertEqual(finished.wait(timeout: .now() + 2), .success)
        XCTAssertEqual(outcome, .revoked)
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
    }

    func testCraftedDualRecordWithOneKeyIsRejectedAtConsume() throws {
        let local = P256.Signing.PrivateKey()
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .dual, localKeyID: "mac-key", companionKeyID: "phone-key")
        try submit(request, local: local, companion: phone)
        let url = directory.appendingPathComponent("\(request.nonce).policy-approval")
        var object = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: String]
        object["companion_public_key_b64"] = object["local_public_key_b64"]
        object["companion_signature_b64"] = object["local_signature_b64"]
        object["companion_generation"] = object["local_generation"]
        try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]).write(to: url)
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consume(
            request: request,
            pinnedLocalKey: local.publicKey.x963Representation,
            pinnedCompanionKey: local.publicKey.x963Representation,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .unsupportedPolicy)
        }
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
    }

    func testParseRejectsMissingEmptyNulAndInconsistentFields() throws {
        let phone = P256.Signing.PrivateKey()
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        let original = try JSONSerialization.jsonObject(with: try PolicyBoundApprovalStore.package(
            request: request,
            local: nil,
            companion: try signed(request, key: phone)
        )) as! [String: String]
        func expect(_ mutate: (inout [String: String]) -> Void, _ field: String) throws {
            var object = original
            mutate(&object)
            let data = try JSONSerialization.data(withJSONObject: object)
            XCTAssertThrowsError(try PolicyBoundApprovalStore.importUserMediatedPackage(
                data,
                pinnedLocalKey: nil,
                pinnedCompanionKey: phone.publicKey.x963Representation,
                directory: directory
            )) { error in
                XCTAssertEqual(error as? BiometricApprovalError, .malformed(field))
            }
        }
        try expect({ $0.removeValue(forKey: "mac_id") }, "mac_id")
        try expect({ $0["mac_id"] = "" }, "mac_id")
        try expect({ $0["workspace_id"] = "ws\0id" }, "workspace_id")
        try expect({ $0["bounds"] = String(repeating: "x", count: 300) }, "bounds")
        var inconsistent = original
        inconsistent["local_key_id"] = "mac-key"
        XCTAssertThrowsError(try PolicyBoundApprovalStore.importUserMediatedPackage(
            try JSONSerialization.data(withJSONObject: inconsistent),
            pinnedLocalKey: nil,
            pinnedCompanionKey: phone.publicKey.x963Representation,
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .unsupportedPolicy)
        }
        try expect({ $0["contract_sha256"] = "abcd" }, "contract_sha256")
        try expect({ $0["companion_generation"] = "01" }, "enrollment")
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
    }

    func testSwappedRoleAndSoftwareKeysDoNotAuthorizeExecution() throws {
        let phone = P256.Signing.PrivateKey()
        let local = P256.Signing.PrivateKey()
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        let enroll = directory.appendingPathComponent("roles", isDirectory: true)
        try BiometricEnrollmentDirectory.save(BiometricEnrollmentRecord(
            keyID: "phone-key",
            publicKey: phone.publicKey.x963Representation,
            state: BiometricEnrollmentRecord.active,
            backend: BiometricEnrollmentRecord.softwareBackend,
            role: EnrollmentIdentity.roleLocal,
            provenance: EnrollmentIdentity.provenanceSoftwareTest,
            generation: 1
        ), directory: enroll)
        try submit(request, local: nil, companion: phone)
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consumeEnrolled(
            request: request,
            enrollmentDirectory: enroll,
            approvalDirectory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .unsupportedPolicy)
        }
        try BiometricEnrollmentDirectory.save(BiometricEnrollmentRecord(
            keyID: "phone-key",
            publicKey: phone.publicKey.x963Representation,
            state: BiometricEnrollmentRecord.active,
            backend: EnrollmentIdentity.backendSoftwareDevelopment,
            role: EnrollmentIdentity.roleCompanion,
            provenance: EnrollmentIdentity.provenanceDevelopment,
            generation: 1
        ), directory: enroll)
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consumeEnrolled(
            request: request,
            enrollmentDirectory: enroll,
            approvalDirectory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .unsupportedPolicy)
        }
        XCTAssertFalse(EnrollmentIdentity.allowsExecution(
            role: EnrollmentIdentity.roleCompanion,
            backend: EnrollmentIdentity.backendSoftwareTest,
            provenance: EnrollmentIdentity.provenanceSoftwareTest,
            state: EnrollmentIdentity.stateActive
        ))
        var dual = sample(policy: .dual, localKeyID: "mac-key", companionKeyID: "phone-key")
        dual.nonce = String(repeating: "c", count: 64)
        try BiometricEnrollmentDirectory.save(BiometricEnrollmentRecord(
            keyID: "mac-key",
            publicKey: local.publicKey.x963Representation,
            state: BiometricEnrollmentRecord.active,
            backend: BiometricEnrollmentRecord.softwareBackend,
            role: EnrollmentIdentity.roleLocal,
            provenance: EnrollmentIdentity.provenanceSoftwareTest,
            generation: 1
        ), directory: enroll)
        try BiometricEnrollmentDirectory.save(BiometricEnrollmentRecord(
            keyID: "phone-key",
            publicKey: phone.publicKey.x963Representation,
            state: BiometricEnrollmentRecord.active,
            backend: BiometricEnrollmentRecord.softwareBackend,
            role: EnrollmentIdentity.roleCompanion,
            provenance: EnrollmentIdentity.provenanceSoftwareTest,
            generation: 1
        ), directory: enroll)
        try submit(dual, local: local, companion: phone)
        XCTAssertThrowsError(try PolicyBoundApprovalStore.consumeForExecution(
            request: dual,
            enrollmentDirectory: enroll,
            approvalDirectory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .unsupportedPolicy)
        }
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: dual.nonce, directory: directory))
    }

    func testCarriedPinIgnoresTheFilesSecureEnclaveLabel() throws {
        let phone = P256.Signing.PrivateKey()
        let carried: [String: String] = [
            "backend": EnrollmentIdentity.backendSecureEnclave,
            "provenance": EnrollmentIdentity.provenanceProduction,
            "role": EnrollmentIdentity.roleCompanion,
            "state": "active",
            "key_id": "phone-key",
            "generation": "2",
            "public_key_x963_b64": phone.publicKey.x963Representation.base64EncodedString(),
        ]
        let record = try BiometricEnrollmentDirectory.pinCarriedCompanion(
            try JSONSerialization.data(withJSONObject: carried),
            directory: directory
        )
        XCTAssertEqual(record.backend, EnrollmentIdentity.backendUnverified)
        XCTAssertEqual(record.provenance, EnrollmentIdentity.provenanceCarriedPin)
        XCTAssertEqual(record.generation, 2)
        XCTAssertFalse(EnrollmentIdentity.allowsExecution(
            role: record.role,
            backend: record.backend,
            provenance: record.provenance,
            state: record.state
        ))
        XCTAssertEqual(
            ProductionNativeBridgeGate.origin(fromCallerBackend: EnrollmentIdentity.backendSecureEnclave),
            .callerSupplied
        )
        XCTAssertFalse(ProductionNativeBridgeGate.allowsProductionEnrollment(
            origin: .callerSupplied
        ))
        XCTAssertFalse(ProductionNativeBridgeGate.allowsProductionEnrollment(
            origin: ProductionNativeBridgeGate.origin(fromCallerBackend: record.backend)
        ))
        XCTAssertTrue(ProductionNativeBridgeGate.status().contains("native enrollment remains open"))
        XCTAssertTrue(ProductionNativeBridgeGate.status().contains("does not carry the Developer ID verifier pin"))
        XCTAssertTrue(ProductionNativeBridgeGate.status().contains("stays guarantee (1)"))
        XCTAssertFalse(ProductionNativeBridgeGate.status().contains("guarantee (2)"))
        XCTAssertFalse(ProductionNativeBridgeGate.status().contains("until a person"))
        XCTAssertFalse(ProductionNativeBridgeGate.allowsProductionEnrollment(
            origin: .callerSupplied,
            pinConfigured: true,
            verifierConnected: true,
            installedProtection: true
        ))
        XCTAssertFalse(ProductionNativeBridgeGate.allowsProductionEnrollment(
            origin: ProductionNativeBridgeGate.origin(fromCallerBackend: ProductionNativeBridgeGate.boundaryBackend),
            pinConfigured: true,
            verifierConnected: true,
            installedProtection: true
        ))
        XCTAssertFalse(ProductionNativeBridgeGate.allowsProductionEnrollment(
            origin: .secureEnclaveHumanStep,
            pinConfigured: true,
            verifierConnected: true,
            installedProtection: true
        ))
        XCTAssertFalse(ProductionNativeBridgeGate.allowsProductionEnrollment(
            origin: .secureEnclaveHumanStep,
            pinConfigured: false,
            verifierConnected: true,
            installedProtection: true
        ))
        XCTAssertThrowsError(try ProductionNativeBridgeGate.beginHumanSecureEnclaveEnrollment()) { error in
            XCTAssertEqual(error as? ProductionEnrollmentError, .biometricPromptNotInvoked)
        }
        let local = IsolatedNativeEnrollment.complete(role: EnrollmentIdentity.roleLocal)
        let companion = IsolatedNativeEnrollment.complete(role: EnrollmentIdentity.roleCompanion)
        XCTAssertEqual(local?.hardware, false)
        XCTAssertEqual(local?.bridge, IsolatedNativeEnrollment.bridge)
        XCTAssertEqual(companion?.role, EnrollmentIdentity.roleCompanion)
        XCTAssertNil(IsolatedNativeEnrollment.complete(role: "production"))
        let linked = IsolatedNativeEnrollment.connected([local!, companion!])
        XCTAssertTrue(linked.local)
        XCTAssertTrue(linked.companion)
        XCTAssertTrue(ProductionNativeBridgeGate.status(signers: [local!, companion!]).contains("local=true"))
        var swapped = carried
        swapped["role"] = EnrollmentIdentity.roleLocal
        XCTAssertThrowsError(try BiometricEnrollmentDirectory.pinCarriedCompanion(
            try JSONSerialization.data(withJSONObject: swapped),
            directory: directory
        )) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .unsupportedPolicy)
        }
    }

    func testPostAuthenticationRejectsAChangedOrExpiredEnrollment() throws {
        let key = Data(repeating: 4, count: 65)
        let before = CompanionEnrollmentSnapshot(
            keyID: "phone-key",
            publicKey: key,
            role: EnrollmentIdentity.roleCompanion,
            backend: EnrollmentIdentity.backendSecureEnclave,
            provenance: EnrollmentIdentity.provenanceProduction,
            state: EnrollmentIdentity.stateActive,
            generation: 1
        )
        func reject(_ mutate: (inout CompanionEnrollmentSnapshot) -> Void, now: Int = 1_000) {
            var after = before
            mutate(&after)
            XCTAssertThrowsError(try CompanionPostAuthentication.accept(
                before: before,
                after: after,
                expiryUnix: 2_000,
                now: now
            ))
        }
        reject { $0.state = BiometricEnrollmentRecord.revoked; $0.generation = 2 }
        reject { $0.generation = 2 }
        reject { $0.publicKey = Data(repeating: 5, count: 65) }
        reject { $0.backend = EnrollmentIdentity.backendSoftwareTest; $0.provenance = EnrollmentIdentity.provenanceSoftwareTest }
        reject { $0.provenance = EnrollmentIdentity.provenanceDiagnostic }
        reject({ _ in }, now: 2_000)
        XCTAssertNoThrow(try CompanionPostAuthentication.accept(
            before: before,
            after: before,
            expiryUnix: 2_000,
            now: 1_000
        ))
    }

    func testExecutionEvaluationNeverStartsARun() throws {
        let request = sample(policy: .companion, companionKeyID: "phone-key")
        var calls = 0
        let refused = PolicyBoundApprovalStore.evaluateExecution(
            request: request,
            enrollmentDirectory: directory,
            approvalDirectory: directory
        ) { _, _, _ in
            calls += 1
            throw BiometricApprovalError.unsupportedPolicy
        }
        XCTAssertEqual(calls, 1)
        XCTAssertFalse(refused.started)
        XCTAssertFalse(refused.consumeSucceeded)
        XCTAssertEqual(refused.reason, BiometricApprovalError.unsupportedPolicy.description)
        let accepted = PolicyBoundApprovalStore.evaluateExecution(
            request: request,
            enrollmentDirectory: directory,
            approvalDirectory: directory
        ) { _, _, _ in
            calls += 1
        }
        XCTAssertEqual(calls, 2)
        XCTAssertFalse(accepted.started)
        XCTAssertTrue(accepted.consumeSucceeded)
        XCTAssertEqual(accepted.reason, "consumed")
        let app = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/RunSpecimenApp")
        guard let enumerator = FileManager.default.enumerator(at: app, includingPropertiesForKeys: nil) else {
            XCTFail("missing app sources")
            return
        }
        for case let file as URL in enumerator where file.pathExtension == "swift" {
            let text = try String(contentsOf: file, encoding: .utf8)
            XCTAssertFalse(text.contains("evaluateExecution"), file.lastPathComponent)
            XCTAssertFalse(text.contains("consumeForExecution"), file.lastPathComponent)
        }
    }

    func testInjectedNativeSignerEnrollsWithoutABiometricPrompt() throws {
        struct FixtureNativeSigner: HumanNativeSigning {
            var hardware = false
            func publicKey(role: String) -> Data {
                Data([0x04, UInt8(role.utf8.first ?? 0)])
            }

            func sign(role: String, message: Data) -> Data {
                message + Data(role.utf8)
            }
        }

        let receipt = try ProductionNativeBridgeGate.beginHumanSecureEnclaveEnrollment(
            signer: FixtureNativeSigner(),
            policy: "dual"
        )
        XCTAssertFalse(receipt.hardware)
        XCTAssertFalse(receipt.biometricInvoked)
        XCTAssertEqual(receipt.policy, "dual")
        XCTAssertEqual(receipt.roles, ["mac", "phone"])
        XCTAssertEqual(Set(receipt.publicKeys.keys), Set(["mac", "phone"]))
        XCTAssertFalse(receipt.signatures["mac"]?.isEmpty ?? true)
        XCTAssertFalse(receipt.signatures["phone"]?.isEmpty ?? true)
        XCTAssertTrue(ProductionNativeBridgeGate.status().contains("injected native signer is not hardware"))
        XCTAssertTrue(ProductionNativeBridgeGate.status().contains("A software signer is not the native adapter"))
        XCTAssertTrue(ProductionNativeBridgeGate.status().contains("E2 is not closed"))
        XCTAssertThrowsError(
            try ProductionNativeBridgeGate.beginHumanSecureEnclaveEnrollment(
                signer: Optional<FixtureNativeSigner>.none,
                policy: "local"
            )
        ) { error in
            XCTAssertEqual(error as? ProductionEnrollmentError, .biometricPromptNotInvoked)
        }
        XCTAssertThrowsError(
            try ProductionNativeBridgeGate.beginHumanSecureEnclaveEnrollment(
                signer: FixtureNativeSigner(hardware: true),
                policy: "local"
            )
        ) { error in
            XCTAssertEqual(error as? ProductionEnrollmentError, .callerHardwareLabelRefused)
        }
    }

    func testHumanOperatedAdapterEnrollsWithoutABiometricPrompt() throws {
        struct FixtureAdapter: HumanOperatedNativeAdapting {
            func publicKey(role: String) -> Data {
                Data([0x04, UInt8(role.utf8.first ?? 0)])
            }

            func sign(role: String, message: Data) -> Data {
                message + Data(role.utf8)
            }
        }

        let receipt = try HumanOperatedNativeAdapterGate.begin(adapter: FixtureAdapter(), policy: "dual")
        XCTAssertFalse(receipt.biometricInvoked)
        XCTAssertFalse(receipt.e2Closed)
        XCTAssertEqual(receipt.roles, ["mac", "phone"])
        XCTAssertThrowsError(try HumanOperatedNativeAdapterGate.begin(adapter: Optional<FixtureAdapter>.none)) { error in
            XCTAssertEqual(error as? ProductionEnrollmentError, .biometricPromptNotInvoked)
        }
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("Sources/RunSpecimenCore/RSBA2Package.swift"),
            encoding: .utf8
        )
        XCTAssertFalse(source.contains("SecureEnclave.P256.Signing.PrivateKey("))
        XCTAssertTrue(ProductionNativeBridgeGate.status().contains("An origin string is not production trust"))
        struct MockOsBoundary: SecureEnclaveKeyMaking {
            func makeSessionKey() throws -> NativeSessionKey {
                NativeSessionKey(
                    publicKey: Data([9, 9, 9]),
                    accessPolicy: "biometry-current-set-on-each-signature"
                )
            }
        }
        struct FixedPhone: PhonePeerComparing {
            var publicKey: Data
            var signed: Data
            func sign(challenge: Data) throws -> Data { signed }
        }
        let local = try ProductionNativeBridgeGate.enrollFromUserInvokedControl(
            policy: "local",
            maker: MockOsBoundary()
        )
        XCTAssertEqual(local.publicKey, Data([9, 9, 9]))
        XCTAssertThrowsError(
            try ProductionNativeBridgeGate.enrollFromUserInvokedControl(
                policy: "companion",
                maker: MockOsBoundary()
            )
        )
        let privateKey = P256.Signing.PrivateKey()
        let otherKey = P256.Signing.PrivateKey()
        let challenge = BoundDeviceChallenge(
            holderId: "holder",
            generation: 1,
            role: "phone",
            expiry: 10,
            nonce: "nonce",
            challenge: Data([1, 2, 3, 4])
        )
        let message = challenge.canonicalBytes()
        let signature = try privateKey.signature(for: message).rawRepresentation
        let nonces = MemoryChallengeNonceStore()
        let compared = try ProductionNativeBridgeGate.enrollPairedPhone(
            challenge: challenge,
            peer: FixedPhone(publicKey: privateKey.publicKey.x963Representation, signed: signature),
            localPublicKey: local.publicKey,
            nonces: nonces
        )
        XCTAssertEqual(compared, privateKey.publicKey.x963Representation)
        XCTAssertThrowsError(
            try ProductionNativeBridgeGate.enrollPairedPhone(
                challenge: challenge,
                peer: FixedPhone(publicKey: privateKey.publicKey.x963Representation, signed: signature),
                localPublicKey: local.publicKey,
                nonces: nonces
            )
        ) { error in
            XCTAssertEqual(error as? ProductionEnrollmentError, .replayedChallenge)
        }
        XCTAssertThrowsError(
            try ProductionNativeBridgeGate.enrollPairedPhone(
                challenge: challenge,
                peer: FixedPhone(publicKey: privateKey.publicKey.x963Representation, signed: Data([1, 2, 3])),
                localPublicKey: nil,
                nonces: MemoryChallengeNonceStore()
            )
        ) { error in
            XCTAssertEqual(error as? ProductionEnrollmentError, .signatureRejected)
        }
        XCTAssertThrowsError(
            try ProductionNativeBridgeGate.enrollPairedPhone(
                challenge: challenge,
                peer: FixedPhone(publicKey: otherKey.publicKey.x963Representation, signed: signature),
                localPublicKey: nil,
                nonces: MemoryChallengeNonceStore()
            )
        ) { error in
            XCTAssertEqual(error as? ProductionEnrollmentError, .signatureRejected)
        }
        var tampered = challenge
        tampered.challenge = Data([9, 9, 9, 9])
        XCTAssertThrowsError(
            try ProductionNativeBridgeGate.enrollPairedPhone(
                challenge: tampered,
                peer: FixedPhone(publicKey: privateKey.publicKey.x963Representation, signed: signature),
                localPublicKey: nil,
                nonces: MemoryChallengeNonceStore()
            )
        ) { error in
            XCTAssertEqual(error as? ProductionEnrollmentError, .signatureRejected)
        }
        let cancelled = MemoryChallengeNonceStore()
        cancelled.cancel(challenge.nonce)
        XCTAssertThrowsError(
            try ProductionNativeBridgeGate.enrollPairedPhone(
                challenge: challenge,
                peer: FixedPhone(publicKey: privateKey.publicKey.x963Representation, signed: signature),
                localPublicKey: nil,
                nonces: cancelled
            )
        ) { error in
            XCTAssertEqual(error as? ProductionEnrollmentError, .staleChallenge)
        }
        XCTAssertThrowsError(
            try ProductionNativeBridgeGate.enrollPairedPhone(
                challenge: challenge,
                peer: FixedPhone(publicKey: local.publicKey, signed: signature),
                localPublicKey: local.publicKey,
                nonces: MemoryChallengeNonceStore()
            )
        )
        let holderSource = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("holder/Sources/RunSpecimenHolderApp/main.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(holderSource.contains("SecureEnclave.P256.Signing.PrivateKey("))
        XCTAssertTrue(holderSource.contains("Button(\"Enroll with Secure Enclave\")"))
        XCTAssertTrue(holderSource.contains("Button(\"Enroll paired phone\")"))
        XCTAssertFalse(holderSource.contains("onAppear(perform: enroll"))
        let live = holderSource.split(separator: "struct LiveSecureEnclaveKeyMaker", maxSplits: 1)
        XCTAssertEqual(live.count, 2)
        XCTAssertFalse(String(live[0]).contains("SecureEnclave.P256.Signing.PrivateKey("))
        XCTAssertTrue(live[1].contains("SecureEnclave.P256.Signing.PrivateKey("))
        XCTAssertTrue(holderSource.contains("issuePhoneChallenge"))
        XCTAssertTrue(holderSource.contains("enrollLocal"))
        XCTAssertTrue(holderSource.contains("biometry-current-set-on-each-signature"))
        XCTAssertTrue(holderSource.contains("A biometric press does not finish missing implementation"))
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
            companionKeyID: companionKeyID,
            localGeneration: localKeyID.isEmpty ? 0 : 1,
            companionGeneration: companionKeyID.isEmpty ? 0 : 1
        )
    }
}
