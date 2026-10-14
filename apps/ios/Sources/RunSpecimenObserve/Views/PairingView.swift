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
    @State private var showAdvanced = false
    private let feedbackGenerator = UINotificationFeedbackGenerator()

    private var urlIsValid: Bool {
        let trimmed = session.baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed) else { return false }
        let scheme = (url.scheme ?? "").lowercased()
        return scheme == "http" || scheme == "https"
    }

    private var tokenIsValid: Bool {
        !session.pairingToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var tlsRequired: Bool {
        let trimmed = session.baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed) else { return false }
        return (url.scheme ?? "").lowercased() == "https"
    }

    private var tlsIsValid: Bool {
        !tlsRequired || !session.tlsFingerprint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var canPair: Bool {
        urlIsValid && tokenIsValid && tlsIsValid && !busy
    }

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
                        Text("Connect to a Mac you control to observe runs and sign requests.")
                            .font(.subheadline)
                            .foregroundStyle(RSTheme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                BoundaryBanner(text: session.boundaryCopy)

                VStack(alignment: .leading, spacing: 10) {
                    fieldLabel("Mac companion URL")
                    TextField("https://192.168.x.y:8787/", text: $session.baseURLString)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .padding(12)
                        .background(RSTheme.elevated)
                        .foregroundStyle(RSTheme.ink)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .stroke(urlIsValid || session.baseURLString.isEmpty ? Color.clear : RSTheme.danger.opacity(0.5), lineWidth: 1)
                        )
                    Text("The URL shown by the Mac companion. Use your Mac's local IP or Tailscale address, not 127.0.0.1.")
                        .font(.caption2)
                        .foregroundStyle(RSTheme.muted)

                    fieldLabel("Pairing token")
                    SecureField("Paste from Mac terminal", text: $session.pairingToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding(12)
                        .background(RSTheme.elevated)
                        .foregroundStyle(RSTheme.ink)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .stroke(tokenIsValid || session.pairingToken.isEmpty ? Color.clear : RSTheme.danger.opacity(0.5), lineWidth: 1)
                        )
                    Text("The token authorizes this phone to observe. Copy it from the Mac companion output.")
                        .font(.caption2)
                        .foregroundStyle(RSTheme.muted)

                    if tlsRequired {
                        fieldLabel("TLS certificate fingerprint")
                        TextField("SHA-256 fingerprint", text: $session.tlsFingerprint)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding(12)
                            .background(RSTheme.elevated)
                            .foregroundStyle(RSTheme.ink)
                            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 4, style: .continuous)
                                    .stroke(tlsIsValid ? Color.clear : RSTheme.danger.opacity(0.5), lineWidth: 1)
                            )
                        Text("Required for HTTPS. Copy tls_fingerprint_sha256 from the Mac companion output.")
                            .font(.caption2)
                            .foregroundStyle(RSTheme.muted)
                    }
                }

                DisclosureGroup("Advanced settings", isExpanded: $showAdvanced) {
                    VStack(alignment: .leading, spacing: 10) {
                        fieldLabel("Mac session public key")
                        TextField("For holder verification", text: $session.macSessionPublicKey)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding(12)
                            .background(RSTheme.elevated)
                            .foregroundStyle(RSTheme.ink)
                            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))

                        DisclosureGroup("What is this?") {
                            Text("The Mac holder generates a session key after local enrollment. This phone verifies holder receipts against that key. Without it, the phone only observes — it cannot verify holder signatures.")
                                .font(.caption2)
                                .foregroundStyle(RSTheme.muted)
                        }
                        .font(.caption)
                        .foregroundStyle(RSTheme.muted)

                        fieldLabel("Pinned holder ID")
                        TextField("Holder identity to trust", text: $session.pinnedHolderId)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding(12)
                            .background(RSTheme.elevated)
                            .foregroundStyle(RSTheme.ink)
                            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                            .onChange(of: session.pinnedHolderId) { _, _ in
                                session.rememberPinnedHolderId()
                            }

                        DisclosureGroup("What is this?") {
                            Text("When signing exact-run requests, the phone only signs if the holder ID in the request matches this pin. This prevents a compromised mailbox from substituting a different holder.")
                                .font(.caption2)
                                .foregroundStyle(RSTheme.muted)
                        }
                        .font(.caption)
                        .foregroundStyle(RSTheme.muted)
                    }
                    .padding(.top, 8)
                }
                .font(.subheadline)
                .foregroundStyle(RSTheme.ink)

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
                        Text(busy ? "Connecting…" : "Connect to Mac")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                }
                .buttonStyle(.borderedProminent)
                .tint(RSTheme.signal)
                .foregroundStyle(RSTheme.bg)
                .disabled(!canPair)

                if pairingOutcome == .success && session.lastError == nil {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(RSTheme.signal)
                        Text("Connected successfully")
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
                            Text("Connection failed")
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

                DisclosureGroup("How to set up the Mac") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("On your Mac, run:")
                            .font(.caption)
                            .foregroundStyle(RSTheme.muted)
                        Text(
                            """
                            runspecimen companion \\
                              --workspace <path> --contract <path> \\
                              --allow-lan --host <your-mac-ip> \\
                              --print-token
                            """
                        )
                        .font(.caption.monospaced())
                        .foregroundStyle(RSTheme.cyan)
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(RSTheme.elevated)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                        Text("Prefer Tailscale for secure connections. Copy the URL, token, and TLS fingerprint shown in the output.")
                            .font(.caption)
                            .foregroundStyle(RSTheme.muted)
                    }
                }
                .font(.subheadline)
                .foregroundStyle(RSTheme.ink)

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
