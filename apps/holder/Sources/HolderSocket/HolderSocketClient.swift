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

    public func commit() throws {
        guard FileManager.default.fileExists(atPath: pendingHandle.path),
              FileManager.default.fileExists(atPath: pendingPublic.path)
        else { throw HolderSocketError.missingExactRun }
        try replace(pendingHandle, with: handleURL)
        try replace(pendingPublic, with: publicURL)
    }

    public func discard() {
        try? FileManager.default.removeItem(at: pendingHandle)
        try? FileManager.default.removeItem(at: pendingPublic)
    }

    public func committedHandle() throws -> Data {
        guard FileManager.default.fileExists(atPath: handleURL.path) else {
            throw HolderSocketError.ipcFailed
        }
        return try Data(contentsOf: handleURL)
    }

    public func committedPublicKey() throws -> Data {
        guard FileManager.default.fileExists(atPath: publicURL.path) else {
            throw HolderSocketError.ipcFailed
        }
        return try Data(contentsOf: publicURL)
    }

    /// Stage a replacement. The previous committed files stay until commit.
    public func rotate(handle: Data, publicKey: Data) throws {
        try stage(handle: handle, publicKey: publicKey)
    }

    public func revoke() throws {
        discard()
        try? FileManager.default.removeItem(at: handleURL)
        try? FileManager.default.removeItem(at: publicURL)
        if FileManager.default.fileExists(atPath: handleURL.path) {
            throw HolderSocketError.ipcFailed
        }
    }

    private var pendingHandle: URL { directory.appendingPathComponent("mac-session-handle.pending") }
    private var pendingPublic: URL { directory.appendingPathComponent("mac-session-public.pending") }
    private var handleURL: URL { directory.appendingPathComponent("mac-session-handle") }
    private var publicURL: URL { directory.appendingPathComponent("mac-session-public") }

    private func replace(_ source: URL, with destination: URL) throws {
        if FileManager.default.fileExists(atPath: destination.path) {
            _ = try FileManager.default.replaceItemAt(destination, withItemAt: source)
        } else {
            try FileManager.default.moveItem(at: source, to: destination)
        }
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
    if connected != 0 { throw HolderSocketError.ipcFailed }
    try requireLocalPeer(fd)
    try writeAll(fd: fd, bytes: frame, deadline: deadline, cancelled: cancelled)
    return try readFrame(fd: fd, deadline: deadline, cancelled: cancelled)
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
            if count < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                var pollItem = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
                let ready = poll(&pollItem, 1, 50)
                if ready < 0 && errno != EINTR { throw HolderSocketError.ipcFailed }
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
        if count == 0 { throw HolderSocketError.ipcFailed }
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
