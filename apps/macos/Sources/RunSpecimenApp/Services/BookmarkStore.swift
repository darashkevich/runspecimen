import Foundation
import AppKit

/// Persists security-scoped bookmarks for workspace folders and the CLI binary.
/// Required for App Sandbox (Mac App Store Target A) and used for Target B parity.
@MainActor
final class BookmarkStore {
    static let shared = BookmarkStore()

    private let defaults = UserDefaults.standard
    private let workspaceKey = "rs.bookmark.workspace"
    private let cliKey = "rs.bookmark.cli"

    private var activeWorkspaceURL: URL?
    private var activeCLIURL: URL?

    func loadWorkspace() -> URL? {
        resolve(key: workspaceKey, storing: &activeWorkspaceURL)
    }

    func loadCLI() -> URL? {
        resolve(key: cliKey, storing: &activeCLIURL)
    }

    func saveWorkspace(_ url: URL) throws {
        try persist(url, key: workspaceKey, storing: &activeWorkspaceURL, readOnly: false)
    }

    func saveCLI(_ url: URL) throws {
        try persist(url, key: cliKey, storing: &activeCLIURL, readOnly: true)
    }

    func startAccessingWorkspace() -> URL? {
        guard let url = activeWorkspaceURL ?? loadWorkspace() else { return nil }
        _ = url.startAccessingSecurityScopedResource()
        activeWorkspaceURL = url
        return url
    }

    func startAccessingCLI() -> URL? {
        guard let url = activeCLIURL ?? loadCLI() else { return nil }
        _ = url.startAccessingSecurityScopedResource()
        activeCLIURL = url
        return url
    }

    func stopAll() {
        activeWorkspaceURL?.stopAccessingSecurityScopedResource()
        activeCLIURL?.stopAccessingSecurityScopedResource()
    }

    private func persist(_ url: URL, key: String, storing: inout URL?, readOnly: Bool) throws {
        storing?.stopAccessingSecurityScopedResource()
        var options: URL.BookmarkCreationOptions = [.withSecurityScope]
        if readOnly {
            options.insert(.securityScopeAllowOnlyReadAccess)
        }
        let data = try url.bookmarkData(options: options, includingResourceValuesForKeys: nil, relativeTo: nil)
        defaults.set(data, forKey: key)
        _ = url.startAccessingSecurityScopedResource()
        storing = url
    }

    private func resolve(key: String, storing: inout URL?) -> URL? {
        guard let data = defaults.data(forKey: key) else { return nil }
        var stale = false
        do {
            let url = try URL(
                resolvingBookmarkData: data,
                options: [.withSecurityScope],
                relativeTo: nil,
                bookmarkDataIsStale: &stale
            )
            if stale {
                // Refresh bookmark when possible.
                if let fresh = try? url.bookmarkData(
                    options: [.withSecurityScope],
                    includingResourceValuesForKeys: nil,
                    relativeTo: nil
                ) {
                    defaults.set(fresh, forKey: key)
                }
            }
            _ = url.startAccessingSecurityScopedResource()
            storing = url
            return url
        } catch {
            return nil
        }
    }
}

enum PanelPicker {
    @MainActor
    static func pickWorkspace() -> URL? {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.message = "Choose a RunSpecimen workspace folder"
        panel.prompt = "Select Workspace"
        guard panel.runModal() == .OK else { return nil }
        return panel.url
    }

    @MainActor
    static func pickCLI() -> URL? {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.treatsFilePackagesAsDirectories = true
        panel.message = "Choose the runspecimen executable (user-selected for App Sandbox)"
        panel.prompt = "Select CLI"
        guard panel.runModal() == .OK else { return nil }
        return panel.url
    }

    @MainActor
    static func pickContract(startingAt directory: URL?) -> URL? {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.json]
        panel.message = "Choose a RunSpecimen contract JSON"
        panel.prompt = "Select Contract"
        if let directory {
            panel.directoryURL = directory
        }
        guard panel.runModal() == .OK else { return nil }
        return panel.url
    }
}
