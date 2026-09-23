import SwiftUI
#if canImport(RunSpecimenCore)
import RunSpecimenCore
#endif

struct MainConsoleView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        VStack(spacing: 0) {
            TopBar()
            Divider().overlay(RSTheme.line)
            if let issue = model.cliSetupIssue {
                Text(issue)
                    .font(.system(size: 12))
                    .foregroundStyle(RSTheme.danger)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(RSTheme.danger.opacity(0.08))
                    .accessibilityLabel(
                        issue.lowercased().contains("version mismatch")
                            ? "CLI version mismatch"
                            : "CLI setup issue"
                    )
                    .accessibilityValue(issue)
            }
            if model.contractURL == nil {
                ContractPrompt()
            } else {
                GeometryReader { geo in
                    let stacked = geo.size.width < 880
                    if stacked {
                        VStack(spacing: 12) {
                            StatusLifecycleView()
                                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                            EvidenceInspectorView()
                                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                        }
                        .padding(.horizontal, 16)
                        .padding(.top, 12)
                    } else {
                        HSplitView {
                            StatusLifecycleView()
                                .frame(minWidth: 280, idealWidth: 420)
                            EvidenceInspectorView()
                                .frame(minWidth: 320)
                        }
                        .padding(.horizontal, 16)
                        .padding(.top, 12)
                    }
                }
            }
            ActionBar()
        }
    }
}

struct TopBar: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        ViewThatFits(in: .horizontal) {
            bar(showPath: true)
            bar(showPath: false)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(RSTheme.bg.opacity(0.72))
    }

    private func bar(showPath: Bool) -> some View {
        HStack(spacing: 10) {
            HStack(spacing: 8) {
                SignalMark(animated: false)
                Text("RunSpecimen")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(RSTheme.ink)
                    .lineLimit(1)
            }
            .accessibilityElement(children: .combine)
            .layoutPriority(1)

            CapsuleLabel(text: model.cliIdentity?.version ?? "CLI missing", tone: model.hasCLI ? .signal : .amber)
                .accessibilityLabel(model.hasCLI ? "CLI version \(model.cliIdentity?.version ?? "")" : "CLI missing")
                .help(model.cliSourceLabel.map { "Source: \($0)" } ?? (DistributionChannel.current.requiresBundledHelper ? "Bundled engine missing" : "Select or install runspecimen 0.2.0rc14+"))
                .layoutPriority(1)

            if let source = model.cliSourceLabel ?? model.cliIdentity?.source.label {
                CapsuleLabel(text: source, tone: source == "Bundled Helpers" ? .signal : .amber)
                    .accessibilityLabel("CLI source \(source)")
                    .help("Discovery source (ADR-002). Prefer Bundled Helper forces Contents/Helpers.")
            }
            if model.dashboardRunning {
                CapsuleLabel(text: "Dashboard", tone: .amber)
                    .accessibilityLabel("Dashboard child process running")
                    .help("Loopback dashboard is running; it stops on quit or Stop Dashboard")
            }

            if showPath, let path = model.workspaceURL?.path {
                Text(path)
                    .font(RSTheme.monoSmall)
                    .foregroundStyle(RSTheme.muted)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .help(path)
                    .layoutPriority(0)
            }

            Spacer(minLength: 8)

            Button("Contract…") { Task { await model.chooseContract() } }
            Button("Workspace…") { Task { await model.chooseWorkspace() } }
            Button {
                Task { await model.refreshAll() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(model.isBusy)
            .keyboardShortcut("r", modifiers: [.command])
        }
    }
}

struct ContractPrompt: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        VStack(spacing: 16) {
            Spacer()
            Text("Select a contract")
                .font(RSTheme.titleFont)
                .foregroundStyle(RSTheme.ink)
            Text("Contracts declare argv, caps, provenance roots, and postflight assertions. One composition — pick the JSON that bounds this run.")
                .font(.system(size: 14))
                .foregroundStyle(RSTheme.muted)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 460)
            Button {
                Task { await model.chooseContract() }
            } label: {
                Label("Open Contract JSON", systemImage: "doc.text")
            }
            .buttonStyle(SignalButtonStyle(emphasized: true))
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }
}

enum CapsuleTone {
    case signal, amber, muted, danger
}

struct CapsuleLabel: View {
    var text: String
    var tone: CapsuleTone

    private var color: Color {
        switch tone {
        case .signal: return RSTheme.signal
        case .amber: return RSTheme.amber
        case .muted: return RSTheme.muted
        case .danger: return RSTheme.danger
        }
    }

    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .semibold, design: .monospaced))
            .foregroundStyle(color)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(color.opacity(0.12))
            .overlay(
                Capsule().stroke(color.opacity(0.35), lineWidth: 1)
            )
            .clipShape(Capsule())
    }
}
