import XCTest
@testable import RunSpecimenCore
@testable import RunSpecimenApp

final class CLIServiceCaptureFailureTests: XCTestCase {
    func testRunLifecycleRejectsEachCaptureFailure() async {
        await assertEachAxis { service in
            _ = try await service.runLifecycle(
                action: .validate,
                workspace: URL(fileURLWithPath: "/tmp/rs-cli-service"),
                contract: URL(fileURLWithPath: "/tmp/rs-cli-service/contract.json"),
                campaignID: "campaign",
                runID: "run"
            )
        }
    }

    func testVersionRejectsEachCaptureFailure() async {
        await assertEachAxis { service in
            _ = try await service.version()
        }
    }

    private func assertEachAxis(_ body: (CLIService) async throws -> Void) async {
        let axes: [(String, BoundedProcessCapture.Output, String)] = [
            ("timedOut", output(timedOut: true), "timed out"),
            ("cancelled", output(cancelled: true), "cancelled"),
            ("streamReadError", output(streamReadError: EIO), "could not be read"),
            ("cleanupFailed", output(cleanupFailed: true), "descendant"),
        ]
        var failures: [String] = []
        for (name, captured, needle) in axes {
            let service = CLIService(processes: FixedCapture(captured))
            await service.setCLI(URL(fileURLWithPath: "/bin/echo"), source: .manual)
            do {
                try await body(service)
                failures.append("\(name) was accepted")
            } catch let error as AppError {
                if !error.message.contains(needle) {
                    failures.append("\(name) said \(error.message)")
                }
            } catch {
                failures.append("\(name) threw \(error)")
            }
        }
        XCTAssertEqual(failures, [])
    }

    private func output(
        timedOut: Bool = false,
        cancelled: Bool = false,
        cleanupFailed: Bool = false,
        streamReadError: Int32? = nil
    ) -> BoundedProcessCapture.Output {
        var captured = BoundedProcessCapture.Output(
            exitCode: 0,
            stdout: Data("runspecimen 0.2.0rc15\n".utf8),
            stderr: Data("kept-stderr\n".utf8),
            stdoutTruncated: false,
            stderrTruncated: false,
            timedOut: timedOut,
            cancelled: cancelled
        )
        captured.cleanupFailed = cleanupFailed
        captured.streamReadError = streamReadError
        return captured
    }
}

private struct FixedCapture: ProcessCapturing {
    var captured: BoundedProcessCapture.Output

    init(_ captured: BoundedProcessCapture.Output) {
        self.captured = captured
    }

    func capture(
        executable: URL,
        arguments: [String],
        environment: [String: String],
        currentDirectory: URL?,
        isCancelled: @escaping @Sendable () -> Bool
    ) throws -> BoundedProcessCapture.Output {
        captured
    }
}
