import XCTest
@testable import RunSpecimenCore

final class WorkflowConfirmationGateTests: XCTestCase {
    private func sample(title: String = "Create snapshot") -> WorkflowRequest {
        WorkflowRequest(
            title: title,
            detail: "Writes a snapshot. This does not approve or run.",
            arguments: ["snapshot", "create", "--id", "s1"]
        )
    }

    func testConfirmThenDismissStillExecutesOnce() {
        var gate = WorkflowConfirmationGate()
        gate.present(sample())
        let claimed = gate.confirm()
        gate.cancel()

        XCTAssertEqual(claimed?.title, "Create snapshot")
        XCTAssertNil(gate.pending)
        XCTAssertTrue(gate.beginExecution(of: claimed!))
        XCTAssertFalse(gate.beginExecution(of: claimed!))
        gate.finishExecution()
        XCTAssertEqual(gate.completedExecutions, 1)
        XCTAssertFalse(gate.isExecuting)
    }

    func testDismissThenConfirmExecutesNothing() {
        var gate = WorkflowConfirmationGate()
        gate.present(sample())
        gate.cancel()
        XCTAssertNil(gate.confirm())
        XCTAssertFalse(gate.beginExecution(of: sample()))
        gate.finishExecution()
        XCTAssertEqual(gate.completedExecutions, 0)
    }

    func testSecondConfirmIsIgnored() {
        var gate = WorkflowConfirmationGate()
        gate.present(sample())
        let first = gate.confirm()
        XCTAssertNil(gate.confirm())
        XCTAssertTrue(gate.beginExecution(of: first!))
        gate.finishExecution()
        XCTAssertEqual(gate.completedExecutions, 1)
    }

    func testBusyConfirmDoesNotStartAnotherExecution() {
        var gate = WorkflowConfirmationGate()
        let first = sample()
        gate.present(first)
        let claimed = gate.confirm()
        XCTAssertTrue(gate.beginExecution(of: claimed!))

        gate.present(sample(title: "Apply configuration"))
        XCTAssertNil(gate.pending)
        XCTAssertNil(gate.confirm())
        XCTAssertFalse(gate.beginExecution(of: sample(title: "Apply configuration")))

        gate.finishExecution()
        XCTAssertEqual(gate.completedExecutions, 1)
        XCTAssertFalse(gate.isExecuting)
    }

    func testConfirmedDecisionWritesOnceAndCancelWritesNothing() throws {
        let root = try repoRoot()
        let python = try pythonExecutable(in: root)
        let workspace = FileManager.default.temporaryDirectory
            .appendingPathComponent("rs-confirm-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: workspace) }

        let decision = workspace
            .appendingPathComponent(".runspecimen", isDirectory: true)
            .appendingPathComponent("decisions", isDirectory: true)
            .appendingPathComponent("qa-confirm.json")
        let arguments = [
            "-m", "runspecimen", "decisions", "capture",
            "--workspace", workspace.path,
            "--id", "qa-confirm",
            "--rationale", "recorded after an explicit confirm",
            "--classification", "human"
        ]
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = root.appendingPathComponent("src").path
        environment["PYTHONDONTWRITEBYTECODE"] = "1"

        var gate = WorkflowConfirmationGate()
        gate.present(WorkflowRequest(
            title: "Capture decision",
            detail: "Records a note. This does not approve or run.",
            arguments: arguments
        ))
        gate.cancel()
        XCTAssertNil(gate.confirm())
        XCTAssertFalse(FileManager.default.fileExists(atPath: decision.path))

        gate.present(WorkflowRequest(
            title: "Capture decision",
            detail: "Records a note. This does not approve or run.",
            arguments: arguments
        ))
        let claimed = gate.confirm()
        gate.cancel()
        XCTAssertEqual(claimed?.arguments, arguments)
        XCTAssertTrue(gate.beginExecution(of: claimed!))
        let output = try BoundedProcessCapture.run(
            executable: python,
            arguments: claimed!.arguments,
            environment: environment,
            byteLimit: 1_048_576,
            timeout: 30
        )
        gate.finishExecution()
        XCTAssertFalse(gate.beginExecution(of: claimed!))

        XCTAssertEqual(output.exitCode, 0, String(data: output.stderr, encoding: .utf8) ?? "")
        XCTAssertFalse(output.timedOut)
        XCTAssertFalse(output.cancelled)
        XCTAssertTrue(FileManager.default.fileExists(atPath: decision.path))
        XCTAssertEqual(gate.completedExecutions, 1)
        let text = try String(contentsOf: decision, encoding: .utf8)
        XCTAssertTrue(text.contains("qa-confirm"))
        XCTAssertFalse(text.contains("APPROVE"))
    }

    private func repoRoot() throws -> URL {
        let source = URL(fileURLWithPath: #filePath)
        let root = source
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        guard FileManager.default.fileExists(atPath: root.appendingPathComponent("src/runspecimen").path) else {
            throw XCTSkip("Repository root was not next to the test source.")
        }
        return root
    }

    private func pythonExecutable(in root: URL) throws -> URL {
        let bundled = root.appendingPathComponent(".tools/python/bin/python3.11")
        if FileManager.default.isExecutableFile(atPath: bundled.path) {
            return bundled
        }
        let system = URL(fileURLWithPath: "/usr/bin/python3")
        if FileManager.default.isExecutableFile(atPath: system.path) {
            return system
        }
        throw XCTSkip("No Python executable is available for the workflow command.")
    }
}
