import Darwin
import Foundation

/// Runs a child process while both output pipes are drained on other threads.
///
/// Waiting for exit before reading either pipe deadlocks once the child writes
/// more than the pipe buffer. Bytes past `byteLimit` are discarded so the child
/// can still exit. The child is created in its own process group. Timeout and
/// cancellation signal that group, including after the leader has exited.
/// The caller's process group is never signaled. A child that ignores SIGTERM
/// cannot hold this call open.
public enum BoundedProcessCapture {
    public static let defaultTerminationGrace: TimeInterval = 0.5

    public struct Output: Equatable, Sendable {
        public var exitCode: Int32
        public var stdout: Data
        public var stderr: Data
        public var stdoutTruncated: Bool
        public var stderrTruncated: Bool
        public var timedOut: Bool
        public var cancelled: Bool
        public var cleanupFailed: Bool = false
        /// Set when a pipe read fails. Zero is end of stream, not an error.
        /// `EINTR` is retried and does not set this.
        public var streamReadError: Int32? = nil
    }

    /// What one `read` result means. A short positive count is data, not EOF.
    public enum ReadDisposition: Equatable {
        case data
        case end
        case retry
        case failed(Int32)
    }

    public static func readDisposition(count: Int, errorNumber: Int32) -> ReadDisposition {
        if count > 0 {
            return .data
        }
        if count == 0 {
            return .end
        }
        if errorNumber == EINTR {
            return .retry
        }
        return .failed(errorNumber)
    }

    /// Applies injected read results in order. Used by tests and mirrored by the live drain.
    public static func reduceReads(_ reads: [StagedRead]) -> (data: Data, error: Int32?) {
        var data = Data()
        for read in reads {
            switch readDisposition(count: read.count, errorNumber: read.errorNumber) {
            case .data:
                let available = read.bytes.prefix(read.count)
                data.append(available)
            case .end:
                return (data, nil)
            case .retry:
                continue
            case .failed(let code):
                return (data, code)
            }
        }
        return (data, nil)
    }

    public struct StagedRead: Equatable {
        public var count: Int
        public var errorNumber: Int32
        public var bytes: Data

        public init(count: Int, errorNumber: Int32 = 0, bytes: Data = Data()) {
            self.count = count
            self.errorNumber = errorNumber
            self.bytes = bytes
        }
    }

    public enum GroupSignal: Equatable {
        case signaled
        case empty
        case refused
        case failed
    }

    public static func run(
        executable: URL,
        arguments: [String],
        environment: [String: String]? = nil,
        currentDirectory: URL? = nil,
        byteLimit: Int = 8 * 1024 * 1024,
        timeout: TimeInterval? = nil,
        terminationGrace: TimeInterval = defaultTerminationGrace,
        readyMarker: Data? = nil,
        readyDeadline: TimeInterval = 5,
        isCancelled: @escaping @Sendable () -> Bool = { false }
    ) throws -> Output {
        let pipes = try openPipes()
        let stdoutBuffer = ByteBuffer(limit: byteLimit)
        let stderrBuffer = ByteBuffer(limit: byteLimit)
        let readers = DispatchGroup()
        let stdoutHandle = FileHandle(fileDescriptor: pipes.stdoutRead, closeOnDealloc: true)
        let stderrHandle = FileHandle(fileDescriptor: pipes.stderrRead, closeOnDealloc: true)
        drain(stdoutHandle, into: stdoutBuffer, group: readers)
        drain(stderrHandle, into: stderrBuffer, group: readers)

        let pid: pid_t
        do {
            pid = try spawn(
                executable: executable,
                arguments: arguments,
                environment: environment,
                currentDirectory: currentDirectory,
                stdoutRead: pipes.stdoutRead,
                stdoutWrite: pipes.stdoutWrite,
                stderrRead: pipes.stderrRead,
                stderrWrite: pipes.stderrWrite
            )
        } catch {
            Darwin.close(pipes.stdoutWrite)
            Darwin.close(pipes.stderrWrite)
            try? stdoutHandle.close()
            try? stderrHandle.close()
            _ = readers.wait(timeout: .now() + 1)
            throw error
        }
        Darwin.close(pipes.stdoutWrite)
        Darwin.close(pipes.stderrWrite)
        guard let ownedPgid = verifiedOwnedGroup(pid) else {
            _ = kill(pid, SIGKILL)
            _ = reapPid(pid, limit: 1)
            try? stdoutHandle.close()
            try? stderrHandle.close()
            _ = readers.wait(timeout: .now() + 1)
            throw EngineReportError(message: "Could not establish an owned process group.")
        }

        var timedOut = false
        var cancelled = false
        var alreadyReaped: Int32?
        let startup = Date()
        // A nil marker arms the timeout immediately. A marker holds the timeout
        // and cancellation until the child has printed it, so a slow start
        // cannot be mistaken for an ignored signal.
        var armed: Date? = readyMarker == nil ? startup : nil
        while alreadyReaped == nil {
            if let status = tryReap(pid) {
                alreadyReaped = status
                break
            }
            if armed == nil {
                if let readyMarker, stdoutBuffer.contains(readyMarker) {
                    armed = Date()
                } else if Date().timeIntervalSince(startup) >= readyDeadline {
                    _ = stopOwnedGroup(ownedPgid, grace: max(0, terminationGrace))
                    _ = reapPid(pid, limit: max(0, terminationGrace))
                    try? stdoutHandle.close()
                    try? stderrHandle.close()
                    _ = readers.wait(timeout: .now() + 1)
                    throw EngineReportError(message: "The child was not ready before the startup deadline.")
                } else {
                    Thread.sleep(forTimeInterval: 0.01)
                    continue
                }
            }
            if isCancelled() {
                cancelled = true
                break
            }
            if let timeout, let armed, Date().timeIntervalSince(armed) >= timeout {
                timedOut = true
                break
            }
            Thread.sleep(forTimeInterval: 0.01)
        }
        var cleanupFailed = false
        if timedOut || cancelled {
            let stopped = stopOwnedGroup(ownedPgid, grace: max(0, terminationGrace))
            cleanupFailed = stopped.failed
            if alreadyReaped == nil {
                alreadyReaped = stopped.status
            }
        }
        let exitCode = alreadyReaped ?? reapPid(pid, limit: max(0, terminationGrace))
        if readers.wait(timeout: .now() + 2) == .timedOut {
            try? stdoutHandle.close()
            try? stderrHandle.close()
            _ = readers.wait(timeout: .now() + 1)
        }

        let stdout = stdoutBuffer.snapshot()
        let stderr = stderrBuffer.snapshot()
        return Output(
            exitCode: exitCode,
            stdout: stdout.data,
            stderr: stderr.data,
            stdoutTruncated: stdout.truncated,
            stderrTruncated: stderr.truncated,
            timedOut: timedOut,
            cancelled: cancelled,
            cleanupFailed: cleanupFailed,
            streamReadError: stdout.readError ?? stderr.readError
        )
    }

    /// True when `pgid` is a group this process may signal.
    ///
    /// The caller's own group and init are never signalable. A recorded group
    /// stays signalable after its leader exits; membership is not re-derived
    /// from a dead pid.
    public static func groupIsSignalable(_ pgid: pid_t) -> Bool {
        pgid > 1 && pgid != getpgrp()
    }

    public static func classifyGroupSignal(rc: Int32, errorNumber: Int32) -> GroupSignal {
        if rc == 0 {
            return .signaled
        }
        if errorNumber == ESRCH {
            return .empty
        }
        return .failed
    }

    /// SIGTERM, then SIGKILL the owned group even if the leader has exited.
    ///
    /// A zombie leader is reaped before the final membership check so it is not
    /// reported as a surviving descendant. `failed` is true when a member may
    /// still be alive or the signal was refused.
    private static func stopOwnedGroup(_ pgid: pid_t, grace: TimeInterval) -> (failed: Bool, status: Int32?) {
        var status: Int32?
        let terminated = signalOwnedGroup(pgid: pgid, signal: SIGTERM)
        if terminated == .refused {
            return (true, nil)
        }
        if terminated == .empty || waitUntilGroupEmpty(pgid, limit: grace, leaderStatus: &status) {
            return (false, status)
        }
        let killed = signalOwnedGroup(pgid: pgid, signal: SIGKILL)
        if killed == .refused || killed == .failed {
            return (true, status)
        }
        _ = waitUntilGroupEmpty(pgid, limit: grace, leaderStatus: &status)
        return (groupHasMembers(pgid), status)
    }

    static func signalOwnedGroup(pgid: pid_t, signal: Int32) -> GroupSignal {
        guard groupIsSignalable(pgid) else { return .refused }
        let rc = kill(-pgid, signal)
        if rc == 0 {
            return .signaled
        }
        return classifyGroupSignal(rc: rc, errorNumber: errno)
    }

    private static func groupHasMembers(_ pgid: pid_t) -> Bool {
        switch signalOwnedGroup(pgid: pgid, signal: 0) {
        case .signaled:
            return true
        case .empty:
            return false
        case .refused, .failed:
            return true
        }
    }

    private static func waitUntilGroupEmpty(
        _ pgid: pid_t,
        limit: TimeInterval,
        leaderStatus: inout Int32?
    ) -> Bool {
        let deadline = Date().addingTimeInterval(limit)
        while Date() < deadline {
            collectLeader(pgid, into: &leaderStatus)
            if !groupHasMembers(pgid) {
                return true
            }
            Thread.sleep(forTimeInterval: 0.01)
        }
        collectLeader(pgid, into: &leaderStatus)
        return !groupHasMembers(pgid)
    }

    private static func collectLeader(_ pgid: pid_t, into status: inout Int32?) {
        guard status == nil else { return }
        if case .exited(let code) = pollPid(pgid) {
            status = code
        }
    }

    private static func verifiedOwnedGroup(_ pid: pid_t) -> pid_t? {
        guard pid > 1, getpgid(pid) == pid, pid != getpgrp() else { return nil }
        return pid
    }

    private struct PipePair {
        var stdoutRead: Int32
        var stdoutWrite: Int32
        var stderrRead: Int32
        var stderrWrite: Int32
    }

    private static func openPipes() throws -> PipePair {
        var stdout = [Int32](repeating: -1, count: 2)
        var stderr = [Int32](repeating: -1, count: 2)
        let outOK = stdout.withUnsafeMutableBufferPointer { pipe($0.baseAddress) == 0 }
        let errOK = stderr.withUnsafeMutableBufferPointer { pipe($0.baseAddress) == 0 }
        guard outOK, errOK else {
            stdout.forEach { if $0 >= 0 { Darwin.close($0) } }
            stderr.forEach { if $0 >= 0 { Darwin.close($0) } }
            throw EngineReportError(message: "Could not create output pipes.")
        }
        return PipePair(
            stdoutRead: stdout[0], stdoutWrite: stdout[1],
            stderrRead: stderr[0], stderrWrite: stderr[1]
        )
    }

    /// The child is born in its own process group. A later `setpgid` is not used.
    private static func spawn(
        executable: URL,
        arguments: [String],
        environment: [String: String]?,
        currentDirectory: URL?,
        stdoutRead: Int32,
        stdoutWrite: Int32,
        stderrRead: Int32,
        stderrWrite: Int32
    ) throws -> pid_t {
        var actions: posix_spawn_file_actions_t?
        var attr: posix_spawnattr_t?
        guard posix_spawn_file_actions_init(&actions) == 0 else {
            throw EngineReportError(message: "Could not prepare the child process.")
        }
        defer { posix_spawn_file_actions_destroy(&actions) }
        guard posix_spawnattr_init(&attr) == 0 else {
            throw EngineReportError(message: "Could not prepare the child process.")
        }
        defer { posix_spawnattr_destroy(&attr) }
        guard posix_spawnattr_setflags(&attr, Int16(POSIX_SPAWN_SETPGROUP)) == 0,
              posix_spawnattr_setpgroup(&attr, 0) == 0 else {
            throw EngineReportError(message: "Could not request a new process group.")
        }
        if let currentDirectory {
            guard currentDirectory.path.withCString({ posix_spawn_file_actions_addchdir_np(&actions, $0) }) == 0 else {
                throw EngineReportError(message: "Could not set the child working directory.")
            }
        }
        guard posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null", O_RDONLY, 0) == 0,
              posix_spawn_file_actions_adddup2(&actions, stdoutWrite, STDOUT_FILENO) == 0,
              posix_spawn_file_actions_adddup2(&actions, stderrWrite, STDERR_FILENO) == 0,
              posix_spawn_file_actions_addclose(&actions, stdoutRead) == 0,
              posix_spawn_file_actions_addclose(&actions, stdoutWrite) == 0,
              posix_spawn_file_actions_addclose(&actions, stderrRead) == 0,
              posix_spawn_file_actions_addclose(&actions, stderrWrite) == 0 else {
            throw EngineReportError(message: "Could not attach the child output pipes.")
        }

        var argv = cStrings([executable.path] + arguments)
        defer { freeCStrings(argv) }
        let envp = environment.map { cStrings($0.map { "\($0.key)=\($0.value)" }.sorted()) }
        defer { if let envp { freeCStrings(envp) } }

        var pid: pid_t = 0
        let rc: Int32 = executable.path.withCString { path in
            argv.withUnsafeMutableBufferPointer { argvBuf in
                if let envp {
                    var envCopy = envp
                    return envCopy.withUnsafeMutableBufferPointer { envBuf in
                        posix_spawn(&pid, path, &actions, &attr, argvBuf.baseAddress, envBuf.baseAddress)
                    }
                }
                return posix_spawn(&pid, path, &actions, &attr, argvBuf.baseAddress, nil)
            }
        }
        guard rc == 0, pid > 1 else {
            throw EngineReportError(message: "Could not start the child process.")
        }
        return pid
    }

    private static func cStrings(_ values: [String]) -> [UnsafeMutablePointer<CChar>?] {
        values.map { strdup($0) } + [nil]
    }

    private static func freeCStrings(_ values: [UnsafeMutablePointer<CChar>?]) {
        for pointer in values {
            free(pointer)
        }
    }

    private enum Reap {
        case running
        case exited(Int32)
        case lost
    }

    private static func pollPid(_ pid: pid_t) -> Reap {
        var status: Int32 = 0
        let rc = waitpid(pid, &status, WNOHANG)
        if rc == pid {
            return .exited(statusCode(status))
        }
        if rc < 0 && errno == ECHILD {
            return .lost
        }
        return .running
    }

    private static func tryReap(_ pid: pid_t) -> Int32? {
        if case .exited(let status) = pollPid(pid) {
            return status
        }
        return nil
    }

    /// Reaps the leader. Returns -1 if it is still alive after `limit`.
    private static func reapPid(_ pid: pid_t, limit: TimeInterval) -> Int32 {
        let deadline = Date().addingTimeInterval(limit)
        while Date() < deadline {
            switch pollPid(pid) {
            case .exited(let status):
                return status
            case .lost:
                return -1
            case .running:
                Thread.sleep(forTimeInterval: 0.01)
            }
        }
        if case .exited(let status) = pollPid(pid) {
            return status
        }
        DispatchQueue.global(qos: .utility).async {
            var status: Int32 = 0
            _ = waitpid(pid, &status, 0)
        }
        return -1
    }

    private static func statusCode(_ status: Int32) -> Int32 {
        let waited = status & 0x7f
        if waited == 0 {
            return (status >> 8) & 0xff
        }
        if waited != 0x7f {
            return waited
        }
        return -1
    }

    /// One `read` returns the bytes already in the pipe. Filling a 64 KiB
    /// buffer would hide a short readiness line until the child exits.
    private static func drain(_ handle: FileHandle, into buffer: ByteBuffer, group: DispatchGroup) {
        group.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            defer { group.leave() }
            let fd = handle.fileDescriptor
            var storage = [UInt8](repeating: 0, count: 65_536)
            while true {
                let outcome = storage.withUnsafeMutableBytes { raw -> (Int, Int32) in
                    guard let base = raw.baseAddress else { return (-1, EFAULT) }
                    let count = Darwin.read(fd, base, raw.count)
                    return (count, count < 0 ? errno : 0)
                }
                switch readDisposition(count: outcome.0, errorNumber: outcome.1) {
                case .data:
                    buffer.append(Data(storage.prefix(outcome.0)))
                case .end:
                    return
                case .retry:
                    continue
                case .failed(let code):
                    buffer.noteReadFailure(code)
                    return
                }
            }
        }
    }
}

public struct EngineReportError: Error, Equatable, CustomStringConvertible, Sendable {
    public var message: String

    public var description: String { message }

    public init(message: String) {
        self.message = message
    }
}

/// Turns a captured engine run into a JSON object.
///
/// Truncation, a non-object body, timeout, and cancellation are errors.
/// A truncated buffer is never decoded as an empty success.
public enum EngineReportDecoder {
    public struct JSONPayload {
        public var object: [String: Any]
        public var pretty: String
    }

    public static func jsonPayload(from output: BoundedProcessCapture.Output) throws -> JSONPayload {
        if output.cleanupFailed {
            throw EngineReportError(message: "The engine stopped, but an owned descendant was still running.")
        }
        if let code = output.streamReadError {
            throw EngineReportError(message: "The engine output could not be read (errno \(code)).")
        }
        if output.timedOut {
            throw EngineReportError(message: "The engine timed out before it finished.")
        }
        if output.cancelled {
            throw EngineReportError(message: "The engine was cancelled before it finished.")
        }
        if output.stdoutTruncated || output.stderrTruncated {
            throw EngineReportError(message: "Output was truncated. The report is incomplete.")
        }
        if output.exitCode != 0 {
            let stderr = String(data: output.stderr, encoding: .utf8) ?? ""
            let stdout = String(data: output.stdout, encoding: .utf8) ?? ""
            let message = stderr.isEmpty ? stdout : stderr
            throw EngineReportError(
                message: message.isEmpty ? "The engine failed (exit \(output.exitCode))." : message
            )
        }
        guard let object = (try? JSONSerialization.jsonObject(with: output.stdout)) as? [String: Any] else {
            throw EngineReportError(message: "The engine report was not a complete JSON object.")
        }
        let pretty: String
        if let data = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys]),
           let text = String(data: data, encoding: .utf8) {
            pretty = text
        } else {
            pretty = String(data: output.stdout, encoding: .utf8) ?? ""
        }
        return JSONPayload(object: object, pretty: pretty)
    }
}

private final class ByteBuffer: @unchecked Sendable {
    private let lock = NSLock()
    private var storage = Data()
    private var didTruncate = false
    private var readError: Int32?
    private let limit: Int

    init(limit: Int) {
        self.limit = max(0, limit)
    }

    func contains(_ marker: Data) -> Bool {
        guard !marker.isEmpty else { return true }
        lock.lock()
        defer { lock.unlock() }
        return storage.range(of: marker) != nil
    }

    func append(_ data: Data) {
        lock.lock()
        defer { lock.unlock() }
        guard !didTruncate else { return }
        let room = limit - storage.count
        if room <= 0 {
            didTruncate = true
            return
        }
        if data.count <= room {
            storage.append(data)
        } else {
            storage.append(data.prefix(room))
            didTruncate = true
        }
    }

    func noteReadFailure(_ code: Int32) {
        lock.lock()
        defer { lock.unlock() }
        if readError == nil {
            readError = code
        }
    }

    func snapshot() -> (data: Data, truncated: Bool, readError: Int32?) {
        lock.lock()
        defer { lock.unlock() }
        return (storage, didTruncate, readError)
    }
}
