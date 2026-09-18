import SwiftUI

@MainActor
final class EmptyStateMotion: ObservableObject {
    @Published var pulse = false
}

struct BrandEmptyState: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @StateObject private var motion = EmptyStateMotion()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top, spacing: 28) {
                    VStack(alignment: .leading, spacing: 18) {
                    HStack(spacing: 12) {
                        SignalMark(animated: !reduceMotion && motion.pulse)
                            .accessibilityHidden(true)
                        Text("RunSpecimen")
                            .font(.system(size: 42, weight: .bold, design: .default))
                            .minimumScaleFactor(0.6)
                            .lineLimit(1)
                            .foregroundStyle(RSTheme.ink)
                            .accessibilityAddTraits(.isHeader)
                    }

                    Text("One human-approved bounded run.\nLocal evidence. No telemetry.")
                        .font(.system(size: 20, weight: .regular))
                        .foregroundStyle(RSTheme.muted)
                        .lineSpacing(4)
                        .fixedSize(horizontal: false, vertical: true)

                    Text("Native control surface for the CLI enforcement engine. Approval stays interactive on a real TTY. The dashboard remains read-only.")
                        .font(.system(size: 14))
                        .foregroundStyle(RSTheme.soft)
                        .frame(maxWidth: 520, alignment: .leading)

                    FitHStack(spacing: 12, alignment: .center) {
                        Button {
                            Task { await model.chooseCLI() }
                        } label: {
                            Label(model.hasCLI ? "CLI selected" : "Select runspecimen CLI", systemImage: "terminal")
                        }
                        .buttonStyle(SignalButtonStyle(emphasized: !model.hasCLI))
                        .accessibilityHint(model.hasCLI ? "Change the selected runspecimen binary" : "Open a file picker to choose the runspecimen executable")

                        Button {
                            Task { await model.chooseWorkspace() }
                        } label: {
                            Label(model.hasWorkspace ? "Workspace selected" : "Open Workspace", systemImage: "folder")
                        }
                        .buttonStyle(SignalButtonStyle(emphasized: model.hasCLI && !model.hasWorkspace))
                        .disabled(!model.hasCLI)
                        .accessibilityHint("Choose a workspace folder via Open panel")
                    }
                    .padding(.top, 8)

                    if let issue = model.cliSetupIssue {
                        CLISetupBanner(
                            title: issue.lowercased().contains("version mismatch")
                                || issue.lowercased().contains("too old")
                                || issue.lowercased().contains("need 0.2")
                                || issue.lowercased().contains("need python")
                                ? (issue.lowercased().contains("python") ? "HOST PYTHON REQUIRED" : "CLI VERSION MISMATCH")
                                : "CLI SETUP REQUIRED",
                            message: issue
                        )
                            .padding(.top, 16)
                    } else if let note = model.pathProbeNote {
                        Text(note)
                            .font(.system(size: 12))
                            .foregroundStyle(RSTheme.amber)
                            .frame(maxWidth: 520, alignment: .leading)
                            .padding(.top, 12)
                            .accessibilityLabel("CLI discovery note")
                            .accessibilityValue(note)
                    }

                    NonGoalsStrip()
                        .padding(.top, 28)
                    }
                    .frame(maxWidth: 640, alignment: .leading)

                    Spacer(minLength: 0)
                }

                FooterHint()
                    .padding(.top, 36)
                    .padding(.bottom, 8)
            }
            .padding(.horizontal, 32)
            .padding(.vertical, 28)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .onAppear {
            if !reduceMotion {
                withAnimation(.easeInOut(duration: 2.4).repeatForever(autoreverses: true)) {
                    motion.pulse = true
                }
            }
        }
    }
}

struct SignalMark: View {
    var animated: Bool

    var body: some View {
        Circle()
            .fill(
                RadialGradient(
                    colors: [Color(red: 0.85, green: 1.0, blue: 0.69), RSTheme.signal, RSTheme.signalDeep],
                    center: .topLeading,
                    startRadius: 1,
                    endRadius: 16
                )
            )
            .frame(width: 14, height: 14)
            .shadow(color: RSTheme.signal.opacity(animated ? 0.55 : 0.25), radius: animated ? 10 : 4)
            .accessibilityLabel("RunSpecimen signal mark")
    }
}

struct NonGoalsStrip: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("HONEST NON-GOALS")
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(RSTheme.amber)
                .tracking(1.2)
            Text("Not an OS sandbox · Not a scheduler · Not compliance theater · Receipts are local hash chains, not digital signatures")
                .font(.system(size: 12))
                .foregroundStyle(RSTheme.soft)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}

struct CLISetupBanner: View {
    var title: String = "CLI SETUP REQUIRED"
    var message: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(RSTheme.danger)
                .tracking(1.0)
            Text(message)
                .font(.system(size: 13))
                .foregroundStyle(RSTheme.ink)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(RSTheme.danger.opacity(0.1))
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .stroke(RSTheme.danger.opacity(0.35), lineWidth: 1)
                )
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel(title)
        .accessibilityValue(message)
    }
}

struct FooterHint: View {
    var body: some View {
        Text("Install: python3 -m pip install 'runspecimen==0.2.0rc10'   ·   Local-only · Apache-2.0")
            .font(RSTheme.monoSmall)
            .foregroundStyle(RSTheme.soft)
    }
}

struct SignalButtonStyle: ButtonStyle {
    var emphasized: Bool = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 14, weight: .semibold))
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(emphasized ? RSTheme.signal.opacity(configuration.isPressed ? 0.85 : 1) : RSTheme.bgPanel)
            )
            .foregroundStyle(emphasized ? Color.black.opacity(0.85) : RSTheme.ink)
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(emphasized ? RSTheme.signalDeep : RSTheme.line, lineWidth: 1)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
