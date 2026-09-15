import Foundation
import SwiftUI
import AppKit

@MainActor
final class AppModel: ObservableObject {
    @Published var cliIdentity: CLIIdentity?
    @Published var workspaceURL: URL?
    @Published var contractURL: URL?
    @Published var contract: ContractSummary?
    @Published var doctor: DoctorReport?
    @Published var status: RunStatus?
    @Published var lastOutput: String = ""
    @Published var isBusy = false
    @Published var error: AppError?
    @Published var showApproveSheet = false
    @Published var showSettings = false
    @Published var pathProbeNote: String?
    /// Persistent banner when CLI is missing, stale bookmark, or below 0.2.0rc9.
    @Published var cliSetupIssue: String?

    let cli = CLIService()
    private let bookmarks = BookmarkStore.shared
    private var terminateObserver: NSObjectProtocol?

    var hasWorkspace: Bool { workspaceURL != nil }
    var hasCLI: Bool { cliIdentity != nil }
    var isReady: Bool { hasWorkspace && hasCLI && contractURL != nil }

    init() {
        terminateObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                await self?.shutdown()
            }
        }
    }

    deinit {
        if let terminateObserver {
            NotificationCenter.default.removeObserver(terminateObserver)
        }
    }

    func bootstrap() async {
        cliSetupIssue = nil
        pathProbeNote = nil

        // 1) Restore security-scoped bookmark (sandbox / MAS path).
        if let cliURL = bookmarks.loadCLI() {
            let fm = FileManager.default
            if fm.isExecutableFile(atPath: cliURL.path) {
                await cli.setCLI(cliURL)
                await refreshCLIIdentity()
            } else {
                cliSetupIssue = "Saved CLI bookmark points to a missing binary:\n\(cliURL.path)\nRe-select runspecimen via Open panel."
            }
        }

        // 2) PATH / common PyPI install locations (Developer ID / local convenience).
        if cliIdentity == nil {
            if let probed = await cli.resolveFromPATH() {
                pathProbeNote = "Found runspecimen at \(probed.path). For App Store sandbox, re-select via Open panel so a security-scoped bookmark is stored."
                await cli.setCLI(probed)
                do {
                    try bookmarks.saveCLI(probed)
                } catch {
                    // Bookmark may fail outside sandbox grant; still usable this session.
                }
                await refreshCLIIdentity()
            }
        }

        if cliIdentity == nil && cliSetupIssue == nil {
            cliSetupIssue = "runspecimen CLI not found. Install 0.2.0rc9+ then select the binary:\npython3 -m pip install 'runspecimen==0.2.0rc9'"
        }

        if let ws = bookmarks.loadWorkspace() {
            workspaceURL = ws
        }
    }

    func chooseWorkspace() async {
        guard let url = PanelPicker.pickWorkspace() else { return }
        do {
            try bookmarks.saveWorkspace(url)
            workspaceURL = url
            contractURL = nil
            contract = nil
            status = nil
            await runDoctor()
        } catch {
            self.error = AppError(message: error.localizedDescription)
        }
    }

    func chooseCLI() async {
        guard let url = PanelPicker.pickCLI() else { return }
        let name = url.lastPathComponent
        guard name == "runspecimen" || name.hasPrefix("runspecimen") else {
            self.error = AppError(message: "Please select the runspecimen executable (basename must be runspecimen).")
            return
        }
        do {
            try bookmarks.saveCLI(url)
            await cli.setCLI(url)
            cliSetupIssue = nil
            await refreshCLIIdentity()
        } catch {
            self.error = AppError(message: error.localizedDescription)
        }
    }

    func chooseContract() async {
        guard let url = PanelPicker.pickContract(startingAt: workspaceURL) else { return }
        contractURL = url
        await loadContractSummary()
        await refreshStatus()
    }

    func refreshAll() async {
        await refreshCLIIdentity()
        await runDoctor()
        await loadContractSummary()
        await refreshStatus()
    }

    func refreshCLIIdentity() async {
        do {
            cliIdentity = try await cli.version()
            cliSetupIssue = nil
        } catch {
            cliIdentity = nil
            let message = (error as? AppError)?.message ?? error.localizedDescription
            cliSetupIssue = message
            if let appError = error as? AppError {
                self.error = appError
            }
        }
    }

    func runDoctor() async {
        guard let workspaceURL else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            _ = bookmarks.startAccessingWorkspace()
            _ = bookmarks.startAccessingCLI()
            doctor = try await cli.doctor(workspace: workspaceURL)
        } catch {
            self.error = AppError(message: (error as? AppError)?.message ?? error.localizedDescription)
        }
    }

    func loadContractSummary() async {
        guard let contractURL else { return }
        do {
            let data = try Data(contentsOf: contractURL)
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            let argv = obj["argv"] as? [String] ?? []
            contract = ContractSummary(
                url: contractURL,
                campaignID: obj["campaign_id"] as? String ?? "",
                runID: obj["run_id"] as? String ?? "",
                argv: argv,
                contractHash: nil
            )
        } catch {
            self.error = AppError(message: "Could not read contract: \(error.localizedDescription)")
        }
    }

    func refreshStatus() async {
        guard let workspaceURL, let contract else { return }
        guard !contract.campaignID.isEmpty, !contract.runID.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            _ = bookmarks.startAccessingWorkspace()
            _ = bookmarks.startAccessingCLI()
            status = try await cli.status(
                workspace: workspaceURL,
                campaignID: contract.campaignID,
                runID: contract.runID,
                contract: contractURL
            )
        } catch {
            // Missing run state is normal for a fresh contract.
            let message = (error as? AppError)?.message ?? error.localizedDescription
            if message.lowercased().contains("error") {
                status = nil
                lastOutput = message
            }
        }
    }

    func perform(_ action: LifecycleAction) async {
        guard let workspaceURL, let contractURL, let contract else {
            error = AppError(message: "Select workspace and contract first.")
            return
        }
        if action == .approve {
            showApproveSheet = true
            return
        }
        isBusy = true
        defer { isBusy = false }
        do {
            _ = bookmarks.startAccessingWorkspace()
            _ = bookmarks.startAccessingCLI()
            lastOutput = try await cli.runLifecycle(
                action: action,
                workspace: workspaceURL,
                contract: contractURL,
                campaignID: contract.campaignID,
                runID: contract.runID
            )
            await refreshStatus()
            await runDoctor()
        } catch {
            self.error = AppError(message: (error as? AppError)?.message ?? error.localizedDescription)
        }
    }

    func isActionEnabled(_ action: LifecycleAction) -> Bool {
        guard isReady, !isBusy else { return false }
        if doctor?.ok == false { return action == .validate || action == .dashboard }
        let phase = status?.phase ?? "none"
        switch action {
        case .validate, .dashboard:
            return true
        case .approve:
            return phase == "none" || phase == "approved" || phase.isEmpty
        case .preflight:
            return phase == "approved" || phase == "preflighted"
        case .run:
            return phase == "approved" || phase == "preflighted"
        case .postflight:
            return phase == "completed" || phase == "failed"
        case .verify:
            return phase == "postflighted" || status?.certificateID != nil
        }
    }

    func shutdown() async {
        await cli.stopDashboard()
        bookmarks.stopAll()
    }
}
