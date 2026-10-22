import XCTest

final class RefreshUITests: XCTestCase {
    func testCancelledRefreshDoesNotInventAnUpdateTimestamp() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "cancelled"
        app.launch()
        XCTAssertTrue(app.staticTexts["Stale"].waitForExistence(timeout: 15))
        let inventedUpdate = app.staticTexts["lastSuccessfulRefresh"]
        XCTAssertFalse(inventedUpdate.exists, app.debugDescription)
        let cancelled = app.staticTexts["Refresh cancelled."].firstMatch
        XCTAssertTrue(cancelled.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(cancelled.isHittable, app.debugDescription)
    }

    func testTransportFailureIsVisibleBesideConnectionStatus() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "failure"
        app.launch()
        XCTAssertTrue(app.staticTexts["Stale"].waitForExistence(timeout: 15))
        let failure = app.staticTexts["connectionRefreshFailure"]
        XCTAssertTrue(failure.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(failure.isHittable, app.debugDescription)
    }
    func testRefreshButtonPublishesRecoveredStatusWithoutPullToRefresh() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "recover"
        app.launch()
        XCTAssertTrue(app.staticTexts["Stale"].waitForExistence(timeout: 15))
        let refresh = app.buttons["Refresh status"]
        XCTAssertTrue(refresh.isHittable, app.debugDescription)
        refresh.tap()
        XCTAssertTrue(app.staticTexts["button-refresh"].waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(app.staticTexts["Connected"].exists, app.debugDescription)
        XCTAssertTrue(app.staticTexts["lastSuccessfulRefresh"].exists, app.debugDescription)
        XCTAssertTrue(app.staticTexts.matching(identifier: "Status refreshed.").allElementsBoundByIndex.contains(where: { $0.isHittable }), app.debugDescription)
    }

    func testPairedPhoneHasVisiblePairingEntry() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "recover"
        app.launch()
        let entry = app.buttons["pairIPhone"]
        XCTAssertTrue(entry.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(entry.isHittable, app.debugDescription)
        entry.tap()
        XCTAssertTrue(app.textFields["https://192.168.x.y:8787/"].waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(app.staticTexts["Connect to your Mac"].exists, app.debugDescription)
    }

    func testPairingEditsAreDiscardedWhenGoingBack() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_REFRESH_TEST"] = "recover"
        app.launch()
        let entry = app.buttons["pairIPhone"]
        XCTAssertTrue(entry.waitForExistence(timeout: 15), app.debugDescription)
        entry.tap()
        let url = app.textFields["https://192.168.x.y:8787/"]
        XCTAssertTrue(url.waitForExistence(timeout: 15))
        XCTAssertEqual(url.value as? String, "http://localhost")
        url.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 15), app.debugDescription)
        url.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: "http://localhost".count) + "https://candidate.invalid")
        // Text entry and the SwiftUI binding can settle on separate UI cycles.
        // Require the actual candidate value before testing navigation rollback.
        let edited = expectation(for: NSPredicate(format: "value == %@", "https://candidate.invalid"), evaluatedWith: url)
        wait(for: [edited], timeout: 15)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(entry.waitForExistence(timeout: 15), app.debugDescription)
        entry.tap()
        XCTAssertTrue(url.waitForExistence(timeout: 15))
        XCTAssertEqual(url.value as? String, "http://localhost", "Backing out must not change the working connection")
    }

}
