import XCTest
@testable import RunSpecimenMacCompanion

final class CompanionBoundaryTests: XCTestCase {
    func testBoundaryRefusesLifecycleMutationFlags() {
        XCTAssertFalse(CompanionBoundary.canApprove)
        XCTAssertFalse(CompanionBoundary.canExecute)
        XCTAssertEqual(CompanionBoundary.mode, "observe")
    }

    func testStableBundleIdentifiers() {
        XCTAssertEqual(CompanionBoundary.bundleIdentifier, "com.darashkevich.runspecimen.companion")
        XCTAssertEqual(CompanionBoundary.iosObserveBundleIdentifier, "com.darashkevich.runspecimen.observe")
        XCTAssertTrue(CompanionBoundary.shippingChannel.contains("TestFlight"))
    }

    func testLaunchPlanNeverIncludesApproveOrRun() {
        let plan = CompanionLaunchPlan(
            workspace: "/tmp/ws",
            contract: "/tmp/ws/contract.json",
            host: "192.168.1.2",
            allowLAN: true
        )
        let joined = plan.processArguments.joined(separator: " ")
        XCTAssertTrue(joined.contains("companion"))
        XCTAssertTrue(joined.contains("--allow-lan"))
        XCTAssertFalse(joined.contains("approve"))
        XCTAssertFalse(joined.split(separator: " ").contains("run"))
    }

    func testArmPlanIsRemoteConfirmNotApprove() {
        let plan = CompanionLaunchPlan(
            workspace: "/tmp/ws",
            contract: "/tmp/ws/contract.json"
        )
        let args = plan.armRemoteConfirmArguments
        XCTAssertEqual(args.first, "remote-confirm")
        XCTAssertEqual(args[1], "arm")
        XCTAssertFalse(args.contains("approve"))
    }
}
