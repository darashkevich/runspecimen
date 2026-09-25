import SwiftUI
import AppKit
#if canImport(RunSpecimenCore)
import RunSpecimenCore
#endif

@main
struct RunSpecimenApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var model = AppModel()
    @Environment(\.openWindow) private var openWindow

    var body: some Scene {
        Window("RunSpecimen", id: "main") {
            RootView()
                .environmentObject(model)
                .frame(minWidth: WindowPlacement.minSize.width, minHeight: WindowPlacement.minSize.height)
                .task {
                    appDelegate.model = model
                    await model.bootstrapOnce()
                }
                .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
                    DashboardChild.shared.stop()
                    Task { @MainActor in
                        await model.shutdown()
                    }
                }
        }
        .windowStyle(.automatic)
        .windowResizability(.contentMinSize)
        .defaultPosition(.center)
        .defaultSize(width: WindowPlacement.defaultSize.width, height: WindowPlacement.defaultSize.height)
        .commands {
            CommandGroup(after: .newItem) {
                Button("Show Main Window") {
                    let open = { openWindow(id: "main") }
                    appDelegate.openMainWindow = open
                    open()
                }
                .keyboardShortcut("0", modifiers: [.command])
            }
            CommandGroup(replacing: .appInfo) {
                Button("About RunSpecimen") {
                    model.showAbout = true
                }
            }
            CommandGroup(after: .appInfo) {
                Button("Privacy Policy…") {
                    NSWorkspace.shared.open(AppLinks.privacyPolicy)
                }
                Divider()
            }
            CommandMenu("Workspace") {
                Button("Open Reviewer Demo") {
                    Task { await model.openReviewerDemo() }
                }
                .keyboardShortcut("d", modifiers: [.command, .option, .shift])
                Button("Open Workspace…") {
                    Task { await model.chooseWorkspace() }
                }
                .keyboardShortcut("o", modifiers: [.command])
                Button("Open Contract…") {
                    Task { await model.chooseContract() }
                }
                .keyboardShortcut("o", modifiers: [.command, .shift])
                Divider()
                Button("Refresh Status") {
                    Task { await model.refreshAll() }
                }
                .keyboardShortcut("r", modifiers: [.command])
                Button("Refresh Evidence") {
                    Task { await model.refreshEvidenceDetails() }
                }
                .disabled(model.isBusy || !model.hasWorkspace)
                Button("Workflows…") {
                    model.showWorkflows = true
                }
                .disabled(!model.hasWorkspace)
            }
            CommandMenu("Lifecycle") {
                Button("Validate") {
                    Task { await model.requestPerform(.validate) }
                }
                .keyboardShortcut("1", modifiers: [.command])
                .disabled(!model.isActionEnabled(.validate))
                Button("Approve…") {
                    Task { await model.requestPerform(.approve) }
                }
                .keyboardShortcut("a", modifiers: [.command, .shift])
                .disabled(!model.isActionEnabled(.approve))
                Button("Preflight") {
                    Task { await model.requestPerform(.preflight) }
                }
                .keyboardShortcut("2", modifiers: [.command])
                .disabled(!model.isActionEnabled(.preflight))
                Button("Run…") {
                    Task { await model.requestPerform(.run) }
                }
                .keyboardShortcut("3", modifiers: [.command])
                .disabled(!model.isActionEnabled(.run))
                Button("Postflight…") {
                    Task { await model.requestPerform(.postflight) }
                }
                .keyboardShortcut("4", modifiers: [.command])
                .disabled(!model.isActionEnabled(.postflight))
                Button("Verify") {
                    Task { await model.requestPerform(.verify) }
                }
                .keyboardShortcut("5", modifiers: [.command])
                .disabled(!model.isActionEnabled(.verify))
                Divider()
                if DistributionChannel.current.allowsBrowserDashboard {
                    Button("Open Dashboard") {
                        Task { await model.requestPerform(.dashboard) }
                    }
                    .keyboardShortcut("d", modifiers: [.command, .shift])
                    .disabled(!model.isActionEnabled(.dashboard))
                    Button("Stop Dashboard") {
                        Task { await model.stopDashboard() }
                    }
                    .keyboardShortcut("d", modifiers: [.command, .option])
                    .disabled(!model.dashboardRunning)
                }
            }
            CommandMenu("Engine") {
                if !DistributionChannel.current.requiresBundledHelper {
                    Button("Select runspecimen CLI…") {
                        Task { await model.chooseCLI() }
                    }
                }
                Button("Prefer Bundled Helper") {
                    Task { await model.preferBundledHelper() }
                }
                Button("Clear CLI Bookmark & Rediscover") {
                    Task { await model.clearCLIBookmarkAndRediscover() }
                }
                Divider()
                Button("Settings…") {
                    model.showSettings = true
                }
                .keyboardShortcut(",", modifiers: [.command])
            }
            CommandGroup(replacing: .help) {
                Button("RunSpecimen Help") {
                    NSWorkspace.shared.open(AppLinks.site)
                }
                Button("User Guide") {
                    NSWorkspace.shared.open(AppLinks.userGuide)
                }
                Button("Privacy Policy") {
                    NSWorkspace.shared.open(AppLinks.privacyPolicy)
                }
                Button("Security Policy") {
                    NSWorkspace.shared.open(AppLinks.securityPolicy)
                }
            }
        }

        Settings {
            SettingsView()
                .environmentObject(model)
                .frame(minWidth: 420, minHeight: 480)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var model: AppModel?
    var openMainWindow: (() -> Void)?

    func applicationDidFinishLaunching(_ notification: Notification) {
        if MasSandboxE2E.isRequested {
            Task { @MainActor in
                await MasSandboxE2E.runAndExit()
            }
            return
        }
        WindowSanitizer.install()
        DispatchQueue.main.async {
            self.presentMainWindowIfNeeded()
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        SessionRestore.quitWhenLastWindowCloses
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        // Ensure loopback dashboard is dead before quit (2.4.5(iii)).
        DashboardChild.shared.stop()
        return .terminateNow
    }

    func applicationWillTerminate(_ notification: Notification) {
        DashboardChild.shared.stop()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            presentMainWindowIfNeeded()
        }
        WindowSanitizer.apply()
        return true
    }

    /// SwiftUI remembers a closed main window. File → Show Main Window and a
    /// later launch both need a visible window without resetting the workspace.
    func presentMainWindowIfNeeded() {
        if NSApp.windows.contains(where: { $0.isVisible && !$0.isSheet && $0.level == .normal }) {
            return
        }
        if let openMainWindow {
            openMainWindow()
            return
        }
        guard let file = NSApp.mainMenu?.items.first(where: { $0.title == "File" })?.submenu,
              let item = file.items.first(where: { $0.title == "Show Main Window" }),
              let action = item.action else {
            return
        }
        NSApp.sendAction(action, to: item.target, from: item)
    }
}

struct RootView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ZStack {
            AtmosphericBackground()
            if model.hasWorkspace && model.hasCLI {
                MainConsoleView()
            } else {
                BrandEmptyState()
            }
        }
        .preferredColorScheme(.dark)
        .alert(item: $model.error) { err in
            Alert(title: Text("RunSpecimen"), message: Text(err.message), dismissButton: .default(Text("OK")))
        }
        .confirmationDialog(
            model.pendingConfirmAction?.confirmationTitle ?? "Confirm",
            isPresented: Binding(
                get: { model.pendingConfirmAction != nil },
                set: { if !$0 { model.cancelPendingAction() } }
            ),
            titleVisibility: .visible
        ) {
            if let action = model.pendingConfirmAction {
                Button(action.title, role: action == .run ? .destructive : nil) {
                    Task { await model.confirmPendingAction() }
                }
                Button("Cancel", role: .cancel) {
                    model.cancelPendingAction()
                }
            }
        } message: {
            Text(model.pendingConfirmAction?.confirmationMessage ?? "")
        }
        .sheet(isPresented: $model.showApproveSheet) {
            ApproveSheet()
                .environmentObject(model)
                .frame(minWidth: 520, idealWidth: 680, minHeight: 420, idealHeight: 520)
        }
        .sheet(isPresented: $model.showAbout) {
            AboutView()
                .environmentObject(model)
                .frame(minWidth: 420, minHeight: 360)
        }
        .sheet(isPresented: $model.showWorkflows) {
            WorkflowSheet()
                .environmentObject(model)
        }
        .sheet(isPresented: $model.showSettings) {
            SettingsView()
                .environmentObject(model)
                .frame(minWidth: 420, minHeight: 480)
        }
    }
}
