import XCTest
@testable import RunSpecimenCore

final class StoreDashboardPolicyTests: XCTestCase {
    func testStoreHasNoBrowserServerButOtherChannelsKeepIt() {
        XCTAssertFalse(DistributionChannel.mas.allowsBrowserDashboard)
        XCTAssertTrue(DistributionChannel.local.allowsBrowserDashboard)
        XCTAssertTrue(DistributionChannel.developerID.allowsBrowserDashboard)
    }
}
