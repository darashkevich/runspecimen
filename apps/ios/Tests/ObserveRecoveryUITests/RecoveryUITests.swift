import XCTest

final class RecoveryUITests: XCTestCase {
    func testRecoveryNoticeCanBeDismissedReopenedAndExported() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_RECOVERY_TEST"] = "1"
        app.launch()
        let banner = app.descendants(matching: .any)["rotationRecoveryFailure"].firstMatch
        XCTAssertTrue(banner.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertTrue(app.buttons["Retry key recovery"].exists)
        XCTAssertTrue(app.buttons["Export recovery diagnostics"].exists)
        app.buttons["Dismiss notice"].tap()
        let hidden = expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: banner)
        wait(for: [hidden], timeout: 5)
        let reopen = app.buttons["Key recovery"]
        XCTAssertTrue(reopen.waitForExistence(timeout: 5))
        reopen.tap()
        XCTAssertTrue(banner.waitForExistence(timeout: 5))
        let failure = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Key recovery needs attention:")).firstMatch.label
        let copy = app.buttons["Copy recovery diagnostics"]
        XCTAssertTrue(copy.waitForExistence(timeout: 5), app.debugDescription)
        copy.tap()
        XCTAssertTrue(app.staticTexts["Recovery diagnostics copied."].waitForExistence(timeout: 5))
        app.buttons["Inspect copied diagnostics"].tap()
        let copied = app.staticTexts["copiedRecoveryDiagnostics"].label
        XCTAssertEqual(copied, "RunSpecimen key recovery\n" + failure + "\nRecovery evidence is retained. Retry after restoring storage access; do not delete key records or reset generation counters.")
    }
}
