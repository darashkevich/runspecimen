import Foundation

/// Distribution channel stamped into Info.plist (`RSDistributionChannel`) by `build_app.sh`.
/// MAS builds fail closed without a frozen bundled helper and never fall through to PATH.
public enum DistributionChannel: String, Sendable, Equatable {
    case mas
    case developerID = "developer-id"
    case local

    public static var current: DistributionChannel {
        let raw = Bundle.main.object(forInfoDictionaryKey: "RSDistributionChannel") as? String
        return parse(raw)
    }

    public static func parse(_ raw: String?) -> DistributionChannel {
        switch (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "mas", "app-store", "appstore":
            return .mas
        case "developer-id", "developer_id", "notarized":
            return .developerID
        default:
            return .local
        }
    }

    /// Mac App Store / sandboxed Store builds: require Contents/Helpers; no PATH probe.
    public var requiresBundledHelper: Bool { self == .mas }

    /// Store builds must not depend on a host-installed PyPI CLI.
    public var allowsPATHProbe: Bool { self != .mas }

    /// The Store app uses native evidence views and never starts a listening server.
    public var allowsBrowserDashboard: Bool { self != .mas }

    public var label: String {
        switch self {
        case .mas: return "Mac App Store"
        case .developerID: return "Developer ID"
        case .local: return "Local"
        }
    }
}
