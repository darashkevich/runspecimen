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

    /// A stored contract path may only name a file inside the workspace.
    public static func isSafeRelativePath(_ relative: String) -> Bool {
        !relative.isEmpty
            && !relative.hasPrefix("/")
            && !relative.hasPrefix("~")
            && !relative.contains("..")
            && !relative.contains("\0")
    }

    /// Relative path of a regular file that stays inside the workspace after symlink resolution.
    public static func relativeContractPath(contract: URL, workspace: URL) -> String? {
        guard let contained = containedContract(contract: contract, workspace: workspace) else { return nil }
        let root = workspace.resolvingSymlinksInPath().standardizedFileURL
        let prefix = root.path == "/" ? "/" : root.path + (root.path.hasSuffix("/") ? "" : "/")
        guard contained.path.hasPrefix(prefix) else { return nil }
        let relative = String(contained.path.dropFirst(prefix.count))
        guard isSafeRelativePath(relative) else { return nil }
        return relative
    }

    /// True when the resolved URL sits strictly inside the workspace.
    /// Used to refuse snapshot restore destinations and exported files that would
    /// overwrite the workspace that holds the receipt.
    public static func isInsideWorkspace(url: URL, workspace: URL) -> Bool {
        let workspaceURL = workspace.resolvingSymlinksInPath().standardizedFileURL
        let target = url.resolvingSymlinksInPath().standardizedFileURL
        guard workspaceURL.isFileURL, target.isFileURL else { return false }
        let root = workspaceURL.path == "/" ? "/" : workspaceURL.path + (workspaceURL.path.hasSuffix("/") ? "" : "/")
        return target.path.hasPrefix(root) || target.path == workspaceURL.path
    }

    /// The Mac app stays running after the main window closes so File → Show
    /// Main Window and Command-0 can reopen it. Quit still happens from the
    /// application menu.
    public static let quitWhenLastWindowCloses = false
}
