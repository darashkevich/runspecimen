import SwiftUI

struct EvidenceInspectorView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("EVIDENCE")
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(RSTheme.soft)
                .tracking(1.1)
            Text("Receipt inspector")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(RSTheme.ink)
                .accessibilityAddTraits(.isHeader)

            Text("Local hash-chained certificate — not an asymmetric digital signature. Symmetric MAC labels apply only if an HMAC field is present.")
                .font(.system(size: 12))
                .foregroundStyle(RSTheme.amber.opacity(0.9))

            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    evidenceRow("Certificate ID", model.status?.certificateID)
                    evidenceRow("Event head", model.status?.eventHead)
                    evidenceRow("Contract hash", model.status?.contractHash)
                    evidenceRow("Source hash", model.status?.sourceHash)
                    evidenceRow("Runtime ID", model.status?.runtimeID)
                    if let code = model.status?.exitCode {
                        evidenceRow("Exit code", String(code))
                    }
                    if let ok = model.status?.postflightOK {
                        evidenceRow("Postflight", ok ? "passed" : "failed")
                    }

                    if let json = model.status?.rawJSON {
                        Text("Status JSON")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(RSTheme.soft)
                            .padding(.top, 8)
                        Text(json)
                            .font(RSTheme.monoSmall)
                            .foregroundStyle(RSTheme.muted)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    } else if !model.lastOutput.isEmpty {
                        Text(model.lastOutput)
                            .font(RSTheme.monoSmall)
                            .foregroundStyle(RSTheme.muted)
                            .textSelection(.enabled)
                    } else {
                        Text("No run state yet. Validate, then approve on a real TTY.")
                            .font(.system(size: 13))
                            .foregroundStyle(RSTheme.soft)
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

    private func evidenceRow(_ label: String, _ value: String?) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.system(size: 11))
                .foregroundStyle(RSTheme.soft)
            Text(value?.isEmpty == false ? value! : "—")
                .font(RSTheme.monoSmall)
                .foregroundStyle(RSTheme.ink)
                .textSelection(.enabled)
        }
        .accessibilityElement(children: .combine)
    }
}
