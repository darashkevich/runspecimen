import Foundation

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

    /// Rejects a missing version, an unknown version, and keys outside the schema.
    public static func parse(_ data: Data) throws -> Fields {
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
        let localGeneration = generation(object["local_generation"])
        let companionGeneration = generation(object["companion_generation"])
        switch policy {
        case "local":
            guard localGeneration > 0, companionGeneration == 0 else { throw ParseFailure.malformed("enrollment") }
        case "companion":
            guard companionGeneration > 0, localGeneration == 0 else { throw ParseFailure.malformed("enrollment") }
        default:
            guard localGeneration > 0, companionGeneration > 0 else { throw ParseFailure.malformed("enrollment") }
        }
        guard let expiry = Int(object["expiry_unix"] ?? "") else {
            throw ParseFailure.malformed("expiry_unix")
        }
        return Fields(
            policy: policy,
            macID: object["mac_id"] ?? "",
            workspaceID: object["workspace_id"] ?? "",
            runID: object["run_id"] ?? "",
            contractSHA256: object["contract_sha256"] ?? "",
            inputsSHA256: object["inputs_sha256"] ?? "",
            bounds: object["bounds"] ?? "",
            nonce: object["nonce"] ?? "",
            expiryUnix: expiry,
            localKeyID: object["local_key_id"] ?? "",
            companionKeyID: object["companion_key_id"] ?? "",
            localGeneration: localGeneration,
            companionGeneration: companionGeneration,
            localPublicKeyB64: object["local_public_key_b64"],
            localSignatureB64: object["local_signature_b64"],
            companionPublicKeyB64: object["companion_public_key_b64"],
            companionSignatureB64: object["companion_signature_b64"]
        )
    }

    private static func generation(_ text: String?) -> Int {
        guard let text, let value = Int(text), value > 0, String(value) == text else { return 0 }
        return value
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
