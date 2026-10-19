import XCTest

final class RefreshUITests: XCTestCase {
    func testCancelledRefreshDoesNotInventAnUpdateTimestamp() {
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "cancelled"
        app.launch()
        XCTAssertTrue(app.staticTexts["Stale"].waitForExistence(timeout: 15))
        let inventedUpdate = app.staticTexts["lastSuccessfulRefresh"]
        XCTAssertFalse(inventedUpdate.exists, app.debugDescription)
        XCTAssertTrue(app.staticTexts["Refresh cancelled."].firstMatch.isHittable, app.debugDescription)
    }

    func testTransportFailureIsVisibleBesideConnectionStatus() {
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "failure"
        app.launch()
        XCTAssertTrue(app.staticTexts["Stale"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["connectionRefreshFailure"].isHittable, app.debugDescription)
    }
    func testRefreshButtonPublishesRecoveredStatusWithoutPullToRefresh() {
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "recover"
        app.launch()
        XCTAssertTrue(app.staticTexts["Stale"].waitForExistence(timeout: 15))
        let refresh = app.buttons["Refresh status"]
        XCTAssertTrue(refresh.isHittable, app.debugDescription)
        refresh.tap()
        XCTAssertTrue(app.staticTexts["button-refresh"].waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(app.staticTexts["Connected"].exists, app.debugDescription)
        XCTAssertTrue(app.staticTexts["lastSuccessfulRefresh"].exists, app.debugDescription)
        XCTAssertTrue(app.staticTexts.matching(identifier: "Status refreshed.").allElementsBoundByIndex.contains(where: { $0.isHittable }), app.debugDescription)
    }

    func testPairedPhoneHasVisiblePairingEntry() {
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "recover"
        app.launch()
        let entry = app.buttons["pairIPhone"]
        XCTAssertTrue(entry.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(entry.isHittable, app.debugDescription)
        entry.tap()
        XCTAssertTrue(app.textFields["https://192.168.x.y:8787/"].waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(app.staticTexts["Connect to your Mac"].exists, app.debugDescription)
    }

}
