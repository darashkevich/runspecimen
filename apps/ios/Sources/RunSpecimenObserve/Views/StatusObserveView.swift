import SwiftUI
import UIKit

struct StatusObserveView: View {
    @EnvironmentObject private var session: CompanionSession
    @State private var busy = false
    @State private var lastRefreshTime: Date?
    @State private var showDisconnectConfirmation = false
    @State private var confirmOutcome: ActionResultState = .idle
    @State private var refuseOutcome: ActionResultState = .idle
    private let feedbackGenerator = UINotificationFeedbackGenerator()

    enum ActionResultState: Equatable {
        case idle
        case inProgress
        case success(String)
        case failure(String)
    }

    private var confirmIsValid: Bool {
        let challenge = session.challengeInput.trimmingCharacters(in: .whitespacesAndNewlines)
        let phrase = session.approvePhraseInput.trimmingCharacters(in: .whitespacesAndNewlines)
        return !challenge.isEmpty && phrase == "APPROVE"
    }

    private var refuseIsValid: Bool {
        let challenge = session.challengeInput.trimmingCharacters(in: .whitespacesAndNewlines)
        let reason = session.refuseReasonInput.trimmingCharacters(in: .whitespacesAndNewlines)
        return !challenge.isEmpty && (1...240).contains(reason.count)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                connectionStatus

                BoundaryBanner(text: session.boundaryCopy)

                lifecycleCard

                if session.remoteConfirmPending {
                    remoteConfirmPanel
                } else {
                    Text("No remote confirm pending. Primary approval is the Mac's local APPROVE command.")
                        .font(.footnote)
                        .foregroundStyle(RSTheme.muted)
                }

                phonePeerCard
                exactRunCard
                actionsCard

                if let note = session.lastAttentionNote {
                    resultBanner(note, isError: false)
                }
                if let note = session.lastRemoteConfirmNote {
                    resultBanner(note, isError: false)
                }
                if let error = session.lastError {
                    resultBanner(error, isError: true)
                }

                NavigationLink {
                    CompanionHardwareApprovalView()
                } label: {
                    HStack {
                        Image(systemName: "key.fill")
                            .foregroundStyle(RSTheme.cyan)
                        Text("Manage this iPhone's key")
                            .foregroundStyle(RSTheme.ink)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption)
                            .foregroundStyle(RSTheme.muted)
                    }
                    .padding(14)
                    .background(RSTheme.panel)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }

                safetyReminder

                disconnectButton
            }
            .padding(20)
            .rsReadableWidth(720)
        }
        .refreshable {
            await refreshWithTimestamp()
        }
        .task {
            await refreshWithTimestamp()
        }
        .confirmationDialog(
            "Disconnect from Mac?",
            isPresented: $showDisconnectConfirmation,
            titleVisibility: .visible
        ) {
            Button("Disconnect", role: .destructive) {
                session.disconnect()
            }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("This removes the pairing but does not revoke your iPhone key. To revoke, go to 'Manage this iPhone's key' first.")
        }
    }

    private var connectionStatus: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(session.status != nil ? RSTheme.signal : RSTheme.amber)
                .frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 2) {
                Text(session.status != nil ? "Connected" : "Offline")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(RSTheme.ink)
                if let time = lastRefreshTime {
                    Text("Updated \(time, style: .relative) ago")
                        .font(.caption2)
                        .foregroundStyle(RSTheme.muted)
                }
            }
            Spacer()
        }
        .padding(12)
        .background(RSTheme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private var lifecycleCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("LIFECYCLE")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
                .tracking(0.6)
            Text(session.status?.phase?.uppercased() ?? "—")
                .font(.largeTitle.weight(.semibold))
                .foregroundStyle(RSTheme.signal)
                .minimumScaleFactor(0.6)
                .lineLimit(1)
            FitHStack(spacing: 16, alignment: .top) {
                meta("Campaign", session.status?.campaignId ?? "—")
                meta("Run", session.status?.runId ?? "—")
            }
            FitHStack(spacing: 16, alignment: .top) {
                meta("Event chain", chainLabel)
                meta("Lease", leaseLabel)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RSTheme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private var phonePeerCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("PHONE PEER KEY")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
                .tracking(0.6)
            Text(session.phonePeerNote)
                .font(.footnote)
                .foregroundStyle(RSTheme.muted)
            actionButton("Sign phone peer challenge", tint: RSTheme.cyan) {
                await session.signPhonePeerChallenge()
            }
            actionButton("Cancel phone peer challenge", tint: RSTheme.danger) {
                await session.cancelPhonePeerChallenge()
            }
            actionButton("Enroll phone key after verification", tint: RSTheme.ink.opacity(0.85)) {
                await session.commitPhoneKeyAfterHolderVerification()
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RSTheme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private var exactRunCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("EXACT RUN")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
                .tracking(0.6)
            Text(session.exactRunNote)
                .font(.footnote)
                .foregroundStyle(RSTheme.muted)
            if !session.reviewedExactRunLines.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(session.reviewedExactRunLines.enumerated()), id: \.offset) { index, line in
                        formattedLine(line, index: index)
                    }
                }
                .padding(10)
                .background(RSTheme.elevated)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            }
            actionButton("Review exact run", tint: RSTheme.cyan) {
                await session.reviewRetainedExactRun()
            }
            actionButton("Sign reviewed exact run", tint: RSTheme.ink.opacity(0.85)) {
                await session.approveReviewedExactRun()
            }
            actionButton("Cancel exact run review", tint: RSTheme.danger) {
                session.cancelExactRunReview()
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RSTheme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    @ViewBuilder
    private func formattedLine(_ line: String, index: Int) -> some View {
        if line.hasPrefix("argv ") {
            VStack(alignment: .leading, spacing: 2) {
                Text("argv")
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(RSTheme.muted)
                let args = String(line.dropFirst(5))
                ForEach(Array(parseArgv(args).enumerated()), id: \.offset) { argIndex, arg in
                    HStack(alignment: .top, spacing: 4) {
                        Text("[\(argIndex)]")
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundStyle(RSTheme.muted)
                            .frame(width: 30, alignment: .trailing)
                        Text(escapeForDisplay(arg))
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(RSTheme.ink)
                            .textSelection(.enabled)
                    }
                }
            }
        } else {
            Text(line)
                .font(.system(.footnote, design: .monospaced))
                .foregroundStyle(RSTheme.ink)
                .textSelection(.enabled)
        }
    }

    private func parseArgv(_ joined: String) -> [String] {
        joined.components(separatedBy: " ")
    }

    private func escapeForDisplay(_ arg: String) -> String {
        var result = ""
        for char in arg {
            switch char {
            case "\n": result += "\\n"
            case "\r": result += "\\r"
            case "\t": result += "\\t"
            case "\0": result += "\\0"
            case " ": result += "␣"
            default:
                if char.asciiValue ?? 0 < 32 {
                    result += String(format: "\\x%02X", char.asciiValue ?? 0)
                } else {
                    result.append(char)
                }
            }
        }
        return result
    }

    private var actionsCard: some View {
        VStack(spacing: 10) {
            actionButton("Refresh status", tint: RSTheme.cyan) {
                await refreshWithTimestamp()
            }
            actionButton("Request attention on Mac", tint: RSTheme.amber) {
                await session.requestAttention()
            }
            actionButton("Open dashboard on Mac", tint: RSTheme.ink.opacity(0.85)) {
                await session.openDashboardOnMac()
            }
        }
    }

    private var remoteConfirmPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Remote Confirm")
                .font(.headline)
                .foregroundStyle(RSTheme.ink)
            Text(
                session.status?.companion?.remoteConfirm?.claim
                    ?? "Type the challenge shown on the Mac, then type APPROVE. This is not the same as the Mac's local APPROVE."
            )
            .font(.footnote)
            .foregroundStyle(RSTheme.muted)
            .fixedSize(horizontal: false, vertical: true)

            chipRow

            VStack(alignment: .leading, spacing: 4) {
                Text("CHALLENGE FROM MAC")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(RSTheme.muted)
                TextField("Enter challenge", text: $session.challengeInput)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                    .padding(12)
                    .background(RSTheme.elevated)
                    .foregroundStyle(RSTheme.ink)
                    .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 4, style: .continuous)
                            .stroke(session.challengeInput.isEmpty ? Color.clear : RSTheme.signal.opacity(0.3), lineWidth: 1)
                    )
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("TYPE APPROVE")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(RSTheme.muted)
                TextField("APPROVE", text: $session.approvePhraseInput)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                    .padding(12)
                    .background(RSTheme.elevated)
                    .foregroundStyle(RSTheme.ink)
                    .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 4, style: .continuous)
                            .stroke(session.approvePhraseInput == "APPROVE" ? RSTheme.signal.opacity(0.3) : Color.clear, lineWidth: 1)
                    )
                if !session.approvePhraseInput.isEmpty && session.approvePhraseInput != "APPROVE" {
                    Text("Must be exactly APPROVE")
                        .font(.caption2)
                        .foregroundStyle(RSTheme.danger)
                }
            }

            Button {
                feedbackGenerator.prepare()
                confirmOutcome = .inProgress
                Task {
                    await session.submitRemoteConfirm()
                    if session.lastError == nil {
                        feedbackGenerator.notificationOccurred(.success)
                        confirmOutcome = .success("Confirmed")
                    } else {
                        feedbackGenerator.notificationOccurred(.error)
                        confirmOutcome = .failure(session.lastError ?? "Failed")
                    }
                }
            } label: {
                HStack {
                    if case .inProgress = confirmOutcome {
                        ProgressView().tint(RSTheme.bg)
                    }
                    Text("Submit Confirm")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            }
            .buttonStyle(.borderedProminent)
            .tint(RSTheme.signal)
            .disabled(!confirmIsValid || confirmOutcome == .inProgress)

            outcomeView(confirmOutcome)

            Divider()

            VStack(alignment: .leading, spacing: 4) {
                Text("REFUSE REASON")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(RSTheme.muted)
                TextField("Why this is refused", text: $session.refuseReasonInput)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .padding(12)
                    .background(RSTheme.elevated)
                    .foregroundStyle(RSTheme.ink)
                    .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                Text("\(session.refuseReasonInput.count)/240 characters")
                    .font(.caption2)
                    .foregroundStyle(session.refuseReasonInput.count > 240 ? RSTheme.danger : RSTheme.muted)
            }

            Button {
                feedbackGenerator.prepare()
                refuseOutcome = .inProgress
                Task {
                    await session.submitRemoteRefuse()
                    if session.lastError == nil {
                        feedbackGenerator.notificationOccurred(.success)
                        refuseOutcome = .success("Refused")
                    } else {
                        feedbackGenerator.notificationOccurred(.error)
                        refuseOutcome = .failure(session.lastError ?? "Failed")
                    }
                }
            } label: {
                HStack {
                    if case .inProgress = refuseOutcome {
                        ProgressView().tint(RSTheme.bg)
                    }
                    Text("Refuse (no approval)")
                        .fontWeight(.semibold)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            }
            .buttonStyle(.borderedProminent)
            .tint(RSTheme.danger)
            .disabled(!refuseIsValid || refuseOutcome == .inProgress)

            outcomeView(refuseOutcome)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RSTheme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(RSTheme.signal.opacity(0.35), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func outcomeView(_ state: ActionResultState) -> some View {
        switch state {
        case .idle, .inProgress:
            EmptyView()
        case .success(let message):
            HStack(spacing: 6) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(RSTheme.signal)
                Text(message)
                    .font(.caption)
                    .foregroundStyle(RSTheme.ink)
            }
        case .failure(let message):
            HStack(spacing: 6) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(RSTheme.danger)
                Text(message)
                    .font(.caption)
                    .foregroundStyle(RSTheme.ink)
            }
        }
    }

    @ViewBuilder
    private func resultBanner(_ message: String, isError: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: isError ? "exclamationmark.triangle.fill" : "info.circle.fill")
                .foregroundStyle(isError ? RSTheme.danger : RSTheme.signal)
            Text(message)
                .font(.footnote)
                .foregroundStyle(RSTheme.ink)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background((isError ? RSTheme.danger : RSTheme.signal).opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
    }

    private var safetyReminder: some View {
        Text("This app cannot approve runs. The Mac's local APPROVE command is the primary control.")
            .font(.footnote.weight(.medium))
            .foregroundStyle(RSTheme.muted)
    }

    private var disconnectButton: some View {
        Button("Disconnect from Mac", role: .destructive) {
            showDisconnectConfirmation = true
        }
        .padding(.top, 8)
    }

    private var chipRow: some View {
        let pending = session.status?.companion?.remoteConfirm
        let chips = pending?.chips
        return LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 140), spacing: 8)],
            alignment: .leading,
            spacing: 8
        ) {
            chip("Who", pending?.who ?? "operator · workspace")
            chip("What", pending?.what ?? "—")
            chip("Expiry", chips?.expiry ?? "—")
            chip("Lease", chips?.lease ?? leaseLabel)
            chip("Isolation", chips?.isolation ?? "native-unspecified")
            chip("Predecessor", chips?.predecessor ?? "none")
        }
    }

    private func chip(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title.uppercased())
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
            Text(value)
                .font(.caption.monospaced())
                .foregroundStyle(RSTheme.ink)
                .lineLimit(2)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RSTheme.elevated)
        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
    }

    private var chainLabel: String {
        guard let ok = session.status?.eventChainOk else { return "—" }
        return ok ? "OK" : "Broken"
    }

    private var leaseLabel: String {
        guard let held = session.status?.workspaceLeaseHeldByOther else { return "—" }
        return held ? "Held" : "Free"
    }

    private func meta(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title.uppercased())
                .font(.caption2)
                .foregroundStyle(RSTheme.muted)
            Text(value)
                .font(.subheadline.monospaced())
                .foregroundStyle(RSTheme.ink)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func actionButton(_ title: String, tint: Color, action: @escaping () async -> Void) -> some View {
        Button {
            busy = true
            Task {
                await action()
                busy = false
            }
        } label: {
            Text(title)
                .fontWeight(.semibold)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
        }
        .buttonStyle(.borderedProminent)
        .tint(tint)
        .disabled(busy)
    }

    private func refreshWithTimestamp() async {
        await session.refresh()
        lastRefreshTime = Date()
    }
}
