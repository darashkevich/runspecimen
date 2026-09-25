import Foundation

public enum SessionRestoreError: Error, Equatable, LocalizedError, Sendable {
    case contractOutsideWorkspace

    public var errorDescription: String? {
        switch self {
        case .contractOutsideWorkspace:
            return "Contract must be a regular file inside the selected workspace."
        }
    }
}

/// Decides which contract file a later launch may show again.
///
/// Restoration is path containment only. It does not materialize a demo,
/// clear receipts, or start a run.
public enum SessionRestore {
    /// A contract is restorable when the resolved file sits strictly inside the
    /// resolved workspace. Sibling names (`workspace-evil`) do not match.
    public static func containedContract(contract: URL, workspace: URL) -> URL? {
        let workspaceURL = workspace.resolvingSymlinksInPath().standardizedFileURL
        let contractURL = contract.resolvingSymlinksInPath().standardizedFileURL
        guard workspaceURL.isFileURL, contractURL.isFileURL else { return nil }
        let root = workspaceURL.path == "/" ? "/" : workspaceURL.path + (workspaceURL.path.hasSuffix("/") ? "" : "/")
        guard contractURL.path.hasPrefix(root) else { return nil }
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: contractURL.path, isDirectory: &isDirectory),
              !isDirectory.boolValue else {
            return nil
        }
        return contractURL
    }

    /// The Mac app stays running after the main window closes so File → Show
    /// Main Window and Command-0 can reopen it. Quit still happens from the
    /// application menu.
    public static let quitWhenLastWindowCloses = false
}
