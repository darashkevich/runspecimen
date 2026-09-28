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

    func testHardwarePathsReturnBeforeSecureEnclaveWithoutAHumanTap() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("observe-gate-" + UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let fields = try RSBA2Package.parse(JSONSerialization.data(withJSONObject: package()))
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.enroll(keyID: "phone-vector", directory: directory, humanTap: false)) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .humanTapRequired)
        }
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.sign(fields: fields, directory: directory, humanTap: false)) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .humanTapRequired)
        }
        XCTAssertThrowsError(try CompanionSecureEnclaveEnrollment.revoke(keyID: "phone-vector", directory: directory, humanTap: false)) { error in
            XCTAssertEqual(error as? CompanionHardwareRefusal, .humanTapRequired)
        }
        let names = try FileManager.default.contentsOfDirectory(atPath: directory.path)
        XCTAssertTrue(names.isEmpty)
        XCTAssertFalse(EnrollmentIdentity.allowsExecution(
            role: EnrollmentIdentity.roleCompanion,
            backend: EnrollmentIdentity.backendSoftwareDevelopment,
            provenance: EnrollmentIdentity.provenanceDevelopment,
            state: EnrollmentIdentity.stateActive
        ))
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
