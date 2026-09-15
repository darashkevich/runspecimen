import Foundation
import SwiftUI

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

    let cli = CLIService()
    private let bookmarks = BookmarkStore.shared

    var hasWorkspace: Bool { workspaceURL != nil }
    var hasCLI: Bool { cliIdentity != nil }
    var isReady: Bool { hasWorkspace && hasCLI && contractURL != nil }

    func bootstrap() async {
        if let cliURL = bookmarks.loadCLI() {
            await cli.setCLI(cliURL)
            await refreshCLIIdentity()
        } else if let probed = await cli.resolveFromPATH() {
            // PATH probe is convenience for non-sandbox / Developer ID debug only.
            // MAS builds should prefer Open-panel selection (persisted bookmark).
            pathProbeNote = "Found runspecimen on PATH. For App Store sandbox, re-select via Open panel."
            await cli.setCLI(probed)
            do {
                try bookmarks.saveCLI(probed)
            } catch {
                // Bookmark may fail outside sandbox grant; still usable this session.
            }
            await refreshCLIIdentity()
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
        guard url.lastPathComponent == "runspecimen" || url.path.contains("runspecimen") else {
            self.error = AppError(message: "Please select the runspecimen executable.")
            return
        }
        do {
            try bookmarks.saveCLI(url)
            await cli.setCLI(url)
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
        } catch {
            cliIdentity = nil
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

    func shutdown() {
        bookmarks.stopAll()
    }
}
