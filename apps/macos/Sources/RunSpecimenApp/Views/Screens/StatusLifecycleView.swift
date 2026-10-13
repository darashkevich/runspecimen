import SwiftUI

struct StatusLifecycleView: View {
    @EnvironmentObject private var model: AppModel

    private var next: ConsumerNextStep {
        ConsumerNextStep.current(
            phase: model.status?.phase ?? "none",
            doctorOK: model.doctor?.ok,
            hasCertificate: model.status?.certificateID != nil,
            isBusy: model.isBusy,
            leaseBusy: model.status?.leaseHeldByOther == true
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("This run")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(RSTheme.soft)
                Text(ConsumerCopy.phaseHeadline(model.status?.phase ?? "none"))
                    .font(.system(size: 22, weight: .semibold, design: .rounded))
                    .foregroundStyle(RSTheme.ink)
                    .accessibilityAddTraits(.isHeader)
            }

            LifecycleRail(
                activePhase: model.status?.phase ?? "none",
                hasCertificate: model.status?.certificateID != nil
            )

            NextStepBanner(step: next) {
                if let action = next.action {
                    Task { await model.requestPerform(action) }
                }
            }
            .disabled(next.action == nil || (next.action.map { !model.isActionEnabled($0) } ?? true))

            RSCard {
                VStack(alignment: .leading, spacing: 10) {
                    metric("Project", model.contract?.campaignID ?? "—")
                    metric("This run", model.contract?.runID ?? "—")
                    metric("Folder", model.status?.leaseHeldByOther == true ? "Busy" : "Clear")
                    metric("History", chainLabel)
                    if let argv = model.contract?.argv, !argv.isEmpty {
                        metric("Command", argv.joined(separator: " "))
                    }
                }
            }

            if let doctor = model.doctor {
                HStack(spacing: 10) {
                    CapsuleLabel(
                        text: doctor.ok ? "Engine is ready" : "Engine needs a moment",
                        tone: doctor.ok ? .signal : .danger
                    )
                    DetailsDisclosure(title: "Engine details") {
                        Text("Doctor \(doctor.ok ? "OK" : "fail") · Python \(doctor.python)")
                            .font(RSTheme.monoSmall)
                            .foregroundStyle(RSTheme.muted)
                    }
                }
                .accessibilityElement(children: .combine)
            }

            Text("Looking does not approve or start anything. You choose the next step.")
                .font(.system(size: 12))
                .foregroundStyle(RSTheme.soft)
                .fixedSize(horizontal: false, vertical: true)

            Spacer(minLength: 0)
        }
        .padding(8)
    }

    private var chainLabel: String {
        guard let status = model.status else { return "—" }
        if status.eventCount == 0 { return "Empty" }
        return status.eventChainOK ? "Looks intact · \(status.eventCount) events" : "Does not match"
    }

    private func metric(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.system(size: 11))
                .foregroundStyle(RSTheme.soft)
            Text(value)
                .font(.system(size: 13, design: value.count > 24 ? .monospaced : .default))
                .foregroundStyle(RSTheme.ink)
                .textSelection(.enabled)
        }
        .accessibilityElement(children: .combine)
    }
}

struct NextStepBanner: View {
    var step: ConsumerNextStep
    var action: () -> Void

    private var tint: Color {
        switch step.tone {
        case .success: return RSTheme.signal
        case .warning: return RSTheme.amber
        case .danger: return RSTheme.danger
        case .action, .calm: return RSTheme.brand
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(step.title)
                .font(.system(size: 15, weight: .semibold, design: .rounded))
                .foregroundStyle(RSTheme.ink)
            Text(step.body)
                .font(.system(size: 13))
                .foregroundStyle(RSTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
            if let lifecycle = step.action {
                Button(lifecycle.consumerTitle, action: action)
                    .buttonStyle(SignalButtonStyle(emphasized: step.tone == .action || step.tone == .success))
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(tint.opacity(0.10))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(tint.opacity(0.28), lineWidth: 1)
                )
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel(step.title)
        .accessibilityValue(step.body)
    }
}

struct LifecycleRail: View {
    var activePhase: String
    var hasCertificate: Bool = false

    private var index: Int {
        if hasCertificate { return 4 }
        switch activePhase {
        case "approved": return 0
        case "preflighted": return 1
        case "running", "completed", "failed": return 2
        case "postflighted": return 3
        default: return -1
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            ForEach(0..<5, id: \.self) { i in
                let label = ConsumerCopy.railLabel(at: i)
                VStack(spacing: 6) {
                    Circle()
                        .fill(i <= index ? RSTheme.brand : RSTheme.bgElevated)
                        .overlay(Circle().stroke(i <= index ? RSTheme.brand : RSTheme.line, lineWidth: 1))
                        .frame(width: 12, height: 12)
                    Text(label)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(i <= index ? RSTheme.ink : RSTheme.soft)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .accessibilityLabel("\(label)\(i <= index ? ", recorded" : ", not reached")")
                .help(ConsumerCopy.railEngineName(at: i))
                if i < 4 {
                    Rectangle()
                        .fill(i < index ? RSTheme.brand.opacity(0.45) : RSTheme.line)
                        .frame(height: 1)
                        .offset(y: -10)
                }
            }
        }
        .padding(.vertical, 8)
        .accessibilityElement(children: .contain)
    }
}
