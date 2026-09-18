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
            .rsReadableWidth(720)
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

            chipRow

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

            Text("REFUSE REASON")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
            TextField("Why this pending confirm is refused", text: $session.refuseReasonInput)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(12)
                .background(RSTheme.elevated)
                .foregroundStyle(RSTheme.ink)

            actionButton("Refuse pending (no approval)", tint: RSTheme.danger) {
                await session.submitRemoteRefuse()
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
