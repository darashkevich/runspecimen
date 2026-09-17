import Foundation

/// Shared constants for the Mac companion helper.
/// Lifecycle enforcement remains in the Python CLI (`runspecimen companion`).
public enum CompanionBoundary {
    public static let mode = "observe"
    public static let canApprove = false
    public static let canExecute = false
    public static let adrRelativePath = "docs/ADR-003-ios-companion-observation.md"

    public static let operatorSummary = """
    RunSpecimen Mac companion helper is observation plumbing only.
    It does not approve, run, preflight, or postflight.
    Human approval remains real-TTY APPROVE on this Mac.
    This is not an OS sandbox.
    """
}

public struct CompanionLaunchPlan: Equatable, Sendable {
    public var workspace: String
    public var contract: String
    public var host: String
    public var allowLAN: Bool
    public var printToken: Bool

    public init(
        workspace: String,
        contract: String,
        host: String = "127.0.0.1",
        allowLAN: Bool = false,
        printToken: Bool = true
    ) {
        self.workspace = workspace
        self.contract = contract
        self.host = host
        self.allowLAN = allowLAN
        self.printToken = printToken
    }

    /// Arguments for `runspecimen companion …` — never includes approve/run.
    public var processArguments: [String] {
        var args = [
            "companion",
            "--workspace", workspace,
            "--contract", contract,
            "--host", host,
        ]
        if allowLAN { args.append("--allow-lan") }
        if printToken { args.append("--print-token") }
        return args
    }
}
