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
        let hidden = expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: banner)
        wait(for: [hidden], timeout: 5)
        let reopen = app.buttons["Key recovery"]
        XCTAssertTrue(reopen.waitForExistence(timeout: 5), app.debugDescription)
        reopen.tap()
        XCTAssertTrue(banner.waitForExistence(timeout: 5), app.debugDescription)
        app.buttons["Export recovery diagnostics"].tap()
        // App-presented share-sheet chrome. Do not wait for SharingUIService Copy.
        let sheet = app.navigationBars["UIActivityView"]
        XCTAssertTrue(sheet.waitForExistence(timeout: 5), app.debugDescription)
    }
}
