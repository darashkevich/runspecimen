import SwiftUI

struct StatusObserveView: View {
    @EnvironmentObject private var session: CompanionSession
    @State private var busy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                BoundaryBanner(text: session.boundaryCopy)

                VStack(alignment: .leading, spacing: 8) {
                    Text("Lifecycle")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(RSTheme.muted)
                    Text(session.status?.phase?.uppercased() ?? "—")
                        .font(.system(size: 34, weight: .semibold, design: .rounded))
                        .foregroundStyle(RSTheme.signal)
                    HStack(spacing: 16) {
                        meta("Campaign", session.status?.campaignId ?? "—")
                        meta("Run", session.status?.runId ?? "—")
                    }
                    HStack(spacing: 16) {
                        meta("Event chain", chainLabel)
                        meta("Lease", leaseLabel)
                    }
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RSTheme.panel)

                if session.remoteConfirmPending {
                    remoteConfirmPanel
                } else {
                    Text("No Mac-armed remote confirm pending. Primary approval remains Mac TTY APPROVE.")
                        .font(.footnote)
                        .foregroundStyle(RSTheme.muted)
                }

                VStack(spacing: 10) {
                    actionButton("Refresh status", tint: RSTheme.cyan) {
                        await session.refresh()
                    }
                    actionButton("Request attention on Mac", tint: RSTheme.amber) {
                        await session.requestAttention()
                    }
                    actionButton("Open local dashboard on Mac", tint: RSTheme.ink.opacity(0.85)) {
                        await session.openDashboardOnMac()
                    }
                }

                if let note = session.lastAttentionNote {
                    Text(note)
                        .font(.footnote)
                        .foregroundStyle(RSTheme.signal)
                }
                if let note = session.lastRemoteConfirmNote {
                    Text(note)
                        .font(.footnote)
                        .foregroundStyle(RSTheme.signal)
                }
                if let error = session.lastError {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(RSTheme.danger)
                }

                Text("There is no one-tap Approve control. Plugins cannot approve through this app.")
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(RSTheme.muted)

                Button("Disconnect pairing", role: .destructive) {
                    session.disconnect()
                }
                .padding(.top, 8)
            }
            .padding(20)
        }
        .refreshable {
            await session.refresh()
        }
        .task {
            await session.refresh()
        }
    }

    private var remoteConfirmPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Remote human confirm")
                .font(.headline)
                .foregroundStyle(RSTheme.ink)
            Text(
                session.status?.companion?.remoteConfirm?.claim
                    ?? "Type the challenge shown on the Mac, then type APPROVE. Not equivalent to local TTY APPROVE."
            )
            .font(.footnote)
            .foregroundStyle(RSTheme.muted)
            .fixedSize(horizontal: false, vertical: true)

            Text("MAC CHALLENGE")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
            TextField("Challenge from Mac display", text: $session.challengeInput)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .padding(12)
                .background(RSTheme.elevated)
                .foregroundStyle(RSTheme.ink)

            Text("CONFIRM PHRASE")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
            TextField("Type APPROVE", text: $session.approvePhraseInput)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .padding(12)
                .background(RSTheme.elevated)
                .foregroundStyle(RSTheme.ink)

            actionButton("Submit remote human confirm", tint: RSTheme.signal) {
                await session.submitRemoteConfirm()
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RSTheme.panel)
        .overlay(
            RoundedRectangle(cornerRadius: 4, style: .continuous)
                .stroke(RSTheme.signal.opacity(0.35), lineWidth: 1)
        )
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
}
