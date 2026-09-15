import SwiftUI

@MainActor
final class ApproveSheetModel: ObservableObject {
    @Published var transcript = ""
    @Published var input = ""
    @Published var started = false
    @Published var statusNote = "Review the bound command, then type APPROVE exactly when prompted."
    var session: PTYApprovalSession?
}

/// First-party approval surface. Spawns `runspecimen approve` on a real PTY.
/// Never auto-submits APPROVE — human must type the phrase intentionally.
struct ApproveSheet: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @StateObject private var sheet = ApproveSheetModel()

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().overlay(RSTheme.line)
            ScrollViewReader { proxy in
                ScrollView {
                    Text(sheet.transcript.isEmpty ? "Starting interactive approval PTY…" : sheet.transcript)
                        .font(RSTheme.mono)
                        .foregroundStyle(RSTheme.ink)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                        .padding(16)
                        .id("tail")
                }
                .background(RSTheme.bg)
                .onChange(of: sheet.transcript) { _, _ in
                    if !reduceMotion {
                        withAnimation(.easeOut(duration: 0.15)) {
                            proxy.scrollTo("tail", anchor: .bottom)
                        }
                    } else {
                        proxy.scrollTo("tail", anchor: .bottom)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 10) {
                Text(sheet.statusNote)
                    .font(.system(size: 12))
                    .foregroundStyle(RSTheme.amber)
                    .accessibilityLabel(sheet.statusNote)

                HStack {
                    TextField("Type APPROVE to bind — nothing is sent automatically", text: $sheet.input)
                        .textFieldStyle(.roundedBorder)
                        .font(RSTheme.mono)
                        .onSubmit { sendInput() }
                        .accessibilityLabel("Approval confirmation field")
                        .accessibilityHint("Type the word APPROVE and press Send. The app will not submit it for you automatically.")

                    Button("Send") { sendInput() }
                        .buttonStyle(SignalButtonStyle(emphasized: true))
                        .disabled(sheet.input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                    Button("Cancel") {
                        sheet.session?.stop()
                        dismiss()
                    }
                    .keyboardShortcut(.cancelAction)
                }
            }
            .padding(16)
            .background(RSTheme.bgElevated)
        }
        .background(AtmosphericBackground().opacity(0.35))
        .onAppear { startSession() }
        .onDisappear { sheet.session?.stop() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Human approval")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(RSTheme.ink)
                Spacer()
                CapsuleLabel(text: "TTY required", tone: .amber)
            }
            Text("This sheet attaches runspecimen approve to a real PTY so the engine’s interactive gate still holds. Agents and plugins cannot approve unattended.")
                .font(.system(size: 12))
                .foregroundStyle(RSTheme.muted)
            if let argv = model.contract?.argv {
                Text(argv.joined(separator: " "))
                    .font(RSTheme.monoSmall)
                    .foregroundStyle(RSTheme.signal)
                    .textSelection(.enabled)
            }
        }
        .padding(16)
        .background(RSTheme.bgPanel.opacity(0.95))
    }

    private func startSession() {
        guard !sheet.started else { return }
        sheet.started = true
        guard let cli = model.cliIdentity?.path,
              let workspace = model.workspaceURL,
              let contract = model.contractURL else {
            sheet.statusNote = "Missing CLI, workspace, or contract."
            return
        }
        _ = BookmarkStore.shared.startAccessingCLI()
        _ = BookmarkStore.shared.startAccessingWorkspace()

        let session = PTYApprovalSession { chunk in
            Task { @MainActor in
                sheet.transcript.append(chunk)
            }
        }
        sheet.session = session
        do {
            try session.start(cli: cli, workspace: workspace, contract: contract)
            sheet.statusNote = "PTY live. Read the prompt carefully, then type APPROVE yourself."
        } catch {
            sheet.statusNote = (error as? AppError)?.message ?? error.localizedDescription
        }
    }

    private func sendInput() {
        let line = sheet.input
        guard !line.isEmpty else { return }
        sheet.session?.sendLine(line)
        sheet.input = ""
        // Deliberately do not auto-detect or coerce APPROVE.
    }
}
