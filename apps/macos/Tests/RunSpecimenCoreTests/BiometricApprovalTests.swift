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

    func testChangedSignatureIsTamperAndDoesNotSpendTheNonce() throws {
        let key = P256.Signing.PrivateKey()
        let request = sample(nonce: nonce(), expiry: 2_000)
        try submit(request, key: key, now: 1_000)
        var bytes = try Data(contentsOf: pending(request.nonce))
        bytes[bytes.count - 1] ^= 0x01
        try bytes.write(to: pending(request.nonce))
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

    private func nonce() -> String {
        String(repeating: "a", count: 64)
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
