import SwiftUI

struct StatusLifecycleView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            sectionHeader("Lifecycle", subtitle: model.status?.phaseLabel ?? "Awaiting status")

            LifecycleRail(activePhase: model.status?.phase ?? "none")

            VStack(alignment: .leading, spacing: 10) {
                metric("Campaign", model.contract?.campaignID ?? "—")
                metric("Run", model.contract?.runID ?? "—")
                metric("Lease", model.status?.leaseHeldByOther == true ? "Busy" : "Clear")
                metric("Chain", chainLabel)
                if let argv = model.contract?.argv, !argv.isEmpty {
                    metric("Argv", argv.joined(separator: " "))
                }
            }
            .padding(14)
            .background(panelBackground)

            if let doctor = model.doctor {
                HStack(spacing: 10) {
                    CapsuleLabel(text: doctor.ok ? "Doctor OK" : "Doctor fail", tone: doctor.ok ? .signal : .danger)
                    Text("Python \(doctor.python)")
                        .font(RSTheme.monoSmall)
                        .foregroundStyle(RSTheme.muted)
                }
                .accessibilityElement(children: .combine)
            }

            Text("Evidence inspection is read-only. Approve / run / postflight stay explicit human actions through the bundled engine.")
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
        return status.eventChainOK ? "OK · \(status.eventCount) events" : "Invalid"
    }

    private func sectionHeader(_ title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased())
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(RSTheme.soft)
                .tracking(1.1)
            Text(subtitle)
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(RSTheme.ink)
                .accessibilityAddTraits(.isHeader)
        }
    }

    private func metric(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.system(size: 11))
                .foregroundStyle(RSTheme.soft)
            Text(value)
                .font(RSTheme.monoSmall)
                .foregroundStyle(RSTheme.ink)
                .textSelection(.enabled)
        }
        .accessibilityElement(children: .combine)
    }

    private var panelBackground: some View {
        RoundedRectangle(cornerRadius: 14, style: .continuous)
            .fill(RSTheme.bgPanel.opacity(0.85))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(RSTheme.line, lineWidth: 1)
            )
    }
}

struct LifecycleRail: View {
    var activePhase: String

    private var index: Int {
        switch activePhase {
        case "approved": return 0
        case "preflighted": return 1
        case "running", "completed", "failed": return 2
        case "postflighted": return 3
        default: return -1
        }
    }

    private let labels = ["Approve", "Preflight", "Run", "Postflight", "Verify"]

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(labels.enumerated()), id: \.offset) { i, label in
                VStack(spacing: 6) {
                    Circle()
                        .fill(i <= index ? RSTheme.signal : RSTheme.bgElevated)
                        .overlay(Circle().stroke(i <= index ? RSTheme.signalDeep : RSTheme.line, lineWidth: 1))
                        .frame(width: 12, height: 12)
                    Text(label)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(i <= index ? RSTheme.ink : RSTheme.soft)
                }
                .frame(maxWidth: .infinity)
                .accessibilityLabel("\(label)\(i <= index ? ", recorded" : ", not reached")")
                if i < labels.count - 1 {
                    Rectangle()
                        .fill(i < index ? RSTheme.signal.opacity(0.5) : RSTheme.line)
                        .frame(height: 1)
                        .offset(y: -10)
                }
            }
        }
        .padding(.vertical, 8)
        .accessibilityElement(children: .contain)
    }
}
