import SwiftUI
import RunSpecimenMacCompanion

@main
struct RunSpecimenCompanionUIApp: App {
    var body: some Scene {
        WindowGroup("RunSpecimen Companion") {
            CompanionHostView()
        }
        .defaultSize(width: 520, height: 420)
    }
}

struct CompanionHostView: View {
    @State private var workspace = ""
    @State private var contract = ""
    @State private var host = "127.0.0.1"
    @State private var allowLAN = false
    @State private var commandPreview = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Mac companion (observe)")
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

            Text("This UI only shows the CLI you must run locally. It does not inject APPROVE.")
                .font(.footnote)
                .foregroundStyle(.secondary)

            ScrollView {
                Text(commandPreview.isEmpty ? "Fill workspace + contract to preview." : commandPreview)
                    .font(.system(.body, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(Color.primary.opacity(0.06))
            }
            .frame(maxHeight: 120)

            Spacer(minLength: 0)
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onAppear(perform: refreshPreview)
    }

    private func refreshPreview() {
        guard !workspace.isEmpty, !contract.isEmpty else {
            commandPreview = ""
            return
        }
        let plan = CompanionLaunchPlan(
            workspace: workspace,
            contract: contract,
            host: host,
            allowLAN: allowLAN,
            printToken: true
        )
        commandPreview = "runspecimen " + plan.processArguments.joined(separator: " ")
    }
}
