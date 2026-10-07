import SwiftUI

/// Buttons on this screen call the Secure Enclave directly.
///
/// Nothing calls it until the person taps. The tap is only the call site.
/// Face ID on the key operation is the authentication. Revoke does not evaluate
/// that context. Rotate enrolls the replacement through `enroll`, then revokes
/// the current key without a second prompt.
enum CompanionHardwareHints {
    static let revoke = "Revokes the enrolled key without asking for Face ID. Does not approve a Mac run."
    static let rotate = "Enrolls the replacement key through the same Secure Enclave enrollment as Enroll, then revokes the current key without asking for Face ID. Does not approve a Mac run."
}

struct CompanionHardwareApprovalView: View {
    @State private var keyID = "iphone-companion"
    @State private var replacementKeyID = "iphone-companion-2"
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
                    .accessibilityHint(CompanionHardwareHints.revoke)
                TextField("Replacement key id", text: $replacementKeyID)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .padding(12)
                    .background(RSTheme.elevated)
                    .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                Button("Rotate to the replacement key") { rotateKey() }
                    .accessibilityHint(CompanionHardwareHints.rotate)
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
            let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: keyID, directory: directory)
            let carried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: record.keyID, directory: directory)
            pairingText = String(decoding: carried, as: UTF8.self)
            message = "Enrolled generation \(record.generation). Carry the public record to the Mac. This did not approve a run."
        } catch {
            pairingText = ""
            message = "Face ID enrollment did not finish. No Mac run was approved."
        }
    }

    private func rotateKey() {
        signatureText = ""
        do {
            let record = try CompanionSecureEnclaveEnrollment.rotate(
                from: keyID,
                to: replacementKeyID,
                directory: directory
            )
            keyID = record.keyID
            let carried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: record.keyID, directory: directory)
            pairingText = String(decoding: carried, as: UTF8.self)
            message = "Replacement key generation \(record.generation) is enrolled. The previous key is revoked. This did not approve a run."
        } catch let error as CompanionHardwareRefusal {
            if case .malformed("rotation-incomplete") = error {
                message = "The replacement key was enrolled, and the previous key was not revoked. No run was approved."
            } else {
                pairingText = ""
                message = "Rotation did not finish. No Mac run was approved."
            }
        } catch {
            pairingText = ""
            message = "Rotation did not finish. No Mac run was approved."
        }
    }

    private func revokeKey() {
        signatureText = ""
        do {
            try CompanionSecureEnclaveEnrollment.revoke(keyID: keyID, directory: directory)
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
            let signature = try CompanionSecureEnclaveEnrollment.signDisplayed(
                packageText: packageText,
                displayed: fields,
                directory: directory
            )
            signatureText = signature.base64EncodedString()
            message = "Face ID signed this request on this iPhone. The signature was not sent. It is not physical presence at the Mac, and it does not start a run."
        } catch {
            signatureText = ""
            message = "Face ID signing did not finish. Nothing was sent."
        }
    }
}
