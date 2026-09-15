import Foundation
import Darwin

/// Runs `runspecimen approve` attached to a real PTY so the engine's interactive
/// TTY gate (`isatty` on stdin/stdout) remains intact.
///
/// Uses `posix_spawn` + `openpty` (Swift marks `fork()` unavailable).
/// The session never auto-types APPROVE. The human must enter the phrase.
final class PTYApprovalSession: @unchecked Sendable {
    private var masterFD: Int32 = -1
    private var childPID: pid_t = 0
    private let outputHandler: @Sendable (String) -> Void
    private var reader: DispatchSourceRead?

    init(onOutput: @escaping @Sendable (String) -> Void) {
        self.outputHandler = onOutput
    }

    deinit {
        stop()
    }

    func start(cli: URL, workspace: URL, contract: URL) throws {
        stop()

        var master: Int32 = 0
        var slave: Int32 = 0
        guard openpty(&master, &slave, nil, nil, nil) == 0 else {
            throw AppError(message: "Unable to allocate a PTY for interactive approval.")
        }
        masterFD = master

        var actions: posix_spawn_file_actions_t? = nil
        posix_spawn_file_actions_init(&actions)
        defer { posix_spawn_file_actions_destroy(&actions) }

        posix_spawn_file_actions_adddup2(&actions, slave, STDIN_FILENO)
        posix_spawn_file_actions_adddup2(&actions, slave, STDOUT_FILENO)
        posix_spawn_file_actions_adddup2(&actions, slave, STDERR_FILENO)
        posix_spawn_file_actions_addclose(&actions, master)
        posix_spawn_file_actions_addclose(&actions, slave)

        let args = [
            cli.path,
            "approve",
            "--workspace", workspace.path,
            "--contract", contract.path
        ]
        // Shell-script helpers (Contents/Helpers --from-src launcher) must be
        // exec'd via /bin/bash under App Sandbox; Mach-O CLIs spawn directly.
        let spawnPath: String
        let argvStrings: [String]
        if CLIService.isShellScript(at: cli) {
            spawnPath = "/bin/bash"
            argvStrings = ["/bin/bash"] + args
        } else {
            spawnPath = cli.path
            argvStrings = args
        }
        let argv: [UnsafeMutablePointer<CChar>?] = argvStrings.map { strdup($0) } + [nil]
        defer {
            for ptr in argv where ptr != nil {
                free(ptr)
            }
        }

        // Match CLIService PATH so host Python / Homebrew remain discoverable
        // from the PTY child (posix_spawn defaults would drop app-augmented PATH).
        let envMap = CLIService.augmentedEnvironment()
        var envPointers: [UnsafeMutablePointer<CChar>?] = envMap.map { strdup("\($0.key)=\($0.value)") }
        envPointers.append(nil)
        defer {
            for ptr in envPointers where ptr != nil {
                free(ptr)
            }
        }

        var pid: pid_t = 0
        let spawnRC = argv.withUnsafeBufferPointer { argvBuf -> Int32 in
            envPointers.withUnsafeMutableBufferPointer { envBuf -> Int32 in
                guard let argvBase = argvBuf.baseAddress, let envBase = envBuf.baseAddress else {
                    return EINVAL
                }
                return posix_spawn(
                    &pid,
                    spawnPath,
                    &actions,
                    nil,
                    UnsafeMutablePointer(mutating: argvBase),
                    envBase
                )
            }
        }
        close(slave)

        guard spawnRC == 0 else {
            close(master)
            masterFD = -1
            throw AppError(message: "posix_spawn failed for approval PTY (errno \(spawnRC)).")
        }

        childPID = pid
        startReader()
    }

    func send(_ text: String) {
        guard masterFD >= 0 else { return }
        text.withCString { ptr in
            _ = write(masterFD, ptr, strlen(ptr))
        }
    }

    func sendLine(_ text: String) {
        send(text + "\n")
    }

    func stop() {
        reader?.cancel()
        reader = nil
        if masterFD >= 0 {
            close(masterFD)
            masterFD = -1
        }
        if childPID > 0 {
            var status: Int32 = 0
            _ = waitpid(childPID, &status, WNOHANG)
            if kill(childPID, 0) == 0 {
                kill(childPID, SIGTERM)
            }
            childPID = 0
        }
    }

    private func startReader() {
        let fd = masterFD
        let source = DispatchSource.makeReadSource(fileDescriptor: fd, queue: .global(qos: .userInteractive))
        source.setEventHandler { [weak self] in
            var buffer = [UInt8](repeating: 0, count: 4096)
            let count = read(fd, &buffer, buffer.count)
            guard count > 0 else { return }
            let chunk = String(bytes: buffer[0..<count], encoding: .utf8) ?? ""
            self?.outputHandler(chunk)
        }
        reader = source
        source.resume()
    }
}
