import CryptoKit
import Darwin
import Foundation

public let holderSocketMaxFrameBytes = 65_536
public let holderInstalledSocketPath = "/Library/Application Support/com.darashkevich.runspecimen.holder/holder.sock"

public enum HolderSocketError: Error, Equatable {
    case missingCaller
    case ipcFailed
    case unauthenticated
    case unbound
    case replayed
    case endpointRefused
    case peerRefused
    case deadlineExceeded
    case frameTooLarge
    case cancelled
    case peerClosed
    case missingExactRun
}

public struct IssuedDeviceChallenge: Equatable {
    public var role: String
    public var nonce: String
    public var expiry: Int
    public var generation: Int
    public var holderId: String
    public var challenge: Data
    public var challengeBase64: String
    public var bound: Data

    public init(
        role: String,
        nonce: String,
        expiry: Int,
        generation: Int,
        holderId: String,
        challenge: Data,
        challengeBase64: String,
        bound: Data
    ) {
        self.role = role
        self.nonce = nonce
        self.expiry = expiry
        self.generation = generation
        self.holderId = holderId
        self.challenge = challenge
        self.challengeBase64 = challengeBase64
        self.bound = bound
    }
}

public struct PreparedPhoneReceipt: Equatable {
    public var challengeId: String
    public var receipt: Data
    public var macPublicKey: String

    public init(challengeId: String, receipt: Data, macPublicKey: String) {
        self.challengeId = challengeId
        self.receipt = receipt
        self.macPublicKey = macPublicKey
    }
}

public struct SealedPhoneReceipt: Equatable {
    public var challengeId: String
    public var receipt: String
    public var signature: String
    public var macPublicKey: String
    public var phoneFingerprint: String
    public var holderId: String
    public var generation: Int
    public var outcome: String

    public init(
        challengeId: String,
        receipt: String,
        signature: String,
        macPublicKey: String,
        phoneFingerprint: String,
        holderId: String,
        generation: Int,
        outcome: String
    ) {
        self.challengeId = challengeId
        self.receipt = receipt
        self.signature = signature
        self.macPublicKey = macPublicKey
        self.phoneFingerprint = phoneFingerprint
        self.holderId = holderId
        self.generation = generation
        self.outcome = outcome
    }
}

public struct IssuedExactRun: Equatable {
    public var nonce: String
    public var bound: Data
    public var payloadDigest: String
    public var launchArgv: [String]

    public init(nonce: String, bound: Data, payloadDigest: String, launchArgv: [String]) {
        self.nonce = nonce
        self.bound = bound
        self.payloadDigest = payloadDigest
        self.launchArgv = launchArgv
    }
}

/// Sealed key bytes in Application Support. This directory is not the Keychain
/// and it is not the Secure Enclave. Commit replaces the previous files only
/// after the holder accepts the new key.
public struct StagedCustodyFiles {
    public let directory: URL

    public init(directory: URL) {
        self.directory = directory
    }

    public func stage(handle: Data, publicKey: Data) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try handle.write(to: pendingHandle, options: .atomic)
        try publicKey.write(to: pendingPublic, options: .atomic)
    }

    /// One record. A failure after the next-file write leaves the previous generation.
    public func commit(failAfterFirstWrite: Bool = false) throws {
        guard FileManager.default.fileExists(atPath: pendingHandle.path),
              FileManager.default.fileExists(atPath: pendingPublic.path)
        else { throw HolderSocketError.missingExactRun }
        let handle = try Data(contentsOf: pendingHandle)
        let publicKey = try Data(contentsOf: pendingPublic)
        let generation = (try? committedGeneration()).map { $0 + 1 } ?? 1
        let record: [String: Any] = [
            "generation": generation,
            "handle": handle.base64EncodedString(),
            "publicKey": publicKey.base64EncodedString(),
        ]
        let encoded = try JSONSerialization.data(withJSONObject: record)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try encoded.write(to: nextRecordURL, options: .atomic)
        if failAfterFirstWrite {
            throw HolderSocketError.ipcFailed
        }
        if FileManager.default.fileExists(atPath: recordURL.path) {
            _ = try FileManager.default.replaceItemAt(recordURL, withItemAt: nextRecordURL)
        } else {
            try FileManager.default.moveItem(at: nextRecordURL, to: recordURL)
        }
        discard()
    }

    public func discard() {
        try? FileManager.default.removeItem(at: pendingHandle)
        try? FileManager.default.removeItem(at: pendingPublic)
    }

    public func committedGeneration() throws -> Int {
        guard let generation = holderJSONInt(try readRecord()["generation"]) else {
            throw HolderSocketError.ipcFailed
        }
        return generation
    }

    public func committedHandle() throws -> Data {
        try decodedRecordField("handle")
    }

    public func committedPublicKey() throws -> Data {
        try decodedRecordField("publicKey")
    }

    /// Stage a replacement. The previous committed files stay until commit.
    public func rotate(handle: Data, publicKey: Data) throws {
        try stage(handle: handle, publicKey: publicKey)
    }

    public func revoke() throws {
        discard()
        try? FileManager.default.removeItem(at: recordURL)
        try? FileManager.default.removeItem(at: nextRecordURL)
        if FileManager.default.fileExists(atPath: recordURL.path) {
            throw HolderSocketError.ipcFailed
        }
    }

    private var pendingHandle: URL { directory.appendingPathComponent("mac-session-handle.pending") }
    private var pendingPublic: URL { directory.appendingPathComponent("mac-session-public.pending") }
    private var recordURL: URL { directory.appendingPathComponent("custody.json") }
    private var nextRecordURL: URL { directory.appendingPathComponent("custody-next.json") }

    private func readRecord() throws -> [String: Any] {
        let data = try Data(contentsOf: recordURL)
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw HolderSocketError.ipcFailed
        }
        return object
    }

    private func decodedRecordField(_ name: String) throws -> Data {
        guard let text = try readRecord()[name] as? String, let data = Data(base64Encoded: text) else {
            throw HolderSocketError.ipcFailed
        }
        return data
    }
}

public final class HolderSocketClient: @unchecked Sendable {
    public let socketPath: String
    public private(set) var ioOffMainThread = false
    private var callerId = ""
    private var callerSecret = ""
    private var acceptedMacs = Set<String>()
    private let lock = NSLock()

    public init(socketPath: String = holderInstalledSocketPath) {
        self.socketPath = socketPath
    }

    public func authenticate(callerId: String, callerSecret: String) throws {
        let id = callerId.trimmingCharacters(in: .whitespacesAndNewlines)
        let secret = callerSecret.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !id.isEmpty, secret.count >= 32 else { throw HolderSocketError.missingCaller }
        lock.lock()
        self.callerId = id
        self.callerSecret = secret
        lock.unlock()
    }

    public func issueChallenge(role: String, deadline: TimeInterval = 5) async throws -> IssuedDeviceChallenge {
        let body = try await transact(["op": "issue-device-challenge", "role": role], deadline: deadline)
        guard
            let nonce = body["nonce"] as? String,
            let expiry = holderJSONInt(body["expiry"]),
            let generation = holderJSONInt(body["generation"]),
            let holderId = body["holder_id"] as? String,
            let challengeB64 = body["challenge"] as? String,
            let boundB64 = body["bound"] as? String,
            let challenge = Data(base64Encoded: challengeB64),
            let bound = Data(base64Encoded: boundB64),
            body["enrolled"] as? Bool == false
        else { throw HolderSocketError.ipcFailed }
        return IssuedDeviceChallenge(
            role: role,
            nonce: nonce,
            expiry: expiry,
            generation: generation,
            holderId: holderId,
            challenge: challenge,
            challengeBase64: challengeB64,
            bound: bound
        )
    }

    public func enrollLocal(
        publicKey: Data,
        accessPolicy: String,
        issued: IssuedDeviceChallenge,
        signature: Data,
        deadline: TimeInterval = 5
    ) async throws -> String {
        guard accessPolicy == "biometry-current-set-on-each-signature", !publicKey.isEmpty else {
            throw HolderSocketError.ipcFailed
        }
        return try await submit(
            role: "mac",
            publicKeyBase64: publicKey.base64EncodedString(),
            issued: issued,
            signatureBase64: signature.base64EncodedString(),
            deadline: deadline
        )
    }

    public func issuePhoneChallenge(deadline: TimeInterval = 5) async throws -> IssuedDeviceChallenge {
        try await issueChallenge(role: "phone", deadline: deadline)
    }

    public func submit(
        role: String,
        publicKeyBase64: String,
        issued: IssuedDeviceChallenge,
        signatureBase64: String,
        deadline: TimeInterval = 5
    ) async throws -> String {
        let body = try await transact([
            "op": "submit-device-signature",
            "role": role,
            "public_key": publicKeyBase64,
            "signature": signatureBase64,
            "holder_id": issued.holderId,
            "generation": issued.generation,
            "expiry": issued.expiry,
            "nonce": issued.nonce,
            "challenge": issued.challengeBase64,
        ], deadline: deadline)
        guard body["verified"] as? Bool == true, body["consumed"] as? Bool == true else {
            throw HolderSocketError.ipcFailed
        }
        guard body["hardware"] as? Bool == false else { throw HolderSocketError.ipcFailed }
        return "verified \(role) consumed \(issued.nonce)"
    }

    public func cancel(role: String, deadline: TimeInterval = 5) async throws {
        let body = try await transact(["op": "cancel-device-challenge", "role": role], deadline: deadline)
        guard body["cancelled"] as? Bool == true, body["enrolled"] as? Bool == false else {
            throw HolderSocketError.ipcFailed
        }
    }

    public func issueExactRun(
        payloadDigest: String,
        launchArgv: [String],
        deadline: TimeInterval = 5
    ) async throws -> IssuedExactRun {
        guard payloadDigest.count == 64, !launchArgv.isEmpty else { throw HolderSocketError.missingExactRun }
        let body = try await transact([
            "op": "issue-exact-run",
            "payload_digest": payloadDigest,
            "launch_argv": launchArgv,
        ], deadline: deadline)
        guard
            let nonce = body["nonce"] as? String,
            let boundB64 = body["bound"] as? String,
            let bound = Data(base64Encoded: boundB64),
            body["authorized"] as? Bool != true
        else { throw HolderSocketError.ipcFailed }
        return IssuedExactRun(nonce: nonce, bound: bound, payloadDigest: payloadDigest, launchArgv: launchArgv)
    }

    public func authorizeExactRun(
        issued: IssuedExactRun,
        publicKeyBase64: String,
        signatureBase64: String,
        deadline: TimeInterval = 5
    ) async throws -> String {
        let body = try await transact([
            "op": "authorize-exact-run",
            "payload_digest": issued.payloadDigest,
            "launch_argv": issued.launchArgv,
            "nonce": issued.nonce,
            "public_key": publicKeyBase64,
            "signature": signatureBase64,
        ], deadline: deadline)
        guard body["authorized"] as? Bool == true, body["consumed"] as? Bool == true else {
            throw HolderSocketError.ipcFailed
        }
        guard body["hardware"] as? Bool == false else { throw HolderSocketError.ipcFailed }
        return "exact run consumed \(issued.nonce)"
    }

    public func issueSnapshotExactRun(
        policy: String,
        workspace: String,
        files: [[String]],
        binding: [String: Any],
        deadline: TimeInterval = 5
    ) async throws -> RetainedExactRun {
        let rows: [Any] = files.map { [$0[0], $0[1]] as [Any] }
        let body = try await transact([
            "op": "issue-exact-run",
            "policy": policy,
            "workspace": workspace,
            "files": rows,
            "binding": binding,
        ], deadline: deadline)
        guard
            let nonce = body["nonce"] as? String,
            let boundB64 = body["bound"] as? String,
            let bound = Data(base64Encoded: boundB64),
            let generation = holderJSONInt(body["generation"]),
            let keyGeneration = holderJSONInt(body["key_generation"]),
            let expiry = holderJSONInt(body["expiry"]),
            body["authorized"] as? Bool == false,
            body["run_integration_complete"] as? Bool == false
        else { throw HolderSocketError.missingExactRun }
        let enrolledText = body["enrolled_mac_public_key"] as? String ?? ""
        let enrolled = Data(base64Encoded: enrolledText) ?? Data()
        return RetainedExactRun(
            nonce: nonce,
            bound: bound,
            policy: body["policy"] as? String ?? policy,
            generation: generation,
            keyGeneration: keyGeneration,
            expiry: expiry,
            enrolledMacPublicKey: enrolled
        )
    }

    public func exactRunLiveSession(deadline: TimeInterval = 5) async throws -> ExactRunLiveSession {
        let body = try await transact(["op": "session-generation"], deadline: deadline)
        guard
            let generation = holderJSONInt(body["generation"]),
            let keyGeneration = holderJSONInt(body["key_generation"]),
            body["run_integration_complete"] as? Bool == false
        else { throw HolderSocketError.ipcFailed }
        return ExactRunLiveSession(
            policy: body["policy"] as? String ?? "",
            generation: generation,
            keyGeneration: keyGeneration
        )
    }

    public func authorizeSnapshotExactRun(
        nonce: String,
        policy: String,
        signatures: [String: String],
        deadline: TimeInterval = 5
    ) async throws {
        let body = try await transact([
            "op": "authorize-exact-run",
            "nonce": nonce,
            "policy": policy,
            "signatures": signatures,
        ], deadline: deadline)
        guard
            body["authorized"] as? Bool == true,
            body["consumed"] as? Bool == true,
            body["run_integration_complete"] as? Bool == false,
            body["hardware"] as? Bool == false
        else { throw HolderSocketError.ipcFailed }
    }

    public func executeSnapshotExactRun(
        nonce: String,
        signatures: [String: String],
        deadline: TimeInterval = 30
    ) async throws -> String {
        let body = try await transact([
            "op": "execute-exact-run",
            "nonce": nonce,
            "signatures": signatures,
        ], deadline: deadline)
        guard
            body["exit_code"] as? Int == 0,
            body["run_integration_complete"] as? Bool == false,
            body["e2_closed"] as? Bool == false
        else { throw HolderSocketError.ipcFailed }
        return "snapshot execute \(nonce); run_integration_complete false"
    }

    public func preparePhoneReceipt(challengeId: String, deadline: TimeInterval = 5) async throws -> PreparedPhoneReceipt {
        let body = try await transact([
            "op": "prepare-phone-receipt",
            "challenge_id": challengeId,
        ], deadline: deadline)
        guard
            body["verified"] as? Bool == false,
            body["sealed"] as? Bool == false,
            let receiptB64 = body["receipt"] as? String,
            let receipt = Data(base64Encoded: receiptB64),
            let macPublicKey = body["mac_public_key"] as? String
        else { throw HolderSocketError.ipcFailed }
        return PreparedPhoneReceipt(challengeId: challengeId, receipt: receipt, macPublicKey: macPublicKey)
    }

    public func sealPhoneReceipt(
        challengeId: String,
        signatureBase64: String,
        deadline: TimeInterval = 5
    ) async throws -> SealedPhoneReceipt {
        let body = try await transact([
            "op": "seal-phone-receipt",
            "challenge_id": challengeId,
            "signature": signatureBase64,
        ], deadline: deadline)
        guard
            body["sealed"] as? Bool == true,
            body["verified"] as? Bool == true,
            body["enrolled"] as? Bool == false,
            let receipt = body["receipt"] as? String,
            let macPublicKey = body["mac_public_key"] as? String,
            let phoneFingerprint = body["phone_fingerprint"] as? String,
            let holderId = body["holder_id"] as? String,
            let generation = holderJSONInt(body["generation"]),
            let outcome = body["outcome"] as? String
        else { throw HolderSocketError.ipcFailed }
        return SealedPhoneReceipt(
            challengeId: challengeId,
            receipt: receipt,
            signature: signatureBase64,
            macPublicKey: macPublicKey,
            phoneFingerprint: phoneFingerprint,
            holderId: holderId,
            generation: generation,
            outcome: outcome
        )
    }

    public func transact(_ fields: [String: Any], deadline: TimeInterval = 5) async throws -> [String: Any] {
        let requestId = UUID().uuidString
        var body = fields
        body["request_id"] = requestId
        let secret = lockedSecret()
        let caller = lockedCaller()
        guard !caller.isEmpty, !secret.isEmpty else { throw HolderSocketError.missingCaller }
        let sealed = try seal(body, callerId: caller, secret: secret)
        let frame = Data((holderCanonicalJSON(sealed) + "\n").utf8)
        let flag = CancelFlag()
        return try await withTaskCancellationHandler {
            try await Task.detached(priority: .userInitiated) { [socketPath] in
                let response = try socketExchange(
                    frame,
                    path: socketPath,
                    deadline: Date().addingTimeInterval(deadline),
                    cancelled: { flag.cancelled },
                    noteThread: { offMain in
                        self.lock.lock()
                        self.ioOffMainThread = offMain
                        self.lock.unlock()
                    }
                )
                return try self.openAuthenticated(response, requestId: requestId, secret: secret)
            }.value
        } onCancel: {
            flag.cancel()
        }
    }

    public func seal(_ body: [String: Any], callerId: String, secret: String) throws -> [String: Any] {
        let covered: [String: Any] = ["body": body, "caller_id": callerId, "protocol": 1]
        let mac = try hmacHex(holderCanonicalJSON(covered), secret: secret)
        return ["body": body, "caller_id": callerId, "mac": mac, "protocol": 1]
    }

    private func openAuthenticated(_ response: Data, requestId: String, secret: String) throws -> [String: Any] {
        let parsed: Any
        do {
            parsed = try JSONSerialization.jsonObject(with: response)
        } catch {
            throw HolderSocketError.unauthenticated
        }
        guard let object = parsed as? [String: Any] else {
            throw HolderSocketError.unauthenticated
        }
        guard holderJSONInt(object["protocol"]) == 1 else { throw HolderSocketError.unauthenticated }
        guard object["caller_id"] as? String == "holder" else { throw HolderSocketError.unauthenticated }
        guard let mac = object["mac"] as? String, mac.count == 64 else { throw HolderSocketError.unauthenticated }
        var covered = object
        covered.removeValue(forKey: "mac")
        let expected = try hmacHex(holderCanonicalJSON(covered), secret: secret)
        guard expected == mac else { throw HolderSocketError.unauthenticated }
        lock.lock()
        let seen = acceptedMacs.contains(mac)
        if !seen { acceptedMacs.insert(mac) }
        lock.unlock()
        if seen { throw HolderSocketError.replayed }
        guard let body = object["body"] as? [String: Any] else { throw HolderSocketError.unauthenticated }
        guard body["request_id"] as? String == requestId else { throw HolderSocketError.unbound }
        if object["ok"] as? Bool == false || body["ok"] as? Bool == false {
            throw HolderSocketError.ipcFailed
        }
        return body
    }

    private func lockedSecret() -> String {
        lock.lock()
        defer { lock.unlock() }
        return callerSecret
    }

    private func lockedCaller() -> String {
        lock.lock()
        defer { lock.unlock() }
        return callerId
    }

    private func hmacHex(_ text: String, secret: String) throws -> String {
        guard let key = dataFromHex(secret) else { throw HolderSocketError.missingCaller }
        let code = HMAC<SHA256>.authenticationCode(for: Data(text.utf8), using: SymmetricKey(data: key))
        return code.map { String(format: "%02x", $0) }.joined()
    }
}

private final class CancelFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var value = false
    var cancelled: Bool {
        lock.lock()
        defer { lock.unlock() }
        return value
    }
    func cancel() {
        lock.lock()
        value = true
        lock.unlock()
    }
}

func socketExchange(
    _ frame: Data,
    path: String,
    deadline: Date,
    cancelled: () -> Bool,
    noteThread: (Bool) -> Void
) throws -> Data {
    noteThread(!Thread.isMainThread)
    try refuseUnsafeEndpoint(path)
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    if fd < 0 { throw HolderSocketError.ipcFailed }
    defer { close(fd) }
    let flags = fcntl(fd, F_GETFL)
    if flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0 { throw HolderSocketError.ipcFailed }
    var noSignal: Int32 = 1
    if setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &noSignal, socklen_t(MemoryLayout<Int32>.size)) != 0 {
        throw HolderSocketError.ipcFailed
    }
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)
    guard path.utf8.count < 104 else { throw HolderSocketError.endpointRefused }
    let connected: Int32 = path.withCString { cString in
        withUnsafeMutablePointer(to: &address) { pointer in
            let raw = UnsafeMutableRawPointer(pointer)
            let offset = MemoryLayout.offset(of: \sockaddr_un.sun_path) ?? 0
            strncpy(raw.advanced(by: offset).assumingMemoryBound(to: CChar.self), cString, 103)
            return pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
    }
    if connected != 0 && errno != EINPROGRESS && errno != EINTR {
        throw HolderSocketError.ipcFailed
    }
    try waitUntilWritable(fd: fd, deadline: deadline, cancelled: cancelled)
    try requireLocalPeer(fd)
    try writeAll(fd: fd, bytes: frame, deadline: deadline, cancelled: cancelled)
    return try readFrame(fd: fd, deadline: deadline, cancelled: cancelled)
}

func waitUntilWritable(fd: Int32, deadline: Date, cancelled: () -> Bool) throws {
    while true {
        if cancelled() { throw HolderSocketError.cancelled }
        if Date() >= deadline { throw HolderSocketError.deadlineExceeded }
        var item = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
        let remain = Int(deadline.timeIntervalSinceNow * 1000)
        let slice = Int32(min(50, max(1, remain)))
        let ready = poll(&item, 1, slice)
        if ready == 0 { continue }
        if ready < 0 {
            if errno == EINTR { continue }
            throw HolderSocketError.ipcFailed
        }
        var soerr: Int32 = 0
        var length = socklen_t(MemoryLayout<Int32>.size)
        if getsockopt(fd, SOL_SOCKET, SO_ERROR, &soerr, &length) != 0 {
            throw HolderSocketError.ipcFailed
        }
        if soerr == 0 { return }
        if soerr == EPIPE || soerr == ECONNRESET || soerr == ECONNABORTED {
            throw HolderSocketError.peerClosed
        }
        throw HolderSocketError.ipcFailed
    }
}

func refuseUnsafeEndpoint(_ path: String) throws {
    var info = stat()
    if lstat(path, &info) != 0 { throw HolderSocketError.endpointRefused }
    if info.st_mode & S_IFMT == S_IFLNK { throw HolderSocketError.endpointRefused }
    if info.st_mode & S_IFMT != S_IFSOCK { throw HolderSocketError.endpointRefused }
}

func requireLocalPeer(_ fd: Int32) throws {
    var uid: uid_t = 0
    var gid: gid_t = 0
    if getpeereid(fd, &uid, &gid) != 0 { throw HolderSocketError.peerRefused }
    if uid != 0 && uid != getuid() { throw HolderSocketError.peerRefused }
}

func writeAll(fd: Int32, bytes: Data, deadline: Date, cancelled: () -> Bool) throws {
    var sent = 0
    let total = bytes.count
    try bytes.withUnsafeBytes { raw in
        guard let base = raw.baseAddress else { throw HolderSocketError.ipcFailed }
        while sent < total {
            if cancelled() { throw HolderSocketError.cancelled }
            if Date() >= deadline { throw HolderSocketError.deadlineExceeded }
            let count = send(fd, base.advanced(by: sent), total - sent, 0)
            if count > 0 {
                sent += count
                continue
            }
            if count < 0 && (errno == EPIPE || errno == ECONNRESET) {
                throw HolderSocketError.peerClosed
            }
            if count < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                var pollItem = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
                let ready = poll(&pollItem, 1, 50)
                if ready < 0 && errno != EINTR { throw HolderSocketError.ipcFailed }
                if pollItem.revents & Int16(POLLHUP | POLLERR) != 0 {
                    throw HolderSocketError.peerClosed
                }
                continue
            }
            throw HolderSocketError.ipcFailed
        }
    }
}

func readFrame(fd: Int32, deadline: Date, cancelled: () -> Bool) throws -> Data {
    var buffer = Data()
    var chunk = [UInt8](repeating: 0, count: 4096)
    while true {
        if cancelled() { throw HolderSocketError.cancelled }
        if Date() >= deadline { throw HolderSocketError.deadlineExceeded }
        var pollItem = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
        let ready = poll(&pollItem, 1, 50)
        if ready < 0 {
            if errno == EINTR { continue }
            throw HolderSocketError.ipcFailed
        }
        if ready == 0 { continue }
        let count = recv(fd, &chunk, chunk.count, 0)
        if count < 0 {
            if errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK { continue }
            throw HolderSocketError.ipcFailed
        }
        if count == 0 { throw HolderSocketError.peerClosed }
        buffer.append(contentsOf: chunk.prefix(count))
        if buffer.count > holderSocketMaxFrameBytes { throw HolderSocketError.frameTooLarge }
        if let end = buffer.firstIndex(of: 10), end > 0 {
            return buffer.prefix(end)
        }
    }
}

public func holderCanonicalJSON(_ value: Any) -> String {
    if let object = value as? [String: Any] {
        let parts = object.keys.sorted().map { key in
            let rendered = holderCanonicalJSON(object[key] as Any)
            return "\"\(key)\":\(rendered)"
        }
        return "{\(parts.joined(separator: ","))}"
    }
    if let text = value as? String {
        let escaped = text
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        return "\"\(escaped)\""
    }
    if let list = value as? [Any] {
        return "[\(list.map { holderCanonicalJSON($0) }.joined(separator: ","))]"
    }
    if let number = value as? NSNumber {
        if CFGetTypeID(number) == CFBooleanGetTypeID() {
            return number.boolValue ? "true" : "false"
        }
        return number.stringValue
    }
    if let number = value as? Int {
        return String(number)
    }
    return "null"
}

public func holderJSONInt(_ value: Any?) -> Int? {
    if let number = value as? Int { return number }
    if let number = value as? NSNumber { return number.intValue }
    return nil
}

func dataFromHex(_ hex: String) -> Data? {
    guard hex.count.isMultiple(of: 2) else { return nil }
    var data = Data()
    var index = hex.startIndex
    while index < hex.endIndex {
        let next = hex.index(index, offsetBy: 2)
        guard let byte = UInt8(hex[index..<next], radix: 16) else { return nil }
        data.append(byte)
        index = next
    }
    return data
}
