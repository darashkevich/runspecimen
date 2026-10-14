import CryptoKit
import SwiftUI

/// Development-only software signing. The shipping Observe target does not compile this file.
struct DevelopmentCompanionSignView: View {
    @State private var packageText = ""
    @State private var lines: [String] = []
    @State private var message = "Development software signature only. This is not Face ID and it does not approve a Mac run."
    @State private var fields: RSBA2Package.Fields?
    @State private var developmentKeyRaw: Data?
    @State private var developmentRecord: DevelopmentPairingRecord?
    @State private var signatureText = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                BoundaryBanner(text: message)
                Text("This screen exists only in the development app. A software signature is not biometric completion.")
                    .font(.footnote)
                    .foregroundStyle(RSTheme.muted)
                TextEditor(text: $packageText)
                    .font(.system(.footnote, design: .monospaced))
                    .frame(minHeight: 160)
                    .accessibilityLabel("Development approval package")
                Button("Show request") { showRequest() }
                Button("Create development software key") { createDevelopmentKey() }
                    .accessibilityHint("Creates a software P-256 key. Does not call Face ID or the Secure Enclave.")
                if let developmentRecord {
                    Text("Development pairing record: key \(developmentRecord.keyID), generation \(developmentRecord.generation), backend \(developmentRecord.backend).")
                        .font(.system(.footnote, design: .monospaced))
                        .foregroundStyle(RSTheme.ink)
                        .textSelection(.enabled)
                }
                Button("Sign with development software key") { signWithDevelopmentKey() }
                    .disabled(fields == nil || developmentKeyRaw == nil)
                    .accessibilityHint("Signs with the software key. Does not call Face ID and does not send the signature.")
                if !signatureText.isEmpty {
                    Text(signatureText)
                        .font(.system(.footnote, design: .monospaced))
                        .foregroundStyle(RSTheme.ink)
                        .textSelection(.enabled)
                }
                ForEach(lines, id: \.self) { line in
                    Text(line)
                        .font(.system(.footnote, design: .monospaced))
                        .foregroundStyle(RSTheme.ink)
                        .textSelection(.enabled)
                }
            }
            .padding(20)
        }
        .background(RSTheme.bg)
        .navigationTitle("Development signature")
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: packageText) { _, _ in
            lines = []
            fields = nil
            signatureText = ""
            message = "Development software signature only. This is not Face ID and it does not approve a Mac run."
        }
    }

    private func showRequest() {
        signatureText = ""
        guard let data = packageText.data(using: .utf8) else { return }
        let preview = CompanionApprovalPreview.parse(data)
        lines = preview.lines
        message = preview.refusal
        fields = preview.fields
    }

    private func createDevelopmentKey() {
        let key = DevelopmentCompanionSigner.makeKey()
        developmentKeyRaw = key.rawRepresentation
        developmentRecord = DevelopmentCompanionSigner.record(keyID: "ios-dev-phone", generation: 1, key: key)
        signatureText = ""
        message = "Development software key created in this screen. It is not Face ID and it does not approve a Mac run."
    }

    private func signWithDevelopmentKey() {
        guard let fields, let developmentRecord, let developmentKeyRaw,
              let key = try? P256.Signing.PrivateKey(rawRepresentation: developmentKeyRaw) else {
            message = "Show an RSBA2 request and create a development software key before signing."
            return
        }
        do {
            let signature = try DevelopmentCompanionSigner.sign(fields: fields, record: developmentRecord, key: key)
            signatureText = "Development software signature (not Face ID, not sent, not a Mac approval): \(signature.base64EncodedString())"
            message = "A development software signature is not biometric completion."
        } catch {
            signatureText = ""
            message = "The development software key does not match this request's companion key id and generation, or the policy is local-only."
        }
    }
}
