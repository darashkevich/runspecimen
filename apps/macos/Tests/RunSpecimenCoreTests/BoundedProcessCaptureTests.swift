import Darwin
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

    func testIgnoredSIGTERMIsKilledAfterTheGracePeriod() throws {
        let sibling = Process()
        sibling.executableURL = URL(fileURLWithPath: "/bin/sleep")
        sibling.arguments = ["30"]
        try sibling.run()
        defer {
            if sibling.isRunning {
                sibling.terminate()
                sibling.waitUntilExit()
            }
        }
        let started = Date()
        let output = try BoundedProcessCapture.run(
            executable: python,
            arguments: ["-c", Self.ignoreTermUntil],
            byteLimit: 1024,
            timeout: 0.1,
            terminationGrace: 0.25,
            readyMarker: Self.readyMarker
        )
        let elapsed = Date().timeIntervalSince(started)
        XCTAssertTrue(output.timedOut)
        XCTAssertFalse(output.cancelled)
        XCTAssertEqual(output.exitCode, SIGKILL)
        XCTAssertLessThan(elapsed, Self.startupCeiling)
        XCTAssertTrue(sibling.isRunning, "escalation killed a process it does not own")
    }

    func testCancellationKillsAChildThatIgnoresSIGTERM() throws {
        let armed = Date()
        let output = try BoundedProcessCapture.run(
            executable: python,
            arguments: ["-c", Self.ignoreTermUntil],
            byteLimit: 1024,
            timeout: 30,
            terminationGrace: 0.25,
            readyMarker: Self.readyMarker,
            isCancelled: { Date().timeIntervalSince(armed) >= 0.2 }
        )
        XCTAssertTrue(output.cancelled)
        XCTAssertFalse(output.timedOut)
        XCTAssertEqual(output.exitCode, SIGKILL)
        XCTAssertLessThan(Date().timeIntervalSince(armed), Self.startupCeiling)
    }

    func testGrandchildThatIgnoresSIGTERMDiesWithTheOwnedGroup() throws {
        let started = Date()
        let output = try BoundedProcessCapture.run(
            executable: python,
            arguments: ["-c", Self.ignoreTermAndSpawn],
            byteLimit: 1024,
            timeout: 0.4,
            terminationGrace: 0.3,
            readyMarker: Self.readyMarker
        )
        let elapsed = Date().timeIntervalSince(started)
        XCTAssertTrue(output.timedOut)
        XCTAssertNotEqual(output.exitCode, 0)
        XCTAssertNotEqual(output.exitCode, 3, "child never became its own process group")
        XCTAssertLessThan(elapsed, Self.startupCeiling)
        let pid = Self.descendantPID(in: output.stdout)
        if pid > 1 && kill(pid, 0) == 0 {
            kill(pid, SIGKILL)
            XCTFail("grandchild \(pid) was still running after the capture returned")
        }
    }

    func testIgnoredSIGTERMWithAFullPipeStillReturns() throws {
        let started = Date()
        let output = try BoundedProcessCapture.run(
            executable: python,
            arguments: ["-c", Self.ignoreTermAndFlood],
            byteLimit: 1000,
            timeout: 0.2,
            terminationGrace: 0.25,
            readyMarker: Self.readyMarker
        )
        XCTAssertTrue(output.timedOut)
        XCTAssertTrue(output.stdoutTruncated)
        XCTAssertTrue(output.stderrTruncated)
        XCTAssertEqual(output.stdout.count, 1000)
        XCTAssertEqual(output.stderr.count, 1000)
        XCTAssertEqual(output.exitCode, SIGKILL)
        XCTAssertLessThan(Date().timeIntervalSince(started), Self.startupCeiling)
        XCTAssertThrowsError(try EngineReportDecoder.jsonPayload(from: output)) { error in
            XCTAssertEqual(
                (error as? EngineReportError)?.message,
                "The engine timed out before it finished."
            )
        }
    }

    func testTruncatedCaptureIsNotDecodedAsAnEmptyObject() throws {
        let output = try capture(
            "printf '{'; dd if=/dev/zero bs=1024 count=32 status=none | tr '\\0' a; printf '}'",
            byteLimit: 64,
            timeout: 5
        )
        XCTAssertEqual(output.exitCode, 0)
        XCTAssertTrue(output.stdoutTruncated)
        XCTAssertThrowsError(try EngineReportDecoder.jsonPayload(from: output)) { error in
            XCTAssertEqual(
                (error as? EngineReportError)?.message,
                "Output was truncated. The report is incomplete."
            )
        }
    }

    func testTruncatedFlagRejectsAValidLookingPrefix() {
        let output = BoundedProcessCapture.Output(
            exitCode: 0,
            stdout: Data("{\"ok\":true}".utf8),
            stderr: Data(),
            stdoutTruncated: true,
            stderrTruncated: false,
            timedOut: false,
            cancelled: false
        )
        XCTAssertThrowsError(try EngineReportDecoder.jsonPayload(from: output)) { error in
            XCTAssertEqual(
                (error as? EngineReportError)?.message,
                "Output was truncated. The report is incomplete."
            )
        }
    }

    func testStderrTruncationRejectsACompleteStdoutObject() {
        let output = BoundedProcessCapture.Output(
            exitCode: 0,
            stdout: Data("{\"ok\":true}".utf8),
            stderr: Data("partial".utf8),
            stdoutTruncated: false,
            stderrTruncated: true,
            timedOut: false,
            cancelled: false
        )
        XCTAssertThrowsError(try EngineReportDecoder.jsonPayload(from: output)) { error in
            XCTAssertEqual(
                (error as? EngineReportError)?.message,
                "Output was truncated. The report is incomplete."
            )
        }
    }

    func testMalformedJSONIsNotAnEmptyObject() throws {
        let output = try capture("printf '{'", byteLimit: 1024, timeout: 5)
        XCTAssertEqual(output.exitCode, 0)
        XCTAssertFalse(output.stdoutTruncated)
        XCTAssertThrowsError(try EngineReportDecoder.jsonPayload(from: output)) { error in
            XCTAssertEqual(
                (error as? EngineReportError)?.message,
                "The engine report was not a complete JSON object."
            )
        }
    }

    func testEngineFailureIsNotAnEmptyObject() {
        let output = BoundedProcessCapture.Output(
            exitCode: 7,
            stdout: Data("not-json".utf8),
            stderr: Data("boom".utf8),
            stdoutTruncated: false,
            stderrTruncated: false,
            timedOut: false,
            cancelled: false
        )
        XCTAssertThrowsError(try EngineReportDecoder.jsonPayload(from: output)) { error in
            XCTAssertEqual((error as? EngineReportError)?.message, "boom")
        }
    }

    func testJSONArrayAndEmptyBodyAreNotEmptyObjects() {
        for body in ["[]", "null", "\"text\"", ""] {
            let output = BoundedProcessCapture.Output(
                exitCode: 0,
                stdout: Data(body.utf8),
                stderr: Data(),
                stdoutTruncated: false,
                stderrTruncated: false,
                timedOut: false,
                cancelled: false
            )
            XCTAssertThrowsError(try EngineReportDecoder.jsonPayload(from: output), "body \(body)") { error in
                XCTAssertEqual(
                    (error as? EngineReportError)?.message,
                    "The engine report was not a complete JSON object."
                )
            }
        }
    }

    func testParentExitDoesNotLeaveAChildThatIgnoresSIGTERM() throws {
        let output = try BoundedProcessCapture.run(
            executable: python,
            arguments: ["-c", Self.parentExitsChildIgnores],
            byteLimit: 1024,
            timeout: 0.2,
            terminationGrace: 0.3,
            readyMarker: Self.readyMarker
        )
        XCTAssertTrue(output.timedOut)
        XCTAssertFalse(output.cleanupFailed)
        let pid = Self.descendantPID(in: output.stdout)
        XCTAssertGreaterThan(pid, 1)
        if pid > 1 && kill(pid, 0) == 0 {
            kill(pid, SIGKILL)
            XCTFail("child \(pid) survived after its parent exited")
        }
    }

    func testGroupSignalRefusesTheCallerGroupAndClassifiesFailures() {
        XCTAssertFalse(BoundedProcessCapture.groupIsSignalable(getpgrp()))
        XCTAssertFalse(BoundedProcessCapture.groupIsSignalable(0))
        XCTAssertFalse(BoundedProcessCapture.groupIsSignalable(1))
        XCTAssertFalse(BoundedProcessCapture.groupIsSignalable(-4))
        XCTAssertEqual(BoundedProcessCapture.classifyGroupSignal(rc: 0, errorNumber: 0), .signaled)
        XCTAssertEqual(BoundedProcessCapture.classifyGroupSignal(rc: -1, errorNumber: ESRCH), .empty)
        XCTAssertEqual(BoundedProcessCapture.classifyGroupSignal(rc: -1, errorNumber: EPERM), .failed)
        XCTAssertEqual(
            BoundedProcessCapture.signalOwnedGroup(pgid: getpgrp(), signal: 0),
            .refused
        )
    }

    func testStartupDeadlineFailsWhenTheChildNeverBecomesReady() {
        XCTAssertThrowsError(
            try BoundedProcessCapture.run(
                executable: URL(fileURLWithPath: "/bin/sleep"),
                arguments: ["30"],
                timeout: 0.05,
                readyMarker: Self.readyMarker,
                readyDeadline: 0.2
            )
        ) { error in
            XCTAssertEqual(
                (error as? EngineReportError)?.message,
                "The child was not ready before the startup deadline."
            )
        }
    }

    func testInterruptedReadIsRetriedAndAHardReadErrorIsNotSuccess() {
        XCTAssertEqual(BoundedProcessCapture.readDisposition(count: 4, errorNumber: EINTR), .data)
        XCTAssertEqual(BoundedProcessCapture.readDisposition(count: 0, errorNumber: EINTR), .end)
        XCTAssertEqual(BoundedProcessCapture.readDisposition(count: -1, errorNumber: EINTR), .retry)
        XCTAssertEqual(BoundedProcessCapture.readDisposition(count: -1, errorNumber: EIO), .failed(EIO))

        let ready = BoundedProcessCapture.reduceReads([
            .init(count: -1, errorNumber: EINTR),
            .init(count: 5, bytes: Data("READY".utf8)),
            .init(count: 0),
        ])
        XCTAssertEqual(ready.data, Data("READY".utf8))
        XCTAssertNil(ready.error)

        let failed = BoundedProcessCapture.reduceReads([
            .init(count: 2, bytes: Data("ok".utf8)),
            .init(count: -1, errorNumber: EIO),
        ])
        XCTAssertEqual(failed.data, Data("ok".utf8))
        XCTAssertEqual(failed.error, EIO)

        let output = BoundedProcessCapture.Output(
            exitCode: 0,
            stdout: Data("{\"ok\":true}".utf8),
            stderr: Data(),
            stdoutTruncated: false,
            stderrTruncated: false,
            timedOut: false,
            cancelled: false,
            streamReadError: EIO
        )
        XCTAssertThrowsError(try EngineReportDecoder.jsonPayload(from: output)) { error in
            XCTAssertEqual(
                (error as? EngineReportError)?.message,
                "The engine output could not be read (errno \(EIO))."
            )
        }
    }

    func testCleanupFailureIsNotReportedAsAPlainTimeout() {
        let output = BoundedProcessCapture.Output(
            exitCode: -1,
            stdout: Data(),
            stderr: Data(),
            stdoutTruncated: false,
            stderrTruncated: false,
            timedOut: true,
            cancelled: false,
            cleanupFailed: true
        )
        XCTAssertThrowsError(try EngineReportDecoder.jsonPayload(from: output)) { error in
            XCTAssertEqual(
                (error as? EngineReportError)?.message,
                "The engine stopped, but an owned descendant was still running."
            )
        }
    }

    func testCompleteJSONObjectDecodes() throws {
        let output = try capture("printf '%s' '{\"ok\":true}'", byteLimit: 1024, timeout: 5)
        let payload = try EngineReportDecoder.jsonPayload(from: output)
        XCTAssertEqual(payload.object["ok"] as? Bool, true)
        XCTAssertTrue(payload.pretty.contains("\"ok\""))
    }

    private let python = URL(fileURLWithPath: "/usr/bin/python3")
    /// Startup may be slower than the action timeout. The capture waits for
    /// this marker, then applies the short timeout. 8s is the startup deadline
    /// plus kill grace, not a longer grace period.
    private static let startupCeiling: TimeInterval = 8
    private static let readyMarker = Data("READY".utf8)
    private static let ignoreTermUntil = """
    import signal, sys, time
    time.sleep(0.35)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    sys.stdout.write("READY\\n")
    sys.stdout.flush()
    time.sleep(30)
    """
    private static let ignoreTermAndSpawn = """
    import os, signal, subprocess, sys, time
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if os.getpgid(0) != os.getpid():
        sys.exit(3)
    read_fd, write_fd = os.pipe()
    code = (
        "import os,signal,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "os.write(%d, b'1'); time.sleep(30)" % write_fd
    )
    child = subprocess.Popen(
        ["/usr/bin/python3", "-c", code],
        pass_fds=(write_fd,),
    )
    os.close(write_fd)
    os.read(read_fd, 1)
    sys.stdout.write("READY %d\\n" % child.pid)
    sys.stdout.flush()
    time.sleep(30)
    """
    private static let parentExitsChildIgnores = """
    import os, signal, sys, time
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        os.write(write_fd, b"1")
        time.sleep(30)
        os._exit(0)
    os.close(write_fd)
    os.read(read_fd, 1)
    time.sleep(0.35)
    sys.stdout.write("READY %d\\n" % pid)
    sys.stdout.flush()
    time.sleep(30)
    """
    private static let ignoreTermAndFlood = """
    import signal, sys, time
    time.sleep(0.35)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    sys.stdout.write("READY\\n")
    sys.stdout.flush()
    sys.stdout.buffer.write(b"x" * 200000)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(b"y" * 200000)
    sys.stderr.buffer.flush()
    time.sleep(30)
    """

    private static func descendantPID(in data: Data) -> pid_t {
        let text = String(data: data, encoding: .utf8) ?? ""
        guard let range = text.range(of: "READY") else { return -1 }
        let rest = text[range.upperBound...].trimmingCharacters(in: .whitespacesAndNewlines)
        let token = rest.split(whereSeparator: { $0.isWhitespace }).first.map(String.init) ?? ""
        return pid_t(token) ?? -1
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
