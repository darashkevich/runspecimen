import Foundation

/// Pure materialize rules for the bundled Reviewer Demo workspace.
/// Keeps evidence by default; destructive reset is explicit and lease-aware.
public enum ReviewerDemoMaterializer: Sendable {
    public static let folderName = "ReviewerDemo"
    public static let contractName = "contract.json"

    public enum Mode: Sendable, Equatable {
        /// Return the existing destination when it already has a contract.
        case reuseExisting
        /// Delete and recopy only when no workspace lease artifacts are present.
        case resetIfIdle
        /// Always create a unique sibling folder; never delete the fixed demo.
        case uniqueCopy
    }

    public enum MaterializeError: Error, Equatable, LocalizedError {
        case missingBundledSource
        case leaseHeld(path: String)
        case copyFailed(String)

        public var errorDescription: String? {
            switch self {
            case .missingBundledSource:
                return "Bundled reviewer demo source is missing."
            case .leaseHeld(let path):
                return "Refusing to reset Reviewer Demo while a workspace lease is present at \(path)."
            case .copyFailed(let message):
                return message
            }
        }
    }

    /// Fixed Application Support destination used by App Review.
    public static func fixedDestination(under supportDirectory: URL) -> URL {
        supportDirectory
            .appendingPathComponent("RunSpecimen", isDirectory: true)
            .appendingPathComponent(folderName, isDirectory: true)
    }

    public static func contractURL(in workspace: URL) -> URL {
        workspace.appendingPathComponent(contractName)
    }

    public static func hasUsableContract(at workspace: URL, fileManager: FileManager = .default) -> Bool {
        fileManager.fileExists(atPath: contractURL(in: workspace).path)
    }

    /// True when `.runspecimen/execution.lock` or `execution.meta.json` exists.
    /// Matches the engine lease layout (`paths.LEASE_*` under workspace state root).
    public static func leaseArtifactsPresent(at workspace: URL, fileManager: FileManager = .default) -> Bool {
        let root = workspace.appendingPathComponent(".runspecimen", isDirectory: true)
        let lock = root.appendingPathComponent("execution.lock")
        let meta = root.appendingPathComponent("execution.meta.json")
        return fileManager.fileExists(atPath: lock.path) || fileManager.fileExists(atPath: meta.path)
    }

    public static func materialize(
        source: URL,
        supportDirectory: URL,
        mode: Mode = .reuseExisting,
        fileManager: FileManager = .default,
        uniqueSuffix: String? = nil
    ) throws -> URL {
        guard fileManager.fileExists(atPath: contractURL(in: source).path) else {
            throw MaterializeError.missingBundledSource
        }

        switch mode {
        case .reuseExisting:
            let dest = fixedDestination(under: supportDirectory)
            if hasUsableContract(at: dest, fileManager: fileManager) {
                return dest
            }
            return try copyFresh(from: source, to: dest, fileManager: fileManager)

        case .resetIfIdle:
            let dest = fixedDestination(under: supportDirectory)
            if fileManager.fileExists(atPath: dest.path) {
                if leaseArtifactsPresent(at: dest, fileManager: fileManager) {
                    throw MaterializeError.leaseHeld(path: dest.path)
                }
                try fileManager.removeItem(at: dest)
            }
            return try copyFresh(from: source, to: dest, fileManager: fileManager)

        case .uniqueCopy:
            let suffix = uniqueSuffix ?? UUID().uuidString
            let dest = supportDirectory
                .appendingPathComponent("RunSpecimen", isDirectory: true)
                .appendingPathComponent("\(folderName)-\(suffix)", isDirectory: true)
            return try copyFresh(from: source, to: dest, fileManager: fileManager)
        }
    }

    private static func copyFresh(from source: URL, to dest: URL, fileManager: FileManager) throws -> URL {
        do {
            try fileManager.createDirectory(at: dest.deletingLastPathComponent(), withIntermediateDirectories: true)
            try fileManager.copyItem(at: source, to: dest)
            try? fileManager.removeItem(at: dest.appendingPathComponent(".runspecimen", isDirectory: true))
            return dest
        } catch {
            throw MaterializeError.copyFailed(error.localizedDescription)
        }
    }
}
