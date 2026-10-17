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
    func testRefreshButtonPublishesRecoveredStatusWithoutPullToRefresh() {
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "recover"
        app.launch()
        XCTAssertTrue(app.staticTexts["Stale"].waitForExistence(timeout: 15))
        let refresh = app.buttons["Refresh status"]
        for _ in 0..<6 {
            if refresh.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(refresh.isHittable, app.debugDescription)
        refresh.tap()
        XCTAssertTrue(app.staticTexts["button-refresh"].waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(app.staticTexts["Connected"].exists, app.debugDescription)
        XCTAssertTrue(app.staticTexts.matching(identifier: "Status refreshed.").allElementsBoundByIndex.contains(where: { $0.isHittable }), app.debugDescription)
    }

}
