import SwiftUI
import AppKit

@main
struct RunSpecimenApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .task {
                    appDelegate.model = model
                    await model.bootstrap()
                }
                .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
                    DashboardChild.shared.stop()
                    Task { @MainActor in
                        await model.shutdown()
                    }
                }
        }
        .windowStyle(.automatic)
        .defaultSize(width: 1180, height: 760)
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandMenu("Workspace") {
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
            CommandMenu("RunSpecimen") {
                Button("Approve…") {
                    Task { await model.requestPerform(.approve) }
                }
                .keyboardShortcut("a", modifiers: [.command, .shift])
                .disabled(!model.isActionEnabled(.approve))
                Button("Settings…") {
                    model.showSettings = true
                }
                .keyboardShortcut(",", modifiers: [.command])
            }
        }

        Settings {
            SettingsView()
                .environmentObject(model)
                .frame(width: 540, height: 560)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var model: AppModel?

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        // Ensure loopback dashboard is dead before quit (2.4.5(iii)).
        DashboardChild.shared.stop()
        return .terminateNow
    }

    func applicationWillTerminate(_ notification: Notification) {
        DashboardChild.shared.stop()
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
                .frame(minWidth: 680, minHeight: 520)
        }
    }
}
