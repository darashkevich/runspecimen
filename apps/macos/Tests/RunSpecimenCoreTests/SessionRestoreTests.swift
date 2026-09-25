import XCTest
import RunSpecimenCore

final class SessionRestoreTests: XCTestCase {
    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("rs-session-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
    }

    func testContractInsideWorkspaceIsRestorable() throws {
        let workspace = root.appendingPathComponent("workspace", isDirectory: true)
        try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
        let contract = workspace.appendingPathComponent("contract.json")
        try Data("{}".utf8).write(to: contract)
        let restored = SessionRestore.containedContract(contract: contract, workspace: workspace)
        XCTAssertEqual(restored?.standardizedFileURL, contract.standardizedFileURL)
    }

    func testSiblingDirectoryIsNotInsideWorkspace() throws {
        let workspace = root.appendingPathComponent("workspace", isDirectory: true)
        let sibling = root.appendingPathComponent("workspace-evil", isDirectory: true)
        try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: sibling, withIntermediateDirectories: true)
        let contract = sibling.appendingPathComponent("contract.json")
        try Data("{}".utf8).write(to: contract)
        XCTAssertNil(SessionRestore.containedContract(contract: contract, workspace: workspace))
    }

    func testMissingContractIsNotRestored() throws {
        let workspace = root.appendingPathComponent("workspace", isDirectory: true)
        try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
        let missing = workspace.appendingPathComponent("missing.json")
        XCTAssertNil(SessionRestore.containedContract(contract: missing, workspace: workspace))
    }

    func testDirectoryIsNotAContract() throws {
        let workspace = root.appendingPathComponent("workspace", isDirectory: true)
        let nested = workspace.appendingPathComponent("not-a-file", isDirectory: true)
        try FileManager.default.createDirectory(at: nested, withIntermediateDirectories: true)
        XCTAssertNil(SessionRestore.containedContract(contract: nested, workspace: workspace))
    }

    func testSymlinkEscapeIsRejected() throws {
        let workspace = root.appendingPathComponent("workspace", isDirectory: true)
        let outside = root.appendingPathComponent("outside", isDirectory: true)
        try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: outside, withIntermediateDirectories: true)
        let target = outside.appendingPathComponent("secret.json")
        try Data("{}".utf8).write(to: target)
        let link = workspace.appendingPathComponent("contract.json")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: target)
        XCTAssertNil(SessionRestore.containedContract(contract: link, workspace: workspace))
    }

    func testLastWindowCloseDoesNotQuit() {
        XCTAssertFalse(SessionRestore.quitWhenLastWindowCloses)
    }
}
