import SwiftUI

struct ActionBar: View {
    @EnvironmentObject private var model: AppModel

    private let actions: [LifecycleAction] = [
        .validate, .approve, .preflight, .run, .postflight, .verify, .dashboard
    ]

    var body: some View {
        VStack(spacing: 8) {
            Divider().overlay(RSTheme.line)
            HStack(spacing: 10) {
                ForEach(actions) { action in
                    Button(action.title) {
                        Task { await model.requestPerform(action) }
                    }
                    .buttonStyle(ActionChipStyle(
                        amber: action == .approve,
                        destructive: action == .run
                    ))
                    .disabled(!model.isActionEnabled(action))
                    .help(help(for: action))
                    .accessibilityHint(help(for: action))
                }
                if model.dashboardRunning {
                    Button("Stop Dashboard") {
                        Task { await model.stopDashboard() }
                    }
                    .buttonStyle(ActionChipStyle())
                    .help("Terminate the loopback dashboard child process")
                }
                Spacer()
                if model.dashboardRunning {
                    CapsuleLabel(text: "Dashboard on", tone: .amber)
                        .accessibilityLabel("Dashboard running")
                }
                if model.isBusy {
                    ProgressView()
                        .controlSize(.small)
                        .accessibilityLabel("Working")
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(RSTheme.bgElevated.opacity(0.9))
        }
    }

    private func help(for action: LifecycleAction) -> String {
        switch action {
        case .approve:
            return "Opens an interactive PTY sheet. You must type APPROVE yourself. Shortcut: ⇧⌘A"
        case .dashboard:
            return "Opens the loopback read-only dashboard. It cannot approve or execute. Shortcut: ⇧⌘D"
        case .run:
            return "Executes one bounded run under the workspace lease (asks for confirmation). Shortcut: ⌘3"
        case .postflight:
            return "Runs postflight assertions (asks for confirmation). Shortcut: ⌘4"
        case .validate:
            return "Runs runspecimen validate. Shortcut: ⌘1"
        case .preflight:
            return "Runs runspecimen preflight. Shortcut: ⌘2"
        case .verify:
            return "Runs runspecimen verify. Shortcut: ⌘5"
        }
    }
}

struct ActionChipStyle: ButtonStyle {
    var amber: Bool = false
    var destructive: Bool = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold))
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(background.opacity(configuration.isPressed ? 0.7 : 1))
            )
            .foregroundStyle(foreground)
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(stroke, lineWidth: 1)
            )
    }

    private var background: Color {
        if amber { return RSTheme.amber.opacity(0.18) }
        if destructive { return RSTheme.signal.opacity(0.12) }
        return RSTheme.bgPanel
    }

    private var foreground: Color {
        if amber { return RSTheme.amber }
        return RSTheme.ink
    }

    private var stroke: Color {
        if amber { return RSTheme.amber.opacity(0.45) }
        if destructive { return RSTheme.signal.opacity(0.35) }
        return RSTheme.line
    }
}
