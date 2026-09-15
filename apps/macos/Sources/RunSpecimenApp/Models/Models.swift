import Foundation

struct CLIIdentity: Equatable, Sendable {
    var path: URL
    var version: String
}

struct DoctorReport: Equatable, Sendable {
    var ok: Bool
    var platform: String
    var python: String
    var workspace: String
    var workspaceWritable: Bool
    var workspaceLeaseHeld: Bool
    var rawJSON: String
}

struct RunStatus: Equatable, Sendable {
    var phase: String
    var campaignID: String
    var runID: String
    var workspace: String
    var eventCount: Int
    var eventChainOK: Bool
    var eventChainMessage: String
    var leaseHeldByOther: Bool
    var certificateID: String?
    var eventHead: String?
    var approvalExpiresUnix: Double?
    var argv: [String]
    var contractHash: String?
    var sourceHash: String?
    var runtimeID: String?
    var exitCode: Int?
    var postflightOK: Bool?
    var rawJSON: String

    var phaseLabel: String {
        switch phase {
        case "none", "": return "Not started"
        case "approved": return "Approved"
        case "preflighted": return "Preflighted"
        case "running": return "Running"
        case "completed": return "Completed"
        case "failed": return "Failed"
        case "postflighted": return "Postflighted"
        default: return phase.capitalized
        }
    }
}

struct ContractSummary: Equatable, Sendable {
    var url: URL
    var campaignID: String
    var runID: String
    var argv: [String]
    var contractHash: String?
}

enum LifecycleAction: String, CaseIterable, Identifiable {
    case validate
    case approve
    case preflight
    case run
    case postflight
    case verify
    case dashboard

    var id: String { rawValue }

    var title: String {
        switch self {
        case .validate: return "Validate"
        case .approve: return "Approve…"
        case .preflight: return "Preflight"
        case .run: return "Run"
        case .postflight: return "Postflight"
        case .verify: return "Verify"
        case .dashboard: return "Dashboard"
        }
    }

    var isMutating: Bool {
        switch self {
        case .approve, .preflight, .run, .postflight: return true
        case .validate, .verify, .dashboard: return false
        }
    }

    var requiresTTY: Bool { self == .approve }

    var isDestructiveHint: Bool { self == .run }
}

struct AppError: Identifiable, Error, LocalizedError {
    let id = UUID()
    var message: String
    var errorDescription: String? { message }
}
