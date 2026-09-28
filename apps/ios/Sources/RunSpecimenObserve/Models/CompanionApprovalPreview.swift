import Foundation

/// Display fields from a file a person carried from the Mac.
///
/// This type does not sign, does not call Face ID, and does not approve a run.
struct CompanionApprovalPreview: Equatable {
    var lines: [String]
    var refusal: String

    static let refusalText = "Observe does not sign this request and does not call Face ID. A phone signature is not physical presence at the Mac."

    static func parse(_ data: Data) -> CompanionApprovalPreview {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: String] else {
            return CompanionApprovalPreview(lines: [], refusal: "The carried file is not a biometric approval package.")
        }
        if object["present_at_mac"] != nil {
            return CompanionApprovalPreview(lines: [], refusal: "A carried package cannot claim the person is at the Mac.")
        }
        guard let policy = object["policy"], ["local", "companion", "dual"].contains(policy) else {
            return CompanionApprovalPreview(lines: [], refusal: "The package policy must be local, companion, or dual.")
        }
        var lines = [
            "Policy: \(policy)",
            "Mac: \(object["mac_id"] ?? "")",
            "Workspace: \(object["workspace_id"] ?? "")",
            "Run: \(object["run_id"] ?? "")",
            "Contract: \(object["contract_sha256"] ?? "")",
            "Inputs: \(object["inputs_sha256"] ?? "")",
            "Bounds: \(object["bounds"] ?? "")",
            "Nonce: \(object["nonce"] ?? "")",
            "Expiry unix: \(object["expiry_unix"] ?? "")",
        ]
        if let local = object["local_key_id"], !local.isEmpty {
            lines.append("Local key: \(local)")
        }
        if let companion = object["companion_key_id"], !companion.isEmpty {
            lines.append("Companion key: \(companion)")
        }
        switch policy {
        case "companion":
            lines.append("This phone signature is not physical presence at the Mac.")
        case "dual":
            lines.append("Dual policy needs both signatures over this same request. The phone signature is not physical presence at the Mac.")
        default:
            lines.append("This Mac biometric signature does not show that a phone approved.")
        }
        return CompanionApprovalPreview(lines: lines, refusal: refusalText)
    }
}
