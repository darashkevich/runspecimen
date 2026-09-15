import SwiftUI
import AppKit

struct EvidenceInspectorView: View {
    @EnvironmentObject private var model: AppModel
    @StateObject private var copyFlash = CopyFlashModel()

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("EVIDENCE")
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundStyle(RSTheme.soft)
                        .tracking(1.1)
                    Text("Receipt inspector")
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundStyle(RSTheme.ink)
                        .accessibilityAddTraits(.isHeader)
                }
                Spacer()
                if let message = copyFlash.message {
                    Text(message)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(RSTheme.signal)
                        .transition(.opacity)
                        .accessibilityLabel(message)
                        .accessibilityAddTraits(.updatesFrequently)
                } else if let status = model.status {
                    CapsuleLabel(
                        text: status.eventChainOK ? "Chain OK" : "Chain invalid",
                        tone: status.eventChainOK ? .signal : .danger
                    )
                }
            }

            Text("Local hash-chained certificate — not an asymmetric digital signature. Symmetric MAC labels apply only if an HMAC field is present.")
                .font(.system(size: 12))
                .foregroundStyle(RSTheme.amber.opacity(0.9))

            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let err = model.statusError {
                        ErrorStateCard(
                            title: "Status unavailable",
                            detail: err
                        )
                    } else if model.status == nil && model.lastOutput.isEmpty {
                        EmptyEvidenceCard()
                    } else if let status = model.status, !status.hasEvidenceFields {
                        EmptyEvidenceCard(hint: "Run has phase “\(status.phaseLabel)” but no certificate fields yet. Complete postflight / verify when ready.")
                    }

                    if model.status != nil {
                        evidenceRow("Certificate ID", model.status?.certificateID, copyable: true)
                        evidenceRow("Event head", model.status?.eventHead, copyable: true)
                        evidenceRow("Contract hash", model.status?.contractHash, copyable: true)
                        evidenceRow("Source hash", model.status?.sourceHash, copyable: true)
                        evidenceRow("Runtime ID", model.status?.runtimeID, copyable: true)
                        evidenceRow("Events", model.status.map { "\($0.eventCount)" })
                        if let code = model.status?.exitCode {
                            evidenceRow("Exit code", String(code))
                        }
                        if let ok = model.status?.postflightOK {
                            evidenceRow("Postflight", ok ? "passed" : "failed")
                        }
                        if let msg = model.status?.eventChainMessage, !msg.isEmpty {
                            evidenceRow("Chain note", msg)
                        }
                    }

                    if let json = model.status?.rawJSON {
                        HStack {
                            Text("Status JSON")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(RSTheme.soft)
                            Spacer()
                            Button("Copy JSON") {
                                copyFlash.copy(json, label: "Status JSON")
                            }
                            .font(.system(size: 11, weight: .semibold))
                            .accessibilityHint("Copies the full status JSON to the clipboard.")
                        }
                        .padding(.top, 8)
                        Text(json)
                            .font(RSTheme.monoSmall)
                            .foregroundStyle(RSTheme.muted)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    } else if model.status == nil, !model.lastOutput.isEmpty, model.statusError == nil {
                        Text("Last CLI note")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(RSTheme.soft)
                            .padding(.top, 4)
                        Text(model.lastOutput)
                            .font(RSTheme.monoSmall)
                            .foregroundStyle(RSTheme.muted)
                            .textSelection(.enabled)
                    }
                }
                .padding(14)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(RSTheme.bgPanel.opacity(0.85))
                        .overlay(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .stroke(RSTheme.line, lineWidth: 1)
                        )
                )
            }
        }
        .padding(8)
    }

    private func evidenceRow(_ label: String, _ value: String?, copyable: Bool = false) -> some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.system(size: 11))
                    .foregroundStyle(RSTheme.soft)
                Text(value?.isEmpty == false ? value! : "—")
                    .font(RSTheme.monoSmall)
                    .foregroundStyle(RSTheme.ink)
                    .textSelection(.enabled)
            }
            Spacer(minLength: 0)
            if copyable, let value, !value.isEmpty {
                Button {
                    copyFlash.copy(value, label: label)
                } label: {
                    Image(systemName: "doc.on.doc")
                        .font(.system(size: 11))
                }
                .buttonStyle(.borderless)
                .help("Copy \(label)")
                .accessibilityLabel("Copy \(label)")
                .accessibilityHint("Copies \(label) to the clipboard.")
            }
        }
        .accessibilityElement(children: .combine)
    }
}

@MainActor
final class CopyFlashModel: ObservableObject {
    @Published var message: String?

    func copy(_ text: String, label: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        let next = "Copied \(label)"
        message = next
        NSAccessibility.post(
            element: NSApp as Any,
            notification: .announcementRequested,
            userInfo: [
                .announcement: next as NSString,
                .priority: NSAccessibilityPriorityLevel.medium.rawValue as NSNumber
            ]
        )
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 1_600_000_000)
            if message == next {
                message = nil
            }
        }
    }
}

struct EmptyEvidenceCard: View {
    var hint: String = "No run state yet. Validate the contract, then approve on a real TTY. Receipts appear after the run records events."

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("NO RECEIPT YET")
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(RSTheme.soft)
                .tracking(1.0)
            Text(hint)
                .font(.system(size: 13))
                .foregroundStyle(RSTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.bottom, 4)
        .accessibilityElement(children: .combine)
    }
}

struct ErrorStateCard: View {
    var title: String
    var detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(RSTheme.danger)
                .tracking(1.0)
            Text(detail)
                .font(.system(size: 13))
                .foregroundStyle(RSTheme.ink)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(RSTheme.danger.opacity(0.1))
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .stroke(RSTheme.danger.opacity(0.35), lineWidth: 1)
                )
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel(title)
        .accessibilityValue(detail)
    }
}
