import SwiftUI
import UIKit

enum PairingOutcome: Equatable {
    case none
    case inProgress
    case success
    case failure
}

struct PairingView: View {
    @EnvironmentObject private var session: CompanionSession
    @State private var busy = false
    @State private var pairingOutcome: PairingOutcome = .none
    private let feedbackGenerator = UINotificationFeedbackGenerator()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                FitHStack(spacing: 14, alignment: .top) {
                    Image("BrandMark")
                        .resizable()
                        .scaledToFit()
                        .frame(width: 56, height: 56)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Observe")
                            .font(.largeTitle.weight(.semibold))
                            .foregroundStyle(RSTheme.ink)
                            .minimumScaleFactor(0.7)
                            .lineLimit(1)
                        Text("Pair with a Mac companion you explicitly enable.")
                            .font(.subheadline)
                            .foregroundStyle(RSTheme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                BoundaryBanner(text: session.boundaryCopy)

                VStack(alignment: .leading, spacing: 10) {
                    fieldLabel("Companion URL")
                    TextField("http://100.x.y.z:8787/", text: $session.baseURLString)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .padding(12)
                        .background(RSTheme.elevated)
                        .foregroundStyle(RSTheme.ink)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))

                    fieldLabel("Pairing token")
                    SecureField("From `runspecimen companion --print-token`", text: $session.pairingToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding(12)
                        .background(RSTheme.elevated)
                        .foregroundStyle(RSTheme.ink)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))

                    fieldLabel("Mac session public key")
                    TextField("From the holder after local enrollment", text: $session.macSessionPublicKey)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding(12)
                        .background(RSTheme.elevated)
                        .foregroundStyle(RSTheme.ink)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                    Text("The phone checks the holder receipt against this key. A mailbox verified flag is not a receipt.")
                        .font(.caption2)
                        .foregroundStyle(RSTheme.muted)

                    fieldLabel("Pinned holder id")
                    TextField("From the Mac holder, not from the request", text: $session.pinnedHolderId)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding(12)
                        .background(RSTheme.elevated)
                        .foregroundStyle(RSTheme.ink)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                        .onChange(of: session.pinnedHolderId) { _, _ in
                            session.rememberPinnedHolderId()
                        }
                    Text("An exact-run holder id is signed only when it matches this pin. The mailbox value alone is not trusted.")
                        .font(.caption2)
                        .foregroundStyle(RSTheme.muted)

                    fieldLabel("TLS fingerprint (HTTPS / LAN)")
                    TextField("tls_fingerprint_sha256 from Mac", text: $session.tlsFingerprint)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding(12)
                        .background(RSTheme.elevated)
                        .foregroundStyle(RSTheme.ink)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                    Text("Required for https:// URLs. Loopback http://127.0.0.1 can omit it.")
                        .font(.caption2)
                        .foregroundStyle(RSTheme.muted)
                }

                Button {
                    feedbackGenerator.prepare()
                    busy = true
                    pairingOutcome = .inProgress
                    Task {
                        await session.saveAndPair()
                        busy = false
                        if session.lastError == nil {
                            feedbackGenerator.notificationOccurred(.success)
                            pairingOutcome = .success
                        } else {
                            feedbackGenerator.notificationOccurred(.error)
                            pairingOutcome = .failure
                        }
                    }
                } label: {
                    HStack {
                        if busy { ProgressView().tint(RSTheme.bg) }
                        Text(busy ? "Pairing…" : "Pair & verify capabilities")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                }
                .buttonStyle(.borderedProminent)
                .tint(RSTheme.signal)
                .foregroundStyle(RSTheme.bg)
                .disabled(busy)

                if pairingOutcome == .success && session.lastError == nil {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(RSTheme.signal)
                        Text("Paired successfully")
                            .font(.subheadline)
                            .foregroundStyle(RSTheme.ink)
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RSTheme.signal.opacity(0.12))
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }

                if let error = session.lastError {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 8) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(RSTheme.danger)
                            Text("Pairing failed")
                                .font(.subheadline)
                                .foregroundStyle(RSTheme.ink)
                        }
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(RSTheme.muted)
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RSTheme.danger.opacity(0.12))
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("On the Mac")
                        .font(.headline)
                        .foregroundStyle(RSTheme.ink)
                    Text(
                        """
                        runspecimen companion \\
                          --workspace … --contract … \\
                          --allow-lan --host <private-or-tailscale-ip> \\
                          --print-token
                        # Prefer Tailscale. Non-loopback enables TLS automatically.
                        # Paste url + pairing_token + tls_fingerprint_sha256 here.
                        """
                    )
                    .font(.caption.monospaced())
                    .foregroundStyle(RSTheme.cyan)
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RSTheme.elevated)
                }

                NavigationLink {
                    CompanionApprovalPreviewView()
                } label: {
                    HStack {
                        Image(systemName: "doc.text.magnifyingglass")
                            .foregroundStyle(RSTheme.cyan)
                        Text("Review a carried approval")
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
                .accessibilityHint("Shows a package a person carried. Does not call Face ID.")

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
                .accessibilityHint("Enroll, revoke, rotate, or sign with the Secure Enclave key.")

                #if RS_OBSERVE_DEV_SIGNER
                NavigationLink("Development software signature") {
                    DevelopmentCompanionSignView()
                }
                .accessibilityHint("Development app only. A software signature is not biometric completion.")
                #endif
            }
            .padding(20)
            .rsReadableWidth(720)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func fieldLabel(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.caption2.weight(.semibold))
            .foregroundStyle(RSTheme.muted)
            .tracking(0.6)
    }
}
