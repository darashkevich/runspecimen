import SwiftUI
import AppKit

struct AboutView: View {
    @EnvironmentObject private var model: AppModel

    private var appVersion: String {
        let short = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—"
        let build = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "—"
        return "\(short) (\(build))"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                SignalMark(animated: false)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 4) {
                    Text("RunSpecimen")
                        .font(.system(size: 22, weight: .bold))
                    Text("Native companion for one human-approved bounded run.")
                        .font(.system(size: 13))
                        .foregroundStyle(RSTheme.muted)
                }
            }

            Group {
                LabeledContent("App version") {
                    Text(appVersion)
                        .font(RSTheme.monoSmall)
                        .textSelection(.enabled)
                }
                LabeledContent("CLI engine") {
                    Text(model.cliIdentity?.version ?? "Not selected")
                        .font(RSTheme.monoSmall)
                        .textSelection(.enabled)
                }
                LabeledContent("CLI source") {
                    Text(model.cliSourceLabel ?? model.cliIdentity?.source.label ?? "—")
                        .font(RSTheme.monoSmall)
                        .foregroundStyle(RSTheme.muted)
                }
            }

            Divider()

            Text("Local-only. No product telemetry. Approval stays on a real PTY — this app never types APPROVE. Certificates are hash-chained receipts, not asymmetric digital signatures.")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 16) {
                Link("Privacy policy", destination: AppLinks.privacyPolicy)
                Link("Security policy", destination: AppLinks.securityPolicy)
                Link("User guide", destination: AppLinks.userGuide)
            }
            .font(.system(size: 13, weight: .medium))

            Text("Apache-2.0 · runspecimen.darashkevich.com")
                .font(.system(size: 11))
                .foregroundStyle(RSTheme.soft)
        }
        .padding(24)
        .frame(width: 440)
    }
}

enum AppLinks {
    static let privacyPolicy = URL(string: "https://runspecimen.darashkevich.com/privacy/")!
    static let securityPolicy = URL(string: "https://github.com/darashkevich/runspecimen/blob/main/SECURITY.md")!
    static let userGuide = URL(string: "https://github.com/darashkevich/runspecimen/blob/main/docs/USER_GUIDE.md")!
    static let site = URL(string: "https://runspecimen.darashkevich.com/")!
}
