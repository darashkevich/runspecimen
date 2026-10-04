import XCTest
@testable import HolderSocket

final class HolderSocketClientTests: XCTestCase {
    private let secret = String(repeating: "ab", count: 32)

    func testForgedResponseMacIsRefused() async throws {
        let path = try makeSocket()
        let client = try await client(path)
        let server = FrameServer(path: path)
        let mac = String(repeating: "00", count: 32)
        server.start { _, _ in
            "{\"body\":{\"ok\":true,\"request_id\":\"x\"},\"caller_id\":\"holder\",\"mac\":\"\(mac)\",\"protocol\":1}"
        }
        defer { server.stop() }
        do {
            _ = try await client.transact(["op": "ping"], deadline: 2)
            XCTFail("forged mac was accepted")
        } catch HolderSocketError.unauthenticated {
        }
    }

    func testTamperedResponseBodyIsRefused() async throws {
        let path = try makeSocket()
        let client = try await client(path)
        let server = FrameServer(path: path)
        server.start { request, sealer in
            let sealed = try sealer(request)
            return sealed.replacingOccurrences(of: "\"ok\":true", with: "\"ok\":false")
        }
        defer { server.stop() }
        do {
            _ = try await client.transact(["op": "ping"], deadline: 2)
            XCTFail("tampered body was accepted")
        } catch HolderSocketError.unauthenticated {
        }
    }

    func testReplayedResponseIsRefused() async throws {
        let path = try makeSocket()
        let client = try await client(path)
        let server = FrameServer(path: path)
        let box = FrameBox()
        server.start { request, sealer in
            if let saved = box.frame {
                return saved
            }
            let sealed = try sealer(request)
            box.frame = sealed
            return sealed
        }
        defer { server.stop() }
        let first = try await client.transact(["op": "ping"], deadline: 2)
        XCTAssertEqual(first["ok"] as? Bool, true)
        XCTAssertTrue(client.ioOffMainThread)
        do {
            _ = try await client.transact(["op": "ping"], deadline: 2)
            XCTFail("replayed response was accepted")
        } catch HolderSocketError.replayed {
        }
    }

    func testSocketIORunsOffTheMainThreadAndStopsAtTheDeadline() async throws {
        let path = try makeSocket()
        let client = try await client(path)
        let server = FrameServer(path: path)
        server.start { _, _ in
            Thread.sleep(forTimeInterval: 2)
            return #"{"ok":false}"#
        }
        defer { server.stop() }
        let started = Date()
        do {
            _ = try await client.transact(["op": "ping"], deadline: 0.4)
            XCTFail("hanging socket returned")
        } catch HolderSocketError.deadlineExceeded {
        }
        XCTAssertLessThan(Date().timeIntervalSince(started), 1.5)
        XCTAssertTrue(client.ioOffMainThread)
    }

    func testSymlinkEndpointIsRefused() async throws {
        let path = try makeSocket()
        let link = path + ".link"
        try FileManager.default.createSymbolicLink(atPath: link, withDestinationPath: path)
        let client = HolderSocketClient(socketPath: link)
        try client.authenticate(callerId: "app", callerSecret: secret)
        do {
            _ = try await client.transact(["op": "ping"], deadline: 1)
            XCTFail("symlink endpoint was accepted")
        } catch HolderSocketError.endpointRefused {
        }
    }

    func testPartialWriteCompletes() throws {
        var fds: [Int32] = [-1, -1]
        XCTAssertEqual(socketpair(AF_UNIX, SOCK_STREAM, 0, &fds), 0)
        defer {
            close(fds[0])
            close(fds[1])
        }
        let payload = Data(repeating: 0x61, count: 180_000)
        let received = LockedCount()
        let done = DispatchSemaphore(value: 0)
        let reader = Thread {
            var buffer = [UInt8](repeating: 0, count: 1024)
            var total = 0
            while total < payload.count {
                let count = read(fds[0], &buffer, buffer.count)
                if count > 0 { total += count }
                if count <= 0 { break }
            }
            received.set(total)
            done.signal()
        }
        reader.start()
        try writeAll(
            fd: fds[1],
            bytes: payload,
            deadline: Date().addingTimeInterval(5),
            cancelled: { false }
        )
        close(fds[1])
        fds[1] = -1
        XCTAssertEqual(done.wait(timeout: .now() + 5), .success)
        XCTAssertEqual(received.get(), payload.count)
    }

    func testSaturatedBacklogConnectDoesNotBlock() throws {
        let path = try makeSocket()
        let listener = try listenSocket(path, backlog: 1)
        defer { close(listener) }
        var fillers: [Int32] = []
        defer { fillers.forEach { close($0) } }
        var queueFull = false
        var immediateRefusal = false
        for _ in 0..<256 {
            let pending = socket(AF_UNIX, SOCK_STREAM, 0)
            if pending < 0 { break }
            let flags = fcntl(pending, F_GETFL)
            _ = fcntl(pending, F_SETFL, flags | O_NONBLOCK)
            let connected = connectUnix(pending, path)
            if connected == 0 {
                fillers.append(pending)
                continue
            }
            if errno == EINPROGRESS {
                var item = pollfd(fd: pending, events: Int16(POLLOUT), revents: 0)
                let ready = poll(&item, 1, 30)
                fillers.append(pending)
                if ready == 0 {
                    queueFull = true
                    break
                }
                continue
            }
            close(pending)
            queueFull = true
            immediateRefusal = true
            break
        }
        XCTAssertTrue(queueFull, "the listen queue still accepted another connection")
        XCTAssertFalse(fillers.isEmpty)
        let started = Date()
        do {
            _ = try socketExchange(
                Data("backlog\n".utf8),
                path: path,
                deadline: Date().addingTimeInterval(0.8),
                cancelled: { false },
                noteThread: { _ in }
            )
            XCTFail("saturated backlog connected")
        } catch HolderSocketError.deadlineExceeded, HolderSocketError.ipcFailed {
        }
        let limit = immediateRefusal ? 0.5 : 1.5
        XCTAssertLessThan(Date().timeIntervalSince(started), limit)
    }

    func testNonreadingPeerStopsTheWrite() throws {
        let path = try makeSocket()
        let listener = try listenSocket(path, backlog: 1)
        defer { close(listener) }
        var receiveBuffer = 1024
        _ = setsockopt(listener, SOL_SOCKET, SO_RCVBUF, &receiveBuffer, socklen_t(MemoryLayout<Int32>.size))
        let accepted = LockedFD()
        let accepter = Thread {
            var address = sockaddr_un()
            var length = socklen_t(MemoryLayout<sockaddr_un>.size)
            let fd = withUnsafeMutablePointer(to: &address) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    accept(listener, $0, &length)
                }
            }
            if fd >= 0 {
                var tiny = 1024
                _ = setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &tiny, socklen_t(MemoryLayout<Int32>.size))
            }
            accepted.set(fd)
        }
        accepter.start()
        let frame = Data(repeating: 0x61, count: 60_000)
        let started = Date()
        do {
            _ = try socketExchange(
                frame,
                path: path,
                deadline: Date().addingTimeInterval(0.4),
                cancelled: { false },
                noteThread: { _ in }
            )
            XCTFail("nonreading peer accepted the full write")
        } catch HolderSocketError.deadlineExceeded {
        }
        XCTAssertLessThan(Date().timeIntervalSince(started), 1.5)
        let fd = accepted.get()
        var received = 0
        if fd >= 0 {
            var buffer = [UInt8](repeating: 0, count: 4096)
            while true {
                let count = recv(fd, &buffer, buffer.count, MSG_DONTWAIT)
                if count > 0 {
                    received += count
                } else {
                    break
                }
            }
            close(fd)
        }
        XCTAssertLessThan(received, frame.count)
    }

    func testPeerCloseDoesNotRaiseSIGPIPE() throws {
        let path = try makeSocket()
        let listener = try listenSocket(path, backlog: 1)
        defer { close(listener) }
        let outcome = LockedError()
        let done = DispatchSemaphore(value: 0)
        let client = Thread {
            do {
                _ = try socketExchange(
                    Data(repeating: 0x62, count: 80_000),
                    path: path,
                    deadline: Date().addingTimeInterval(2),
                    cancelled: { false },
                    noteThread: { _ in }
                )
                outcome.set(HolderSocketError.ipcFailed)
            } catch let error as HolderSocketError {
                outcome.set(error)
            } catch {
                outcome.set(HolderSocketError.ipcFailed)
            }
            done.signal()
        }
        client.start()
        var address = sockaddr_un()
        var length = socklen_t(MemoryLayout<sockaddr_un>.size)
        let accepted = withUnsafeMutablePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                accept(listener, $0, &length)
            }
        }
        if accepted >= 0 { close(accepted) }
        XCTAssertEqual(done.wait(timeout: .now() + 3), .success)
        XCTAssertEqual(outcome.get(), .peerClosed)
    }

    func testStagedCustodyCommitFailureKeepsThePreviousGeneration() throws {
        let directory = URL(fileURLWithPath: "/private/tmp/rs-qa-bind-custody-\(UUID().uuidString)", isDirectory: true)
        let store = StagedCustodyFiles(directory: directory)
        try store.stage(handle: Data("generation-one-handle".utf8), publicKey: Data("generation-one-public".utf8))
        try store.commit()
        XCTAssertEqual(try store.committedGeneration(), 1)
        try store.rotate(handle: Data("generation-two-handle".utf8), publicKey: Data("generation-two-public".utf8))
        XCTAssertThrowsError(try store.commit(failAfterFirstWrite: true))
        XCTAssertEqual(try store.committedGeneration(), 1)
        XCTAssertEqual(try store.committedHandle(), Data("generation-one-handle".utf8))
        XCTAssertEqual(try store.committedPublicKey(), Data("generation-one-public".utf8))
    }

    func testStagedCustodyRollsBackToThePreviousKey() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let store = StagedCustodyFiles(directory: directory)
        try store.stage(handle: Data("previous-handle".utf8), publicKey: Data("previous-public".utf8))
        try store.commit()
        try store.rotate(handle: Data("next-handle".utf8), publicKey: Data("next-public".utf8))
        store.discard()
        XCTAssertEqual(try store.committedHandle(), Data("previous-handle".utf8))
        XCTAssertEqual(try store.committedPublicKey(), Data("previous-public".utf8))
        try store.revoke()
        XCTAssertThrowsError(try store.committedHandle())
    }

    private func client(_ path: String) async throws -> HolderSocketClient {
        let client = HolderSocketClient(socketPath: path)
        try client.authenticate(callerId: "app", callerSecret: secret)
        return client
    }

    private func makeSocket() throws -> String {
        let path = "/private/tmp/rs-qa-reply-\(UUID().uuidString).sock"
        if FileManager.default.fileExists(atPath: path) {
            try FileManager.default.removeItem(atPath: path)
        }
        return path
    }
}

private final class FrameBox: @unchecked Sendable {
    var frame: String?
}

private func listenSocket(_ path: String, backlog: Int32) throws -> Int32 {
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    if fd < 0 { throw HolderSocketError.ipcFailed }
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)
    let bound = path.withCString { cString in
        withUnsafeMutablePointer(to: &address) { pointer in
            let raw = UnsafeMutableRawPointer(pointer)
            let offset = MemoryLayout.offset(of: \sockaddr_un.sun_path) ?? 0
            strncpy(raw.advanced(by: offset).assumingMemoryBound(to: CChar.self), cString, 103)
            return pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
    }
    if bound != 0 || listen(fd, backlog) != 0 {
        close(fd)
        throw HolderSocketError.ipcFailed
    }
    return fd
}

private func connectUnix(_ fd: Int32, _ path: String) -> Int32 {
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)
    return path.withCString { cString in
        withUnsafeMutablePointer(to: &address) { pointer in
            let raw = UnsafeMutableRawPointer(pointer)
            let offset = MemoryLayout.offset(of: \sockaddr_un.sun_path) ?? 0
            strncpy(raw.advanced(by: offset).assumingMemoryBound(to: CChar.self), cString, 103)
            return pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
    }
}

private final class LockedFD: @unchecked Sendable {
    private let lock = NSLock()
    private var value: Int32 = -1
    func set(_ next: Int32) {
        lock.lock()
        value = next
        lock.unlock()
    }
    func get() -> Int32 {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
}

private final class LockedError: @unchecked Sendable {
    private let lock = NSLock()
    private var value: HolderSocketError?
    func set(_ next: HolderSocketError) {
        lock.lock()
        value = next
        lock.unlock()
    }
    func get() -> HolderSocketError? {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
}

private final class LockedCount: @unchecked Sendable {
    private let lock = NSLock()
    private var value = 0
    func set(_ next: Int) {
        lock.lock()
        value = next
        lock.unlock()
    }
    func get() -> Int {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
}

private final class FrameServer: @unchecked Sendable {
    let path: String
    private var fd: Int32 = -1
    private var thread: Thread?

    init(path: String) {
        self.path = path
    }

    func start(_ reply: @escaping (String, (String) throws -> String) throws -> String) {
        fd = socket(AF_UNIX, SOCK_STREAM, 0)
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        path.withCString { cString in
            withUnsafeMutablePointer(to: &address) { pointer in
                let raw = UnsafeMutableRawPointer(pointer)
                let offset = MemoryLayout.offset(of: \sockaddr_un.sun_path) ?? 0
                strncpy(raw.advanced(by: offset).assumingMemoryBound(to: CChar.self), cString, 103)
                _ = pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
                }
            }
        }
        listen(fd, 8)
        let secret = String(repeating: "ab", count: 32)
        let sealer = HolderSocketClient(socketPath: path)
        thread = Thread {
            while true {
                let client = accept(self.fd, nil, nil)
                if client < 0 { return }
                var buffer = Data()
                var chunk = [UInt8](repeating: 0, count: 4096)
                while !buffer.contains(10) {
                    let count = recv(client, &chunk, chunk.count, 0)
                    if count <= 0 { break }
                    buffer.append(contentsOf: chunk.prefix(count))
                }
                let text = String(data: buffer.prefix(while: { $0 != 10 }), encoding: .utf8) ?? ""
                let response = (try? reply(text) { request in
                    guard let data = request.data(using: .utf8),
                          let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                          let body = object["body"] as? [String: Any]
                    else { return request }
                    let covered: [String: Any] = [
                        "body": ["ok": true, "request_id": body["request_id"] as Any],
                        "caller_id": "holder",
                        "protocol": 1,
                    ]
                    let mac = try sealer.seal(covered["body"] as! [String: Any], callerId: "holder", secret: secret)["mac"] as! String
                    return holderCanonicalJSON([
                        "body": covered["body"] as Any,
                        "caller_id": "holder",
                        "mac": mac,
                        "protocol": 1,
                    ])
                }) ?? #"{"ok":false}"#
                var bytes = Data(response.utf8)
                bytes.append(10)
                bytes.withUnsafeBytes { raw in
                    if let base = raw.baseAddress {
                        _ = send(client, base, bytes.count, 0)
                    }
                }
                close(client)
            }
        }
        thread?.start()
        Thread.sleep(forTimeInterval: 0.05)
    }

    func stop() {
        close(fd)
        try? FileManager.default.removeItem(atPath: path)
    }
}
