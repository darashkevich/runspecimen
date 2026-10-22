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
        // Synchronize on the replacement control before querying the old banner.
        // Cold CI accessibility snapshots can lag behind the dismiss action.
        let reopen = app.buttons["Key recovery"]
        XCTAssertTrue(reopen.waitForExistence(timeout: 15), app.debugDescription)
        XCTAssertFalse(banner.exists, app.debugDescription)
        reopen.tap()
        XCTAssertTrue(banner.waitForExistence(timeout: 15), app.debugDescription)
        app.buttons["Export recovery diagnostics"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["Copy"].firstMatch.waitForExistence(timeout: 30), app.debugDescription)
    }
}
