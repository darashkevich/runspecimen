import SwiftUI
import AppKit
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
                if !DistributionChannel.current.requiresBundledHelper {
                    Button("Select runspecimen…") {
                        Task { await model.chooseCLI() }
                    }
                    .accessibilityHint("Opens a file picker. Required for App Sandbox bookmark grants.")
                }
                Button("Prefer Bundled Helper") {
                    Task { await model.preferBundledHelper() }
                }
                .accessibilityHint("Clears the saved CLI bookmark and uses Contents/Helpers/runspecimen when staged.")
                Button("Clear CLI Bookmark & Rediscover") {
                    Task { await model.clearCLIBookmarkAndRediscover() }
                }
                .accessibilityHint(DistributionChannel.current.requiresBundledHelper
                    ? "Drops a saved CLI bookmark and uses the bundled engine. Store builds do not select a host CLI."
                    : "Drops the Open-panel bookmark so discovery can use Helpers then PATH.")
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
                Text(DistributionChannel.current.requiresBundledHelper
                     ? "Mac App Store builds use the bundled frozen engine only. Do not pip install a host CLI. Prefer Bundled Helper if Source is not Bundled Helpers."
                     : "Discovery order: Open-panel bookmark → Contents/Helpers/runspecimen → PATH/PyPI (PATH disabled for Mac App Store builds).")
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
                Link("Privacy policy (runspecimen.darashkevich.com)", destination: AppLinks.privacyPolicy)
                Link("Security policy on GitHub", destination: AppLinks.securityPolicy)
                Text("No analytics SDKs. Docs links open in your browser. Workspace contents never leave this Mac via this app.")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }

            Section("Product honesty") {
                Text("Not an OS sandbox. Not a job scheduler. Not a compliance product. Certificates are locally verifiable hash-chained receipts — not digital signatures. HMAC / hash chains are not asymmetric signatures.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }

            if !DistributionChannel.current.requiresBundledHelper {
                Section("Install guidance") {
                    Text("python3 -m pip install 'runspecimen==0.2.0rc12'")
                        .font(RSTheme.monoSmall)
                        .textSelection(.enabled)
                    Text("Or stage a helper: ./Scripts/stage_helper.sh --from-src && ./Scripts/build_app.sh")
                        .font(RSTheme.monoSmall)
                        .textSelection(.enabled)
                    Link("User guide", destination: AppLinks.userGuide)
                    Link("Notarization steps", destination: URL(string: "https://github.com/darashkevich/runspecimen/blob/main/apps/macos/NOTARIZATION.md")!)
                    Link("Helper packaging", destination: URL(string: "https://github.com/darashkevich/runspecimen/blob/main/apps/macos/Helpers/README.md")!)
                }
            }
        }
        .formStyle(.grouped)
        .padding()
    }
}
