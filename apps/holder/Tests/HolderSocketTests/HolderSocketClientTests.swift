import CryptoKit
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

    func testRestartAndConcurrentExchangesBothComplete() async throws {
        let firstPath = try makeSocket()
        let first = try await client(firstPath)
        let firstServer = FrameServer(path: firstPath)
        firstServer.start { request, sealer in try sealer(request) }
        let opened = try await first.transact(["op": "ping"], deadline: 2)
        XCTAssertEqual(opened["ok"] as? Bool, true)
        firstServer.stop()
        let restarted = try makeSocket()
        let second = try await client(restarted)
        let secondServer = FrameServer(path: restarted)
        secondServer.start { request, sealer in try sealer(request) }
        defer { secondServer.stop() }
        async let left = second.transact(["op": "left"], deadline: 2)
        async let right = second.transact(["op": "right"], deadline: 2)
        let pair = try await (left, right)
        XCTAssertEqual(pair.0["ok"] as? Bool, true)
        XCTAssertEqual(pair.1["ok"] as? Bool, true)
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
        XCTAssertGreaterThanOrEqual(accepted, 0)
        Thread.sleep(forTimeInterval: 0.05)
        close(accepted)
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

    func testContinueKeepsThePreparedNonce() async throws {
        let transport = RecordingExactTransport()
        let mailbox = RecordingExactMailbox()
        let signer = RecordingMacSigner()
        let coordinator = ExactRunCoordinator()
        let inputs = sampleInputs(policy: "dual")
        let prepared = try await coordinator.prepare(
            policy: "dual",
            workspace: "/tmp/ws",
            files: [["script", String(repeating: "a", count: 64)]],
            binding: ["policy": "dual"],
            inputs: inputs,
            transport: transport,
            mailbox: mailbox
        )
        let issuesAfterPrepare = await coordinator.issueCount
        let shown = await coordinator.displayedBound
        XCTAssertEqual(issuesAfterPrepare, 1)
        XCTAssertEqual(shown, Data("bound-once".utf8))
        XCTAssertEqual(mailbox.publishedNonce, prepared.nonce)
        mailbox.response = BoundPhoneExactSignature(nonce: prepared.nonce, signature: "cGhvbmU")
        let executed = try await coordinator.continueRun(
            now: prepared.expiry,
            inputs: inputs,
            transport: transport,
            mailbox: mailbox,
            signer: signer
        )
        let issuesAfterContinue = await coordinator.issueCount
        XCTAssertEqual(issuesAfterContinue, 1)
        XCTAssertEqual(transport.authorizedNonce, prepared.nonce)
        XCTAssertEqual(transport.executedNonce, prepared.nonce)
        XCTAssertEqual(executed, "executed \(prepared.nonce)")
        XCTAssertEqual(signer.signedMessage, Data("bound-once".utf8))
        XCTAssertEqual(transport.authorizedSignatures["phone"], "cGhvbmU")
    }

    func testContinueRefusesADifferentPhoneNonceExpiryGenerationAndPolicy() async throws {
        let transport = RecordingExactTransport()
        let mailbox = RecordingExactMailbox()
        let coordinator = ExactRunCoordinator()
        let inputs = sampleInputs(policy: "companion")
        let prepared = try await coordinator.prepare(
            policy: "companion",
            workspace: "/tmp/ws",
            files: [["script", String(repeating: "a", count: 64)]],
            binding: [:],
            inputs: inputs,
            transport: transport,
            mailbox: mailbox
        )
        let issues = await coordinator.issueCount
        mailbox.response = BoundPhoneExactSignature(nonce: "other-nonce", signature: "cGhvbmU")
        do {
            _ = try await coordinator.continueRun(now: prepared.expiry, inputs: inputs, transport: transport, mailbox: mailbox, signer: RecordingMacSigner())
            XCTFail("a different phone nonce was accepted")
        } catch ExactRunCoordinatorError.phoneNotBound {
        }
        let issuesAfterWrongNonce = await coordinator.issueCount
        XCTAssertEqual(issuesAfterWrongNonce, issues)
        XCTAssertNil(transport.authorizedNonce)
        mailbox.response = BoundPhoneExactSignature(nonce: prepared.nonce, signature: "cGhvbmU")
        do {
            _ = try await coordinator.continueRun(now: prepared.expiry + 1, inputs: inputs, transport: transport, mailbox: mailbox, signer: RecordingMacSigner())
            XCTFail("an expired challenge continued")
        } catch ExactRunCoordinatorError.expired {
        }
        transport.live = ExactRunLiveSession(policy: prepared.policy, generation: prepared.generation + 1, keyGeneration: prepared.keyGeneration)
        do {
            _ = try await coordinator.continueRun(now: prepared.expiry, inputs: inputs, transport: transport, mailbox: mailbox, signer: RecordingMacSigner())
            XCTFail("a changed generation continued")
        } catch ExactRunCoordinatorError.generationChanged {
        }
        transport.live = ExactRunLiveSession(policy: "local", generation: prepared.generation, keyGeneration: prepared.keyGeneration)
        do {
            _ = try await coordinator.continueRun(now: prepared.expiry, inputs: inputs, transport: transport, mailbox: mailbox, signer: RecordingMacSigner())
            XCTFail("a changed policy continued")
        } catch ExactRunCoordinatorError.policyRefused {
        }
        let issuesAtEnd = await coordinator.issueCount
        XCTAssertEqual(issuesAtEnd, issues)
    }

    func testChangedInputsAndOverlapDoNotAuthorize() async throws {
        let transport = RecordingExactTransport()
        let mailbox = RecordingExactMailbox()
        let coordinator = ExactRunCoordinator()
        let inputs = sampleInputs(policy: "dual")
        let prepared = try await coordinator.prepare(
            policy: "dual",
            workspace: "/tmp/ws",
            files: [["script", String(repeating: "a", count: 64)]],
            binding: [:],
            inputs: inputs,
            transport: transport,
            mailbox: mailbox
        )
        mailbox.response = BoundPhoneExactSignature(nonce: prepared.nonce, signature: "cGhvbmU")
        var changed = inputs
        changed.scriptDigest = String(repeating: "b", count: 64)
        do {
            _ = try await coordinator.continueRun(now: prepared.expiry, inputs: changed, transport: transport, mailbox: mailbox, signer: RecordingMacSigner())
            XCTFail("changed script continued")
        } catch ExactRunCoordinatorError.inputsChanged {
        }
        XCTAssertNil(transport.authorizedNonce)
        await coordinator.invalidate()
        do {
            _ = try await coordinator.continueRun(now: prepared.expiry, inputs: inputs, transport: transport, mailbox: mailbox, signer: RecordingMacSigner())
            XCTFail("an invalidated challenge continued")
        } catch ExactRunCoordinatorError.missingPrepare {
        }
        XCTAssertNil(transport.executedNonce)
        let gate = PrepareGate()
        let holding = HoldingExactTransport(gate: gate, inner: transport)
        let first = Task {
            try await coordinator.prepare(
                policy: "dual",
                workspace: "/tmp/ws",
                files: [["script", String(repeating: "a", count: 64)]],
                binding: [:],
                inputs: inputs,
                transport: holding,
                mailbox: mailbox
            )
        }
        while await gate.entered == false {
            await Task.yield()
        }
        do {
            _ = try await coordinator.prepare(
                policy: "dual",
                workspace: "/tmp/ws",
                files: [["script", String(repeating: "a", count: 64)]],
                binding: [:],
                inputs: inputs,
                transport: transport,
                mailbox: mailbox
            )
            XCTFail("a second prepare overlapped the first")
        } catch ExactRunCoordinatorError.busy {
        }
        await gate.release()
        _ = try await first.value
        let issuesAfterOverlap = await coordinator.issueCount
        XCTAssertEqual(issuesAfterOverlap, 2)
    }

    func testInvalidateDuringCollectDoesNotExecute() async throws {
        let transport = RecordingExactTransport()
        let gate = PrepareGate()
        let mailbox = HoldingExactMailbox(gate: gate)
        let coordinator = ExactRunCoordinator()
        let inputs = sampleInputs(policy: "companion")
        let prepared = try await coordinator.prepare(
            policy: "companion",
            workspace: "/tmp/ws",
            files: [["script", String(repeating: "a", count: 64)]],
            binding: [:],
            inputs: inputs,
            transport: transport,
            mailbox: mailbox
        )
        mailbox.response = BoundPhoneExactSignature(nonce: prepared.nonce, signature: "cGhvbmU")
        let running = Task {
            try await coordinator.continueRun(
                now: prepared.expiry,
                inputs: inputs,
                transport: transport,
                mailbox: mailbox,
                signer: RecordingMacSigner()
            )
        }
        while await gate.entered == false {
            await Task.yield()
        }
        await coordinator.invalidate()
        await gate.release()
        do {
            _ = try await running.value
            XCTFail("collect after invalidation executed")
        } catch ExactRunCoordinatorError.inputsChanged {
        }
        XCTAssertNil(transport.authorizedNonce)
        XCTAssertNil(transport.executedNonce)
    }

    private func sampleInputs(policy: String) -> ExactRunInputs {
        ExactRunInputs(
            policy: policy,
            workspace: "/tmp/ws",
            scriptDigest: String(repeating: "a", count: 64),
            contractHash: String(repeating: "c", count: 64),
            executable: "/tmp/python"
        )
    }

    func testRestartWithoutReenrollmentSignsTheCommittedKey() throws {
        let key = P256.Signing.PrivateKey()
        let directory = URL(fileURLWithPath: "/private/tmp/rs-qa-reload-\(UUID().uuidString)", isDirectory: true)
        let store = StagedCustodyFiles(directory: directory)
        try store.stage(handle: Data("software-handle-not-enclave".utf8), publicKey: key.publicKey.x963Representation)
        try store.commit()
        let source = SoftwareCommittedKey(store: store, key: key)
        let restarted = ReloadingSessionCustody(source: source)
        let message = Data("retained-bound".utf8)
        let signature = try restarted.sign(role: "mac", message: message, enrolledPublicKey: key.publicKey.x963Representation)
        let parsed = try P256.Signing.ECDSASignature(rawRepresentation: signature)
        XCTAssertTrue(key.publicKey.isValidSignature(parsed, for: message))
        XCTAssertEqual(source.signs, 1)
        let other = P256.Signing.PrivateKey()
        XCTAssertThrowsError(
            try restarted.sign(role: "mac", message: message, enrolledPublicKey: other.publicKey.x963Representation)
        ) { error in
            XCTAssertEqual(error as? CustodyReloadError, .identityMismatch)
        }
        XCTAssertEqual(source.signs, 1)
    }

    private func client(_ path: String) async throws -> HolderSocketClient {
        let client = HolderSocketClient(socketPath: path)
        try client.authenticate(callerId: "app", callerSecret: secret)
        return client
    }

    private func makeSocket() throws -> String {
        let path = "/private/tmp/rs-qa-receipt-\(UUID().uuidString).sock"
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

final class RecordingExactTransport: ExactRunTransport {
    var issues = 0
    var live = ExactRunLiveSession(policy: "dual", generation: 3, keyGeneration: 1)
    var authorizedNonce: String?
    var executedNonce: String?
    var authorizedSignatures: [String: String] = [:]

    func issue(
        policy: String,
        workspace: String,
        files: [[String]],
        binding: [String: Any]
    ) async throws -> RetainedExactRun {
        issues += 1
        live = ExactRunLiveSession(policy: policy, generation: 3, keyGeneration: 1)
        return RetainedExactRun(
            nonce: "nonce-kept",
            bound: Data("bound-once".utf8),
            policy: policy,
            generation: 3,
            keyGeneration: 1,
            expiry: 1_700_000_000,
            enrolledMacPublicKey: Data("mac-public".utf8)
        )
    }

    func liveSession() async throws -> ExactRunLiveSession { live }

    func authorize(nonce: String, policy: String, signatures: [String: String]) async throws {
        authorizedNonce = nonce
        authorizedSignatures = signatures
    }

    func execute(nonce: String, signatures: [String: String]) async throws -> String {
        executedNonce = nonce
        return "executed \(nonce)"
    }
}

final class RecordingExactMailbox: ExactRunPhoneMailbox {
    var publishedNonce: String?
    var response = BoundPhoneExactSignature(nonce: "", signature: "")

    func publish(run: RetainedExactRun) async throws {
        publishedNonce = run.nonce
    }

    func collect(nonce: String) async throws -> BoundPhoneExactSignature {
        response
    }
}

actor PrepareGate {
    private var waiters: [CheckedContinuation<Void, Never>] = []
    private(set) var entered = false

    func enter() async {
        entered = true
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func release() {
        let pending = waiters
        waiters = []
        for continuation in pending {
            continuation.resume()
        }
    }
}

final class HoldingExactTransport: ExactRunTransport {
    let gate: PrepareGate
    let inner: RecordingExactTransport
    init(gate: PrepareGate, inner: RecordingExactTransport) {
        self.gate = gate
        self.inner = inner
    }
    func issue(policy: String, workspace: String, files: [[String]], binding: [String: Any]) async throws -> RetainedExactRun {
        await gate.enter()
        return try await inner.issue(policy: policy, workspace: workspace, files: files, binding: binding)
    }
    func liveSession() async throws -> ExactRunLiveSession { try await inner.liveSession() }
    func authorize(nonce: String, policy: String, signatures: [String: String]) async throws {
        try await inner.authorize(nonce: nonce, policy: policy, signatures: signatures)
    }
    func execute(nonce: String, signatures: [String: String]) async throws -> String {
        try await inner.execute(nonce: nonce, signatures: signatures)
    }
}

final class HoldingExactMailbox: ExactRunPhoneMailbox {
    let gate: PrepareGate
    var response = BoundPhoneExactSignature(nonce: "", signature: "")
    init(gate: PrepareGate) { self.gate = gate }
    func publish(run: RetainedExactRun) async throws {}
    func collect(nonce: String) async throws -> BoundPhoneExactSignature {
        await gate.enter()
        return response
    }
}

final class RecordingMacSigner: ReloadedMacSigner {
    var signedMessage = Data()

    func sign(message: Data, enrolledPublicKey: Data) throws -> Data {
        signedMessage = message
        return Data("mac-sig".utf8)
    }
}

final class SoftwareCommittedKey: CommittedCustodySource {
    let store: StagedCustodyFiles
    let key: P256.Signing.PrivateKey
    var signs = 0

    init(store: StagedCustodyFiles, key: P256.Signing.PrivateKey) {
        self.store = store
        self.key = key
    }

    func committedPublicKey() throws -> Data {
        try store.committedPublicKey()
    }

    func sign(message: Data) throws -> Data {
        let committed = try committedPublicKey()
        guard committed == key.publicKey.x963Representation else {
            throw CustodyReloadError.identityMismatch
        }
        signs += 1
        return try key.signature(for: message).rawRepresentation
    }
}
