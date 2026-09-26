import XCTest
@testable import RunSpecimenCore

final class BoundedProcessCaptureTests: XCTestCase {
    private let bash = URL(fileURLWithPath: "/bin/bash")
    private let oversized = 256 * 1024

    func testOversizedStdoutIsDrained() throws {
        let output = try capture(
            "dd if=/dev/zero bs=1024 count=256 status=none",
            byteLimit: oversized + 1024,
            timeout: 5
        )
        XCTAssertEqual(output.exitCode, 0)
        XCTAssertEqual(output.stdout.count, oversized)
        XCTAssertGreaterThan(output.stdout.count, 65_536)
        XCTAssertFalse(output.stdoutTruncated)
        XCTAssertTrue(output.stderr.isEmpty)
        XCTAssertFalse(output.timedOut)
        XCTAssertFalse(output.cancelled)
    }

    func testOversizedStderrIsDrained() throws {
        let output = try capture(
            "dd if=/dev/zero bs=1024 count=256 status=none >&2",
            byteLimit: oversized + 1024,
            timeout: 5
        )
        XCTAssertEqual(output.exitCode, 0)
        XCTAssertEqual(output.stderr.count, oversized)
        XCTAssertGreaterThan(output.stderr.count, 65_536)
        XCTAssertFalse(output.stderrTruncated)
        XCTAssertTrue(output.stdout.isEmpty)
        XCTAssertFalse(output.timedOut)
        XCTAssertFalse(output.cancelled)
    }

    func testOversizedStdoutAndStderrTogether() throws {
        let both = try capture(
            "dd if=/dev/zero bs=1024 count=256 status=none >&2 & dd if=/dev/zero bs=1024 count=256 status=none; wait",
            byteLimit: oversized + 1024,
            timeout: 5
        )
        XCTAssertEqual(both.exitCode, 0)
        XCTAssertEqual(both.stdout.count, oversized)
        XCTAssertEqual(both.stderr.count, oversized)
        XCTAssertGreaterThan(both.stdout.count, 65_536)
        XCTAssertGreaterThan(both.stderr.count, 65_536)
        XCTAssertFalse(both.stdoutTruncated)
        XCTAssertFalse(both.stderrTruncated)
        XCTAssertFalse(both.timedOut)
        XCTAssertFalse(both.cancelled)
    }

    func testOutputPastTheLimitStillLetsTheChildExit() throws {
        let output = try capture(
            "dd if=/dev/zero bs=1024 count=256 status=none",
            byteLimit: 100_000,
            timeout: 5
        )
        XCTAssertEqual(output.exitCode, 0)
        XCTAssertEqual(output.stdout.count, 100_000)
        XCTAssertTrue(output.stdoutTruncated)
        XCTAssertFalse(output.timedOut)
        XCTAssertFalse(output.cancelled)
    }

    func testFailureReturnsBothStreams() throws {
        let output = try capture(
            "echo out-text; echo err-text >&2; exit 7",
            byteLimit: 65_536,
            timeout: 5
        )
        XCTAssertEqual(output.exitCode, 7)
        XCTAssertTrue(String(data: output.stdout, encoding: .utf8)?.contains("out-text") == true)
        XCTAssertTrue(String(data: output.stderr, encoding: .utf8)?.contains("err-text") == true)
        XCTAssertFalse(output.timedOut)
        XCTAssertFalse(output.cancelled)
    }

    func testCancellationTerminatesAndReturns() throws {
        let started = Date()
        let output = try BoundedProcessCapture.run(
            executable: bash,
            arguments: ["-c", "sleep 30"],
            byteLimit: 1024,
            timeout: 5,
            isCancelled: { true }
        )
        XCTAssertTrue(output.cancelled)
        XCTAssertFalse(output.timedOut)
        XCTAssertLessThan(Date().timeIntervalSince(started), 2)
    }

    func testTimeoutTerminatesAndReturns() throws {
        let started = Date()
        let output = try BoundedProcessCapture.run(
            executable: bash,
            arguments: ["-c", "sleep 30"],
            byteLimit: 1024,
            timeout: 0.3,
            isCancelled: { false }
        )
        XCTAssertTrue(output.timedOut)
        XCTAssertFalse(output.cancelled)
        XCTAssertLessThan(Date().timeIntervalSince(started), 2)
    }

    private func capture(
        _ script: String,
        byteLimit: Int,
        timeout: TimeInterval
    ) throws -> BoundedProcessCapture.Output {
        try BoundedProcessCapture.run(
            executable: bash,
            arguments: ["-c", script],
            byteLimit: byteLimit,
            timeout: timeout
        )
    }
}
