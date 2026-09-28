import Foundation

/// Display fields from a file a person carried from the Mac.
///
/// Parsing uses the shared RSBA2 schema. This type does not call Face ID.
struct CompanionApprovalPreview: Equatable {
    var lines: [String]
    var refusal: String
    var fields: RSBA2Package.Fields?

    static let refusalText = "Observe does not call Face ID. A development software signature is not a Mac approval, and a phone signature is not physical presence at the Mac."

    static func parse(_ data: Data) -> CompanionApprovalPreview {
        do {
            let fields = try RSBA2Package.parse(data)
            return CompanionApprovalPreview(
                lines: RSBA2Package.lines(for: fields),
                refusal: refusalText,
                fields: fields
            )
        } catch let error as RSBA2Package.ParseFailure {
            return CompanionApprovalPreview(lines: [], refusal: refusal(for: error), fields: nil)
        } catch {
            return CompanionApprovalPreview(lines: [], refusal: "The carried file is not a biometric approval package.", fields: nil)
        }
    }

    private static func refusal(for error: RSBA2Package.ParseFailure) -> String {
        switch error {
        case .malformed("presence"):
            return "A carried package cannot claim the person is at the Mac."
        case .malformed("version"):
            return "The package version must be exactly RSBA2."
        case .malformed("policy"):
            return "The package policy must be local, companion, or dual."
        case .malformed("enrollment"):
            return "The package enrollment generation is missing or not canonical."
        case .malformed("package"):
            return "The carried file has keys outside the RSBA2 schema."
        case .malformed:
            return "The carried file is not a biometric approval package."
        }
    }
}
