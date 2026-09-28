import CryptoKit
import XCTest
@testable import RunSpecimenCore

final class BiometricApprovalTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("rs-bio-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: directory)
    }

    func testConsumeOnceThenRejectsReplay() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 2_000)
        try submit(request, key: key, now: 1_000)
        try BiometricApprovalStore.consume(
            request: request,
            pinnedPublicKey: key.publicKey.x963Representation,
            directory: directory,
            now: 1_500
        )
        XCTAssertTrue(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: request,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory,
                now: 1_500
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
                directory: directory,
                now: 1_500
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
                directory: directory,
                now: 1_500
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .tampered)
        }
        try Data("{\"canonical_b64\":\"YQ==\"}".utf8).write(to: pending(request.nonce))
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: request,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory,
                now: 1_500
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
            approvalDirectory: directory,
            now: 1_000
        )
        try BiometricApprovalStore.consumeEnrolled(
            request: first,
            enrollmentDirectory: enrollmentDirectory,
            approvalDirectory: directory,
            now: 1_500
        )
        XCTAssertThrowsError(
            try BiometricApprovalStore.consumeEnrolled(
                request: first,
                enrollmentDirectory: enrollmentDirectory,
                approvalDirectory: directory,
                now: 1_500
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

    func testUserWritableConsumedMarkerCanBeRolledBack() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce("f"), expiry: 2_000)
        try submit(request, key: key, now: 1_000)
        let savedApproval = try Data(contentsOf: pending(request.nonce))
        try BiometricApprovalStore.consume(
            request: request,
            pinnedPublicKey: key.publicKey.x963Representation,
            directory: directory,
            now: 1_500
        )
        try savedApproval.write(to: pending(request.nonce))
        try FileManager.default.removeItem(at: directory.appendingPathComponent("\(request.nonce).consumed"))
        // Restoring these files is enough to consume again. The directory is user-writable.
        try BiometricApprovalStore.consume(
            request: request,
            pinnedPublicKey: key.publicKey.x963Representation,
            directory: directory,
            now: 1_500
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
                directory: directory,
                now: 1_500
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .mismatch)
        }
        XCTAssertFalse(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        try BiometricApprovalStore.consume(
            request: request,
            pinnedPublicKey: key.publicKey.x963Representation,
            directory: directory,
            now: 1_500
        )
    }

    func testExpiredApprovalIsSpentSoAClockChangeCannotReuseIt() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 1_200)
        try submit(request, key: key, now: 1_000)
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: request,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory,
                now: 1_200
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .expired)
        }
        XCTAssertTrue(BiometricApprovalStore.isConsumed(nonce: request.nonce, directory: directory))
        XCTAssertThrowsError(
            try BiometricApprovalStore.consume(
                request: request,
                pinnedPublicKey: key.publicKey.x963Representation,
                directory: directory,
                now: 1_000
            )
        ) { error in
            XCTAssertEqual(error as? BiometricApprovalError, .replay)
        }
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
                        directory: self.directory,
                        now: 1_500
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
        group.wait()
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
                directory: directory,
                now: 1_000
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

    private func submit(_ request: BiometricApprovalRequest, key: P256.Signing.PrivateKey, now: Int) throws {
        try BiometricApprovalStore.submit(
            request: request,
            signature: try signature(request, key: key),
            publicKey: key.publicKey.x963Representation,
            pinnedPublicKey: key.publicKey.x963Representation,
            directory: directory,
            now: now
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
