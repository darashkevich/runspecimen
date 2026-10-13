import SwiftUI

struct ActionBar: View {
    @EnvironmentObject private var model: AppModel

    private let actions: [LifecycleAction] = [
        .validate, .approve, .preflight, .run, .postflight, .verify, .dashboard
    ]

    private var highlighted: LifecycleAction? {
        ConsumerNextStep.current(
            phase: model.status?.phase ?? "none",
            doctorOK: model.doctor?.ok,
            hasCertificate: model.status?.certificateID != nil,
            isBusy: model.isBusy,
            leaseBusy: model.status?.leaseHeldByOther == true
        ).action
    }

    var body: some View {
        VStack(spacing: 0) {
            Divider().overlay(RSTheme.line)
            HStack(alignment: .center, spacing: 10) {
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 108), spacing: 8)],
                    alignment: .leading,
                    spacing: 8
                ) {
                    ForEach(actions.filter { $0 != .dashboard || model.isBrowserDashboardAvailable }) { action in
                        Button(action.consumerTitle) {
                            Task { await model.requestPerform(action) }
                        }
                        .buttonStyle(ActionChipStyle(
                            amber: action == .approve,
                            destructive: action == .run,
                            emphasized: action == highlighted
                        ))
                        .disabled(!model.isActionEnabled(action))
                        .help(help(for: action))
                        .accessibilityLabel(action.consumerTitle)
                        .accessibilityHint(help(for: action))
                    }
                    if model.dashboardRunning {
                        Button("Close timeline") {
                            Task { await model.stopDashboard() }
                        }
                        .buttonStyle(ActionChipStyle())
                        .help("Terminate the loopback dashboard child process")
                    }
                }
                Spacer(minLength: 8)
                if model.dashboardRunning {
                    CapsuleLabel(text: "Timeline open", tone: .amber)
                        .accessibilityLabel("Dashboard running")
                }
                if model.isBusy {
                    ProgressView()
                        .controlSize(.small)
                        .accessibilityLabel("Working")
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(RSTheme.bgElevated.opacity(0.94))
        }
    }

    private func help(for action: LifecycleAction) -> String {
        switch action {
        case .approve:
            return "Opens the review window. You must type APPROVE yourself. Shortcut: ⇧⌘A"
        case .dashboard:
            return "Opens the loopback read-only timeline. It cannot approve or execute. Shortcut: ⇧⌘D"
        case .run:
            return "Starts the approved command once (asks first). Shortcut: ⌘3"
        case .postflight:
            return "Checks that the run did what you allowed (asks first). Shortcut: ⌘4"
        case .validate:
            return "Checks the run plan. Shortcut: ⌘1"
        case .preflight:
            return "Last check that your yes is still valid. Shortcut: ⌘2"
        case .verify:
            return "Opens the checkable receipt. Shortcut: ⌘5"
        }
    }
}

struct ActionChipStyle: ButtonStyle {
    var amber: Bool = false
    var destructive: Bool = false
    var emphasized: Bool = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold))
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(background.opacity(configuration.isPressed ? 0.75 : 1))
            )
            .foregroundStyle(foreground)
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(stroke, lineWidth: emphasized ? 1.5 : 1)
            )
    }

    private var background: Color {
        if emphasized { return RSTheme.brand.opacity(0.16) }
        if amber { return RSTheme.amber.opacity(0.14) }
        if destructive { return RSTheme.brand.opacity(0.08) }
        return RSTheme.bgPanel
    }

    private var foreground: Color {
        if emphasized { return RSTheme.brand }
        if amber { return RSTheme.amber }
        return RSTheme.ink
    }

    private var stroke: Color {
        if emphasized { return RSTheme.brand.opacity(0.45) }
        if amber { return RSTheme.amber.opacity(0.40) }
        if destructive { return RSTheme.brand.opacity(0.22) }
        return RSTheme.line
    }
}
