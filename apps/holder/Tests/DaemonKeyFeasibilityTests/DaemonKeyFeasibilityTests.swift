import XCTest
@testable import DaemonKeyFeasibility

final class DaemonKeyFeasibilityTests: XCTestCase {
    func testUnattendedPathDoesNotReachTheHardwareCallsite() throws {
        let before = DaemonKeyCreationHarness.hardwareCallsiteReached
        let assessment = DaemonKeyCreationHarness.unattendedAssessment()
        XCTAssertEqual(assessment.finding, "unsupported")
        XCTAssertEqual(assessment.readOn, "2026-10-05")
        XCTAssertThrowsError(
            try DaemonKeyCreationHarness.createKeyForExplicitHumanHandoff(
                acknowledgePrivilegedHardwareTrial: false
            )
        ) { error in
            XCTAssertEqual(error as? DaemonKeyCreationError, .handoffRequired)
        }
        XCTAssertEqual(DaemonKeyCreationHarness.hardwareCallsiteReached, before)
        XCTAssertEqual(assessment.hardwareCallsiteReached, before)
    }

    func testHandoffSourcePassesAccessControlIntoKeyCreation() throws {
        let sourceURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/DaemonKeyFeasibility/DaemonKeyFeasibility.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)
        let handoff = source.components(separatedBy: "func createKeyForExplicitHumanHandoff").last ?? ""
        let unattended = source.components(separatedBy: "func createKeyForExplicitHumanHandoff").first ?? ""
        XCTAssertTrue(handoff.contains("SecureEnclave.P256.Signing.PrivateKey(accessControl: access)"))
        XCTAssertFalse(handoff.contains("SecureEnclave.P256.Signing.PrivateKey()"))
        XCTAssertFalse(unattended.contains("SecAccessControlCreateWithFlags"))
        XCTAssertFalse(unattended.contains("SecureEnclave.P256.Signing.PrivateKey"))
        let before = DaemonKeyCreationHarness.hardwareCallsiteReached
        _ = DaemonKeyCreationHarness.unattendedAssessment()
        XCTAssertEqual(DaemonKeyCreationHarness.hardwareCallsiteReached, before)
    }
}
