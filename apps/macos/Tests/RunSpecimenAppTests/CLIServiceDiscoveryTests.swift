import XCTest
import Darwin
@testable import RunSpecimenApp

final class CLIServiceDiscoveryTests: XCTestCase {
    func testShellProbeRejectsExecutableFIFOWithoutWaitingForWriter() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let fifo = root.appendingPathComponent("runspecimen")
        XCTAssertEqual(mkfifo(fifo.path, 0o700), 0)
        let writerFinished = expectation(description: "bounded FIFO fixture completed")
        DispatchQueue.global().asyncAfter(deadline: .now() + 0.6) {
            let fd = open(fifo.path, O_WRONLY | O_NONBLOCK)
            if fd >= 0 {
                let bytes = Array(("#!/bin/bash\n" + String(repeating: "#", count: 64)).utf8)
                _ = bytes.withUnsafeBytes { write(fd, $0.baseAddress!, $0.count) }
                close(fd)
            }
            writerFinished.fulfill()
        }
        let start = Date()
        let shell = CLIService.isShellScript(at: fifo)
        XCTAssertLessThan(Date().timeIntervalSince(start), 0.3, "FIFO discovery must not wait for a writer")
        XCTAssertFalse(shell)
        XCTAssertNil(CLIService.candidatePrefix(at: fifo))
        wait(for: [writerFinished], timeout: 2)
        try FileManager.default.removeItem(at: root)
    }

    func testShellProbeAcceptsRegularScriptAndRejectsDirectory() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let script = root.appendingPathComponent("runspecimen")
        try Data("#!/bin/bash\necho ready\n".utf8).write(to: script)
        XCTAssertTrue(CLIService.isShellScript(at: script))
        XCTAssertFalse(CLIService.isShellScript(at: root))
    }
}
