import Foundation
import AppKit
import Darwin
#if canImport(RunSpecimenCore)
import RunSpecimenCore
#endif

/// Positive end-to-end harness for the **actual sandboxed** `.app` + bundled helper.
///
/// Activated only when `RS_MAS_E2E=1` or `--mas-e2e` is present. Writes JSON to
/// `RS_MAS_E2E_OUT` (default: temp) and exits. Never types `APPROVE` for the human.
enum MasSandboxE2E {
    static var isRequested: Bool {
        ProcessInfo.processInfo.environment["RS_MAS_E2E"] == "1"
            || ProcessInfo.processInfo.arguments.contains("--mas-e2e")
    }

    private struct CheckError: Error, CustomStringConvertible {
        let description: String
        init(_ description: String) { self.description = description }
    }

    @MainActor
    static func runAndExit() async {
        NSApplication.shared.setActivationPolicy(.prohibited)

        // Prefer an explicit out path; fall back to Application Support (sandbox-writable).
        let outURL: URL = {
            if let path = ProcessInfo.processInfo.environment["RS_MAS_E2E_OUT"], !path.isEmpty {
                return URL(fileURLWithPath: path)
            }
            let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
                ?? FileManager.default.temporaryDirectory
            let dir = support.appendingPathComponent("RunSpecimenE2E", isDirectory: true)
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            return dir.appendingPathComponent("last-result.json")
        }()

        var checks: [[String: Any]] = []
        var failed = false

        func record(_ name: String, ok: Bool, detail: String = "") {
            var row: [String: Any] = ["name": name, "ok": ok]
            if !detail.isEmpty { row["detail"] = detail }
            checks.append(row)
            if ok {
                fputs("E2E OK: \(name)\(detail.isEmpty ? "" : " — \(detail)")\n", stdout)
            } else {
                failed = true
                fputs("E2E FAIL: \(name) — \(detail)\n", stderr)
            }
        }

        // --- 1) Bundled helper resolves + runs inside parent sandbox ---
        let helper: URL
        do {
            guard let bundled = CLIService.bundledHelperURL() else {
                throw CheckError("bundled RunSpecimenEngine/Helpers runspecimen missing")
            }
            helper = bundled
            let channel = DistributionChannel.current
            guard channel.requiresBundledHelper else {
                throw CheckError("expected MAS channel (requiresBundledHelper); got \(channel.rawValue)")
            }
            let cli = CLIService()
            await cli.setCLI(helper, source: .bundledHelper)
            // Probe via Process capturing stdout+stderr — some hosts print version on stderr.
            let probe = try await runHelper(cli: cli, arguments: ["--version"])
            let versionText = (probe.stdout + "\n" + probe.stderr)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard probe.exitCode == 0, versionText.lowercased().contains("runspecimen") else {
                throw CheckError(
                    "helper --version failed inside sandbox (rc=\(probe.exitCode)): stdout=\(probe.stdout) stderr=\(probe.stderr)"
                )
            }
            guard versionText.contains("0.2.0rc10") else {
                throw CheckError("helper version not rc10: \(versionText)")
            }
            let identity = try await cli.version()
            record(
                "bundled_helper_version",
                ok: true,
                detail: "\(identity.version) channel=\(channel.rawValue) probe=\(versionText)"
            )
        } catch {
            record("bundled_helper_version", ok: false, detail: "\(error)")
            finish(outURL: outURL, checks: checks, failed: true)
            return
        }

        let cli = CLIService()
        await cli.setCLI(helper, source: .bundledHelper)

        // --- 2) Workspace bookmark round-trip (security-scoped) ---
        let fm = FileManager.default
        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "")
        let workParent = fm.temporaryDirectory.appendingPathComponent("rs-mas-e2e-\(stamp)", isDirectory: true)
        let demoURL = workParent.appendingPathComponent("demo", isDirectory: true)
        do {
            try? fm.removeItem(at: workParent)
            try fm.createDirectory(at: workParent, withIntermediateDirectories: true)
            // init-demo requires the path to not exist yet.
            let initOut = try await runHelper(cli: cli, arguments: [
                "init-demo", "--workspace", demoURL.path
            ])
            guard initOut.exitCode == 0 else {
                throw CheckError("init-demo failed: \(initOut.stderr)\(initOut.stdout)")
            }
            let bookmarks = BookmarkStore.shared
            try bookmarks.saveWorkspace(demoURL)
            guard let loaded = bookmarks.loadWorkspace() else {
                throw CheckError("loadWorkspace returned nil after save")
            }
            guard loaded.resolvingSymlinksInPath().path == demoURL.resolvingSymlinksInPath().path else {
                throw CheckError("bookmark path mismatch: \(loaded.path) vs \(demoURL.path)")
            }
            guard bookmarks.startAccessingWorkspace() != nil else {
                throw CheckError("startAccessingWorkspace failed")
            }
            record("workspace_bookmark", ok: true, detail: demoURL.path)
        } catch {
            record("workspace_bookmark", ok: false, detail: "\(error)")
            finish(outURL: outURL, checks: checks, failed: true)
            return
        }

        let contractURL = demoURL.appendingPathComponent("contract.json")
        guard fm.isReadableFile(atPath: contractURL.path) else {
            record("workspace_bookmark", ok: false, detail: "contract.json missing after init-demo")
            finish(outURL: outURL, checks: checks, failed: true)
            return
        }

        // --- 3) Dashboard launch + cleanup (2.4.5(iii)) ---
        do {
            // Use the same runLifecycle path as the UI (omit browser focus under e2e).
            _ = try await cli.runLifecycle(
                action: .dashboard,
                workspace: demoURL,
                contract: contractURL,
                campaignID: "e2e",
                runID: "e2e"
            )
            try await Task.sleep(nanoseconds: 400_000_000)
            let runningBefore = await cli.isDashboardRunning() || DashboardChild.shared.isRunning
            guard runningBefore else {
                throw CheckError("dashboard did not stay running after launch")
            }
            await cli.stopDashboard()
            cli.stopDashboardSync()
            DashboardChild.shared.stop()
            try await Task.sleep(nanoseconds: 900_000_000)
            let runningAfter = await cli.isDashboardRunning() || DashboardChild.shared.isRunning
            guard !runningAfter else {
                throw CheckError("dashboard still running after stopDashboard")
            }
            record("dashboard_cleanup", ok: true, detail: "launched then stopped")
        } catch {
            record("dashboard_cleanup", ok: false, detail: "\(error)")
            DashboardChild.shared.stop()
            await cli.stopDashboard()
            cli.stopDashboardSync()
        }

        // --- 4) Human PTY approval gate — wait; never auto-send APPROVE ---
        do {
            precondition(SecurityBoundary.neverAutoApprove, "SecurityBoundary.neverAutoApprove must be true")

            let approvalDir = demoURL
                .appendingPathComponent(".runspecimen/runs", isDirectory: true)
            // Snapshot any existing approval docs before the gate.
            let beforeApprovals = approvalFiles(under: demoURL)

            final class TranscriptBox: @unchecked Sendable {
                private let lock = NSLock()
                private var text = ""
                func append(_ chunk: String) {
                    lock.lock()
                    text += chunk
                    lock.unlock()
                }
                func snapshot() -> String {
                    lock.lock()
                    defer { lock.unlock() }
                    return text
                }
            }
            let box = TranscriptBox()
            let session = PTYApprovalSession { chunk in
                box.append(chunk)
            }
            try session.start(cli: helper, workspace: demoURL, contract: contractURL)

            // Wait for the interactive prompt without typing APPROVE.
            let deadline = Date().addingTimeInterval(8)
            var sawPrompt = false
            while Date() < deadline {
                let snap = box.snapshot()
                let lowered = snap.lowercased()
                if lowered.contains("approve") || snap.contains("APPROVE") || lowered.contains("type") {
                    sawPrompt = true
                    break
                }
                try await Task.sleep(nanoseconds: 150_000_000)
            }

            // Hold the gate open — human path must wait; we deliberately send nothing.
            try await Task.sleep(nanoseconds: 1_500_000_000)

            let finalTranscript = box.snapshot()

            // Critical: harness must not inject APPROVE (and app must not have done so).
            let sentApprove = finalTranscript
                .components(separatedBy: .newlines)
                .contains { $0.trimmingCharacters(in: .whitespaces) == "APPROVE" }
            // Engine echoes human input; without send, APPROVE must not appear as a lone line
            // after a completed approval. Fresh init-demo has no approval yet.
            let afterApprovals = approvalFiles(under: demoURL)
            let newApprovals = afterApprovals.subtracting(beforeApprovals)

            session.stop()

            if !sawPrompt && finalTranscript.isEmpty {
                throw CheckError("PTY produced no output (helper spawn failed inside sandbox?)")
            }
            if sentApprove {
                throw CheckError("transcript contains lone APPROVE line — auto-send suspected: \(finalTranscript)")
            }
            if !newApprovals.isEmpty {
                throw CheckError("approval file written without human APPROVE: \(newApprovals)")
            }
            // Positive assertion: gate waited (prompt seen OR still interactive / no approval written).
            record(
                "pty_approval_waits_for_human",
                ok: true,
                detail: sawPrompt
                    ? "prompt observed; no APPROVE sent; no approval written"
                    : "no APPROVE sent; no approval written (transcript \(finalTranscript.count) chars)"
            )
            _ = approvalDir
        } catch {
            record("pty_approval_waits_for_human", ok: false, detail: "\(error)")
        }

        BookmarkStore.shared.stopAll()
        finish(outURL: outURL, checks: checks, failed: failed)
    }

    private static func finish(outURL: URL, checks: [[String: Any]], failed: Bool) {
        let payload: [String: Any] = [
            "ok": !failed,
            "channel": DistributionChannel.current.rawValue,
            "checks": checks,
            "note": "Never types APPROVE; Store upload still Yahor-only."
        ]
        if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]),
           let text = String(data: data, encoding: .utf8) {
            // Always emit on stdout so the driver can parse even when sandbox redirects files.
            fputs("E2E_RESULT_JSON_BEGIN\n", stdout)
            fputs(text, stdout)
            fputs("\nE2E_RESULT_JSON_END\n", stdout)
            do {
                try data.write(to: outURL, options: .atomic)
                fputs("E2E wrote \(outURL.path)\n", stdout)
            } catch {
                fputs("E2E file write skipped (\(error)) — stdout JSON is authoritative\n", stdout)
            }
        }
        fflush(stdout)
        fflush(stderr)
        exit(failed ? 1 : 0)
    }

    private struct HelperResult {
        var exitCode: Int32
        var stdout: String
        var stderr: String
    }

    private static func runHelper(cli: CLIService, arguments: [String]) async throws -> HelperResult {
        // Use doctor-style private run via public APIs where possible.
        // init-demo is not on LifecycleAction — spawn Process like CLIService.
            let url = try await cli.requireCLI()
            return try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<HelperResult, Error>) in
                DispatchQueue.global(qos: .userInitiated).async {
                    do {
                        let process = Process()
                        let invocation = CLIService.processInvocation(for: url, arguments: arguments)
                        process.executableURL = invocation.executable
                        process.arguments = invocation.arguments
                        process.environment = CLIService.augmentedEnvironment()
                        if url.path.contains("/Contents/Helpers/") || url.path.contains("/RunSpecimenEngine/") {
                            process.currentDirectoryURL = url.deletingLastPathComponent()
                        }
                        let out = Pipe()
                        let err = Pipe()
                        process.standardOutput = out
                        process.standardError = err
                        process.standardInput = FileHandle.nullDevice
                        try process.run()
                        process.waitUntilExit()
                        let stdout = String(data: out.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                        let stderr = String(data: err.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                        continuation.resume(returning: HelperResult(
                            exitCode: process.terminationStatus,
                            stdout: stdout,
                            stderr: stderr
                        ))
                    } catch {
                        continuation.resume(throwing: error)
                    }
                }
            }
        }

    private static func approvalFiles(under workspace: URL) -> Set<String> {
        let root = workspace.appendingPathComponent(".runspecimen", isDirectory: true)
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: nil
        ) else {
            return []
        }
        var found = Set<String>()
        for case let url as URL in enumerator {
            if url.lastPathComponent == "approval.json" {
                found.insert(url.path)
            }
        }
        return found
    }
}
