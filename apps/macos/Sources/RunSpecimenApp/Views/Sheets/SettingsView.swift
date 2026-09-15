import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Form {
            Section("CLI engine") {
                LabeledContent("Binary") {
                    Text(model.cliIdentity?.path.path ?? "Not selected")
                        .font(RSTheme.monoSmall)
                        .textSelection(.enabled)
                        .lineLimit(2)
                }
                LabeledContent("Version") {
                    Text(model.cliIdentity?.version ?? "—")
                        .font(RSTheme.monoSmall)
                }
                LabeledContent("Minimum") {
                    Text("0.2.0rc9+")
                        .font(RSTheme.monoSmall)
                        .foregroundStyle(RSTheme.muted)
                }
                Button("Select runspecimen…") {
                    Task { await model.chooseCLI() }
                }
                .accessibilityHint("Opens a file picker. Required for App Sandbox bookmark grants.")
                if let issue = model.cliSetupIssue {
                    Text(issue)
                        .font(.system(size: 11))
                        .foregroundStyle(RSTheme.danger)
                        .textSelection(.enabled)
                } else if let note = model.pathProbeNote {
                    Text(note)
                        .font(.system(size: 11))
                        .foregroundStyle(RSTheme.amber)
                }
                Text("Mac App Store builds must use a user-selected executable (security-scoped bookmark). See APP_STORE.md. Optional future: Contents/Helpers — see Helpers/README.md.")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }

            Section("Privacy") {
                LabeledContent("Telemetry") {
                    Text("None — local only")
                        .foregroundStyle(RSTheme.signal)
                }
                LabeledContent("App Privacy") {
                    Text("Data Not Collected")
                }
                Link("Security policy on GitHub", destination: URL(string: "https://github.com/darashkevich/runspecimen/blob/main/SECURITY.md")!)
                Text("No analytics SDKs. Docs links open in your browser. Workspace contents never leave this Mac via this app.")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }

            Section("Product honesty") {
                Text("Not an OS sandbox. Not a job scheduler. Not a compliance product. Certificates are locally verifiable hash-chained receipts — not digital signatures. HMAC / hash chains are not asymmetric signatures.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }

            Section("Install guidance") {
                Text("python3 -m pip install 'runspecimen==0.2.0rc9'")
                    .font(RSTheme.monoSmall)
                    .textSelection(.enabled)
                Link("User guide", destination: URL(string: "https://github.com/darashkevich/runspecimen/blob/main/docs/USER_GUIDE.md")!)
                Link("Notarization steps", destination: URL(string: "https://github.com/darashkevich/runspecimen/blob/cursor/macos-native-app/apps/macos/NOTARIZATION.md")!)
            }
        }
        .formStyle(.grouped)
        .padding()
    }
}
