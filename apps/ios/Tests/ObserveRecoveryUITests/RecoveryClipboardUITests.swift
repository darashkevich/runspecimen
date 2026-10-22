import XCTest

final class RecoveryClipboardUITests: XCTestCase {
    func testRecoveryCopyContainsRetainedDiagnostics() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment["RUNSPECIMEN_UI_RECOVERY_TEST"] = "1"
        app.launch()
        XCTAssertTrue(app.buttons["Copy recovery diagnostics"].waitForExistence(timeout: 15), app.debugDescription)
        let failure = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Key recovery needs attention:")).firstMatch.label
        let copy = app.buttons["Copy recovery diagnostics"]
        XCTAssertTrue(copy.waitForExistence(timeout: 30), app.debugDescription)
        copy.tap()
        XCTAssertTrue(app.staticTexts["Recovery diagnostics copied."].waitForExistence(timeout: 15))
        app.buttons["Inspect copied diagnostics"].tap()
        let diagnostics = app.staticTexts["copiedRecoveryDiagnostics"]
        let ready = expectation(for: NSPredicate(format: "label BEGINSWITH %@", "RunSpecimen key recovery\n"), evaluatedWith: diagnostics)
        wait(for: [ready], timeout: 15)
        let copied = diagnostics.label
        XCTAssertEqual(copied, "RunSpecimen key recovery\n" + failure + "\nRecovery evidence is retained. Retry after restoring storage access; do not delete key records or reset generation counters.")
    }
}
