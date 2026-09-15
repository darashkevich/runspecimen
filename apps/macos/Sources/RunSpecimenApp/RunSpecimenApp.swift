import SwiftUI
import AppKit

@main
struct RunSpecimenApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .task { await model.bootstrap() }
                .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
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
            CommandMenu("RunSpecimen") {
                Button("Approve…") {
                    Task { await model.perform(.approve) }
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
                .frame(width: 520, height: 520)
        }
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
        .sheet(isPresented: $model.showApproveSheet) {
            ApproveSheet()
                .environmentObject(model)
                .frame(minWidth: 680, minHeight: 520)
        }
    }
}
