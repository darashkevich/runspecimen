import XCTest

final class RefreshUITests: XCTestCase {
    func testCancelledRefreshDoesNotInventAnUpdateTimestamp() {
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "cancelled"
        app.launch()
        XCTAssertTrue(app.staticTexts["Stale"].waitForExistence(timeout: 15))
        let inventedUpdate = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Updated ")).firstMatch
        XCTAssertFalse(inventedUpdate.exists, app.debugDescription)
        XCTAssertTrue(app.staticTexts["Refresh cancelled."].firstMatch.isHittable, app.debugDescription)
    }

    func testTransportFailureIsVisibleBesideConnectionStatus() {
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "failure"
        app.launch()
        XCTAssertTrue(app.staticTexts["Stale"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["Fixture Mac is unreachable"].firstMatch.isHittable, app.debugDescription)
    }
}
