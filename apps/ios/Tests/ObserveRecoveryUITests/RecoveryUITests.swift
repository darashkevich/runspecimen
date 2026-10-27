import XCTest

final class RecoveryUITests: XCTestCase {
    private func phase(_ name: String, _ body: () -> Void) {
        let start = Date()
        XCTContext.runActivity(named: "QA2 phase: " + name) { activity in
            body()
            let timing = XCTAttachment(string: "seconds=\(Date().timeIntervalSince(start))")
            timing.lifetime = .keepAlways
            activity.add(timing)
        }
    }

    func testRecoveryNoticeCanBeDismissedReopenedAndExported() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_RECOVERY_TEST"] = "1"
        phase("launch") { app.launch() }
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
        phase("export tap") { app.buttons["Export recovery diagnostics"].tap() }
        // Cold CI SharingUIService took 55 seconds to publish Copy after the
        // app supplied its diagnostics. Keep a bounded positive readiness wait;
        // a missing action still fails, with no relaunch or assertion retry.
        phase("Copy snapshot query") { XCTAssertTrue(app.descendants(matching: .any)["Copy"].firstMatch.waitForExistence(timeout: 90), app.debugDescription) }
    }
}
