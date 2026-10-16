import Foundation

/// Display fields from a file a person carried from the Mac.
///
/// Parsing uses the shared RSBA2 schema. This type does not call Face ID.
struct CompanionApprovalPreview: Equatable {
    var lines: [String]
    var refusal: String
    var fields: RSBA2Package.Fields?

    static let refusalText = "Showing this package does not call Face ID and does not approve a Mac run. A phone signature is not physical presence at the Mac."

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
            return "The carried file has keys outside the RSBA2 schema or is too large."
        case .malformed("mac_id"), .malformed("workspace_id"), .malformed("run_id"), .malformed("bounds"):
            return "A required request field is missing, empty, or contains a NUL."
        case .malformed("contract_sha256"), .malformed("inputs_sha256"), .malformed("nonce"):
            return "A fingerprint or nonce is not canonical lowercase hex."
        case .malformed("expiry_unix"):
            return "The expiry is missing or not a canonical positive integer."
        case .malformed("public_key"), .malformed("signature"):
            return "A signature field is incomplete or the wrong length."
        case .malformed:
            return "The carried file is not a biometric approval package."
        }
    }
}

enum ActionOutcome: Equatable {
    case none
    case inProgress
    case success(String)
    case failure(message: String, detail: String?)
}

/// The selection displayed by the view retains the person's stored identity even
/// when its file is missing. Other active keys never silently replace it.
struct HardwareKeySelection {
    let keyID: String
    let records: [CompanionPairingRecord]
    let isUnavailable: Bool
    let corruptKeyIDs: [(keyID: String, error: String)]

    init(persistedKeyID: String, directory: URL) throws {
        let listing = try CompanionSecureEnclaveEnrollment.listKeysWithCorrupt(directory: directory)
        keyID = persistedKeyID
        records = listing.validRecords
        corruptKeyIDs = listing.corruptKeyIDs
        isUnavailable = !records.contains { $0.keyID == persistedKeyID }
            && !corruptKeyIDs.contains { $0.keyID == persistedKeyID }
    }
}

enum HardwareKeyActions {
    static func markMacUpdated(keyID: String, directory: URL, refresh: () throws -> Void) throws -> ActionOutcome {
        try CompanionSecureEnclaveEnrollment.markMacUpdated(keyID: keyID, directory: directory)
        try refresh()
        return .success("Key marked as updated on Mac.")
    }
}

/// Persisted replacement relationships keep every outstanding export available
/// across selection changes, refreshes and app relaunches.
struct HardwareRotationExport: Identifiable, Equatable {
    let keyID: String
    let generation: Int
    let isRevoked: Bool
    let json: String
    var id: String { keyID + ":" + String(generation) }
    var title: String { isRevoked ? "Revoked key '\(keyID)' (share with Mac)" : "New active key '\(keyID)' (share with Mac)" }

    static func pending(directory: URL) throws -> [Self] {
        let records = try CompanionSecureEnclaveEnrollment.listKeysWithCorrupt(directory: directory).validRecords
        var cards: [String: Self] = [:]
        for replacement in records {
            guard let previousID = replacement.replacesKeyID else { continue }
            let previous = try CompanionSecureEnclaveEnrollment.inspect(keyID: previousID, directory: directory)
            guard previous.state == CompanionSecureEnclaveEnrollment.revoked,
                  replacement.macUpdatePending || previous.macUpdatePending else { continue }
            for record in [replacement, previous] {
                let json = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: record.keyID, directory: directory)
                let card = Self(keyID: record.keyID, generation: record.generation,
                    isRevoked: record.state == CompanionSecureEnclaveEnrollment.revoked, json: String(decoding: json, as: UTF8.self))
                cards[card.id] = card
            }
        }
        return cards.values.sorted { $0.id < $1.id }
    }
}
