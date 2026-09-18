import Foundation

struct CompanionCapabilities: Codable, Equatable {
    var product: String
    var mode: String
    var canApprove: Bool
    var canExecute: Bool
    var canMutateLifecycle: Bool
    var canRemoteConfirm: Bool?
    var boundary: String
    var remoteConfirm: RemoteConfirmCapability?

    enum CodingKeys: String, CodingKey {
        case product, mode, boundary
        case canApprove = "can_approve"
        case canExecute = "can_execute"
        case canMutateLifecycle = "can_mutate_lifecycle"
        case canRemoteConfirm = "can_remote_confirm"
        case remoteConfirm = "remote_confirm"
    }
}

struct RemoteConfirmCapability: Codable, Equatable {
    var pending: Bool?
    var notEquivalentTo: String?
    var claim: String?

    enum CodingKeys: String, CodingKey {
        case pending, claim
        case notEquivalentTo = "not_equivalent_to"
    }
}

struct CompanionStatus: Codable, Equatable {
    var phase: String?
    var campaignId: String?
    var runId: String?
    var eventChainOk: Bool?
    var workspaceLeaseHeldByOther: Bool?
    var companion: CompanionFlags?

    enum CodingKeys: String, CodingKey {
        case phase
        case campaignId = "campaign_id"
        case runId = "run_id"
        case eventChainOk = "event_chain_ok"
        case workspaceLeaseHeldByOther = "workspace_lease_held_by_other"
        case companion
    }
}

struct CompanionFlags: Codable, Equatable {
    var mode: String?
    var canApprove: Bool?
    var canExecute: Bool?
    var canRemoteConfirm: Bool?
    var note: String?
    var remoteConfirm: RemoteConfirmPending?

    enum CodingKeys: String, CodingKey {
        case mode, note
        case canApprove = "can_approve"
        case canExecute = "can_execute"
        case canRemoteConfirm = "can_remote_confirm"
        case remoteConfirm = "remote_confirm"
    }
}

struct RemoteConfirmPending: Codable, Equatable {
    var pending: Bool?
    var canRemoteConfirm: Bool?
    var challengeId: String?
    var expiresAtUnix: Double?
    var instruction: String?
    var claim: String?
    var notEquivalentTo: String?
    var confirmChannel: String?
    var who: String?
    var what: String?
    var chips: RemoteConfirmChips?

    enum CodingKeys: String, CodingKey {
        case pending, instruction, claim, who, what, chips
        case canRemoteConfirm = "can_remote_confirm"
        case challengeId = "challenge_id"
        case expiresAtUnix = "expires_at_unix"
        case notEquivalentTo = "not_equivalent_to"
        case confirmChannel = "confirm_channel"
    }
}

struct RemoteConfirmChips: Codable, Equatable {
    var expiry: String?
    var lease: String?
    var isolation: String?
    var predecessor: String?
    var wallTimeoutSec: Int?

    enum CodingKeys: String, CodingKey {
        case expiry, lease, isolation, predecessor
        case wallTimeoutSec = "wall_timeout_sec"
    }
}

struct RemoteConfirmResult: Codable, Equatable {
    var ok: Bool?
    var settled: Bool?
    var refused: Bool?
    var confirmChannel: String?
    var note: String?
    var reason: String?

    enum CodingKeys: String, CodingKey {
        case ok, settled, refused, note, reason
        case confirmChannel = "confirm_channel"
    }
}

struct PairingConfig: Codable, Equatable {
    var baseURL: URL
    var pairingToken: String
    /// SHA-256 fingerprint of the Mac companion TLS cert (colons optional). Required for HTTPS.
    var tlsFingerprint: String?

    enum CodingKeys: String, CodingKey {
        case baseURL
        case pairingToken
        case tlsFingerprint
    }
}
