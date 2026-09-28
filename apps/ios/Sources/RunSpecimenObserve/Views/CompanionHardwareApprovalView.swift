import SwiftUI

/// The only screen that may pass `humanTap: true`.
///
/// Nothing on this screen calls the Secure Enclave until the person taps a button.
struct CompanionHardwareApprovalView: View {
    @State private var keyID = "iphone-companion"
    @State private var packageText = ""
    @State private var lines: [String] = []
    @State private var fields: RSBA2Package.Fields?
    @State private var message = "Face ID runs only after you tap a button on this screen. A software signature is not biometric completion."
    @State private var pairingText = ""
    @State private var signatureText = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                BoundaryBanner(text: message)
                Text("The key stays in this iPhone's Secure Enclave. The public pairing record is a file you carry to the Mac. This screen does not open a network connection.")
                    .font(.footnote)
                    .foregroundStyle(RSTheme.muted)
                TextField("Companion key id", text: $keyID)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .padding(12)
                    .background(RSTheme.elevated)
                    .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                Button("Enroll this iPhone") { enroll() }
                    .accessibilityHint("Asks for Face ID and creates a Secure Enclave key. Does not approve a Mac run by itself.")
                Button("Revoke this iPhone key") { revokeKey() }
                    .accessibilityHint("Asks for Face ID and revokes the enrolled key.")
                if !pairingText.isEmpty {
                    Text(pairingText)
                        .font(.system(.footnote, design: .monospaced))
                        .foregroundStyle(RSTheme.ink)
                        .textSelection(.enabled)
                }
                TextEditor(text: $packageText)
                    .font(.system(.footnote, design: .monospaced))
                    .frame(minHeight: 140)
                    .accessibilityLabel("Carried approval package to sign")
                Button("Show request") { showRequest() }
                    .accessibilityHint("Displays the request. Does not call Face ID.")
                Button("Sign with Face ID") { signPackage() }
                    .disabled(fields == nil)
                    .accessibilityHint("Asks for Face ID and signs the displayed request. Does not send the signature.")
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
        .navigationTitle("This iPhone")
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: packageText) { _, _ in
            lines = []
            fields = nil
            signatureText = ""
        }
        .onChange(of: keyID) { _, _ in
            pairingText = ""
            signatureText = ""
        }
    }

    private var directory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return base.appendingPathComponent("RunSpecimenObservePairing", isDirectory: true)
    }

    private func enroll() {
        signatureText = ""
        do {
            let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: keyID, directory: directory, humanTap: true)
            let carried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: record.keyID, directory: directory)
            pairingText = String(decoding: carried, as: UTF8.self)
            message = "Enrolled generation \(record.generation). Carry the public record to the Mac. This did not approve a run."
        } catch {
            pairingText = ""
            message = "Face ID enrollment did not finish. No Mac run was approved."
        }
    }

    private func revokeKey() {
        signatureText = ""
        do {
            try CompanionSecureEnclaveEnrollment.revoke(keyID: keyID, directory: directory, humanTap: true)
            pairingText = ""
            message = "This iPhone key is revoked. A later signature with the old generation will not verify."
        } catch {
            message = "Revocation did not finish. The previous key was not replaced."
        }
    }

    private func showRequest() {
        signatureText = ""
        guard let data = packageText.data(using: .utf8) else { return }
        let preview = CompanionApprovalPreview.parse(data)
        lines = preview.lines
        fields = preview.fields
        message = preview.refusal
    }

    private func signPackage() {
        guard let fields else {
            message = "Show an RSBA2 request before signing."
            return
        }
        do {
            let signature = try CompanionSecureEnclaveEnrollment.sign(fields: fields, directory: directory, humanTap: true)
            signatureText = signature.base64EncodedString()
            message = "Face ID signed this request on this iPhone. The signature was not sent. It is not physical presence at the Mac, and it does not start a run."
        } catch {
            signatureText = ""
            message = "Face ID signing did not finish. Nothing was sent."
        }
    }
}
