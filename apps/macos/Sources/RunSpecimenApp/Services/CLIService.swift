import Darwin
import Foundation
#if canImport(RunSpecimenCore)
import RunSpecimenCore
#endif

/// Invokes the user-selected (or bundled / PATH-discovered) `runspecimen` binary.
/// Does not weaken engine gates: mutating commands go through the real CLI.
actor CLIService {
    private(set) var cliURL: URL?
    private(set) var resolutionSource: CLIResolutionSource?
    /// Tracked dashboard child so we can terminate it on app quit (App Store 2.4.5(iii)).
    private var dashboardProcess: Process?

    func setCLI(_ url: URL?, source: CLIResolutionSource) {
        cliURL = url
        resolutionSource = url == nil ? nil : source
    }

    /// Bundled engine under `Contents/Helpers/runspecimen` (ADR-002).
    /// Present only when packaging staged a real helper into the `.app`.
    nonisolated func resolveBundledHelper() -> URL? {
        Self.bundledHelperURL()
    }

    /// Broad discovery for Developer ID / local debug. MAS builds still prefer Open-panel bookmarks.
    nonisolated func resolveFromPATH() -> URL? {
        let fileManager = FileManager.default
        var candidates: [URL] = []

        let path = ProcessInfo.processInfo.environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        for dir in path.split(separator: ":") {
            candidates.append(URL(fileURLWithPath: String(dir)).appendingPathComponent("runspecimen"))
        }

        let home = Self.realHomeDirectory()
        let extras: [String] = [
            ".local/bin/runspecimen",
            "Library/Python/3.14/bin/runspecimen",
            "Library/Python/3.13/bin/runspecimen",
            "Library/Python/3.12/bin/runspecimen",
            "Library/Python/3.11/bin/runspecimen",
            "Library/Python/3.10/bin/runspecimen",
            "Library/Python/3.9/bin/runspecimen",
            ".pyenv/shims/runspecimen",
            "miniconda3/bin/runspecimen",
            "mambaforge/bin/runspecimen",
            "anaconda3/bin/runspecimen"
        ]
        for rel in extras {
            candidates.append(home.appendingPathComponent(rel))
        }
        candidates += [
            URL(fileURLWithPath: "/opt/homebrew/bin/runspecimen"),
            URL(fileURLWithPath: "/usr/local/bin/runspecimen"),
            URL(fileURLWithPath: "/opt/homebrew/opt/python@3.12/bin/runspecimen"),
            URL(fileURLWithPath: "/opt/homebrew/opt/python@3.11/bin/runspecimen")
        ]

        // Deduplicate while preserving order.
        var seen = Set<String>()
        for candidate in candidates {
            let path = candidate.path
            guard !seen.contains(path) else { continue }
            seen.insert(path)
            if fileManager.isExecutableFile(atPath: path) {
                return candidate.resolvingSymlinksInPath()
            }
        }
        return nil
    }

    func version() async throws -> CLIIdentity {
        let url = try requireCLI()
        let output = try await run(arguments: ["--version"], expectJSON: false)
        let version = (output.stdout + "\n" + output.stderr)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if version.lowercased().contains("need python") {
            throw AppError(message: CLIVersionGate.failureMessage(for: .unparseable(raw: version)) ?? version)
        }
        guard version.lowercased().contains("runspecimen") || version.contains(".") else {
            throw AppError(message: "Selected binary did not report a RunSpecimen version:\n\(version)\n(exit \(output.exitCode))")
        }
        let evaluation = CLIVersionGate.evaluate(versionOutput: version)
        if let message = CLIVersionGate.failureMessage(for: evaluation) {
            throw AppError(message: message)
        }
        return CLIIdentity(path: url, version: version, source: resolutionSource ?? .manual)
    }

    func doctor(workspace: URL) async throws -> DoctorReport {
        let data = try await runJSON(arguments: ["doctor", "--workspace", workspace.path])
        let obj = data.object
        return DoctorReport(
            ok: obj["ok"] as? Bool ?? false,
            platform: obj["platform"] as? String ?? "—",
            python: obj["python"] as? String ?? "—",
            workspace: obj["workspace"] as? String ?? workspace.path,
            workspaceWritable: obj["workspace_writable"] as? Bool ?? false,
            workspaceLeaseHeld: obj["workspace_lease_held"] as? Bool ?? false,
            rawJSON: data.pretty
        )
    }

    func status(workspace: URL, campaignID: String, runID: String, contract: URL?) async throws -> RunStatus {
        var args = [
            "status",
            "--workspace", workspace.path,
            "--campaign-id", campaignID,
            "--run-id", runID
        ]
        if let contract {
            args += ["--contract", contract.path]
        }
        let data = try await runJSON(arguments: args)
        let obj = data.object
        let state = obj["state"] as? [String: Any] ?? [:]
        let approval = obj["approval"] as? [String: Any]
        let certificate = obj["certificate"] as? [String: Any]
        let contractInfo = obj["contract"] as? [String: Any]
        let runtime = (state["runtime"] as? [String: Any]) ?? (approval?["runtime"] as? [String: Any])

        let argv: [String]
        if let list = contractInfo?["argv"] as? [String] {
            argv = list
        } else if let list = approval?["argv"] as? [String] {
            argv = list
        } else if let list = state["argv"] as? [String] {
            argv = list
        } else {
            argv = []
        }

        return RunStatus(
            phase: (obj["phase"] as? String) ?? (state["phase"] as? String) ?? "none",
            campaignID: obj["campaign_id"] as? String ?? campaignID,
            runID: obj["run_id"] as? String ?? runID,
            workspace: obj["workspace"] as? String ?? workspace.path,
            eventCount: obj["event_count"] as? Int ?? 0,
            eventChainOK: obj["event_chain_ok"] as? Bool ?? true,
            eventChainMessage: obj["event_chain_msg"] as? String ?? "",
            leaseHeldByOther: (obj["workspace_lease_held_by_other"] as? Bool)
                ?? (obj["lease_held_by_other"] as? Bool)
                ?? false,
            certificateID: certificate?["certificate_id"] as? String,
            eventHead: certificate?["event_head"] as? String,
            approvalExpiresUnix: (approval?["expires_at_unix"] as? Double)
                ?? (state["approval_expires_at_unix"] as? Double),
            argv: argv,
            contractHash: (contractInfo?["hash"] as? String)
                ?? (approval?["contract_hash"] as? String)
                ?? (state["contract_hash"] as? String),
            sourceHash: (approval?["source_hash"] as? String) ?? (state["source_hash"] as? String),
            runtimeID: runtime?["runtime_id"] as? String,
            exitCode: state["exit_code"] as? Int,
            postflightOK: state["postflight_ok"] as? Bool,
            rawJSON: data.pretty
        )
    }

    func validate(workspace: URL, contract: URL) async throws -> String {
        let data = try await runJSON(arguments: [
            "validate",
            "--workspace", workspace.path,
            "--contract", contract.path
        ])
        return data.pretty
    }

    func runLifecycle(
        action: LifecycleAction,
        workspace: URL,
        contract: URL,
        campaignID: String,
        runID: String
    ) async throws -> String {
        precondition(action != .approve, "Approve must use PTYSession")
        var args: [String]
        switch action {
        case .validate:
            args = ["validate", "--workspace", workspace.path, "--contract", contract.path]
        case .preflight:
            args = ["preflight", "--workspace", workspace.path, "--contract", contract.path]
        case .run:
            args = ["run", "--workspace", workspace.path, "--contract", contract.path]
        case .postflight:
            args = ["postflight", "--workspace", workspace.path, "--contract", contract.path]
        case .verify:
            args = [
                "verify",
                "--workspace", workspace.path,
                "--contract", contract.path,
                "--campaign-id", campaignID,
                "--run-id", runID
            ]
        case .dashboard:
            args = [
                "dashboard",
                "--workspace", workspace.path,
                "--contract", contract.path
            ]
            // GUI opens the browser; the MAS e2e harness must not.
            if !MasSandboxE2E.isRequested {
                args.append("--open")
            }
        case .approve:
            args = []
        }
        if action == .dashboard {
            try launchDashboard(arguments: args)
            return "Dashboard launching on loopback (read-only). It cannot approve or execute. It will be stopped when you quit RunSpecimen."
        }
        let result = try await run(arguments: args, expectJSON: false)
        if result.exitCode != 0 {
            throw AppError(message: result.stderr.isEmpty ? result.stdout : result.stderr)
        }
        return result.stdout.isEmpty ? result.stderr : result.stdout
    }

    func isDashboardRunning() -> Bool {
        dashboardProcess?.isRunning == true
    }

    /// Terminate any tracked dashboard child. Signals only that PID (not a process group)
    /// because Foundation.Process inherits the app's group by default.
    func stopDashboard() {
        guard let process = dashboardProcess else { return }
        dashboardProcess = nil
        guard process.isRunning else { return }
        let pid = process.processIdentifier
        process.terminate()
        kill(pid, SIGTERM)
        DispatchQueue.global().asyncAfter(deadline: .now() + 1.5) {
            if process.isRunning {
                kill(pid, SIGKILL)
            }
        }
    }

    /// Synchronous best-effort stop for `applicationWillTerminate` (async Task may not finish).
    nonisolated func stopDashboardSync() {
        DashboardChild.shared.stop()
    }

    func requireCLI() throws -> URL {
        guard let cliURL else {
            throw AppError(
                message: "runspecimen CLI not selected. Use “Select runspecimen CLI” (Open panel), install 0.2.0rc10+, or stage a bundled helper under Contents/Helpers."
            )
        }
        let fm = FileManager.default
        guard fm.isExecutableFile(atPath: cliURL.path) else {
            throw AppError(
                message: "runspecimen CLI is missing or not executable at:\n\(cliURL.path)\nRe-select it via Open panel, or reinstall 0.2.0rc10+."
            )
        }
        return cliURL
    }

    // MARK: - Bundle helper path

    nonisolated static func bundledHelperURL() -> URL? {
        let fm = FileManager.default
        // Prefer Bundle.main when running as .app; fall back to relative layout for tests.
        let candidates: [URL] = {
            var urls: [URL] = []
            if let resourceURL = Bundle.main.resourceURL {
                // PyInstaller onedir lives under Resources (sandbox-safe; Helpers cannot
                // hold unsigned data like base_library.zip next to nested code).
                urls.append(
                    resourceURL.appendingPathComponent("RunSpecimenEngine/runspecimen")
                )
                // Legacy / ADR-002: …/Contents/Resources → …/Contents/Helpers/runspecimen
                urls.append(
                    resourceURL
                        .deletingLastPathComponent()
                        .appendingPathComponent("Helpers/runspecimen")
                )
            }
            if let exe = Bundle.main.executableURL {
                urls.append(
                    exe.deletingLastPathComponent()
                        .deletingLastPathComponent()
                        .appendingPathComponent("Resources/RunSpecimenEngine/runspecimen")
                )
                urls.append(
                    exe.deletingLastPathComponent()
                        .deletingLastPathComponent()
                        .appendingPathComponent("Helpers/runspecimen")
                )
            }
            let bundleURL = Bundle.main.bundleURL
            urls.append(bundleURL.appendingPathComponent("Contents/Resources/RunSpecimenEngine/runspecimen"))
            urls.append(bundleURL.appendingPathComponent("Contents/Helpers/runspecimen"))
            urls.append(bundleURL.appendingPathComponent("Helpers/runspecimen"))
            return urls
        }()

        var seen = Set<String>()
        for url in candidates {
            let path = url.path
            guard !seen.contains(path) else { continue }
            seen.insert(path)
            // Ignore non-executable placeholders (README / .gitkeep copies).
            guard fm.isExecutableFile(atPath: path) else { continue }
            // Refuse obviously tiny stub markers.
            if let attrs = try? fm.attributesOfItem(atPath: path),
               let size = attrs[.size] as? NSNumber,
               size.intValue < 64 {
                continue
            }
            return url.resolvingSymlinksInPath()
        }
        return nil
    }

    // MARK: - Process helpers

    private struct ProcessResult: Sendable {
        var exitCode: Int32
        var stdout: String
        var stderr: String
    }

    private struct JSONPayload {
        var object: [String: Any]
        var pretty: String
    }

    private func runJSON(arguments: [String]) async throws -> JSONPayload {
        let result = try await run(arguments: arguments, expectJSON: true)
        if result.exitCode != 0 {
            throw AppError(message: result.stderr.isEmpty ? result.stdout : result.stderr)
        }
        let raw = result.stdout.data(using: .utf8) ?? Data()
        let obj = (try? JSONSerialization.jsonObject(with: raw)) as? [String: Any] ?? [:]
        let pretty: String
        if let data = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys]),
           let text = String(data: data, encoding: .utf8) {
            pretty = text
        } else {
            pretty = result.stdout
        }
        return JSONPayload(object: obj, pretty: pretty)
    }

    private func run(arguments: [String], expectJSON: Bool) async throws -> ProcessResult {
        let url = try requireCLI()
        return try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    let process = Process()
                    let invocation = Self.processInvocation(for: url, arguments: arguments)
                    process.executableURL = invocation.executable
                    process.arguments = invocation.arguments
                    process.environment = Self.augmentedEnvironment()
                    // Bundled Helpers live next to the launcher; keep cwd stable for relative paths.
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
                    _ = expectJSON
                    continuation.resume(returning: ProcessResult(
                        exitCode: process.terminationStatus,
                        stdout: stdout,
                        stderr: stderr
                    ))
                } catch {
                    continuation.resume(throwing: AppError(message: error.localizedDescription))
                }
            }
        }
    }

    private func launchDashboard(arguments: [String]) throws {
        stopDashboard()
        DashboardChild.shared.stop()
        let url = try requireCLI()
        let process = Process()
        let invocation = Self.processInvocation(for: url, arguments: arguments)
        process.executableURL = invocation.executable
        process.arguments = invocation.arguments
        process.environment = Self.augmentedEnvironment()
        if url.path.contains("/Contents/Helpers/") || url.path.contains("/RunSpecimenEngine/") {
            process.currentDirectoryURL = url.deletingLastPathComponent()
        }
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.standardInput = FileHandle.nullDevice
        process.qualityOfService = .utility
        try process.run()
        dashboardProcess = process
        DashboardChild.shared.attach(process)
    }

    /// Foundation Process + posix_spawn both honor shebangs, but sandbox hosts
    /// sometimes fail to exec a text script as the Mach-O file. Route shell
    /// launchers through `/bin/bash` explicitly while keeping argv paths intact.
    nonisolated static func processInvocation(for cli: URL, arguments: [String]) -> (executable: URL, arguments: [String]) {
        if isShellScript(at: cli) {
            return (
                URL(fileURLWithPath: "/bin/bash"),
                [cli.path] + arguments
            )
        }
        return (cli, arguments)
    }

    nonisolated static func isShellScript(at url: URL) -> Bool {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return false }
        defer { try? handle.close() }
        let prefix = handle.readData(ofLength: 64)
        guard let text = String(data: prefix, encoding: .utf8) else { return false }
        let first = text.split(separator: "\n", maxSplits: 1).first.map(String.init) ?? ""
        return first.hasPrefix("#!") && (
            first.contains("bash") || first.contains("sh") || first.contains("/env")
        )
    }

    nonisolated static func augmentedEnvironment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        let home = Self.realHomeDirectory().path
        let extras = [
            "\(home)/.local/bin",
            "\(home)/Library/Python/3.14/bin",
            "\(home)/Library/Python/3.13/bin",
            "\(home)/Library/Python/3.12/bin",
            "\(home)/Library/Python/3.11/bin",
            "\(home)/.pyenv/shims",
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin"
        ]
        let path = env["PATH"] ?? "/usr/bin:/bin"
        env["PATH"] = (extras + [path]).joined(separator: ":")
        // No telemetry knobs to set; keep engine local-only.
        return env
    }

    /// Sandboxed `NSHomeDirectory()` is the container; PATH probes need the real user home.
    nonisolated static func realHomeDirectory() -> URL {
        if let pw = getpwuid(getuid()), let dir = pw.pointee.pw_dir {
            return URL(fileURLWithPath: String(cString: dir), isDirectory: true)
        }
        return FileManager.default.homeDirectoryForCurrentUser
    }
}

/// Process handle shared with terminate path so dashboard dies even if actor Tasks are cancelled.
final class DashboardChild: @unchecked Sendable {
    static let shared = DashboardChild()
    private let lock = NSLock()
    private var process: Process?

    func attach(_ process: Process) {
        lock.lock()
        self.process = process
        lock.unlock()
    }

    func stop() {
        lock.lock()
        let process = self.process
        self.process = nil
        lock.unlock()
        guard let process, process.isRunning else { return }
        let pid = process.processIdentifier
        process.terminate()
        kill(pid, SIGTERM)
        // Brief wait then force-kill — terminate handlers must be sync and short.
        let deadline = Date().addingTimeInterval(0.8)
        while process.isRunning, Date() < deadline {
            Thread.sleep(forTimeInterval: 0.05)
        }
        if process.isRunning {
            kill(pid, SIGKILL)
        }
    }

    var isRunning: Bool {
        lock.lock()
        defer { lock.unlock() }
        return process?.isRunning == true
    }
}
