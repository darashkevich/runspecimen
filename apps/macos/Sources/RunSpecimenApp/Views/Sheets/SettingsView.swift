import SwiftUI
#if canImport(RunSpecimenCore)
import RunSpecimenCore
#endif

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
                LabeledContent("Source") {
                    Text(model.cliSourceLabel ?? model.cliIdentity?.source.label ?? "—")
                        .font(RSTheme.monoSmall)
                        .foregroundStyle(RSTheme.muted)
                }
                LabeledContent("Minimum") {
                    Text("\(CLIVersionGate.minimum.displayMinimum)+")
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
                Text("Discovery order: Open-panel bookmark → Contents/Helpers/runspecimen (if staged) → PATH/PyPI probe. MAS builds should use bookmark or bundled helper. See Helpers/README.md and ADR-002.")
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
                Link("Helper packaging", destination: URL(string: "https://github.com/darashkevich/runspecimen/blob/cursor/macos-native-app/apps/macos/Helpers/README.md")!)
            }
        }
        .formStyle(.grouped)
        .padding()
    }
}
