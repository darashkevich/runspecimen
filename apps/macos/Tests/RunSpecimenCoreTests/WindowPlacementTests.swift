import XCTest
@testable import RunSpecimenCore

final class WindowPlacementTests: XCTestCase {
    private let screen = CGRect(x: 0, y: 0, width: 1512, height: 949)

    func testOffscreenGiantFrameIsCenteredOnDisplay() {
        let broken = CGRect(x: -1573, y: -4600, width: 1512, height: 5600)
        XCTAssertTrue(WindowPlacement.needsSanitize(frame: broken, screens: [screen]))

        let next = WindowPlacement.sanitize(frame: broken, screens: [screen])
        XCTAssertEqual(next.width, WindowPlacement.defaultSize.width, accuracy: 0.5)
        XCTAssertEqual(next.height, WindowPlacement.defaultSize.height, accuracy: 0.5)
        XCTAssertGreaterThanOrEqual(next.minX, screen.minX - 0.5)
        XCTAssertLessThanOrEqual(next.maxX, screen.maxX + 0.5)
        XCTAssertGreaterThanOrEqual(next.minY, screen.minY - 0.5)
        XCTAssertLessThanOrEqual(next.maxY, screen.maxY + 0.5)
        XCTAssertFalse(WindowPlacement.needsSanitize(frame: next, screens: [screen]))
    }

    func testReasonableFrameIsLeftAlone() {
        let ok = CGRect(x: 80, y: 60, width: 1180, height: 760)
        XCTAssertFalse(WindowPlacement.needsSanitize(frame: ok, screens: [screen]))
        let next = WindowPlacement.sanitize(frame: ok, screens: [screen])
        XCTAssertEqual(next.origin.x, ok.origin.x, accuracy: 0.5)
        XCTAssertEqual(next.origin.y, ok.origin.y, accuracy: 0.5)
        XCTAssertEqual(next.size.width, ok.size.width, accuracy: 0.5)
        XCTAssertEqual(next.size.height, ok.size.height, accuracy: 0.5)
    }

    func testTinyFrameGrowsToMinimum() {
        let tiny = CGRect(x: 40, y: 40, width: 200, height: 180)
        XCTAssertTrue(
            WindowPlacement.needsSanitize(frame: tiny, screens: [screen]),
            "on-screen frames smaller than minSize must still be sanitized"
        )
        let next = WindowPlacement.sanitize(frame: tiny, screens: [screen])
        XCTAssertGreaterThanOrEqual(next.width, WindowPlacement.minSize.width - 0.5)
        XCTAssertGreaterThanOrEqual(next.height, WindowPlacement.minSize.height - 0.5)
        XCTAssertFalse(WindowPlacement.needsSanitize(frame: next, screens: [screen]))
    }
}
