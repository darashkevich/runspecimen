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
        let masMsg = CLIVersionGate.failureMessage(
            for: CLIVersionGate.evaluate(versionOutput: "0.2.0rc8"),
            channel: .mas
        ) ?? ""
        XCTAssertFalse(masMsg.contains("pip install"))
        XCTAssertTrue(masMsg.contains("bundled"))
    }

    func testPythonHelperUnparseableMessage() {
        let raw = "runspecimen helper: need Python 3.9+ on PATH (bundled package is stdlib-only)."
        let msg = CLIVersionGate.failureMessage(for: .unparseable(raw: raw)) ?? ""
        XCTAssertTrue(msg.lowercased().contains("python"))
        XCTAssertFalse(msg.contains("Could not parse runspecimen version"))
    }

    func testResolutionSourceLabels() {
        XCTAssertFalse(CLIResolutionSource.bundledHelper.label.isEmpty)
        XCTAssertEqual(CLIResolutionSource.bookmark.label, "Saved bookmark")
    }

    func testDistributionChannelParse() {
        XCTAssertEqual(DistributionChannel.parse("mas"), .mas)
        XCTAssertEqual(DistributionChannel.parse("app-store"), .mas)
        XCTAssertEqual(DistributionChannel.parse("developer-id"), .developerID)
        XCTAssertEqual(DistributionChannel.parse(nil), .local)
        XCTAssertEqual(DistributionChannel.parse("local"), .local)
        XCTAssertTrue(DistributionChannel.mas.requiresBundledHelper)
        XCTAssertFalse(DistributionChannel.mas.allowsPATHProbe)
        XCTAssertTrue(DistributionChannel.local.allowsPATHProbe)
    }

    func testSecurityBoundaryInvariants() {
        XCTAssertTrue(SecurityBoundary.assertsInvariants())
        XCTAssertTrue(SecurityBoundary.neverAutoApprove)
        XCTAssertTrue(SecurityBoundary.notConfinedByAppUISandboxAlone.contains(where: {
            $0.localizedCaseInsensitiveContains("payload")
        }))
    }
}
