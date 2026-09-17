import Foundation

struct CompanionCapabilities: Codable, Equatable {
    var product: String
    var mode: String
    var canApprove: Bool
    var canExecute: Bool
    var canMutateLifecycle: Bool
    var boundary: String

    enum CodingKeys: String, CodingKey {
        case product, mode, boundary
        case canApprove = "can_approve"
        case canExecute = "can_execute"
        case canMutateLifecycle = "can_mutate_lifecycle"
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
    var note: String?

    enum CodingKeys: String, CodingKey {
        case mode, note
        case canApprove = "can_approve"
        case canExecute = "can_execute"
    }
}

struct PairingConfig: Codable, Equatable {
    var baseURL: URL
    var pairingToken: String
}
