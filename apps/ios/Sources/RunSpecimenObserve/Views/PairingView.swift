import SwiftUI

struct PairingView: View {
    @EnvironmentObject private var session: CompanionSession
    @State private var busy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(spacing: 14) {
                    Image("BrandMark")
                        .resizable()
                        .scaledToFit()
                        .frame(width: 56, height: 56)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Observe")
                            .font(.largeTitle.weight(.semibold))
                            .foregroundStyle(RSTheme.ink)
                        Text("Pair with a Mac companion you explicitly enable.")
                            .font(.subheadline)
                            .foregroundStyle(RSTheme.muted)
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
                    busy = true
                    Task {
                        await session.saveAndPair()
                        busy = false
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

                if let error = session.lastError {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(RSTheme.danger)
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
            }
            .padding(20)
        }
    }

    private func fieldLabel(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.caption2.weight(.semibold))
            .foregroundStyle(RSTheme.muted)
            .tracking(0.6)
    }
}
