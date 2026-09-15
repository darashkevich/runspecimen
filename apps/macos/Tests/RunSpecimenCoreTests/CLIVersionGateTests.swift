import XCTest
@testable import RunSpecimenCore

final class CLIVersionGateTests: XCTestCase {
    func testParseFinal() {
        let v = CLIVersionGate.parse(from: "runspecimen 0.2.0")
        XCTAssertEqual(v, CLIVersionGate.ParsedVersion(major: 0, minor: 2, patch: 0, preKind: 1, preNum: 0))
    }

    func testParseRC() {
        let v = CLIVersionGate.parse(from: "runspecimen 0.2.0rc9")
        XCTAssertEqual(v, CLIVersionGate.ParsedVersion(major: 0, minor: 2, patch: 0, preKind: 0, preNum: 9))
    }

    func testParseDashedRC() {
        let v = CLIVersionGate.parse(from: "0.2.0-rc.9")
        XCTAssertEqual(v, CLIVersionGate.ParsedVersion(major: 0, minor: 2, patch: 0, preKind: 0, preNum: 9))
    }

    func testMinimumAccepted() {
        switch CLIVersionGate.evaluate(versionOutput: "runspecimen 0.2.0rc9") {
        case .ok: break
        default: XCTFail("0.2.0rc9 should be accepted")
        }
    }

    func testFinalNewerThanRC() {
        let rc = CLIVersionGate.parse(from: "0.2.0rc9")!
        let final = CLIVersionGate.parse(from: "0.2.0")!
        XCTAssertLessThan(rc, final)
        switch CLIVersionGate.evaluate(versionOutput: "0.2.0") {
        case .ok: break
        default: XCTFail("0.2.0 final should pass gate")
        }
    }

    func testTooOld() {
        switch CLIVersionGate.evaluate(versionOutput: "runspecimen 0.2.0rc8") {
        case .tooOld(let found, let required, _):
            XCTAssertEqual(found.preNum, 8)
            XCTAssertEqual(required.displayMinimum, "0.2.0rc9")
        default:
            XCTFail("expected tooOld")
        }
        XCTAssertNotNil(CLIVersionGate.failureMessage(for: CLIVersionGate.evaluate(versionOutput: "0.2.0rc8")))
    }

    func testUnparseable() {
        switch CLIVersionGate.evaluate(versionOutput: "not-a-version") {
        case .unparseable: break
        default: XCTFail("expected unparseable")
        }
    }

    func testResolutionSourceLabels() {
        XCTAssertFalse(CLIResolutionSource.bundledHelper.label.isEmpty)
        XCTAssertEqual(CLIResolutionSource.bookmark.label, "Saved bookmark")
    }
}
