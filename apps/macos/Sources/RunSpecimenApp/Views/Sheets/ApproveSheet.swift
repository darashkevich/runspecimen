import SwiftUI
import AppKit

/// First-party approval surface. Spawns `runspecimen approve` on a real PTY.
/// Never auto-submits APPROVE — human must type the phrase intentionally.
struct ApproveSheet: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @StateObject private var sheet = ApproveSheetModel()
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().overlay(RSTheme.line)
            transcriptPane
            inputBar
        }
        .background(AtmosphericBackground().opacity(0.35))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Human approval sheet")
        .accessibilityHint("Interactive PTY for runspecimen approve. Type APPROVE yourself when prompted. The app never submits it automatically.")
        .onAppear {
            startSession()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                inputFocused = true
            }
        }
        .onDisappear {
            sheet.session?.stop()
        }
    }

    private var transcriptPane: some View {
        ScrollViewReader { proxy in
            ScrollView {
                Text(sheet.transcript.isEmpty ? "Getting the approval prompt ready…" : sheet.transcript)
                    .font(RSTheme.mono)
                    .foregroundStyle(RSTheme.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
                    .padding(16)
                    .id("tail")
                    .accessibilityLabel("Approval transcript")
                    .accessibilityValue(sheet.transcript.isEmpty ? "Waiting for PTY output" : sheet.transcript)
            }
            .background(RSTheme.bg)
            .accessibilityElement(children: .contain)
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
    }

    private var inputBar: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(sheet.statusNote)
                .font(.system(size: 12))
                .foregroundStyle(sheet.sessionFailed ? RSTheme.danger : RSTheme.amber)
                .accessibilityLabel("Approval status")
                .accessibilityValue(sheet.statusNote)
                .accessibilityAddTraits(.updatesFrequently)

            HStack(alignment: .center, spacing: 10) {
                TextField("Type APPROVE to bind — nothing is sent automatically", text: $sheet.input)
                    .textFieldStyle(.roundedBorder)
                    .font(RSTheme.mono)
                    .focused($inputFocused)
                    .disabled(sheet.sessionFailed)
                    .onSubmit { sendInput() }
                    .accessibilityLabel("Approval confirmation field")
                    .accessibilityHint("Type the word APPROVE exactly as prompted, then press Send. RunSpecimen will not type APPROVE for you.")

                Button("Send") { sendInput() }
                    .buttonStyle(SignalButtonStyle(emphasized: true))
                    .disabled(sheet.sessionFailed || sheet.input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityLabel("Send line to approval PTY")
                    .accessibilityHint("Sends only what you typed. Does not auto-complete APPROVE.")
                    .keyboardShortcut(.defaultAction)

                Button("Cancel") {
                    sheet.session?.stop()
                    dismiss()
                }
                .keyboardShortcut(.cancelAction)
                .accessibilityLabel("Cancel approval")
                .accessibilityHint("Stops the PTY session without approving.")
            }

            Text("Only you can approve. Assistants cannot type APPROVE, and this app will not type it for you.")
                .font(.system(size: 11))
                .foregroundStyle(RSTheme.soft)
                .accessibilityLabel("Invariant: agents and plugins cannot approve. Only a human on this PTY.")
        }
        .padding(16)
        .background(RSTheme.bgElevated)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Review and approve")
                    .font(.system(size: 20, weight: .semibold, design: .rounded))
                    .foregroundStyle(RSTheme.ink)
                    .accessibilityAddTraits(.isHeader)
                Spacer()
                CapsuleLabel(text: "You type this yourself", tone: .amber)
                    .accessibilityLabel("TTY required. Interactive terminal gate.")
            }
            Text("This window is the real approval step. Read the plan, then type APPROVE when you are ready. Assistants cannot approve unattended.")
                .font(.system(size: 13))
                .foregroundStyle(RSTheme.muted)
                .accessibilityLabel("Explanation: real PTY attached so interactive approval gate holds. Unattended agent approval is not possible.")
            if let argv = model.contract?.argv, !argv.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("What will run")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(RSTheme.soft)
                    Text(argv.joined(separator: " "))
                        .font(RSTheme.monoSmall)
                        .foregroundStyle(RSTheme.brand)
                        .textSelection(.enabled)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Bound command: \(argv.joined(separator: " "))")
            }
            DetailsDisclosure(title: "Show fingerprints and exact terms") {
                VStack(alignment: .leading, spacing: 6) {
                    if let campaign = model.contract?.campaignID {
                        labeled("Project (campaign)", campaign)
                    }
                    if let run = model.contract?.runID {
                        labeled("This run", run)
                    }
                    if let hash = model.contract?.contractHash {
                        labeled("Plan fingerprint (SHA-256)", hash)
                    }
                    Text("Human approval · TTY required. This sheet attaches runspecimen approve to a real PTY so the engine’s interactive gate still holds.")
                        .font(.system(size: 12))
                        .foregroundStyle(RSTheme.soft)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(16)
        .background(RSTheme.bgPanel.opacity(0.95))
    }

    private func labeled(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.system(size: 11))
                .foregroundStyle(RSTheme.soft)
            Text(value)
                .font(RSTheme.monoSmall)
                .foregroundStyle(RSTheme.ink)
                .textSelection(.enabled)
        }
    }

    private func startSession() {
        guard !sheet.started else { return }
        sheet.started = true
        guard let cli = model.cliIdentity?.path,
              let workspace = model.workspaceURL,
              let contract = model.contractURL else {
            sheet.sessionFailed = true
            sheet.statusNote = "Missing CLI, workspace, or contract. Close this sheet and finish setup."
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
            sheet.statusNote = "Waiting on you. When the prompt appears, type APPROVE yourself."
            announceAccessibility(sheet.statusNote)
        } catch {
            sheet.sessionFailed = true
            sheet.statusNote = (error as? AppError)?.message ?? error.localizedDescription
            announceAccessibility(sheet.statusNote)
        }
    }

    private func announceAccessibility(_ message: String) {
        NSAccessibility.post(
            element: NSApp as Any,
            notification: .announcementRequested,
            userInfo: [
                .announcement: message as NSString,
                .priority: NSAccessibilityPriorityLevel.medium.rawValue as NSNumber
            ]
        )
    }

    private func sendInput() {
        let line = sheet.input
        guard !line.isEmpty, !sheet.sessionFailed else { return }
        sheet.session?.sendLine(line)
        sheet.input = ""
        // Deliberately do not auto-detect or coerce APPROVE.
    }
}

@MainActor
final class ApproveSheetModel: ObservableObject {
    @Published var transcript = ""
    @Published var input = ""
    @Published var started = false
    @Published var sessionFailed = false
    @Published var statusNote = "Review the plan, then type APPROVE exactly when prompted."
    var session: PTYApprovalSession?
}
