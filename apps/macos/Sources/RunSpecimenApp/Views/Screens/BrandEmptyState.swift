import SwiftUI
#if canImport(RunSpecimenCore)
import RunSpecimenCore
#endif

@MainActor
final class EmptyStateMotion: ObservableObject {
    @Published var pulse = false
}

struct BrandEmptyState: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @StateObject private var motion = EmptyStateMotion()
    private var storeBuild: Bool { DistributionChannel.current.requiresBundledHelper }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                HStack(spacing: 14) {
                    SignalMark(animated: !reduceMotion && motion.pulse)
                        .accessibilityHidden(true)
                    Text("RunSpecimen")
                        .font(.system(size: 36, weight: .bold, design: .rounded))
                        .minimumScaleFactor(0.6)
                        .lineLimit(1)
                        .foregroundStyle(RSTheme.ink)
                        .accessibilityAddTraits(.isHeader)
                }

                Text(ConsumerCopy.tagline)
                    .font(.system(size: 22, weight: .regular, design: .rounded))
                    .foregroundStyle(RSTheme.ink)
                    .lineSpacing(4)
                    .fixedSize(horizontal: false, vertical: true)

                Text(ConsumerCopy.emptyLede)
                    .font(.system(size: 15))
                    .foregroundStyle(RSTheme.muted)
                    .frame(maxWidth: 520, alignment: .leading)

                OnboardingBeats()

                FitHStack(spacing: 12, alignment: .center) {
                    if storeBuild {
                        Button {
                            Task { await model.openReviewerDemo() }
                        } label: {
                            Label("Try a sample run", systemImage: "play.circle.fill")
                        }
                        .buttonStyle(SignalButtonStyle(emphasized: true))
                        .accessibilityHint("Copy the bundled reviewer workspace and inspect status")
                    } else {
                        Button {
                            Task { await model.chooseCLI() }
                        } label: {
                            Label(model.hasCLI ? "Engine selected" : "Select runspecimen CLI", systemImage: "gearshape")
                        }
                        .buttonStyle(SignalButtonStyle(emphasized: !model.hasCLI))
                        .accessibilityHint(model.hasCLI ? "Change the selected runspecimen binary" : "Open a file picker to choose the runspecimen executable")
                    }

                    Button {
                        Task { await model.chooseWorkspace() }
                    } label: {
                        Label(model.hasWorkspace ? "Folder selected" : "Choose a folder", systemImage: "folder")
                    }
                    .buttonStyle(SignalButtonStyle(emphasized: !storeBuild && model.hasCLI && !model.hasWorkspace))
                    .disabled(!model.hasCLI)
                    .accessibilityHint("Choose a workspace folder via Open panel")
                }

                if let issue = model.cliSetupIssue {
                    CLISetupBanner(
                        title: issue.lowercased().contains("version mismatch")
                            || issue.lowercased().contains("too old")
                            || issue.lowercased().contains("need 0.2")
                            || issue.lowercased().contains("need python")
                            ? (issue.lowercased().contains("python") ? "Python is needed" : "The engine is the wrong version")
                            : "The engine needs a moment",
                        message: issue
                    )
                } else if let note = model.pathProbeNote {
                    Text(note)
                        .font(.system(size: 12))
                        .foregroundStyle(RSTheme.amber)
                        .frame(maxWidth: 520, alignment: .leading)
                        .accessibilityLabel("CLI discovery note")
                        .accessibilityValue(note)
                }

                NonGoalsStrip()
                FooterHint()
                    .padding(.bottom, 8)
            }
            .padding(.horizontal, 36)
            .padding(.vertical, 32)
            .frame(maxWidth: 720, alignment: .leading)
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

struct OnboardingBeats: View {
    private let beats: [(symbol: String, title: String, body: String)] = [
        ("doc.text", "Review the plan", "See what may run, which files count, and what must be true afterward."),
        ("keyboard", "You type APPROVE", "Assistants cannot do this for you. This app will not type it either."),
        ("checkmark.seal", "Keep the receipt", "Later you can tell, in one glance, whether anything changed.")
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(beats.enumerated()), id: \.offset) { index, beat in
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: beat.symbol)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(RSTheme.brand)
                        .frame(width: 28, height: 28)
                        .background(RSTheme.brand.opacity(0.12), in: Circle())
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(index + 1). \(beat.title)")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(RSTheme.ink)
                        Text(beat.body)
                            .font(.system(size: 13))
                            .foregroundStyle(RSTheme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .accessibilityElement(children: .combine)
            }
        }
        .padding(.vertical, 4)
    }
}

struct SignalMark: View {
    var animated: Bool
    var compact: Bool = false

    var body: some View {
        ZStack {
            Circle()
                .fill(RSTheme.brand.opacity(0.16))
                .frame(width: compact ? 22 : 36, height: compact ? 22 : 36)
            Image(systemName: "checkmark.seal.fill")
                .font(.system(size: compact ? 12 : 20, weight: .semibold))
                .foregroundStyle(RSTheme.brand)
                .shadow(color: RSTheme.brand.opacity(animated ? 0.35 : 0.12), radius: animated ? 8 : 2)
        }
        .accessibilityLabel("RunSpecimen signal mark")
    }
}

struct NonGoalsStrip: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("What this does not do")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(RSTheme.ink)
            Text("It does not lock the rest of your Mac. It does not prove your work is true. It does not schedule jobs. The receipt is a checkable history, not a bank-style signature.")
                .font(.system(size: 13))
                .foregroundStyle(RSTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
            DetailsDisclosure(title: "Technical names") {
                Text("Not an OS sandbox · Not a scheduler · Not compliance theater · Receipts are local hash chains, not digital signatures")
                    .font(.system(size: 12))
                    .foregroundStyle(RSTheme.soft)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

struct CLISetupBanner: View {
    var title: String = "The engine needs a moment"
    var message: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(RSTheme.danger)
            Text(message)
                .font(.system(size: 13))
                .foregroundStyle(RSTheme.ink)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(RSTheme.danger.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(RSTheme.danger.opacity(0.28), lineWidth: 1)
                )
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel(title)
        .accessibilityValue(message)
    }
}

struct FooterHint: View {
    private var storeBuild: Bool { DistributionChannel.current.requiresBundledHelper }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(storeBuild
                 ? "Mac App Store · Bundled engine · Local-only · Apache-2.0 · Data Not Collected"
                 : ConsumerCopy.staysLocal)
                .font(.system(size: 12))
                .foregroundStyle(RSTheme.soft)
            if !storeBuild {
                DetailsDisclosure(title: "Engine versions") {
                    Text("Published pin runspecimen==0.2.0rc14. This build's engine is unpublished 0.2.0rc15. Local-only · Apache-2.0")
                        .font(RSTheme.monoSmall)
                        .foregroundStyle(RSTheme.soft)
                        .textSelection(.enabled)
                }
            }
        }
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
                RoundedRectangle(cornerRadius: RSTheme.buttonRadius, style: .continuous)
                    .fill(emphasized
                          ? RSTheme.brand.opacity(configuration.isPressed ? 0.86 : 1)
                          : RSTheme.bgPanel)
            )
            .foregroundStyle(emphasized ? RSTheme.brandOn : RSTheme.ink)
            .overlay(
                RoundedRectangle(cornerRadius: RSTheme.buttonRadius, style: .continuous)
                    .stroke(emphasized ? RSTheme.brand.opacity(0.4) : RSTheme.line, lineWidth: 1)
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
