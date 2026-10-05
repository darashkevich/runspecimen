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
}
