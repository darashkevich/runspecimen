import Foundation
import XCTest
@testable import RunSpecimenCore

final class ReviewerDemoMaterializerTests: XCTestCase {
    func testReuseExistingPreservesEvidence() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("rs-demo-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let source = root.appendingPathComponent("bundled", isDirectory: true)
        try fm.createDirectory(at: source, withIntermediateDirectories: true)
        try "contract".write(to: source.appendingPathComponent("contract.json"), atomically: true, encoding: .utf8)

        let support = root.appendingPathComponent("support", isDirectory: true)
        let first = try ReviewerDemoMaterializer.materialize(
            source: source,
            supportDirectory: support,
            mode: .reuseExisting,
            fileManager: fm
        )
        let receipt = first.appendingPathComponent(".runspecimen/runs/demo/run-001/events.jsonl")
        try fm.createDirectory(at: receipt.deletingLastPathComponent(), withIntermediateDirectories: true)
        try "receipt-line\n".write(to: receipt, atomically: true, encoding: .utf8)

        let second = try ReviewerDemoMaterializer.materialize(
            source: source,
            supportDirectory: support,
            mode: .reuseExisting,
            fileManager: fm
        )
        XCTAssertEqual(first.path, second.path)
        XCTAssertTrue(fm.fileExists(atPath: receipt.path))
        let body = try String(contentsOf: receipt, encoding: .utf8)
        XCTAssertEqual(body, "receipt-line\n")
    }

    func testResetRefusesWhenLeasePresent() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("rs-demo-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let source = root.appendingPathComponent("bundled", isDirectory: true)
        try fm.createDirectory(at: source, withIntermediateDirectories: true)
        try "contract".write(to: source.appendingPathComponent("contract.json"), atomically: true, encoding: .utf8)

        let support = root.appendingPathComponent("support", isDirectory: true)
        let dest = try ReviewerDemoMaterializer.materialize(
            source: source,
            supportDirectory: support,
            mode: .reuseExisting,
            fileManager: fm
        )
        let leaseDir = dest.appendingPathComponent(".runspecimen", isDirectory: true)
        try fm.createDirectory(at: leaseDir, withIntermediateDirectories: true)
        try Data().write(to: leaseDir.appendingPathComponent("execution.lock"))

        XCTAssertThrowsError(
            try ReviewerDemoMaterializer.materialize(
                source: source,
                supportDirectory: support,
                mode: .resetIfIdle,
                fileManager: fm
            )
        ) { error in
            guard let typed = error as? ReviewerDemoMaterializer.MaterializeError,
                  case .leaseHeld = typed else {
                return XCTFail("expected leaseHeld, got \(error)")
            }
        }
        XCTAssertTrue(fm.fileExists(atPath: dest.appendingPathComponent("contract.json").path))
    }

    func testUniqueCopyDoesNotDeleteFixedDemo() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("rs-demo-\(UUID().uuidString)", isDirectory: true)
        defer { try? fm.removeItem(at: root) }

        let source = root.appendingPathComponent("bundled", isDirectory: true)
        try fm.createDirectory(at: source, withIntermediateDirectories: true)
        try "contract".write(to: source.appendingPathComponent("contract.json"), atomically: true, encoding: .utf8)

        let support = root.appendingPathComponent("support", isDirectory: true)
        let fixed = try ReviewerDemoMaterializer.materialize(
            source: source,
            supportDirectory: support,
            mode: .reuseExisting,
            fileManager: fm
        )
        try "keep-me".write(to: fixed.appendingPathComponent("marker.txt"), atomically: true, encoding: .utf8)

        let unique = try ReviewerDemoMaterializer.materialize(
            source: source,
            supportDirectory: support,
            mode: .uniqueCopy,
            fileManager: fm,
            uniqueSuffix: "session-1"
        )
        XCTAssertNotEqual(fixed.path, unique.path)
        XCTAssertTrue(unique.lastPathComponent.hasSuffix("-session-1"))
        XCTAssertEqual(try String(contentsOf: fixed.appendingPathComponent("marker.txt"), encoding: .utf8), "keep-me")
    }
}

final class BundledHelperPolicyTests: XCTestCase {
    func testMasRejectsExternalCLI() {
        let external = URL(fileURLWithPath: "/usr/local/bin/runspecimen")
        let bundled = URL(fileURLWithPath: "/Applications/RunSpecimen.app/Contents/Helpers/runspecimen")
        XCTAssertFalse(BundledHelperPolicy.allowsExternalCLI(channel: .mas))
        XCTAssertFalse(BundledHelperPolicy.acceptsCLI(external, channel: .mas, bundled: bundled))
        XCTAssertTrue(BundledHelperPolicy.acceptsCLI(bundled, channel: .mas, bundled: bundled))
        XCTAssertTrue(BundledHelperPolicy.acceptsCLI(external, channel: .local, bundled: bundled))
    }

    func testPathShapeRecognizesEngineHelper() {
        let engine = URL(fileURLWithPath: "/Apps/RunSpecimen.app/Contents/Resources/RunSpecimenEngine/runspecimen")
        XCTAssertTrue(BundledHelperPolicy.isBundledHelper(engine, bundled: nil))
    }
}
