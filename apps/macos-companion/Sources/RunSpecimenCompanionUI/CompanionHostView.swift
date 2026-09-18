import SwiftUI
import RunSpecimenMacCompanion

@main
struct RunSpecimenCompanionUIApp: App {
    var body: some Scene {
        WindowGroup("RunSpecimen Companion") {
            CompanionHostView()
        }
        .defaultSize(width: 560, height: 560)
    }
}

struct CompanionHostView: View {
    @State private var workspace = ""
    @State private var contract = ""
    @State private var host = "127.0.0.1"
    @State private var allowLAN = false
    @State private var companionPreview = ""
    @State private var armPreview = ""
    @State private var localChallenge = ""
    @State private var challengeFileHint = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Mac companion")
                    .font(.title2.weight(.semibold))
                Text(CompanionBoundary.operatorSummary)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                Form {
                    TextField("Workspace", text: $workspace)
                    TextField("Contract JSON", text: $contract)
                    TextField("Bind host", text: $host)
                    Toggle("Allow LAN / Tailscale bind", isOn: $allowLAN)
                }
                .onChange(of: workspace) { _, _ in refreshPreview() }
                .onChange(of: contract) { _, _ in refreshPreview() }
                .onChange(of: host) { _, _ in refreshPreview() }
                .onChange(of: allowLAN) { _, _ in refreshPreview() }

                Group {
                    Text("1) Start companion (pairing)")
                        .font(.headline)
                    previewBlock(companionPreview.isEmpty ? "Fill workspace + contract." : companionPreview)

                    Text("2) Arm remote human confirm (local challenge)")
                        .font(.headline)
                    previewBlock(armPreview.isEmpty ? "Fill workspace + contract." : armPreview)
                    Text("Run the arm command in a real TTY. The challenge is shown only on this Mac.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Local challenge display")
                        .font(.headline)
                    Text("Paste the challenge from the arm TTY (or from remote-confirm status). Never send it to an agent.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Text(localChallenge.isEmpty ? "— no challenge pasted —" : localChallenge)
                        .font(.system(size: 28, weight: .bold, design: .monospaced))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .background(Color.primary.opacity(0.08))
                    TextField("Paste Mac challenge here", text: $localChallenge)
                        .textFieldStyle(.roundedBorder)
                    if !challengeFileHint.isEmpty {
                        Text(challengeFileHint)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                }

                Text("Phone must type this challenge plus APPROVE. This is remote human confirm — not local TTY APPROVE.")
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(.secondary)

                Spacer(minLength: 0)
            }
            .padding(20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onAppear(perform: refreshPreview)
    }

    private func previewBlock(_ text: String) -> some View {
        Text(text)
            .font(.system(.body, design: .monospaced))
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .background(Color.primary.opacity(0.06))
    }

    private func refreshPreview() {
        guard !workspace.isEmpty, !contract.isEmpty else {
            companionPreview = ""
            armPreview = ""
            challengeFileHint = ""
            return
        }
        let plan = CompanionLaunchPlan(
            workspace: workspace,
            contract: contract,
            host: host,
            allowLAN: allowLAN,
            printToken: true
        )
        companionPreview = "runspecimen " + plan.processArguments.joined(separator: " ")
        armPreview = "runspecimen " + plan.armRemoteConfirmArguments.joined(separator: " ")
        challengeFileHint =
            "After arm: .runspecimen/runs/<campaign>/<run>/remote_confirm_challenge.local (mode 0600, Mac-local only)"
    }
}
