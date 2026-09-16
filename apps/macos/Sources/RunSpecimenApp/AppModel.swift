import Foundation
import SwiftUI
import AppKit
import RunSpecimenCore

@MainActor
final class AppModel: ObservableObject {
    @Published var cliIdentity: CLIIdentity?
    @Published var workspaceURL: URL?
    @Published var contractURL: URL?
    @Published var contract: ContractSummary?
    @Published var doctor: DoctorReport?
    @Published var status: RunStatus?
    @Published var lastOutput: String = ""
    @Published var statusError: String?
    @Published var isBusy = false
    @Published var error: AppError?
    @Published var showApproveSheet = false
    @Published var showSettings = false
    @Published var showAbout = false
    @Published var pathProbeNote: String?
    /// Persistent banner when CLI is missing, stale bookmark, or below 0.2.0rc9.
    @Published var cliSetupIssue: String?
    @Published var cliSourceLabel: String?
    @Published var dashboardRunning = false
    /// Lifecycle action awaiting user confirmation (Run / Postflight).
    @Published var pendingConfirmAction: LifecycleAction?

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
            // Sync path — async Task may not finish before process exit.
            DashboardChild.shared.stop()
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
        cliSourceLabel = nil

        // Discovery order (ADR-002):
        // 1) Security-scoped bookmark (sandbox / MAS / user override)
        // 2) Bundled Contents/Helpers/runspecimen when staged
        // 3) PATH / common PyPI install locations (Developer ID / local only — never MAS)

        let channel = DistributionChannel.current

        if let cliURL = bookmarks.loadCLI() {
            let fm = FileManager.default
            if fm.isExecutableFile(atPath: cliURL.path) {
                await cli.setCLI(cliURL, source: .bookmark)
                await refreshCLIIdentity()
            } else {
                cliSetupIssue = "Saved CLI bookmark points to a missing binary:\n\(cliURL.path)\nRe-select runspecimen via Open panel."
            }
        }

        if cliIdentity == nil, let bundled = cli.resolveBundledHelper() {
            if channel.requiresBundledHelper, CLIService.isShellScript(at: bundled) {
                // MAS Store builds must ship a frozen Mach-O helper — host Python is not allowed.
                cliSetupIssue = "Mac App Store build requires a self-contained frozen helper under Contents/Helpers (Mach-O). Host-Python package-tree launchers are not permitted. Rebuild with ./Scripts/build_app.sh --mas."
            } else {
                pathProbeNote = "Using bundled engine at \(bundled.path)."
                await cli.setCLI(bundled, source: .bundledHelper)
                await refreshCLIIdentity()
            }
        }

        if cliIdentity == nil, channel.allowsPATHProbe {
            if let probed = cli.resolveFromPATH() {
                // Session-only — never persist PATH probes as bookmarks. Auto-saving
                // fought “Prefer Bundled Helper” / “Clear CLI Bookmark” (next launch
                // looked like an Open-panel override).
                pathProbeNote = "Found runspecimen at \(probed.path). For App Store sandbox, select it via Open panel so a security-scoped bookmark is stored."
                await cli.setCLI(probed, source: .pathProbe)
                await refreshCLIIdentity()
            }
        }

        if cliIdentity == nil && cliSetupIssue == nil {
            if channel.requiresBundledHelper {
                cliSetupIssue = "Mac App Store build: bundled runspecimen helper missing or not executable under Contents/Helpers. This build fails closed — no host Python / PATH fallback."
            } else {
                cliSetupIssue = "runspecimen CLI not found. Install 0.2.0rc10+ then select the binary:\npython3 -m pip install 'runspecimen==0.2.0rc10'\n\nOr stage a helper into Contents/Helpers (see Helpers/README.md)."
            }
        }

        if let ws = bookmarks.loadWorkspace() {
            workspaceURL = ws
        }

        await refreshDashboardFlag()
    }

    func chooseWorkspace() async {
        guard let url = PanelPicker.pickWorkspace() else { return }
        do {
            try bookmarks.saveWorkspace(url)
            workspaceURL = url
            contractURL = nil
            contract = nil
            status = nil
            statusError = nil
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
            await cli.setCLI(url, source: .manual)
            cliSetupIssue = nil
            pathProbeNote = nil
            await refreshCLIIdentity()
        } catch {
            self.error = AppError(message: error.localizedDescription)
        }
    }

    /// Clear the Open-panel CLI bookmark and re-run ADR-002 discovery
    /// (Helpers → PATH). Use this to confirm a staged Contents/Helpers engine.
    func clearCLIBookmarkAndRediscover() async {
        bookmarks.clearCLI()
        await cli.setCLI(nil, source: .manual)
        cliIdentity = nil
        cliSourceLabel = nil
        cliSetupIssue = nil
        pathProbeNote = nil
        await bootstrap()
    }

    /// Prefer a staged Contents/Helpers/runspecimen when present (skips bookmark).
    /// Does not fall through to PATH or re-persist bookmarks — avoids racing the
    /// explicit “use bundled” choice against a prior Open-panel / PATH session.
    func preferBundledHelper() async {
        bookmarks.clearCLI()
        await cli.setCLI(nil, source: .manual)
        cliIdentity = nil
        cliSourceLabel = nil
        cliSetupIssue = nil
        pathProbeNote = nil
        guard let bundled = cli.resolveBundledHelper() else {
            if DistributionChannel.current.requiresBundledHelper {
                cliSetupIssue = "No executable under Contents/Helpers/runspecimen. MAS builds fail closed — rebuild with ./Scripts/build_app.sh --mas (frozen helper required)."
            } else {
                cliSetupIssue = "No executable under Contents/Helpers/runspecimen. Stage with Scripts/stage_helper.sh --from-src or ./Scripts/build_app.sh --frozen-helper, then rebuild."
            }
            return
        }
        if DistributionChannel.current.requiresBundledHelper, CLIService.isShellScript(at: bundled) {
            cliSetupIssue = "Bundled helper is a host-Python launcher. Mac App Store builds require a frozen Mach-O helper (./Scripts/build_app.sh --mas)."
            return
        }
        pathProbeNote = "Using bundled engine at \(bundled.path)."
        await cli.setCLI(bundled, source: .bundledHelper)
        await refreshCLIIdentity()
        if cliIdentity == nil, cliSetupIssue == nil {
            cliSetupIssue = "Bundled helper at \(bundled.path) did not report a usable RunSpecimen version."
        }
    }

    func chooseContract() async {
        guard let url = PanelPicker.pickContract(startingAt: workspaceURL) else { return }
        contractURL = url
        statusError = nil
        await loadContractSummary()
        await refreshStatus()
    }

    func refreshAll() async {
        await refreshCLIIdentity()
        await runDoctor()
        await loadContractSummary()
        await refreshStatus()
        await refreshDashboardFlag()
    }

    func refreshCLIIdentity() async {
        do {
            let identity = try await cli.version()
            cliIdentity = identity
            cliSourceLabel = identity.source.label
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
            statusError = nil
        } catch {
            let message = (error as? AppError)?.message ?? error.localizedDescription
            // Missing run state is normal for a fresh contract.
            let lowered = message.lowercased()
            if lowered.contains("not found") || lowered.contains("no such") || lowered.contains("none") {
                status = nil
                statusError = nil
                lastOutput = message
            } else {
                status = nil
                statusError = message
                lastOutput = message
            }
        }
    }

    /// Entry point for UI / shortcuts — may present a confirmation first.
    func requestPerform(_ action: LifecycleAction) async {
        guard isActionEnabled(action) else { return }
        if action.requiresConfirmation {
            pendingConfirmAction = action
            return
        }
        await perform(action)
    }

    func confirmPendingAction() async {
        guard let action = pendingConfirmAction else { return }
        pendingConfirmAction = nil
        await perform(action)
    }

    func cancelPendingAction() {
        pendingConfirmAction = nil
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
            statusError = nil
            await refreshStatus()
            await runDoctor()
            await refreshDashboardFlag()
        } catch {
            self.error = AppError(message: (error as? AppError)?.message ?? error.localizedDescription)
            await refreshDashboardFlag()
        }
    }

    func stopDashboard() async {
        await cli.stopDashboard()
        cli.stopDashboardSync()
        await refreshDashboardFlag()
        lastOutput = "Dashboard stopped."
    }

    func refreshDashboardFlag() async {
        dashboardRunning = await cli.isDashboardRunning() || DashboardChild.shared.isRunning
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
        cli.stopDashboardSync()
        bookmarks.stopAll()
        dashboardRunning = false
    }
}
