import XCTest

final class RecoveryUITests: XCTestCase {
    private let app = XCUIApplication()

    override func tearDown() {
        // Close any presented activity sheet before ending the owned app.
        if app.state == .runningForeground { app.swipeDown() }
        app.terminate()
        super.tearDown()
    }

    func testRecoveryNoticeCanBeDismissedReopenedAndExported() {
        continueAfterFailure = false
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
        // Query the activity's actionable button, not every accessibility node.
        // Keep the existing bound; snapshot failures must fail the gate.
        XCTAssertTrue(app.buttons["Copy"].firstMatch.waitForExistence(timeout: 90), app.debugDescription)
    }
}
