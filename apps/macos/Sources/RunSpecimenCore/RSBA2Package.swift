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
    public static let provenanceProduction = "production"
    public static let provenanceSoftwareTest = "software-test"
    public static let provenanceDevelopment = "software-development"
    public static let provenanceDiagnostic = "diagnostic"
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
        return false
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
