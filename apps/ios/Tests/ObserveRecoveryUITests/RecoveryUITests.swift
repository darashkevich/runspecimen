import XCTest

final class RecoveryUITests: XCTestCase {
    private let app = XCUIApplication()

    override func tearDown() {
        if app.state == .runningForeground {
            let dismiss = app.otherElements["PopoverDismissRegion"]
            if dismiss.exists {
                dismiss.tap()
            } else {
                app.swipeDown()
            }
        }
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
        // Scope to the share sheet's activity list. Keep the existing bound.
        let copy = app.otherElements["ActivityListView"].buttons["Copy"].firstMatch
        XCTAssertTrue(copy.waitForExistence(timeout: 90), app.debugDescription)
    }
}
