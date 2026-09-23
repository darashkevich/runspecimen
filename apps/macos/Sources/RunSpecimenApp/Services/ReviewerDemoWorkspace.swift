import Foundation
import RunSpecimenCore

/// Copies the bundled reviewer workspace into Application Support so App
/// Review can open a complete campaign without a git tree or Open panel.
///
/// Default policy reuses an existing copy so receipts and an in-progress demo
/// run are not silently deleted. Destructive reset is explicit and lease-aware.
enum ReviewerDemoWorkspace {
    static let folderName = ReviewerDemoMaterializer.folderName
    static let contractName = ReviewerDemoMaterializer.contractName

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

    /// Materialize the reviewer demo. Defaults to reuse; pass `.resetIfIdle` only
    /// for an explicit wipe when no lease artifacts are present.
    static func materialize(
        mode: ReviewerDemoMaterializer.Mode = .reuseExisting
    ) throws -> URL {
        guard let source = bundledRoot() else {
            throw AppError(message: "Bundled reviewer demo is missing from this build (Resources/\(folderName)).")
        }
        let fm = FileManager.default
        let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? fm.temporaryDirectory
        do {
            return try ReviewerDemoMaterializer.materialize(
                source: source,
                supportDirectory: support,
                mode: mode,
                fileManager: fm
            )
        } catch let error as ReviewerDemoMaterializer.MaterializeError {
            throw AppError(message: error.errorDescription ?? String(describing: error))
        } catch {
            throw AppError(message: error.localizedDescription)
        }
    }
}
