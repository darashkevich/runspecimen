import AppKit
import CryptoKit
import Darwin
import Foundation
import LocalAuthentication
import ServiceManagement
import SwiftUI

/// Separate Developer ID product. Registers an embedded SMAppService.daemon.
/// Does not modify the Mac App Store app. Root/admin can still defeat the holder.

@main
struct RunSpecimenHolderApp: App {
    @State private var statusText = "Starting…"
    @State private var detail = ""

    private let daemonPlist = "com.darashkevich.runspecimen.holder.daemon.plist"
    private let custody = UserSessionKeyCustody()
    private let holderClient = HolderSessionClient()
    @State private var callerId = ""
    @State private var callerSecret = ""
    @State private var companionURL = ""
    @State private var pairingToken = ""
    @State private var pendingPhone: IssuedDeviceChallenge?

    var body: some Scene {
        WindowGroup("RunSpecimen Holder") {
            VStack(alignment: .leading, spacing: 12) {
                Text("RunSpecimen Holder")
                    .font(.title)
                Text(statusText)
                    .font(.headline)
                Text(detail)
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                Text("Mechanism: SMAppService.daemon. State is root-owned. A same-user process must not rewrite enrollment, policy, nonces, or leases. Administrator or root can still defeat this holder. This is not human-only execution and not Store parity. An origin string is not production trust. E2 is not closed. A biometric press does not finish missing implementation. The local button reaches the holder over authenticated IPC. The Observe screen returns the phone signature. A root-owned install is still unbuilt.")
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                TextField("Holder caller id", text: $callerId)
                TextField("Holder caller secret", text: $callerSecret)
                TextField("Observe companion URL", text: $companionURL)
                TextField("Observe pairing token", text: $pairingToken)
                Button("Enroll with Secure Enclave") {
                    enrollLocalFromPerson()
                }
                Button("Sign with session key") {
                    signReloadedFromPerson()
                }
                Button("Enroll paired phone") {
                    enrollPhoneFromPerson()
                }
                Button("Accept phone signature") {
                    acceptPhoneFromPerson()
                }
                Button("Cancel phone challenge") {
                    cancelPhoneFromPerson()
                }
            }
            .padding(24)
            .frame(minWidth: 520, minHeight: 280)
            .onAppear(perform: registerDaemon)
        }
    }

    /// The local control creates the OS key and enrolls it over authenticated IPC.
    /// The Secure Enclave constructor runs only inside this button action.
    private func enrollLocalFromPerson() {
        do {
            let held = try LiveSecureEnclaveKeyMaker().makeSessionKey()
            custody.keep(held)
            let client = try authenticatedClient()
            let issued = try client.issueChallenge(role: "mac")
            let signature = try held.sign(issued.bound)
            let receipt = try client.enrollLocal(
                publicKey: held.publicKey,
                accessPolicy: held.accessPolicy,
                issued: issued,
                signature: signature
            )
            statusText = "Holder verified the local key over IPC. E2 is not closed."
            detail = "\(receipt). access=\(held.accessPolicy). A biometric press does not finish missing implementation. A root-owned install is still unbuilt."
        } catch {
            statusText = "Secure Enclave enrollment was not completed"
            detail = "\(error)"
        }
    }

    /// Later signature after restart. Reloads the keychain handle, then signs the new challenge.
    private func signReloadedFromPerson() {
        do {
            let client = try authenticatedClient()
            let issued = try client.issueChallenge(role: "mac")
            let signature = try LiveSecureEnclaveKeyMaker().reloadAndSign(issued.bound)
            let receipt = try client.submit(
                role: "mac",
                publicKey: try LiveSecureEnclaveKeyMaker().reloadPublicKey(),
                issued: issued,
                signature: signature
            )
            statusText = "Holder verified the reloaded session key. E2 is not closed."
            detail = receipt
        } catch {
            statusText = "Reloaded session signature was not completed"
            detail = "\(error)"
        }
    }

    /// Publishes a holder-issued challenge to RunSpecimenObserve. It does not enroll.
    private func enrollPhoneFromPerson() {
        do {
            let client = try authenticatedClient()
            let issued = try client.issuePhoneChallenge()
            try ObserveMailbox.publish(
                issued: issued,
                baseURL: companionURL,
                pairingToken: pairingToken
            )
            pendingPhone = issued
            statusText = "Paired phone challenge is published to RunSpecimenObserve."
            detail = "challenge=\(issued.challenge.count) bytes on /v1/phone-peer-challenge. A local key was not created. The signature is accepted only after P-256 verification and the challenge is consumed. E2 is not closed. A root-owned install is still unbuilt."
        } catch {
            statusText = "Paired phone enrollment was not completed"
            detail = "\(error)"
        }
    }

    private func acceptPhoneFromPerson() {
        do {
            guard let issued = pendingPhone else { throw HolderEnrollmentError.staleChallenge }
            let submission = try ObserveMailbox.collect(baseURL: companionURL, pairingToken: pairingToken)
            guard submission.challenge == issued.challengeBase64 else {
                throw HolderEnrollmentError.tamperedChallenge
            }
            let receipt = try authenticatedClient().submit(
                role: "phone",
                publicKeyBase64: submission.publicKey,
                issued: issued,
                signatureBase64: submission.signature
            )
            pendingPhone = nil
            statusText = "Holder verified the phone signature and consumed the challenge. E2 is not closed."
            detail = receipt
        } catch {
            statusText = "Paired phone enrollment was not completed"
            detail = "\(error)"
        }
    }

    private func cancelPhoneFromPerson() {
        do {
            guard let issued = pendingPhone else { throw HolderEnrollmentError.staleChallenge }
            try authenticatedClient().cancel(role: "phone")
            pendingPhone = nil
            statusText = "Phone challenge was cancelled. It was not enrolled."
            detail = "nonce=\(issued.nonce)"
        } catch {
            statusText = "Phone challenge was not cancelled"
            detail = "\(error)"
        }
    }

    private func authenticatedClient() throws -> HolderSessionClient {
        try holderClient.authenticate(callerId: callerId, callerSecret: callerSecret)
        return holderClient
    }

    private func registerDaemon() {
        let service = SMAppService.daemon(plistName: daemonPlist)
        do {
            try service.register()
        } catch {
            let ns = error as NSError
            // kSMErrorAlreadyRegistered ~= already present
            if !(ns.domain == "SMAppServiceErrorDomain" && ns.code == 1) {
                statusText = "Registration error"
                detail = "\(error)"
                return
            }
        }
        switch service.status {
        case .enabled:
            statusText = "Daemon enabled"
            detail = "SMAppService status: enabled\nBundle: \(Bundle.main.bundleIdentifier ?? "?")"
        case .requiresApproval:
            statusText = "Waiting for System Settings approval"
            detail = """
            Open System Settings → General → Login Items & Extensions.
            Allow “RunSpecimen Holder” Background Items (or Login Items).
            An admin password prompt may appear — enter it yourself; the agent will not.
            Bundle: \(Bundle.main.bundleIdentifier ?? "?")
            """
        case .notRegistered:
            statusText = "Not registered"
            detail = "SMAppService status: notRegistered"
        case .notFound:
            statusText = "Daemon plist not found in bundle"
            detail = "Expected Contents/Library/LaunchDaemons/\(daemonPlist)"
        @unknown default:
            statusText = "Unknown SMAppService status"
            detail = "raw=\(service.status.rawValue)"
        }
    }
}

enum BiometricAccessPolicy {
    /// Each later signature with the live key requires the current biometric set.
    /// Unattended code does not evaluate this policy and does not prompt.
    static let eachSignature = "biometry-current-set-on-each-signature"
}

struct SessionHeldKey {
    let role: String
    let publicKey: Data
    let accessPolicy: String
    let sign: (Data) throws -> Data
}

final class UserSessionKeyCustody {
    private var keys: [String: SessionHeldKey] = [:]

    func keep(_ key: SessionHeldKey) {
        keys[key.role] = key
    }

    func sign(role: String, message: Data) throws -> Data {
        guard let key = keys[role] else { throw HolderEnrollmentError.missingCustody }
        guard key.accessPolicy == BiometricAccessPolicy.eachSignature else {
            throw HolderEnrollmentError.policyRefused
        }
        return try key.sign(message)
    }
}

protocol HolderSecureEnclaveKeyMaking {
    func makeSessionKey() throws -> SessionHeldKey
}

struct LiveSecureEnclaveKeyMaker: HolderSecureEnclaveKeyMaking {
    func makeSessionKey() throws -> SessionHeldKey {
        var error: Unmanaged<CFError>?
        guard let access = SecAccessControlCreateWithFlags(
            kCFAllocatorDefault,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            [.privateKeyUsage, .biometryCurrentSet],
            &error
        ) else {
            throw HolderEnrollmentError.policyRefused
        }
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            accessControl: access,
            authenticationContext: LAContext()
        )
        let publicKey = key.publicKey.x963Representation
        try key.dataRepresentation.write(to: Self.handleURL, options: .atomic)
        try publicKey.write(to: Self.publicURL, options: .atomic)
        return SessionHeldKey(
            role: "mac",
            publicKey: publicKey,
            accessPolicy: BiometricAccessPolicy.eachSignature,
            sign: { message in
                try key.signature(for: message).rawRepresentation
            }
        )
    }

    func reloadPublicKey() throws -> Data {
        guard FileManager.default.fileExists(atPath: Self.publicURL.path) else {
            throw HolderEnrollmentError.missingCustody
        }
        return try Data(contentsOf: Self.publicURL)
    }

    /// Loads the keychain representation and signs. The prompt is on this call, not on enrollment.
    func reloadAndSign(_ message: Data) throws -> Data {
        let token = try Data(contentsOf: Self.handleURL)
        let key = try SecureEnclave.P256.Signing.PrivateKey(dataRepresentation: token)
        return try key.signature(for: message).rawRepresentation
    }

    private static var handleURL: URL {
        support.appendingPathComponent("mac-session-handle")
    }

    private static var publicURL: URL {
        support.appendingPathComponent("mac-session-public")
    }

    private static var support: URL {
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let directory = root.appendingPathComponent("RunSpecimenHolder", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }
}

enum HolderEnrollmentError: Error {
    case emptyKey
    case policyRefused
    case missingCustody
    case localKeyIsNotPhone
    case missingCaller
    case ipcFailed
    case staleChallenge
    case tamperedChallenge
    case observeUnavailable
}

struct IssuedDeviceChallenge {
    var role: String
    var nonce: String
    var expiry: Int
    var generation: Int
    var holderId: String
    var challenge: Data
    var challengeBase64: String
    var bound: Data
}

protocol HolderSessionEnrolling {
    func enrollLocal(publicKey: Data, accessPolicy: String, issued: IssuedDeviceChallenge, signature: Data) throws -> String
    func issuePhoneChallenge() throws -> IssuedDeviceChallenge
}

final class HolderSessionClient: HolderSessionEnrolling {
    private let socketPath = "/Library/Application Support/com.darashkevich.runspecimen.holder/holder.sock"
    private var callerId = ""
    private var callerSecret = ""

    func authenticate(callerId: String, callerSecret: String) throws {
        let id = callerId.trimmingCharacters(in: .whitespacesAndNewlines)
        let secret = callerSecret.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !id.isEmpty, secret.count >= 32 else { throw HolderEnrollmentError.missingCaller }
        self.callerId = id
        self.callerSecret = secret
    }

    func issueChallenge(role: String) throws -> IssuedDeviceChallenge {
        let body = try transact(["op": "issue-device-challenge", "role": role])
        guard
            let nonce = body["nonce"] as? String,
            let expiry = jsonInt(body["expiry"]),
            let generation = jsonInt(body["generation"]),
            let holderId = body["holder_id"] as? String,
            let challengeB64 = body["challenge"] as? String,
            let boundB64 = body["bound"] as? String,
            let challenge = Data(base64Encoded: challengeB64),
            let bound = Data(base64Encoded: boundB64),
            body["enrolled"] as? Bool == false
        else { throw HolderEnrollmentError.ipcFailed }
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

    func enrollLocal(
        publicKey: Data,
        accessPolicy: String,
        issued: IssuedDeviceChallenge,
        signature: Data
    ) throws -> String {
        guard accessPolicy == BiometricAccessPolicy.eachSignature, !publicKey.isEmpty else {
            throw HolderEnrollmentError.policyRefused
        }
        return try submit(role: "mac", publicKey: publicKey, issued: issued, signature: signature)
    }

    func issuePhoneChallenge() throws -> IssuedDeviceChallenge {
        try issueChallenge(role: "phone")
    }

    func submit(role: String, publicKey: Data, issued: IssuedDeviceChallenge, signature: Data) throws -> String {
        try submit(
            role: role,
            publicKeyBase64: publicKey.base64EncodedString(),
            issued: issued,
            signatureBase64: signature.base64EncodedString()
        )
    }

    func submit(
        role: String,
        publicKeyBase64: String,
        issued: IssuedDeviceChallenge,
        signatureBase64: String
    ) throws -> String {
        let body = try transact([
            "op": "submit-device-signature",
            "role": role,
            "public_key": publicKeyBase64,
            "signature": signatureBase64,
            "holder_id": issued.holderId,
            "generation": issued.generation,
            "expiry": issued.expiry,
            "nonce": issued.nonce,
            "challenge": issued.challengeBase64,
        ])
        guard body["verified"] as? Bool == true, body["consumed"] as? Bool == true else {
            throw HolderEnrollmentError.ipcFailed
        }
        guard body["hardware"] as? Bool == false else { throw HolderEnrollmentError.policyRefused }
        return "verified \(role) consumed \(issued.nonce)"
    }

    func cancel(role: String) throws {
        let body = try transact(["op": "cancel-device-challenge", "role": role])
        guard body["cancelled"] as? Bool == true, body["enrolled"] as? Bool == false else {
            throw HolderEnrollmentError.staleChallenge
        }
    }

    private func transact(_ body: [String: Any]) throws -> [String: Any] {
        guard !callerId.isEmpty, !callerSecret.isEmpty else { throw HolderEnrollmentError.missingCaller }
        let sealed = try seal(body)
        let frame = Data((canonicalJSON(sealed) + "\n").utf8)
        let response = try socketExchange(frame)
        guard let object = try JSONSerialization.jsonObject(with: response) as? [String: Any] else {
            throw HolderEnrollmentError.ipcFailed
        }
        if object["ok"] as? Bool == false {
            throw HolderEnrollmentError.ipcFailed
        }
        guard let inner = object["body"] as? [String: Any] else { throw HolderEnrollmentError.ipcFailed }
        return inner
    }

    private func seal(_ body: [String: Any]) throws -> [String: Any] {
        let covered: [String: Any] = ["body": body, "caller_id": callerId, "protocol": 1]
        let mac = try hmacHex(canonicalJSON(covered))
        return ["body": body, "caller_id": callerId, "mac": mac, "protocol": 1]
    }

    private func hmacHex(_ text: String) throws -> String {
        guard let key = dataFromHex(callerSecret) else { throw HolderEnrollmentError.missingCaller }
        let code = HMAC<SHA256>.authenticationCode(for: Data(text.utf8), using: SymmetricKey(data: key))
        return code.map { String(format: "%02x", $0) }.joined()
    }

    private func socketExchange(_ frame: Data) throws -> Data {
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        if fd < 0 { throw HolderEnrollmentError.ipcFailed }
        defer { close(fd) }
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        let path = socketPath
        guard path.utf8.count < 104 else { throw HolderEnrollmentError.ipcFailed }
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
        if connected != 0 { throw HolderEnrollmentError.ipcFailed }
        let sent = frame.withUnsafeBytes { raw -> Int in
            guard let base = raw.baseAddress else { return -1 }
            return send(fd, base, frame.count, 0)
        }
        if sent != frame.count { throw HolderEnrollmentError.ipcFailed }
        var buffer = Data()
        var chunk = [UInt8](repeating: 0, count: 4096)
        while true {
            let count = recv(fd, &chunk, chunk.count, 0)
            if count <= 0 { break }
            buffer.append(contentsOf: chunk.prefix(count))
            if buffer.contains(10) { break }
        }
        guard let end = buffer.firstIndex(of: 10), end > 0 else { throw HolderEnrollmentError.ipcFailed }
        return buffer.prefix(end)
    }
}

enum ObserveMailbox {
    static func publish(issued: IssuedDeviceChallenge, baseURL: String, pairingToken: String) throws {
        let payload: [String: Any] = [
            "challenge_id": issued.nonce,
            "generation": issued.generation,
            "holder_id": issued.holderId,
            "challenge": issued.challengeBase64,
            "expiry": issued.expiry,
            "role": "phone",
        ]
        _ = try request(baseURL: baseURL, pairingToken: pairingToken, path: "/v1/phone-peer-challenge", method: "POST", payload: payload)
    }

    static func collect(baseURL: String, pairingToken: String) throws -> (challenge: String, publicKey: String, signature: String) {
        let body = try request(baseURL: baseURL, pairingToken: pairingToken, path: "/v1/phone-peer-signature", method: "GET", payload: nil)
        guard
            let challenge = body["challenge"] as? String,
            let publicKey = body["public_key"] as? String,
            let signature = body["signature"] as? String,
            body["verified"] as? Bool == false
        else { throw HolderEnrollmentError.staleChallenge }
        return (challenge, publicKey, signature)
    }

    private static func request(
        baseURL: String,
        pairingToken: String,
        path: String,
        method: String,
        payload: [String: Any]?
    ) throws -> [String: Any] {
        let root = baseURL.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard pairingToken.count >= 16, let url = URL(string: root + path) else {
            throw HolderEnrollmentError.observeUnavailable
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("Bearer \(pairingToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let payload {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let semaphore = DispatchSemaphore(value: 0)
        var result: Result<[String: Any], Error>?
        URLSession.shared.dataTask(with: request) { data, response, error in
            defer { semaphore.signal() }
            if let error {
                result = .failure(error)
                return
            }
            guard let http = response as? HTTPURLResponse, let data else {
                result = .failure(HolderEnrollmentError.observeUnavailable)
                return
            }
            if http.statusCode == 409 {
                result = .failure(HolderEnrollmentError.staleChallenge)
                return
            }
            guard (200 ..< 300).contains(http.statusCode),
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else {
                result = .failure(HolderEnrollmentError.observeUnavailable)
                return
            }
            result = .success(object)
        }.resume()
        semaphore.wait()
        switch result {
        case let .success(body):
            return body
        case let .failure(error):
            throw error
        case .none:
            throw HolderEnrollmentError.observeUnavailable
        }
    }
}

func canonicalJSON(_ value: Any) -> String {
    switch value {
    case let object as [String: Any]:
        let parts = object.keys.sorted().map { key in
            "\"\(key)\":\(canonicalJSON(object[key]!))"
        }
        return "{\(parts.joined(separator: ","))}"
    case let text as String:
        let escaped = text
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        return "\"\(escaped)\""
    case let number as Int:
        return String(number)
    case let number as NSNumber:
        return number.stringValue
    default:
        return "null"
    }
}

func jsonInt(_ value: Any?) -> Int? {
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
