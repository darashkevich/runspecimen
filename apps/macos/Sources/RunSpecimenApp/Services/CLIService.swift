import Foundation

/// Invokes the user-selected (or PATH-discovered) `runspecimen` binary.
/// Does not weaken engine gates: mutating commands go through the real CLI.
actor CLIService {
    private(set) var cliURL: URL?

    func setCLI(_ url: URL?) {
        cliURL = url
    }

    func resolveFromPATH() -> URL? {
        let path = ProcessInfo.processInfo.environment["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        let fileManager = FileManager.default
        for dir in path.split(separator: ":") {
            let candidate = URL(fileURLWithPath: String(dir)).appendingPathComponent("runspecimen")
            if fileManager.isExecutableFile(atPath: candidate.path) {
                return candidate
            }
        }
        // Common user install location when launched from GUI (PATH often minimal).
        let home = fileManager.homeDirectoryForCurrentUser
        let locals = [
            home.appendingPathComponent(".local/bin/runspecimen"),
            URL(fileURLWithPath: "/opt/homebrew/bin/runspecimen"),
            URL(fileURLWithPath: "/usr/local/bin/runspecimen")
        ]
        for candidate in locals where fileManager.isExecutableFile(atPath: candidate.path) {
            return candidate
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
            // Non-blocking launch: dashboard serves until terminated.
            try launchDetached(arguments: args)
            return "Dashboard launching on loopback (read-only). It cannot approve or execute."
        }
        let result = try await run(arguments: args, expectJSON: false)
        if result.exitCode != 0 {
            throw AppError(message: result.stderr.isEmpty ? result.stdout : result.stderr)
        }
        return result.stdout.isEmpty ? result.stderr : result.stdout
    }

    func requireCLI() throws -> URL {
        guard let cliURL else {
            throw AppError(message: "Select the runspecimen CLI in Settings (required for App Sandbox).")
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

    private func launchDetached(arguments: [String]) throws {
        let url = try requireCLI()
        let process = Process()
        process.executableURL = url
        process.arguments = arguments
        process.environment = Self.augmentedEnvironment()
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.standardInput = FileHandle.nullDevice
        try process.run()
    }

    private static func augmentedEnvironment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        let extras = [
            "\(NSHomeDirectory())/.local/bin",
            "/opt/homebrew/bin",
            "/usr/local/bin"
        ]
        let path = env["PATH"] ?? "/usr/bin:/bin"
        env["PATH"] = (extras + [path]).joined(separator: ":")
        // No telemetry knobs to set; keep engine local-only.
        return env
    }
}
