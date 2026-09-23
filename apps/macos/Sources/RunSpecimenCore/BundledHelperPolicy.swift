import Foundation

/// MAS / Store builds may only execute the staged Contents/Helpers (or
/// Resources/RunSpecimenEngine) binary. External Open-panel bookmarks and PATH
/// probes are ignored at discovery and refused at execution.
public enum BundledHelperPolicy: Sendable {
    public static func allowsExternalCLI(channel: DistributionChannel) -> Bool {
        !channel.requiresBundledHelper
    }

    /// Whether `candidate` is the bundled helper (same resolved path, or under
    /// known in-app helper locations).
    public static func isBundledHelper(_ candidate: URL, bundled: URL?) -> Bool {
        let resolved = candidate.resolvingSymlinksInPath().standardizedFileURL.path
        if let bundled {
            let bundledPath = bundled.resolvingSymlinksInPath().standardizedFileURL.path
            if resolved == bundledPath {
                return true
            }
        }
        // Path-shape fallback for tests / odd Bundle layouts.
        return resolved.contains("/Contents/Helpers/runspecimen")
            || resolved.hasSuffix("/Contents/Helpers/runspecimen")
            || resolved.contains("/RunSpecimenEngine/runspecimen")
            || resolved.hasSuffix("/RunSpecimenEngine/runspecimen")
    }

    public static func acceptsCLI(
        _ candidate: URL,
        channel: DistributionChannel,
        bundled: URL?
    ) -> Bool {
        if allowsExternalCLI(channel: channel) {
            return true
        }
        return isBundledHelper(candidate, bundled: bundled)
    }

    public static func rejectionMessage(for channel: DistributionChannel) -> String {
        "\(channel.label) builds use the bundled engine only. External CLI bookmarks and host installs are ignored. Use Prefer Bundled Helper."
    }
}
