import SwiftUI
import AppKit
#if canImport(RunSpecimenCore)
import RunSpecimenCore
#endif

/// A consequential expansion command that has not run yet.
struct WorkflowRequest: Identifiable {
    let id = UUID()
    let title: String
    let detail: String
    let arguments: [String]
}

/// Native controls for evidence-expansion commands.
///
/// Read-only commands run immediately. Commands that write files show a preview
/// or a confirmation and do nothing until the human confirms. None of them
/// approve, preflight, or run the selected contract.
struct WorkflowSheet: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss

    @State private var snapshotID = ""
    @State private var restoreDest: URL?
    @State private var planURL: URL?
    @State private var suiteURL: URL?
    @State private var baselineURL: URL?
    @State private var candidateURL: URL?
    @State private var bundleURL: URL?
    @State private var exportURL: URL?
    @State private var backupURL: URL?
    @State private var usageExport: URL?
    @State private var decisionID = ""
    @State private var rationale = ""
    @State private var classification = "human"
    @State private var localError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().overlay(RSTheme.line)
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if model.workspaceURL == nil {
                        Text("Select a workspace before using these controls.")
                            .foregroundStyle(RSTheme.muted)
                    }
                    if let localError {
                        Text(localError)
                            .font(.system(size: 12))
                            .foregroundStyle(RSTheme.danger)
                            .accessibilityLabel("Workflow error")
                            .accessibilityValue(localError)
                    }
                    snapshotSection
                    coordinationSection
                    evaluationSection
                    scenesSection
                    configSection
                    decisionSection
                    usageSection
                    resultSection
                }
                .padding(16)
            }
        }
        .frame(minWidth: 640, minHeight: 520)
        .background(RSTheme.bg)
        .confirmationDialog(
            model.pendingWorkflow?.title ?? "Confirm",
            isPresented: Binding(
                get: { model.pendingWorkflow != nil },
                set: { if !$0 { model.cancelWorkflow() } }
            ),
            presenting: model.pendingWorkflow
        ) { request in
            Button(request.title) {
                Task { await model.confirmWorkflow() }
            }
            Button("Cancel", role: .cancel) {
                model.cancelWorkflow()
            }
        } message: { request in
            Text(request.detail)
        }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Workflows")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(RSTheme.ink)
                Text("Writes wait for confirmation. Nothing here types APPROVE or starts the selected run.")
                    .font(.system(size: 12))
                    .foregroundStyle(RSTheme.muted)
            }
            Spacer()
            Button("Close") { dismiss() }
                .keyboardShortcut(.cancelAction)
        }
        .padding(16)
    }

    private var snapshotSection: some View {
        group("Snapshots") {
            TextField("Snapshot id", text: $snapshotID)
                .textFieldStyle(.roundedBorder)
                .accessibilityLabel("Snapshot id")
            HStack {
                Button("Compare") { Task { await compareSnapshot() } }
                    .disabled(!canRead)
                Button("Create…") { stageSnapshotCreate() }
                    .disabled(!canRead || snapshotID.trimmingCharacters(in: .whitespaces).isEmpty || model.contractURL == nil)
                Button("Choose restore folder") { restoreDest = PanelPicker.pickDirectory(message: "Choose a folder outside this workspace") }
            }
            if let restoreDest {
                Text(restoreDest.path)
                    .font(RSTheme.monoSmall)
                    .foregroundStyle(RSTheme.muted)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            HStack {
                Button("Preview restore") { Task { await previewRestore() } }
                    .disabled(restoreDest == nil || !canRead)
                Button("Restore…") { stageRestore() }
                    .disabled(restoreDest == nil || !canRead)
            }
        }
    }

    private var coordinationSection: some View {
        group("Coordination") {
            fileRow("Plan", planURL) { planURL = PanelPicker.pickJSON(message: "Choose a coordination plan") }
            HStack {
                Button("Validate") { Task { await validatePlan() } }
                    .disabled(planURL == nil)
                Button("Readiness") { Task { await readiness() } }
                    .disabled(planURL == nil)
            }
            Text("Reads the plan and stored evidence. Does not merge or push.")
                .font(.system(size: 12))
                .foregroundStyle(RSTheme.muted)
        }
    }

    private var evaluationSection: some View {
        group("Evaluations") {
            fileRow("Suite", suiteURL) { suiteURL = PanelPicker.pickJSON(message: "Choose an eval suite") }
            Button("Run suite…") { stageEvalRun() }
                .disabled(suiteURL == nil || !canRead)
            fileRow("Baseline result", baselineURL) { baselineURL = PanelPicker.pickJSON(message: "Choose a baseline eval result") }
            fileRow("Candidate result", candidateURL) { candidateURL = PanelPicker.pickJSON(message: "Choose a candidate eval result") }
            Button("Compare") { Task { await compareEval() } }
                .disabled(baselineURL == nil || candidateURL == nil)
        }
    }

    private var scenesSection: some View {
        group("Scenes") {
            Text("Prepares a disposable demo under .runspecimen/scenes-demo. The demo prints approval instructions and never types APPROVE.")
                .font(.system(size: 12))
                .foregroundStyle(RSTheme.muted)
            HStack {
                Button("Prepare…") { stageScenes(prepareOnly: true) }
                    .disabled(!canRead)
                Button("Run checks…") { stageScenes(prepareOnly: false) }
                    .disabled(!canRead)
            }
        }
    }

    private var configSection: some View {
        group("Configuration") {
            fileRow("Bundle", bundleURL) { bundleURL = PanelPicker.pickJSON(message: "Choose a config bundle") }
            HStack {
                Button("Preview") { Task { await previewConfig() } }
                    .disabled(bundleURL == nil || !canRead)
                Button("Apply…") { stageConfigApply() }
                    .disabled(bundleURL == nil || !canRead)
            }
            HStack {
                Button("Choose export file") { exportURL = PanelPicker.pickSaveJSON(message: "Export the active bundle") }
                Button("Export…") { stageExport() }
                    .disabled(exportURL == nil || !canRead)
            }
            fileRow("Backup", backupURL) { backupURL = PanelPicker.pickJSON(message: "Choose a config backup") }
            Button("Rollback…") { stageRollback() }
                .disabled(backupURL == nil || !canRead)
        }
    }

    private var decisionSection: some View {
        group("Decision capture") {
            TextField("Decision id", text: $decisionID)
                .textFieldStyle(.roundedBorder)
            TextField("Rationale", text: $rationale, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(2...4)
            Picker("Classification", selection: $classification) {
                Text("Human").tag("human")
                Text("Agent note").tag("agent")
            }
            .pickerStyle(.segmented)
            .accessibilityHint("Records who made the decision. This does not approve a run.")
            Button("Capture…") { stageDecision() }
                .disabled(!canRead || decisionID.trimmingCharacters(in: .whitespaces).isEmpty || rationale.trimmingCharacters(in: .whitespaces).isEmpty)
        }
    }

    private var usageSection: some View {
        group("Usage import") {
            fileRow("Export", usageExport) { usageExport = PanelPicker.pickJSON(message: "Choose a usage export") }
            Button("Import…") { stageUsageImport() }
                .disabled(usageExport == nil || !canRead)
            Text("Import writes usage records. Summarize stays on Refresh read-only.")
                .font(.system(size: 12))
                .foregroundStyle(RSTheme.muted)
        }
    }

    private var resultSection: some View {
        group(model.isBusy ? "Working…" : "Result") {
            if model.expansionReadout.isEmpty {
                Text("No workflow result yet.")
                    .font(.system(size: 12))
                    .foregroundStyle(RSTheme.muted)
            } else {
                Text(model.expansionReadout)
                    .font(RSTheme.monoSmall)
                    .foregroundStyle(RSTheme.muted)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var canRead: Bool { model.workspaceURL != nil && !model.isBusy }

    private func workspaceArgs(_ command: [String]) -> [String]? {
        guard let workspace = model.workspaceURL else {
            localError = "Select a workspace first."
            return nil
        }
        localError = nil
        return command + ["--workspace", workspace.path]
    }

    private func compareSnapshot() async {
        let id = snapshotID.trimmingCharacters(in: .whitespaces)
        guard !id.isEmpty, let args = workspaceArgs(["snapshot", "compare", "--id", id]) else {
            if snapshotID.trimmingCharacters(in: .whitespaces).isEmpty { localError = "Enter a snapshot id." }
            return
        }
        await model.runWorkflow(args)
    }

    private func stageSnapshotCreate() {
        let id = snapshotID.trimmingCharacters(in: .whitespaces)
        guard !id.isEmpty, let contract = model.contractURL,
              let args = workspaceArgs(["snapshot", "create", "--id", id, "--contract", contract.path]) else {
            localError = "Choose a contract and enter a snapshot id."
            return
        }
        model.pendingWorkflow = WorkflowRequest(
            title: "Create snapshot",
            detail: "Writes snapshot \(id) from the selected contract’s source roots. This does not approve or run.",
            arguments: args
        )
    }

    private func previewRestore() async {
        guard let dest = restoreDest else { return }
        guard destinationIsOutsideWorkspace(dest) else { return }
        let id = snapshotID.trimmingCharacters(in: .whitespaces)
        guard !id.isEmpty, let args = workspaceArgs(["snapshot", "preview-restore", "--id", id, "--dest", dest.path]) else {
            localError = "Enter a snapshot id."
            return
        }
        await model.runWorkflow(args)
    }

    private func stageRestore() {
        guard let dest = restoreDest, destinationIsOutsideWorkspace(dest) else { return }
        let id = snapshotID.trimmingCharacters(in: .whitespaces)
        guard !id.isEmpty, let args = workspaceArgs(["snapshot", "restore", "--id", id, "--dest", dest.path]) else {
            localError = "Enter a snapshot id."
            return
        }
        model.pendingWorkflow = WorkflowRequest(
            title: "Restore snapshot",
            detail: "Writes snapshot \(id) into \(dest.path). The folder is outside this workspace. Cancel leaves it unchanged.",
            arguments: args
        )
    }

    private func destinationIsOutsideWorkspace(_ dest: URL) -> Bool {
        guard let workspace = model.workspaceURL else {
            localError = "Select a workspace first."
            return false
        }
        if SessionRestore.isInsideWorkspace(url: dest, workspace: workspace) {
            localError = "Choose a restore folder outside the workspace."
            return false
        }
        localError = nil
        return true
    }

    private func validatePlan() async {
        guard let plan = planURL else { return }
        await model.runWorkflow(["coordination", "validate", "--plan", plan.path])
    }

    private func readiness() async {
        guard let plan = planURL else { return }
        await model.runWorkflow(["coordination", "readiness", "--plan", plan.path])
    }

    private func stageEvalRun() {
        guard let suite = suiteURL, let args = workspaceArgs(["eval", "run", "--suite", suite.path]) else { return }
        model.pendingWorkflow = WorkflowRequest(
            title: "Run evaluation",
            detail: "Runs \(suite.lastPathComponent) in disposable workspaces and writes a result. This does not approve the selected contract.",
            arguments: args
        )
    }

    private func compareEval() async {
        guard let baseline = baselineURL, let candidate = candidateURL else { return }
        await model.runWorkflow(["eval", "compare", "--baseline", baseline.path, "--candidate", candidate.path])
    }

    private func stageScenes(prepareOnly: Bool) {
        var command = ["scenes"]
        if prepareOnly { command.append("--prepare-only") }
        guard let args = workspaceArgs(command) else { return }
        model.pendingWorkflow = WorkflowRequest(
            title: prepareOnly ? "Prepare scenes" : "Run scene checks",
            detail: prepareOnly
                ? "Replaces .runspecimen/scenes-demo and prints the human approval command. The app will not type APPROVE."
                : "Replaces .runspecimen/scenes-demo and runs the local checks. The app will not type APPROVE or start the selected contract.",
            arguments: args
        )
    }

    private func previewConfig() async {
        guard let bundle = bundleURL, let args = workspaceArgs(["config", "preview", "--bundle", bundle.path]) else { return }
        await model.runWorkflow(args)
    }

    private func stageConfigApply() {
        guard let bundle = bundleURL, let args = workspaceArgs(["config", "apply", "--bundle", bundle.path]) else { return }
        model.pendingWorkflow = WorkflowRequest(
            title: "Apply configuration",
            detail: "Writes the active bundle from \(bundle.lastPathComponent) and keeps a backup. Cancel leaves the current bundle unchanged.",
            arguments: args
        )
    }

    private func stageExport() {
        guard let export = exportURL, let args = workspaceArgs(["config", "export", "--out", export.path]) else { return }
        model.pendingWorkflow = WorkflowRequest(
            title: "Export configuration",
            detail: "Writes the active bundle to \(export.path). Secrets stay excluded. Cancel writes nothing.",
            arguments: args
        )
    }

    private func stageRollback() {
        guard let backup = backupURL, let args = workspaceArgs(["config", "rollback", "--backup", backup.path]) else { return }
        model.pendingWorkflow = WorkflowRequest(
            title: "Roll back configuration",
            detail: "Restores the active bundle from \(backup.lastPathComponent). Cancel leaves the current bundle unchanged.",
            arguments: args
        )
    }

    private func stageDecision() {
        let id = decisionID.trimmingCharacters(in: .whitespaces)
        let why = rationale.trimmingCharacters(in: .whitespaces)
        guard !id.isEmpty, !why.isEmpty,
              let args = workspaceArgs([
                "decisions", "capture",
                "--id", id,
                "--rationale", why,
                "--classification", classification
              ]) else { return }
        model.pendingWorkflow = WorkflowRequest(
            title: "Capture decision",
            detail: "Records decision \(id) as \(classification). This is a note in the workspace. It does not approve or run.",
            arguments: args
        )
    }

    private func stageUsageImport() {
        guard let export = usageExport,
              let args = workspaceArgs(["usage", "import", "--provider", "local_json", "--export", export.path]) else { return }
        model.pendingWorkflow = WorkflowRequest(
            title: "Import usage",
            detail: "Imports \(export.lastPathComponent). Repeating the same file does not double-count. Cancel imports nothing.",
            arguments: args
        )
    }

    @ViewBuilder
    private func group<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(RSTheme.ink)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func fileRow(_ title: String, _ url: URL?, pick: @escaping () -> Void) -> some View {
        HStack {
            Button(title) { pick() }
            Text(url?.lastPathComponent ?? "None selected")
                .font(.system(size: 12))
                .foregroundStyle(RSTheme.muted)
                .lineLimit(1)
        }
    }
}
