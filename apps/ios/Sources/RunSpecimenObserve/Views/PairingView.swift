import SwiftUI
import UIKit

enum PairingOutcome: Equatable {
    case none
    case inProgress
    case success
    case failure

    static var successMessage: String { "Connected successfully. The previous Mac session key and holder pin were cleared. Re-enter them in Advanced settings to use phone-peer enrollment." }
}

struct PairingView: View {
    @EnvironmentObject private var session: CompanionSession
    @State private var busy = false
    @State private var pairingTask: Task<Void, Never>?
    @State private var draftURL = ""
    @State private var draftToken = ""
    @State private var draftFingerprint = ""
    @State private var draftMacKey = ""
    @State private var draftHolderID = ""
    @State private var didLoadDraft = false
    @State private var initialMacKey = ""
    @State private var initialHolderID = ""
    @State private var pairingOutcome: PairingOutcome = .none
    @State private var showAdvanced = false
    private let feedbackGenerator = UINotificationFeedbackGenerator()

    private var urlIsValid: Bool {
        let trimmed = draftURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let url = URL(string: trimmed) else { return false }
        let scheme = (url.scheme ?? "").lowercased()
        return scheme == "http" || scheme == "https"
    }

    private var isLoopback: Bool {
        let trimmed = draftURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed) else { return false }
        let host = (url.host ?? "").lowercased()
        return host == "localhost" || host == "127.0.0.1" || host == "::1"
    }

    private var tokenIsValid: Bool {
        !draftToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var tlsRequired: Bool {
        let trimmed = draftURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed) else { return false }
        return (url.scheme ?? "").lowercased() == "https"
    }

    private var tlsIsValid: Bool {
        !tlsRequired || !draftFingerprint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var canPair: Bool {
        urlIsValid && !isLoopback && tokenIsValid && tlsIsValid && !busy
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
                        Text("Pair iPhone")
                            .font(.largeTitle.weight(.semibold))
                            .foregroundStyle(RSTheme.ink)
                            .minimumScaleFactor(0.7)
                            .lineLimit(1)
                        Text("Connect this iPhone to your Mac to observe runs. Key enrollment is a separate step.")
                            .font(.subheadline)
                            .foregroundStyle(RSTheme.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Connect to your Mac").font(.headline)
                    Text("1. Start the companion service on your Mac.\n2. Copy its reachable HTTPS URL, pairing token, and certificate fingerprint below.\n3. Tap Pair. Keep both devices on a network that can reach the Mac.")
                        .font(.footnote)
                    Text("The Mac must already provide a companion service. This screen does not start it or change the Mac’s network settings.")
                        .font(.caption).foregroundStyle(RSTheme.muted)
                }
                BoundaryBanner(text: session.boundaryCopy)

                VStack(alignment: .leading, spacing: 10) {
                    fieldLabel("Mac companion URL")
                    TextField("https://192.168.x.y:8787/", text: $draftURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .padding(12)
                        .background(RSTheme.elevated)
                        .foregroundStyle(RSTheme.ink)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .stroke((urlIsValid && !isLoopback) || draftURL.isEmpty ? Color.clear : RSTheme.danger.opacity(0.5), lineWidth: 1)
                        )
                    if isLoopback {
                        Text("127.0.0.1 and localhost cannot be used from this phone. Enter your Mac's local IP or Tailscale address.")
                            .font(.caption2)
                            .foregroundStyle(RSTheme.danger)
                    } else {
                        Text("The URL shown by the Mac companion. Use your Mac's local IP or Tailscale address.")
                            .font(.caption2)
                            .foregroundStyle(RSTheme.muted)
                    }

                    fieldLabel("Pairing token")
                    SecureField("Paste from Mac terminal", text: $draftToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding(12)
                        .background(RSTheme.elevated)
                        .foregroundStyle(RSTheme.ink)
                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .stroke(tokenIsValid || draftToken.isEmpty ? Color.clear : RSTheme.danger.opacity(0.5), lineWidth: 1)
                        )
                    Text("The token authorizes this phone to observe. Copy it from the Mac companion output.")
                        .font(.caption2)
                        .foregroundStyle(RSTheme.muted)

                    if tlsRequired {
                        fieldLabel("TLS certificate fingerprint")
                        TextField("SHA-256 fingerprint", text: $draftFingerprint)
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
                        TextField("For holder verification", text: $draftMacKey)
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
                        TextField("Holder identity to trust", text: $draftHolderID)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding(12)
                            .background(RSTheme.elevated)
                            .foregroundStyle(RSTheme.ink)
                            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))


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
                    guard let url = URL(string: draftURL.trimmingCharacters(in: .whitespacesAndNewlines)) else { return }
                    let candidate = PairingConfig(baseURL: url, pairingToken: draftToken,
                        tlsFingerprint: draftFingerprint.isEmpty ? nil : draftFingerprint)
                    let macKey = draftMacKey
                    let holderID = draftHolderID
                    feedbackGenerator.prepare()
                    busy = true
                    pairingOutcome = .inProgress
                    pairingTask?.cancel()
                    pairingTask = Task {
                        let paired = await session.saveAndPair(candidate: candidate)
                        busy = false
                        if paired {
                            session.applyVerifiedPairingTrustEdits(previousMacKey: initialMacKey, previousHolderID: initialHolderID, macKey: macKey, holderID: holderID)
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
                        Text(PairingOutcome.successMessage)
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
        .onDisappear { pairingTask?.cancel() }
        .onAppear {
            guard !didLoadDraft else { return }
            draftURL = session.baseURLString
            draftToken = session.pairingToken
            draftFingerprint = session.tlsFingerprint
            initialMacKey = session.macSessionPublicKey
            initialHolderID = session.pinnedHolderId
            draftMacKey = session.macSessionPublicKey
            draftHolderID = session.pinnedHolderId
            didLoadDraft = true
        }
    }

    private func fieldLabel(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.caption2.weight(.semibold))
            .foregroundStyle(RSTheme.muted)
            .tracking(0.6)
    }
}
