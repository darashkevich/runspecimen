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
            if let issue = model.cliSetupIssue ?? model.sessionNote {
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
        .padding(.vertical, 12)
        .background(RSTheme.bgElevated.opacity(0.92))
    }

    private func bar(showPath: Bool) -> some View {
        HStack(spacing: 10) {
            HStack(spacing: 8) {
                SignalMark(animated: false, compact: true)
                Text("RunSpecimen")
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                    .foregroundStyle(RSTheme.ink)
                    .lineLimit(1)
            }
            .accessibilityElement(children: .combine)
            .layoutPriority(1)

            CapsuleLabel(text: model.cliIdentity?.version ?? "CLI missing", tone: model.hasCLI ? .signal : .amber)
                .accessibilityLabel(model.hasCLI ? "CLI version \(model.cliIdentity?.version ?? "")" : "CLI missing")
                .help(model.cliSourceLabel.map { "Source: \($0)" } ?? (DistributionChannel.current.requiresBundledHelper ? "Bundled engine missing" : "Select a runspecimen binary. This build's engine is unpublished 0.2.0rc15."))
                .layoutPriority(1)

            if let source = model.cliSourceLabel ?? model.cliIdentity?.source.label {
                CapsuleLabel(text: source, tone: source == "Bundled Helpers" ? .signal : .amber)
                    .accessibilityLabel("CLI source \(source)")
                    .help("Discovery source (ADR-002). Prefer Bundled Helper forces Contents/Helpers.")
            }
            if model.dashboardRunning {
                CapsuleLabel(text: "Timeline open", tone: .amber)
                    .accessibilityLabel("Dashboard child process running")
                    .help("Loopback dashboard is running; it stops on quit or Stop Dashboard")
            }

            if showPath, let path = model.workspaceURL?.path {
                Text(friendlyFolderName)
                    .font(.system(size: 12))
                    .foregroundStyle(RSTheme.muted)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .help(path)
                    .layoutPriority(0)
            }

            Spacer(minLength: 8)

            Button("Run plan…") { Task { await model.chooseContract() } }
            Button("Folder…") { Task { await model.chooseWorkspace() } }
            Button {
                Task { await model.refreshAll() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(model.isBusy)
            .keyboardShortcut("r", modifiers: [.command])
        }
    }

    private var friendlyFolderName: String {
        model.workspaceURL?.lastPathComponent ?? ""
    }
}

struct ContractPrompt: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "doc.badge.gearshape")
                .font(.system(size: 36, weight: .medium))
                .foregroundStyle(RSTheme.brand)
                .accessibilityHidden(true)
            Text("Choose a run plan")
                .font(RSTheme.titleFont)
                .foregroundStyle(RSTheme.ink)
            Text("A run plan says what may run, which files count, and what must be true when it finishes. You’ll review it, then type APPROVE yourself.")
                .font(.system(size: 14))
                .foregroundStyle(RSTheme.muted)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 460)
            Button {
                Task { await model.chooseContract() }
            } label: {
                Label("Open a run plan", systemImage: "doc.text")
            }
            .buttonStyle(SignalButtonStyle(emphasized: true))
            DetailsDisclosure(title: "Technical name") {
                Text("This is the contract JSON. It declares argv, caps, provenance roots, and postflight assertions.")
                    .font(.system(size: 12))
                    .foregroundStyle(RSTheme.soft)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: 460)
            }
            .frame(maxWidth: 460)
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
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(color)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(color.opacity(0.12))
            .overlay(
                Capsule().stroke(color.opacity(0.28), lineWidth: 1)
            )
            .clipShape(Capsule())
    }
}
