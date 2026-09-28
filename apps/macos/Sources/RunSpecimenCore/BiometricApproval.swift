import CryptoKit
import Darwin
import Foundation
import LocalAuthentication
import Security

/// Failure of a local biometric approval check.
///
/// A software signature in tests is not a biometric grant. Nothing in this
/// type treats an authentication-success Boolean as permission to run.
public enum BiometricApprovalError: Error, Equatable, CustomStringConvertible, Sendable {
    case malformed(String)
    case expired
    case tampered
    case replay
    case mismatch
    case unsupportedPolicy

    public var description: String {
        switch self {
        case .malformed(let field):
            return "The biometric approval request is malformed (\(field))."
        case .expired:
            return "The biometric approval expired."
        case .tampered:
            return "The biometric approval signature does not match the pinned key."
        case .replay:
            return "The biometric approval was already consumed."
        case .mismatch:
            return "The biometric approval is not for this run."
        case .unsupportedPolicy:
            return "Only a local biometric policy can be consumed. Companion and dual approval are not available."
        }
    }
}

/// One versioned request. The signature covers these fields and nothing else.
public struct BiometricApprovalRequest: Equatable, Sendable {
    public static let localPolicy = "local"
    public static let version = "RSBA1"

    public var macID: String
    public var workspaceID: String
    public var runID: String
    public var contractSHA256: String
    public var inputsSHA256: String
    public var bounds: String
    public var nonce: String
    public var expiryUnix: Int
    public var keyID: String

    public init(
        macID: String,
        workspaceID: String,
        runID: String,
        contractSHA256: String,
        inputsSHA256: String,
        bounds: String,
        nonce: String,
        expiryUnix: Int,
        keyID: String
    ) {
        self.macID = macID
        self.workspaceID = workspaceID
        self.runID = runID
        self.contractSHA256 = contractSHA256
        self.inputsSHA256 = inputsSHA256
        self.bounds = bounds
        self.nonce = nonce
        self.expiryUnix = expiryUnix
        self.keyID = keyID
    }

    /// Bytes that a key must sign. Field order is fixed. Policy is always local.
    public func canonicalBytes() throws -> Data {
        let fields: [(String, String)] = [
            ("policy", Self.localPolicy),
            ("mac_id", macID),
            ("workspace_id", workspaceID),
            ("run_id", runID),
            ("contract_sha256", contractSHA256),
            ("inputs_sha256", inputsSHA256),
            ("bounds", bounds),
            ("nonce", nonce),
            ("expiry_unix", String(expiryUnix)),
            ("key_id", keyID),
        ]
        var out = Data(Self.version.utf8)
        for (name, value) in fields {
            try Self.validate(name: name, value: value)
            out.append(Self.lengthPrefixed(name))
            out.append(Self.lengthPrefixed(value))
        }
        return out
    }

    private static func validate(name: String, value: String) throws {
        guard !value.isEmpty, !value.contains("\0") else {
            throw BiometricApprovalError.malformed(name)
        }
        if name == "nonce" {
            let hex = CharacterSet(charactersIn: "0123456789abcdef")
            guard (32...64).contains(value.count), value.unicodeScalars.allSatisfy({ hex.contains($0) }) else {
                throw BiometricApprovalError.malformed("nonce")
            }
        }
        if name == "key_id" {
            let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
            guard (1...64).contains(value.count), value.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
                throw BiometricApprovalError.malformed("key_id")
            }
        }
    }

    private static func lengthPrefixed(_ text: String) -> Data {
        let bytes = Data(text.utf8)
        var length = UInt32(bytes.count).bigEndian
        var out = Data(bytes: &length, count: 4)
        out.append(bytes)
        return out
    }
}

struct StoredBiometricApproval: Equatable {
    var canonical: Data
    var signature: Data
    var publicKey: Data
}

/// Stores one signed approval and consumes it once under an exclusive lock.
///
/// The pinned public key is an argument. A record that names a different key
/// is rejected. This store does not start a run.
public enum BiometricApprovalStore {
    public static func submit(
        request: BiometricApprovalRequest,
        signature: Data,
        publicKey: Data,
        pinnedPublicKey: Data,
        directory: URL,
        now: Int
    ) throws {
        guard request.expiryUnix > now else {
            throw BiometricApprovalError.expired
        }
        let canonical = try request.canonicalBytes()
        guard publicKey == pinnedPublicKey, verify(canonical: canonical, signature: signature, publicKey: pinnedPublicKey) else {
            throw BiometricApprovalError.tampered
        }
        try withLock(directory) {
            let consumed = consumedURL(directory, request.nonce)
            let pending = pendingURL(directory, request.nonce)
            if FileManager.default.fileExists(atPath: consumed.path) || FileManager.default.fileExists(atPath: pending.path) {
                throw BiometricApprovalError.replay
            }
            let payload = try encode(StoredBiometricApproval(canonical: canonical, signature: signature, publicKey: publicKey))
            try payload.write(to: pending, options: .atomic)
        }
    }

    /// Verifies the live request, then spends the nonce.
    ///
    /// Expiry spends the nonce so a later clock change cannot reuse it.
    /// A mismatch or a bad signature does not spend it.
    public static func consume(
        request: BiometricApprovalRequest,
        pinnedPublicKey: Data,
        directory: URL,
        now: Int
    ) throws {
        let canonical = try request.canonicalBytes()
        try withLock(directory) {
            let consumed = consumedURL(directory, request.nonce)
            if FileManager.default.fileExists(atPath: consumed.path) {
                throw BiometricApprovalError.replay
            }
            let pending = pendingURL(directory, request.nonce)
            let stored: StoredBiometricApproval
            do {
                stored = try decode(Data(contentsOf: pending))
            } catch let error as BiometricApprovalError {
                throw error
            } catch {
                throw BiometricApprovalError.tampered
            }
            guard stored.publicKey == pinnedPublicKey else {
                throw BiometricApprovalError.tampered
            }
            guard verify(canonical: stored.canonical, signature: stored.signature, publicKey: pinnedPublicKey) else {
                throw BiometricApprovalError.tampered
            }
            guard stored.canonical == canonical else {
                throw BiometricApprovalError.mismatch
            }
            if request.expiryUnix <= now {
                try Data("expired\n".utf8).write(to: consumed, options: .atomic)
                throw BiometricApprovalError.expired
            }
            try Data("consumed\n".utf8).write(to: consumed, options: .atomic)
            try? FileManager.default.removeItem(at: pending)
        }
    }

    public static func isConsumed(nonce: String, directory: URL) -> Bool {
        FileManager.default.fileExists(atPath: consumedURL(directory, nonce).path)
    }

    static func verify(canonical: Data, signature: Data, publicKey: Data) -> Bool {
        guard let parsedSignature = try? P256.Signing.ECDSASignature(rawRepresentation: signature),
              let key = try? P256.Signing.PublicKey(x963Representation: publicKey) else {
            return false
        }
        return key.isValidSignature(parsedSignature, for: canonical)
    }

    private static func pendingURL(_ directory: URL, _ nonce: String) -> URL {
        directory.appendingPathComponent("\(nonce).approval")
    }

    private static func consumedURL(_ directory: URL, _ nonce: String) -> URL {
        directory.appendingPathComponent("\(nonce).consumed")
    }

    private static func encode(_ stored: StoredBiometricApproval) throws -> Data {
        let object: [String: String] = [
            "canonical_b64": stored.canonical.base64EncodedString(),
            "public_key_b64": stored.publicKey.base64EncodedString(),
            "signature_b64": stored.signature.base64EncodedString(),
        ]
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    private static func decode(_ data: Data) throws -> StoredBiometricApproval {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: String],
              let canonical = object["canonical_b64"].flatMap({ Data(base64Encoded: $0) }),
              let signature = object["signature_b64"].flatMap({ Data(base64Encoded: $0) }),
              let publicKey = object["public_key_b64"].flatMap({ Data(base64Encoded: $0) }) else {
            throw BiometricApprovalError.tampered
        }
        return StoredBiometricApproval(canonical: canonical, signature: signature, publicKey: publicKey)
    }

    private static func withLock<T>(_ directory: URL, _ body: () throws -> T) throws -> T {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let lockURL = directory.appendingPathComponent("consume.lock")
        let fd = open(lockURL.path, O_CREAT | O_RDWR, 0o600)
        guard fd >= 0 else {
            throw BiometricApprovalError.malformed("lock")
        }
        defer { close(fd) }
        guard flock(fd, LOCK_EX) == 0 else {
            throw BiometricApprovalError.malformed("lock")
        }
        defer { _ = flock(fd, LOCK_UN) }
        return try body()
    }
}

/// Signs one local request with a non-exportable Secure Enclave key.
///
/// The private-key operation requires the current biometric set. This function
/// does not call `LAContext.evaluatePolicy` and does not accept a Boolean in
/// its place. Unit tests must not call it: a real Touch ID or Face ID prompt
/// is a human step.
public enum LocalSecureEnclaveSigner {
    public struct SignedApproval: Equatable, Sendable {
        public var publicKey: Data
        public var signature: Data
    }

    public static func sign(_ request: BiometricApprovalRequest) throws -> SignedApproval {
        let context = LAContext()
        context.localizedFallbackTitle = ""
        var cfError: Unmanaged<CFError>?
        guard let access = SecAccessControlCreateWithFlags(
            nil,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            [.privateKeyUsage, .biometryCurrentSet],
            &cfError
        ) else {
            throw BiometricApprovalError.malformed("access control")
        }
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            accessControl: access,
            authenticationContext: context
        )
        let signature = try key.signature(for: try request.canonicalBytes())
        return SignedApproval(
            publicKey: key.publicKey.x963Representation,
            signature: signature.rawRepresentation
        )
    }
}
