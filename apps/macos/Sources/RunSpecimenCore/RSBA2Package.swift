import CryptoKit
import Foundation

/// Role, backend, and provenance shared by the Mac store and the iOS companion.
///
/// `allowsExecution` is the check a future run path must call. A software key
/// never passes it. Passing a software consume in tests is not biometric completion.
public enum EnrollmentIdentity {
    public static let roleLocal = "local"
    public static let roleCompanion = "companion"
    public static let backendSecureEnclave = "secure-enclave"
    public static let backendSoftwareTest = "software-test-double"
    public static let backendSoftwareDevelopment = "software-development"
    public static let backendUnverified = "unverified"
    public static let provenanceProduction = "production"
    public static let provenanceSoftwareTest = "software-test"
    public static let provenanceDevelopment = "software-development"
    public static let provenanceDiagnostic = "diagnostic"
    /// A public key a person carried. The file's backend label is not copied.
    public static let provenanceCarriedPin = "carried-pin"
    public static let stateActive = "active"

    public static func allowsExecution(role: String, backend: String, provenance: String, state: String) -> Bool {
        (role == roleLocal || role == roleCompanion)
            && backend == backendSecureEnclave
            && provenance == provenanceProduction
            && state == stateActive
    }

    /// Prototype consume may use a software test double. Development and diagnostic keys never pass.
    public static func acceptsPrototype(role: String, backend: String, provenance: String) -> Bool {
        guard role == roleLocal || role == roleCompanion else { return false }
        if backend == backendSoftwareDevelopment || provenance == provenanceDevelopment || provenance == provenanceDiagnostic {
            return false
        }
        if backend == backendSoftwareTest && provenance == provenanceSoftwareTest { return true }
        if backend == backendSecureEnclave && provenance == provenanceProduction { return true }
        return false
    }

    /// Records the store can read. Development and diagnostic identities are recognized so consume can reject them.
    public static func isRecognized(role: String, backend: String, provenance: String) -> Bool {
        if acceptsPrototype(role: role, backend: backend, provenance: provenance) { return true }
        guard role == roleLocal || role == roleCompanion else { return false }
        if backend == backendSecureEnclave && provenance == provenanceDiagnostic { return true }
        if backend == backendSoftwareDevelopment && provenance == provenanceDevelopment { return true }
        if backend == backendUnverified && provenance == provenanceCarriedPin { return true }
        return false
    }
}

/// Engineering enrollment through the isolated double. Not hardware.
///
/// Completing this path does not create a Secure Enclave key and does not prompt.
/// Installed protection and `allowsProductionEnrollment` stay closed.
public struct IsolatedNativeSigner: Equatable, Sendable {
    public var role: String
    public var hardware: Bool
    public var bridge: String

    public init(role: String, hardware: Bool, bridge: String) {
        self.role = role
        self.hardware = hardware
        self.bridge = bridge
    }
}

public enum IsolatedNativeEnrollment {
    public static let bridge = "isolated-native-bridge-double-not-hardware"

    /// Stores an engineering signer. Hardware stays false. A production role is refused.
    public static func complete(role: String) -> IsolatedNativeSigner? {
        guard role == EnrollmentIdentity.roleLocal || role == EnrollmentIdentity.roleCompanion else {
            return nil
        }
        return IsolatedNativeSigner(role: role, hardware: false, bridge: bridge)
    }

    public static func connected(_ signers: [IsolatedNativeSigner]) -> (local: Bool, companion: Bool) {
        var local = false
        var companion = false
        for signer in signers {
            guard signer.hardware == false, signer.bridge == bridge else { continue }
            if signer.role == EnrollmentIdentity.roleLocal { local = true }
            if signer.role == EnrollmentIdentity.roleCompanion { companion = true }
        }
        return (local, companion)
    }
}

/// Who created the key. A caller string cannot become the human Secure Enclave step.
public enum NativeSignerOrigin: String, Equatable, Sendable {
    case callerSupplied = "caller-supplied"
    case softwareDouble = "software-double"
    case secureEnclaveHumanStep = "secure-enclave-human-prompt"
}

public enum ProductionEnrollmentError: Error, Equatable {
    case biometricPromptNotInvoked
    case callerHardwareLabelRefused
    case signerIncomplete
    case signatureRejected
    case replayedChallenge
    case staleChallenge
    case tamperedChallenge
}

public struct BoundDeviceChallenge: Equatable, Sendable {
    public var holderId: String
    public var generation: Int
    public var role: String
    public var expiry: Int
    public var nonce: String
    public var challenge: Data

    public init(holderId: String, generation: Int, role: String, expiry: Int, nonce: String, challenge: Data) {
        self.holderId = holderId
        self.generation = generation
        self.role = role
        self.expiry = expiry
        self.nonce = nonce
        self.challenge = challenge
    }

    /// Same bytes as Python ``bound_device_message``. Not a signature check.
    public func canonicalBytes() -> Data {
        let object = """
        {"challenge":"\(challenge.base64EncodedString())","domain":"holder-device-p256-v1","expiry":\(expiry),"generation":\(generation),"holder_id":"\(holderId)","nonce":"\(nonce)","role":"\(role)"}
        """
        return Data(object.utf8)
    }
}

public final class MemoryChallengeNonceStore: @unchecked Sendable {
    private var spent: Set<String> = []
    private var cancelled: Set<String> = []

    public init() {}

    public func cancel(_ nonce: String) {
        cancelled.insert(nonce)
    }

    public func consume(_ nonce: String) throws {
        if cancelled.contains(nonce) {
            throw ProductionEnrollmentError.staleChallenge
        }
        if spent.contains(nonce) {
            throw ProductionEnrollmentError.replayedChallenge
        }
        spent.insert(nonce)
    }
}

/// In-process native signer. Not hardware. Wire JSON cannot become this type.
///
/// A conforming type must not call `SecureEnclave.P256.Signing.PrivateKey`.
/// Automation supplies a fixture. A person pressing the biometric is a separate step.
public protocol HumanNativeSigning: Sendable {
    var hardware: Bool { get }
    func publicKey(role: String) -> Data
    func sign(role: String, message: Data) -> Data
}

/// OS boundary the user-invoked control calls. Tests supply a mock.
/// The live Secure Enclave constructor is not part of this protocol.
public struct NativeSessionKey: Sendable {
    public let publicKey: Data
    public let accessPolicy: String

    public init(publicKey: Data, accessPolicy: String) {
        self.publicKey = publicKey
        self.accessPolicy = accessPolicy
    }
}

public protocol SecureEnclaveKeyMaking: Sendable {
    func makeSessionKey() throws -> NativeSessionKey
}

public protocol PhonePeerComparing: Sendable {
    var publicKey: Data { get }
    func sign(challenge: Data) throws -> Data
}

public struct HumanEnrollmentReceipt: Equatable, Sendable {
    public var hardware: Bool
    public var biometricInvoked: Bool
    public var policy: String
    public var roles: [String]
    public var publicKeys: [String: Data]
    public var signatures: [String: Data]

    public init(
        hardware: Bool,
        biometricInvoked: Bool,
        policy: String,
        roles: [String],
        publicKeys: [String: Data],
        signatures: [String: Data]
    ) {
        self.hardware = hardware
        self.biometricInvoked = biometricInvoked
        self.policy = policy
        self.roles = roles
        self.publicKeys = publicKeys
        self.signatures = signatures
    }
}

/// Production enrollment status for the Mac app.
///
/// A caller boundary flag is not production enrollment. The Secure Enclave
/// prompt is the human step and is not invoked from this type. This Store
/// app does not carry the Developer ID verifier pin.
public enum ProductionNativeBridgeGate {
    public static let boundaryBackend = "production-boundary-double-not-hardware"
    public static let productionBridge = "native-production-bridge"

    public static func status(signers: [IsolatedNativeSigner] = []) -> String {
        let connected = IsolatedNativeEnrollment.connected(signers)
        return "Source integration of native enrollment remains open. A caller boundary flag is not production enrollment. This Store app does not carry the Developer ID verifier pin and stays guarantee (1). A display name is not a pin. A verifier pin does not authorize a software key. An origin string is not production trust. An injected native signer is not hardware. A software signer is not the native adapter. E2 is not closed. A biometric press does not finish missing implementation. The local control sends the bound challenge over authenticated holder IPC. The Observe screen returns the phone signature. The holder verifies P-256 and consumes the nonce. Still unbuilt: a root-owned installed holder. E2 stays open because source integration and trust are incomplete. A press or an install cannot fix those defects. The Secure Enclave prompt is the human step and was not invoked. Isolated double local=\(connected.local) companion=\(connected.companion)."
    }

    /// Wire and file labels never select the human step.
    public static func origin(fromCallerBackend backend: String) -> NativeSignerOrigin {
        if backend == boundaryBackend
            || backend == EnrollmentIdentity.backendSoftwareTest
            || backend == EnrollmentIdentity.backendSoftwareDevelopment {
            return .softwareDouble
        }
        return .callerSupplied
    }

    /// An origin enum is not production trust. A pin match authenticates verifier
    /// code elsewhere. It does not admit `.secureEnclaveHumanStep` by itself.
    public static func allowsProductionEnrollment(
        origin: NativeSignerOrigin,
        pinConfigured: Bool = false,
        verifierConnected: Bool = false,
        installedProtection: Bool = false
    ) -> Bool {
        _ = (origin, pinConfigured, verifierConnected, installedProtection)
        return false
    }

    /// Calls `maker` only when the caller passes the object from a user-invoked control.
    /// The live `SecureEnclave.P256.Signing.PrivateKey` call is not in this type.
    /// Local session only. Companion and dual are `enrollPairedPhone`.
    public static func enrollFromUserInvokedControl(
        policy: String,
        maker: SecureEnclaveKeyMaking
    ) throws -> NativeSessionKey {
        guard policy == "local" else {
            throw ProductionEnrollmentError.signerIncomplete
        }
        let key = try maker.makeSessionKey()
        if key.publicKey.isEmpty || key.accessPolicy != "biometry-current-set-on-each-signature" {
            throw ProductionEnrollmentError.signerIncomplete
        }
        return key
    }

    /// Verifies P-256 over the bound challenge, then consumes the nonce.
    ///
    /// A nonempty signature is not enough. Verification is not hardware
    /// provenance and not a biometric press. A matching local key is refused.
    public static func enrollPairedPhone(
        challenge: BoundDeviceChallenge,
        peer: PhonePeerComparing,
        localPublicKey: Data?,
        nonces: MemoryChallengeNonceStore
    ) throws -> Data {
        if challenge.challenge.isEmpty || challenge.nonce.isEmpty || challenge.holderId.isEmpty {
            throw ProductionEnrollmentError.tamperedChallenge
        }
        if let localPublicKey, localPublicKey == peer.publicKey {
            throw ProductionEnrollmentError.signerIncomplete
        }
        let message = challenge.canonicalBytes()
        let signature = try peer.sign(challenge: message)
        guard
            let key = try? P256.Signing.PublicKey(x963Representation: peer.publicKey),
            let parsed = try? P256.Signing.ECDSASignature(rawRepresentation: signature),
            key.isValidSignature(parsed, for: message)
        else {
            throw ProductionEnrollmentError.signatureRejected
        }
        try nonces.consume(challenge.nonce)
        return peer.publicKey
    }

    /// Unattended call. Does not call `SecureEnclave.P256.Signing.PrivateKey` and does not prompt.
    public static func beginHumanSecureEnclaveEnrollment() throws {
        throw ProductionEnrollmentError.biometricPromptNotInvoked
    }

    /// Enroll, pair, and sign with an injected native signer.
    ///
    /// `signer` is an in-process dependency. A nil signer takes the unattended
    /// path and throws before any key API. `hardware == true` is a caller label
    /// and is refused. The receipt is not a Secure Enclave enrollment and not
    /// installed protection. This function does not call
    /// `SecureEnclave.P256.Signing.PrivateKey`.
    public static func beginHumanSecureEnclaveEnrollment<S: HumanNativeSigning>(
        signer: S?,
        policy: String = "local"
    ) throws -> HumanEnrollmentReceipt {
        guard let signer else {
            throw ProductionEnrollmentError.biometricPromptNotInvoked
        }
        if signer.hardware {
            throw ProductionEnrollmentError.callerHardwareLabelRefused
        }
        let roles: [String]
        switch policy {
        case "local":
            roles = ["mac"]
        case "companion":
            roles = ["phone"]
        case "dual":
            roles = ["mac", "phone"]
        default:
            throw ProductionEnrollmentError.signerIncomplete
        }
        let message = Data("holder-device-p256-v1:\(policy)".utf8)
        var publicKeys: [String: Data] = [:]
        var signatures: [String: Data] = [:]
        for role in roles {
            let publicKey = signer.publicKey(role: role)
            let signature = signer.sign(role: role, message: message)
            if publicKey.isEmpty || signature.isEmpty {
                throw ProductionEnrollmentError.signerIncomplete
            }
            publicKeys[role] = publicKey
            signatures[role] = signature
        }
        return HumanEnrollmentReceipt(
            hardware: false,
            biometricInvoked: false,
            policy: policy,
            roles: roles,
            publicKeys: publicKeys,
            signatures: signatures
        )
    }
}

/// Human-operated native adapter. Not `HumanNativeSigning` and not a software signer.
///
/// The type has no hardware flag a caller can set. A conforming fixture must not
/// call `SecureEnclave.P256.Signing.PrivateKey`. Automation does not prompt.
/// `e2Closed` stays false because the biometric press is still a human step.
public protocol HumanOperatedNativeAdapting: Sendable {
    func publicKey(role: String) -> Data
    func sign(role: String, message: Data) -> Data
}

public struct HumanOperatedAdapterReceipt: Equatable, Sendable {
    public var biometricInvoked: Bool
    public var e2Closed: Bool
    public var policy: String
    public var roles: [String]
    public var publicKeys: [String: Data]
    public var signatures: [String: Data]

    public init(
        biometricInvoked: Bool,
        e2Closed: Bool,
        policy: String,
        roles: [String],
        publicKeys: [String: Data],
        signatures: [String: Data]
    ) {
        self.biometricInvoked = biometricInvoked
        self.e2Closed = e2Closed
        self.policy = policy
        self.roles = roles
        self.publicKeys = publicKeys
        self.signatures = signatures
    }
}

public enum HumanOperatedNativeAdapterGate {
    /// Enroll, pair, and sign through the adapter. A nil adapter throws before any key API.
    ///
    /// This function does not call `SecureEnclave.P256.Signing.PrivateKey` and does not prompt.
    /// The receipt does not close E2.
    public static func begin<A: HumanOperatedNativeAdapting>(
        adapter: A?,
        policy: String = "local"
    ) throws -> HumanOperatedAdapterReceipt {
        guard let adapter else {
            throw ProductionEnrollmentError.biometricPromptNotInvoked
        }
        let roles: [String]
        switch policy {
        case "local":
            roles = ["mac"]
        case "companion":
            roles = ["phone"]
        case "dual":
            roles = ["mac", "phone"]
        default:
            throw ProductionEnrollmentError.signerIncomplete
        }
        let message = Data("holder-device-p256-v1:\(policy)".utf8)
        var publicKeys: [String: Data] = [:]
        var signatures: [String: Data] = [:]
        for role in roles {
            let publicKey = adapter.publicKey(role: role)
            let signature = adapter.sign(role: role, message: message)
            if publicKey.isEmpty || signature.isEmpty {
                throw ProductionEnrollmentError.signerIncomplete
            }
            publicKeys[role] = publicKey
            signatures[role] = signature
        }
        return HumanOperatedAdapterReceipt(
            biometricInvoked: false,
            e2Closed: false,
            policy: policy,
            roles: roles,
            publicKeys: publicKeys,
            signatures: signatures
        )
    }
}

/// Enrollment facts checked again after a biometric wait.
///
/// Passing this check is not evidence that the person understood the command.
/// It only says the stored key is still the one that was about to sign.
public struct CompanionEnrollmentSnapshot: Equatable, Sendable {
    public var keyID: String
    public var publicKey: Data
    public var role: String
    public var backend: String
    public var provenance: String
    public var state: String
    public var generation: Int

    public init(
        keyID: String,
        publicKey: Data,
        role: String,
        backend: String,
        provenance: String,
        state: String,
        generation: Int
    ) {
        self.keyID = keyID
        self.publicKey = publicKey
        self.role = role
        self.backend = backend
        self.provenance = provenance
        self.state = state
        self.generation = generation
    }
}

public enum CompanionPostAuthentication {
    /// Discards a signature when the live record changed during the wait, or the request expired.
    public static func accept(
        before: CompanionEnrollmentSnapshot,
        after: CompanionEnrollmentSnapshot,
        expiryUnix: Int,
        now: Int
    ) throws {
        guard after.keyID == before.keyID,
              after.publicKey == before.publicKey,
              after.role == before.role,
              after.generation == before.generation,
              after.state == EnrollmentIdentity.stateActive,
              EnrollmentIdentity.allowsExecution(
                role: after.role,
                backend: after.backend,
                provenance: after.provenance,
                state: after.state
              ) else {
            throw RSBA2Package.ParseFailure.malformed("enrollment")
        }
        guard expiryUnix > now else {
            throw RSBA2Package.ParseFailure.malformed("expiry_unix")
        }
    }
}

/// Shared RSBA2 bytes and package schema.
///
/// The iOS app compiles this same file. A package version other than `RSBA2`
/// is rejected before any signature is checked.
public enum RSBA2Package {
    public static let version = "RSBA2"
    public static let allowedKeys: Set<String> = [
        "version", "policy", "mac_id", "workspace_id", "run_id",
        "contract_sha256", "inputs_sha256", "bounds", "nonce", "expiry_unix",
        "local_key_id", "companion_key_id", "local_generation", "companion_generation",
        "local_public_key_b64", "local_signature_b64",
        "companion_public_key_b64", "companion_signature_b64",
    ]

    public struct Fields: Equatable, Sendable {
        public var policy: String
        public var macID: String
        public var workspaceID: String
        public var runID: String
        public var contractSHA256: String
        public var inputsSHA256: String
        public var bounds: String
        public var nonce: String
        public var expiryUnix: Int
        public var localKeyID: String
        public var companionKeyID: String
        public var localGeneration: Int
        public var companionGeneration: Int
        public var localPublicKeyB64: String?
        public var localSignatureB64: String?
        public var companionPublicKeyB64: String?
        public var companionSignatureB64: String?
    }

    public enum ParseFailure: Error, Equatable {
        case malformed(String)
    }

    public static func canonicalBytes(
        policy: String,
        macID: String,
        workspaceID: String,
        runID: String,
        contractSHA256: String,
        inputsSHA256: String,
        bounds: String,
        nonce: String,
        expiryUnix: Int,
        localKeyID: String,
        companionKeyID: String,
        localGeneration: Int,
        companionGeneration: Int
    ) throws -> Data {
        var fields: [(String, String)] = [
            ("policy", policy),
            ("mac_id", macID),
            ("workspace_id", workspaceID),
            ("run_id", runID),
            ("contract_sha256", contractSHA256),
            ("inputs_sha256", inputsSHA256),
            ("bounds", bounds),
            ("nonce", nonce),
            ("expiry_unix", String(expiryUnix)),
        ]
        switch policy {
        case "local":
            guard companionKeyID.isEmpty, companionGeneration == 0 else { throw ParseFailure.malformed("policy") }
            fields.append(("local_key_id", localKeyID))
            fields.append(("local_generation", String(localGeneration)))
        case "companion":
            guard localKeyID.isEmpty, localGeneration == 0 else { throw ParseFailure.malformed("policy") }
            fields.append(("companion_key_id", companionKeyID))
            fields.append(("companion_generation", String(companionGeneration)))
        case "dual":
            guard localKeyID != companionKeyID else { throw ParseFailure.malformed("policy") }
            fields.append(("local_key_id", localKeyID))
            fields.append(("local_generation", String(localGeneration)))
            fields.append(("companion_key_id", companionKeyID))
            fields.append(("companion_generation", String(companionGeneration)))
        default:
            throw ParseFailure.malformed("policy")
        }
        var out = Data(version.utf8)
        for (name, value) in fields {
            try validate(name: name, value: value)
            out.append(lengthPrefixed(name))
            out.append(lengthPrefixed(value))
        }
        return out
    }

    public static func lines(for fields: Fields) -> [String] {
        var lines = [
            "Version: \(version)",
            "Policy: \(fields.policy)",
            "Mac: \(fields.macID)",
            "Workspace: \(fields.workspaceID)",
            "Run: \(fields.runID)",
            "Contract: \(fields.contractSHA256)",
            "Inputs: \(fields.inputsSHA256)",
            "Bounds: \(fields.bounds)",
            "Nonce: \(fields.nonce)",
            "Expiry unix: \(fields.expiryUnix)",
        ]
        switch fields.policy {
        case "local":
            lines.append("Local key: \(fields.localKeyID) generation \(fields.localGeneration)")
            lines.append("This Mac biometric signature does not show that a phone approved, and it does not show that the person understood the command.")
        case "companion":
            lines.append("Companion key: \(fields.companionKeyID) generation \(fields.companionGeneration)")
            lines.append("This phone signature is not physical presence at the Mac.")
        case "dual":
            lines.append("Local key: \(fields.localKeyID) generation \(fields.localGeneration)")
            lines.append("Companion key: \(fields.companionKeyID) generation \(fields.companionGeneration)")
            lines.append("Dual policy needs both signatures over this same request. The phone signature is not physical presence at the Mac.")
        default:
            break
        }
        return lines
    }

    public static let maximumPackageBytes = 16_384

    /// A successful parse is a complete request. Missing, empty, and non-canonical fields fail here.
    public static func parse(_ data: Data) throws -> Fields {
        guard data.count <= maximumPackageBytes else { throw ParseFailure.malformed("package") }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: String] else {
            throw ParseFailure.malformed("package")
        }
        if object["present_at_mac"] != nil {
            throw ParseFailure.malformed("presence")
        }
        guard let versionField = object["version"] else {
            throw ParseFailure.malformed("version")
        }
        guard versionField == version else {
            throw ParseFailure.malformed("version")
        }
        let unknown = Set(object.keys).subtracting(allowedKeys)
        guard unknown.isEmpty else {
            throw ParseFailure.malformed("package")
        }
        guard let policy = object["policy"], ["local", "companion", "dual"].contains(policy) else {
            throw ParseFailure.malformed("policy")
        }
        let macID = try text(object, "mac_id", minimum: 1, maximum: 128)
        let workspaceID = try text(object, "workspace_id", minimum: 1, maximum: 128)
        let runID = try text(object, "run_id", minimum: 1, maximum: 128)
        let contract = try hex(object, "contract_sha256", count: 64)
        let inputs = try hex(object, "inputs_sha256", count: 64)
        let bounds = try text(object, "bounds", minimum: 1, maximum: 256)
        let nonce = try hex(object, "nonce", minimum: 32, maximum: 64)
        let expiry = try canonicalInteger(object, "expiry_unix")
        let localKeyID = try roleKey(object, "local_key_id", required: policy != "companion")
        let companionKeyID = try roleKey(object, "companion_key_id", required: policy != "local")
        let localGeneration = try roleGeneration(object, "local_generation", required: policy != "companion")
        let companionGeneration = try roleGeneration(object, "companion_generation", required: policy != "local")
        if policy == "dual", localKeyID == companionKeyID {
            throw ParseFailure.malformed("policy")
        }
        let localPublic = try signatureMaterial(object, publicKey: "local_public_key_b64", signature: "local_signature_b64", allowed: policy != "companion")
        let companionPublic = try signatureMaterial(object, publicKey: "companion_public_key_b64", signature: "companion_signature_b64", allowed: policy != "local")
        return Fields(
            policy: policy,
            macID: macID,
            workspaceID: workspaceID,
            runID: runID,
            contractSHA256: contract,
            inputsSHA256: inputs,
            bounds: bounds,
            nonce: nonce,
            expiryUnix: expiry,
            localKeyID: localKeyID,
            companionKeyID: companionKeyID,
            localGeneration: localGeneration,
            companionGeneration: companionGeneration,
            localPublicKeyB64: localPublic.publicKey,
            localSignatureB64: localPublic.signature,
            companionPublicKeyB64: companionPublic.publicKey,
            companionSignatureB64: companionPublic.signature
        )
    }

    private static func text(_ object: [String: String], _ key: String, minimum: Int, maximum: Int) throws -> String {
        guard let value = object[key] else { throw ParseFailure.malformed(key) }
        guard (minimum...maximum).contains(value.count), !value.contains("\0"), !value.isEmpty else {
            throw ParseFailure.malformed(key)
        }
        return value
    }

    private static func hex(_ object: [String: String], _ key: String, count: Int) throws -> String {
        try hex(object, key, minimum: count, maximum: count)
    }

    private static func hex(_ object: [String: String], _ key: String, minimum: Int, maximum: Int) throws -> String {
        let value = try text(object, key, minimum: minimum, maximum: maximum)
        let digits = CharacterSet(charactersIn: "0123456789abcdef")
        guard value.unicodeScalars.allSatisfy({ digits.contains($0) }) else {
            throw ParseFailure.malformed(key)
        }
        return value
    }

    private static func canonicalInteger(_ object: [String: String], _ key: String) throws -> Int {
        guard let text = object[key] else { throw ParseFailure.malformed(key) }
        guard let value = Int(text), value > 0, String(value) == text else {
            throw ParseFailure.malformed(key)
        }
        return value
    }

    private static func roleKey(_ object: [String: String], _ key: String, required: Bool) throws -> String {
        if !required {
            if object[key] != nil { throw ParseFailure.malformed("policy") }
            return ""
        }
        let value = try text(object, key, minimum: 1, maximum: 64)
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
        guard value.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
            throw ParseFailure.malformed(key)
        }
        return value
    }

    private static func roleGeneration(_ object: [String: String], _ key: String, required: Bool) throws -> Int {
        if !required {
            if object[key] != nil { throw ParseFailure.malformed("enrollment") }
            return 0
        }
        guard let text = object[key], let value = Int(text), value > 0, String(value) == text else {
            throw ParseFailure.malformed("enrollment")
        }
        return value
    }

    private static func signatureMaterial(
        _ object: [String: String],
        publicKey keyName: String,
        signature signatureName: String,
        allowed: Bool
    ) throws -> (publicKey: String?, signature: String?) {
        let publicKey = object[keyName]
        let signature = object[signatureName]
        if !allowed {
            if publicKey != nil || signature != nil { throw ParseFailure.malformed("policy") }
            return (nil, nil)
        }
        if publicKey == nil && signature == nil { return (nil, nil) }
        guard let publicKey, let signature, !publicKey.contains("\0"), !signature.contains("\0") else {
            throw ParseFailure.malformed("signature")
        }
        guard let publicBytes = Data(base64Encoded: publicKey), publicBytes.count == 65 else {
            throw ParseFailure.malformed("public_key")
        }
        guard let signatureBytes = Data(base64Encoded: signature), signatureBytes.count == 64 else {
            throw ParseFailure.malformed("signature")
        }
        return (publicKey, signature)
    }

    private static func validate(name: String, value: String) throws {
        guard !value.isEmpty, !value.contains("\0") else {
            throw ParseFailure.malformed(name)
        }
        if name == "nonce" {
            let hex = CharacterSet(charactersIn: "0123456789abcdef")
            guard (32...64).contains(value.count), value.unicodeScalars.allSatisfy({ hex.contains($0) }) else {
                throw ParseFailure.malformed("nonce")
            }
        }
        if name == "local_key_id" || name == "companion_key_id" {
            let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
            guard (1...64).contains(value.count), value.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
                throw ParseFailure.malformed(name)
            }
        }
        if name == "local_generation" || name == "companion_generation" {
            guard let number = Int(value), number > 0, String(number) == value else {
                throw ParseFailure.malformed("enrollment")
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
