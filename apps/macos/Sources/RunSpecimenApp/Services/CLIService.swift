import Foundation

/// Minimum CLI the native app expects (PyPI 0.2.0rc9+ / matching repo tree).
enum CLIVersionGate {
    /// Comparable tuple: (major, minor, patch, preKind, preNum)
    /// preKind: 0 = rc/a/b, 1 = final (no pre-release). Higher is newer.
    static let minimum = ParsedVersion(major: 0, minor: 2, patch: 0, preKind: 0, preNum: 9)

    struct ParsedVersion: Comparable, Equatable, Sendable {
        var major: Int
        var minor: Int
        var patch: Int
        /// 0 = pre-release (rc/a/b), 1 = final
        var preKind: Int
        var preNum: Int

        static func < (lhs: ParsedVersion, rhs: ParsedVersion) -> Bool {
            let l = [lhs.major, lhs.minor, lhs.patch, lhs.preKind, lhs.preNum]
            let r = [rhs.major, rhs.minor, rhs.patch, rhs.preKind, rhs.preNum]
            return l.lexicographicallyPrecedes(r)
        }

        var displayMinimum: String { "0.2.0rc9" }
    }

    static func parse(from versionOutput: String) -> ParsedVersion? {
        // Accept "runspecimen 0.2.0rc9", "0.2.0rc9", "0.2.0-rc.9", "0.2.0"
        let lowered = versionOutput.lowercased()
        let pattern = #"(\d+)\.(\d+)\.(\d+)(?:[-.]?(?:rc|a|b|alpha|beta)\.?(\d+))?"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        let range = NSRange(lowered.startIndex..<lowered.endIndex, in: lowered)
        guard let match = regex.firstMatch(in: lowered, range: range) else { return nil }

        func group(_ i: Int) -> String? {
            let r = match.range(at: i)
            guard r.location != NSNotFound, let swift = Range(r, in: lowered) else { return nil }
            return String(lowered[swift])
        }

        guard let major = Int(group(1) ?? ""),
              let minor = Int(group(2) ?? ""),
              let patch = Int(group(3) ?? "") else { return nil }

        if let pre = group(4), let preNum = Int(pre) {
            return ParsedVersion(major: major, minor: minor, patch: patch, preKind: 0, preNum: preNum)
        }
        return ParsedVersion(major: major, minor: minor, patch: patch, preKind: 1, preNum: 0)
    }

    static func evaluate(versionOutput: String) -> Result<ParsedVersion, AppError> {
        guard let parsed = parse(from: versionOutput) else {
            return .failure(AppError(
                message: "Could not parse runspecimen version from:\n\(versionOutput)\nInstall 0.2.0rc9 or newer."
            ))
        }
        if parsed < minimum {
            return .failure(AppError(
                message: "CLI too old (\(versionOutput.trimmingCharacters(in: .whitespacesAndNewlines))). Need \(minimum.displayMinimum)+. Install: python3 -m pip install 'runspecimen==0.2.0rc9'"
            ))
        }
        return .success(parsed)
    }
}

/// Invokes the user-selected (or PATH-discovered) `runspecimen` binary.
/// Does not weaken engine gates: mutating commands go through the real CLI.
actor CLIService {
    private(set) var cliURL: URL?
    /// Tracked dashboard child so we can terminate it on app quit (App Store 2.4.5(iii)).
    private var dashboardProcess: Process?

    func setCLI(_ url: URL?) {
        cliURL = url
    }

    /// Broad discovery for Developer ID / local debug. MAS builds still prefer Open-panel bookmarks.
    func resolveFromPATH() -> URL? {
        let fileManager = FileManager.default
        var candidates: [URL] = []

        let path = ProcessInfo.processInfo.environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        for dir in path.split(separator: ":") {
            candidates.append(URL(fileURLWithPath: String(dir)).appendingPathComponent("runspecimen"))
        }

        let home = fileManager.homeDirectoryForCurrentUser
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
        let version = output.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        guard version.lowercased().contains("runspecimen") || version.contains(".") else {
            throw AppError(message: "Selected binary did not report a RunSpecimen version:\n\(version)")
        }
        switch CLIVersionGate.evaluate(versionOutput: version) {
        case .failure(let err):
            throw err
        case .success:
            break
        }
        return CLIIdentity(path: url, version: version)
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
                "--contract", contract.path,
                "--open"
            ]
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

    func requireCLI() throws -> URL {
        guard let cliURL else {
            throw AppError(
                message: "runspecimen CLI not selected. Use “Select runspecimen CLI” (Open panel) or install 0.2.0rc9+: python3 -m pip install 'runspecimen==0.2.0rc9'"
            )
        }
        let fm = FileManager.default
        guard fm.isExecutableFile(atPath: cliURL.path) else {
            throw AppError(
                message: "runspecimen CLI is missing or not executable at:\n\(cliURL.path)\nRe-select it via Open panel, or reinstall 0.2.0rc9+."
            )
        }
        return cliURL
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
                    process.executableURL = url
                    process.arguments = arguments
                    process.environment = Self.augmentedEnvironment()

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
        let url = try requireCLI()
        let process = Process()
        process.executableURL = url
        process.arguments = arguments
        process.environment = Self.augmentedEnvironment()
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.standardInput = FileHandle.nullDevice
        // New process group so stopDashboard can signal the whole tree.
        process.qualityOfService = .utility
        try process.run()
        dashboardProcess = process
    }

    private static func augmentedEnvironment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        let home = NSHomeDirectory()
        let extras = [
            "\(home)/.local/bin",
            "\(home)/Library/Python/3.14/bin",
            "\(home)/Library/Python/3.13/bin",
            "\(home)/Library/Python/3.12/bin",
            "\(home)/Library/Python/3.11/bin",
            "\(home)/.pyenv/shims",
            "/opt/homebrew/bin",
            "/usr/local/bin"
        ]
        let path = env["PATH"] ?? "/usr/bin:/bin"
        env["PATH"] = (extras + [path]).joined(separator: ":")
        // No telemetry knobs to set; keep engine local-only.
        return env
    }
}
