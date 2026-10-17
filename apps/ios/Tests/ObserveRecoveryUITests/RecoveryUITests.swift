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
        app.buttons["Export recovery diagnostics"].tap()
        // The first cold Simulator share service can populate its remote view
        // after five seconds (CI logs showed Copy created just after that deadline).
        // Wait for the actual action, then exercise it; never sleep or retry export.
        let copy = app.descendants(matching: .any)["Copy"].firstMatch
        XCTAssertTrue(copy.waitForExistence(timeout: 30), app.debugDescription)
        copy.tap()
        let sheetClosed = expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: copy)
        wait(for: [sheetClosed], timeout: 10)
    }
}
