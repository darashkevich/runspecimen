import Foundation

/// Runs a child process while both output pipes are drained on other threads.
///
/// Waiting for exit before reading either pipe deadlocks once the child writes
/// more than the pipe buffer. Bytes past `byteLimit` are discarded so the child
/// can still exit, and the call returns after timeout, cancellation, or failure.
public enum BoundedProcessCapture {
    public struct Output: Equatable, Sendable {
        public var exitCode: Int32
        public var stdout: Data
        public var stderr: Data
        public var stdoutTruncated: Bool
        public var stderrTruncated: Bool
        public var timedOut: Bool
        public var cancelled: Bool
    }

    public static func run(
        executable: URL,
        arguments: [String],
        environment: [String: String]? = nil,
        currentDirectory: URL? = nil,
        byteLimit: Int = 8 * 1024 * 1024,
        timeout: TimeInterval? = nil,
        isCancelled: @escaping @Sendable () -> Bool = { false }
    ) throws -> Output {
        let process = Process()
        process.executableURL = executable
        process.arguments = arguments
        if let environment {
            process.environment = environment
        }
        if let currentDirectory {
            process.currentDirectoryURL = currentDirectory
        }
        let outPipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = errPipe
        process.standardInput = FileHandle.nullDevice

        let stdoutBuffer = ByteBuffer(limit: byteLimit)
        let stderrBuffer = ByteBuffer(limit: byteLimit)
        let readers = DispatchGroup()
        drain(outPipe.fileHandleForReading, into: stdoutBuffer, group: readers)
        drain(errPipe.fileHandleForReading, into: stderrBuffer, group: readers)

        try process.run()

        var timedOut = false
        var cancelled = false
        let started = Date()
        while process.isRunning {
            if isCancelled() {
                cancelled = true
                process.terminate()
                break
            }
            if let timeout, Date().timeIntervalSince(started) >= timeout {
                timedOut = true
                process.terminate()
                break
            }
            Thread.sleep(forTimeInterval: 0.01)
        }
        process.waitUntilExit()
        if readers.wait(timeout: .now() + 2) == .timedOut {
            try? outPipe.fileHandleForReading.close()
            try? errPipe.fileHandleForReading.close()
            _ = readers.wait(timeout: .now() + 1)
        }

        let stdout = stdoutBuffer.snapshot()
        let stderr = stderrBuffer.snapshot()
        return Output(
            exitCode: process.terminationStatus,
            stdout: stdout.data,
            stderr: stderr.data,
            stdoutTruncated: stdout.truncated,
            stderrTruncated: stderr.truncated,
            timedOut: timedOut,
            cancelled: cancelled
        )
    }

    private static func drain(_ handle: FileHandle, into buffer: ByteBuffer, group: DispatchGroup) {
        group.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            defer { group.leave() }
            while true {
                do {
                    guard let chunk = try handle.read(upToCount: 65_536), !chunk.isEmpty else { break }
                    buffer.append(chunk)
                } catch {
                    break
                }
            }
        }
    }
}

private final class ByteBuffer: @unchecked Sendable {
    private let lock = NSLock()
    private var storage = Data()
    private var didTruncate = false
    private let limit: Int

    init(limit: Int) {
        self.limit = max(0, limit)
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

    func snapshot() -> (data: Data, truncated: Bool) {
        lock.lock()
        defer { lock.unlock() }
        return (storage, didTruncate)
    }
}
