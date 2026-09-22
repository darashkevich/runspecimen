import Foundation

/// Copies the bundled reviewer workspace into Application Support so App
/// Review can open a complete campaign without a git tree or Open panel.
enum ReviewerDemoWorkspace {
    static let folderName = "ReviewerDemo"
    static let contractName = "contract.json"

    static func bundledRoot() -> URL? {
        let fm = FileManager.default
        var candidates: [URL] = []
        if let resource = Bundle.main.resourceURL {
            candidates.append(resource.appendingPathComponent(folderName, isDirectory: true))
        }
        if let direct = Bundle.main.url(forResource: folderName, withExtension: nil) {
            candidates.append(direct)
        }
        return candidates.first { fm.fileExists(atPath: $0.appendingPathComponent(contractName).path) }
    }

    static func materialize() throws -> URL {
        guard let source = bundledRoot() else {
            throw AppError(message: "Bundled reviewer demo is missing from this build (Resources/\(folderName)).")
        }
        let fm = FileManager.default
        let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? fm.temporaryDirectory
        let dest = support
            .appendingPathComponent("RunSpecimen", isDirectory: true)
            .appendingPathComponent(folderName, isDirectory: true)
        if fm.fileExists(atPath: dest.path) {
            try fm.removeItem(at: dest)
        }
        try fm.createDirectory(at: dest.deletingLastPathComponent(), withIntermediateDirectories: true)
        try fm.copyItem(at: source, to: dest)
        try? fm.removeItem(at: dest.appendingPathComponent(".runspecimen", isDirectory: true))
        return dest
    }
}
