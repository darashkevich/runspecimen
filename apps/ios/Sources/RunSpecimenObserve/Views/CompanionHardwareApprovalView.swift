import SwiftUI
import UIKit

enum CompanionHardwareHints {
    static let revoke = "Asks for Face ID and revokes this iPhone key. If Face ID is cancelled, nothing changes. Does not approve a Mac run."
    static let rotate = "Asks for Face ID once, then creates a replacement key and revokes the current key. If Face ID is cancelled or any step fails, the old key stays active and nothing changes. Does not approve a Mac run."
}

enum KeyState: Equatable {
    case unknown
    case noKey
    case active(generation: Int)
    case revoked(generation: Int)

    var statusLabel: String {
        switch self {
        case .unknown: return "Checking…"
        case .noKey: return "No key"
        case .active(let gen): return "Active (generation \(gen))"
        case .revoked(let gen): return "Revoked (generation \(gen))"
        }
    }

    var statusColor: Color {
        switch self {
        case .unknown: return RSTheme.muted
        case .noKey: return RSTheme.muted
        case .active: return RSTheme.signal
        case .revoked: return RSTheme.danger
        }
    }

    var statusIcon: String {
        switch self {
        case .unknown: return "questionmark.circle"
        case .noKey: return "key.slash"
        case .active: return "checkmark.shield.fill"
        case .revoked: return "xmark.shield.fill"
        }
    }
}

enum ActionOutcome: Equatable {
    case none
    case inProgress
    case success(String)
    case failure(message: String, detail: String?)
}

struct CompanionHardwareApprovalView: View {
    @State private var keyID = "iphone-companion"
    @State private var replacementKeyID = "iphone-companion-2"
    @State private var packageText = ""
    @State private var lines: [String] = []
    @State private var fields: RSBA2Package.Fields?
    @State private var pairingText = ""
    @State private var signatureText = ""
    @State private var keyState: KeyState = .unknown

    @State private var enrollOutcome: ActionOutcome = .none
    @State private var revokeOutcome: ActionOutcome = .none
    @State private var rotateOutcome: ActionOutcome = .none
    @State private var showOutcome: ActionOutcome = .none
    @State private var signOutcome: ActionOutcome = .none

    @State private var showRevokeConfirmation = false
    @State private var showRotateConfirmation = false
    @State private var showDetailsExpanded = false

    private let feedbackGenerator = UINotificationFeedbackGenerator()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                keyStateCard
                enrollSection
                Divider().background(RSTheme.muted.opacity(0.3))
                revokeRotateSection
                Divider().background(RSTheme.muted.opacity(0.3))
                signRequestSection
            }
            .padding(20)
        }
        .background(RSTheme.bg)
        .navigationTitle("This iPhone")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { refreshKeyState() }
        .onChange(of: keyID) { _, _ in
            pairingText = ""
            signatureText = ""
            refreshKeyState()
        }
        .onChange(of: packageText) { _, _ in
            lines = []
            fields = nil
            signatureText = ""
            showOutcome = .none
            signOutcome = .none
        }
        .confirmationDialog(
            "Revoke this key?",
            isPresented: $showRevokeConfirmation,
            titleVisibility: .visible
        ) {
            Button("Revoke Key", role: .destructive) { revokeKey() }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("This will permanently revoke the key '\(keyID)'. Any signed requests using this key will no longer verify. This cannot be undone.")
        }
        .confirmationDialog(
            "Rotate to a new key?",
            isPresented: $showRotateConfirmation,
            titleVisibility: .visible
        ) {
            Button("Rotate Key", role: .destructive) { rotateKey() }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("This will create a new key '\(replacementKeyID)' and revoke the current key '\(keyID)'. The old key will no longer work. Face ID is required once.")
        }
    }

    private var directory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return base.appendingPathComponent("RunSpecimenObservePairing", isDirectory: true)
    }

    private var keyStateCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("KEY STATUS")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
                .tracking(0.6)

            HStack(spacing: 12) {
                Image(systemName: keyState.statusIcon)
                    .font(.title2)
                    .foregroundStyle(keyState.statusColor)

                VStack(alignment: .leading, spacing: 2) {
                    Text(keyState.statusLabel)
                        .font(.headline)
                        .foregroundStyle(RSTheme.ink)
                    Text("Key ID: \(keyID)")
                        .font(.caption)
                        .foregroundStyle(RSTheme.muted)
                }
                Spacer()
            }
            .padding(14)
            .background(RSTheme.panel)
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

            TextField("Key ID", text: $keyID)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(12)
                .background(RSTheme.elevated)
                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))

            Text("The key stays in this iPhone's Secure Enclave. Only the public pairing record leaves the device.")
                .font(.caption)
                .foregroundStyle(RSTheme.muted)
        }
    }

    private var enrollSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("ENROLL")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
                .tracking(0.6)

            actionButton(
                title: "Enroll this iPhone",
                icon: "key.fill",
                tint: RSTheme.cyan,
                outcome: enrollOutcome,
                disabled: !canEnroll
            ) {
                enroll()
            }

            outcomeView(outcome: enrollOutcome)

            if !pairingText.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Pairing record ready")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(RSTheme.signal)

                    HStack(spacing: 12) {
                        Button {
                            UIPasteboard.general.string = pairingText
                            let generator = UINotificationFeedbackGenerator()
                            generator.notificationOccurred(.success)
                        } label: {
                            Label("Copy", systemImage: "doc.on.doc")
                                .font(.subheadline.weight(.semibold))
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 10)
                        }
                        .buttonStyle(.bordered)
                        .tint(RSTheme.cyan)

                        ShareLink(item: pairingText) {
                            Label("Share", systemImage: "square.and.arrow.up")
                                .font(.subheadline.weight(.semibold))
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 10)
                        }
                        .buttonStyle(.bordered)
                        .tint(RSTheme.cyan)
                    }

                    DisclosureGroup("Show pairing record") {
                        Text(pairingText)
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundStyle(RSTheme.ink)
                            .textSelection(.enabled)
                            .padding(8)
                            .background(RSTheme.elevated)
                            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                    }
                    .font(.caption)
                    .foregroundStyle(RSTheme.muted)
                }
                .padding(12)
                .background(RSTheme.panel)
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }

            Text("Creates a Secure Enclave key. The key is protected by Face ID when used for signing, not during enrollment.")
                .font(.caption)
                .foregroundStyle(RSTheme.muted)
        }
    }

    private var revokeRotateSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("MANAGE KEY")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
                .tracking(0.6)

            actionButton(
                title: "Revoke this key",
                icon: "xmark.circle.fill",
                tint: RSTheme.danger,
                outcome: revokeOutcome,
                disabled: !canRevokeOrRotate
            ) {
                showRevokeConfirmation = true
            }

            outcomeView(outcome: revokeOutcome)

            TextField("Replacement key ID", text: $replacementKeyID)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(12)
                .background(RSTheme.elevated)
                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))

            actionButton(
                title: "Rotate to new key",
                icon: "arrow.triangle.2.circlepath",
                tint: RSTheme.amber,
                outcome: rotateOutcome,
                disabled: !canRevokeOrRotate
            ) {
                showRotateConfirmation = true
            }

            outcomeView(outcome: rotateOutcome)

            Text("Revoke permanently disables the key. Rotate creates a replacement and revokes the old key in one step. Both require Face ID.")
                .font(.caption)
                .foregroundStyle(RSTheme.muted)
        }
    }

    private var signRequestSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("SIGN A REQUEST")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(RSTheme.muted)
                .tracking(0.6)

            Text("Paste a carried approval package from the Mac, then review and sign it.")
                .font(.caption)
                .foregroundStyle(RSTheme.muted)

            TextEditor(text: $packageText)
                .font(.system(.caption, design: .monospaced))
                .frame(minHeight: 100)
                .padding(8)
                .background(RSTheme.elevated)
                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                .accessibilityLabel("Carried approval package to sign")

            actionButton(
                title: "Show request",
                icon: "doc.text.magnifyingglass",
                tint: RSTheme.cyan,
                outcome: showOutcome,
                disabled: packageText.isEmpty
            ) {
                showRequest()
            }

            outcomeView(outcome: showOutcome)

            if !lines.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(lines, id: \.self) { line in
                        Text(line)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(RSTheme.ink)
                            .textSelection(.enabled)
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RSTheme.panel)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            }

            actionButton(
                title: "Sign with Face ID",
                icon: "faceid",
                tint: RSTheme.signal,
                outcome: signOutcome,
                disabled: fields == nil || !canSign
            ) {
                signPackage()
            }

            outcomeView(outcome: signOutcome)

            if !signatureText.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.seal.fill")
                            .foregroundStyle(RSTheme.signal)
                        Text("Signed")
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(RSTheme.signal)
                    }

                    Button {
                        UIPasteboard.general.string = signatureText
                        let generator = UINotificationFeedbackGenerator()
                        generator.notificationOccurred(.success)
                    } label: {
                        Label("Copy signature", systemImage: "doc.on.doc")
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                    }
                    .buttonStyle(.bordered)
                    .tint(RSTheme.signal)

                    DisclosureGroup("Show signature") {
                        Text(signatureText)
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundStyle(RSTheme.ink)
                            .textSelection(.enabled)
                            .padding(8)
                            .background(RSTheme.elevated)
                            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                    }
                    .font(.caption)
                    .foregroundStyle(RSTheme.muted)
                }
                .padding(12)
                .background(RSTheme.panel)
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }

            Text("The signature is not sent automatically. Carry it back to the Mac. Signing does not start a run by itself.")
                .font(.caption)
                .foregroundStyle(RSTheme.muted)
        }
    }

    private var canEnroll: Bool {
        if case .active = keyState { return false }
        if case .inProgress = enrollOutcome { return false }
        return true
    }

    private var canRevokeOrRotate: Bool {
        guard case .active = keyState else { return false }
        if case .inProgress = revokeOutcome { return false }
        if case .inProgress = rotateOutcome { return false }
        return true
    }

    private var canSign: Bool {
        guard case .active = keyState else { return false }
        if case .inProgress = signOutcome { return false }
        return true
    }

    @ViewBuilder
    private func actionButton(
        title: String,
        icon: String,
        tint: Color,
        outcome: ActionOutcome,
        disabled: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button {
            action()
        } label: {
            HStack(spacing: 10) {
                if case .inProgress = outcome {
                    ProgressView()
                        .tint(RSTheme.bg)
                } else {
                    Image(systemName: icon)
                }
                Text(title)
                    .fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
        }
        .buttonStyle(.borderedProminent)
        .tint(tint)
        .foregroundStyle(RSTheme.bg)
        .disabled(disabled || outcome == .inProgress)
    }

    @ViewBuilder
    private func outcomeView(outcome: ActionOutcome) -> some View {
        switch outcome {
        case .none, .inProgress:
            EmptyView()
        case .success(let message):
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(RSTheme.signal)
                Text(message)
                    .font(.subheadline)
                    .foregroundStyle(RSTheme.ink)
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RSTheme.signal.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        case .failure(let message, let detail):
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(RSTheme.danger)
                    Text(message)
                        .font(.subheadline)
                        .foregroundStyle(RSTheme.ink)
                }
                if let detail {
                    DisclosureGroup("Details") {
                        Text(detail)
                            .font(.caption)
                            .foregroundStyle(RSTheme.muted)
                    }
                    .font(.caption)
                    .foregroundStyle(RSTheme.muted)
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RSTheme.danger.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        }
    }

    private func refreshKeyState() {
        keyState = .unknown
        do {
            let record = try CompanionSecureEnclaveEnrollment.inspect(keyID: keyID, directory: directory)
            if record.state == CompanionSecureEnclaveEnrollment.active {
                keyState = .active(generation: record.generation)
            } else {
                keyState = .revoked(generation: record.generation)
            }
        } catch CompanionHardwareRefusal.missing {
            keyState = .noKey
        } catch {
            keyState = .noKey
        }
    }

    private func enroll() {
        feedbackGenerator.prepare()
        enrollOutcome = .inProgress
        signatureText = ""
        pairingText = ""

        DispatchQueue.global(qos: .userInitiated).async {
            let result: Result<CompanionPairingRecord, Error>
            do {
                let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: keyID, directory: directory)
                let carried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: record.keyID, directory: directory)
                result = .success(record)
                DispatchQueue.main.async {
                    pairingText = String(decoding: carried, as: UTF8.self)
                }
            } catch {
                result = .failure(error)
            }

            DispatchQueue.main.async {
                switch result {
                case .success(let record):
                    feedbackGenerator.notificationOccurred(.success)
                    enrollOutcome = .success("Key enrolled (generation \(record.generation)). Share the pairing record with the Mac.")
                    keyState = .active(generation: record.generation)
                case .failure(let error):
                    feedbackGenerator.notificationOccurred(.error)
                    let (message, detail) = describeError(error, action: "enroll")
                    enrollOutcome = .failure(message: message, detail: detail)
                    refreshKeyState()
                }
            }
        }
    }

    private func revokeKey() {
        feedbackGenerator.prepare()
        revokeOutcome = .inProgress
        signatureText = ""
        pairingText = ""

        DispatchQueue.global(qos: .userInitiated).async {
            let result: Result<Void, Error>
            do {
                try CompanionSecureEnclaveEnrollment.revoke(keyID: keyID, directory: directory)
                result = .success(())
            } catch {
                result = .failure(error)
            }

            DispatchQueue.main.async {
                switch result {
                case .success:
                    feedbackGenerator.notificationOccurred(.success)
                    revokeOutcome = .success("Key revoked. It can no longer sign requests.")
                    refreshKeyState()
                case .failure(let error):
                    feedbackGenerator.notificationOccurred(.error)
                    let (message, detail) = describeError(error, action: "revoke")
                    revokeOutcome = .failure(message: message, detail: detail)
                }
            }
        }
    }

    private func rotateKey() {
        feedbackGenerator.prepare()
        rotateOutcome = .inProgress
        signatureText = ""
        pairingText = ""

        DispatchQueue.global(qos: .userInitiated).async {
            let result: Result<CompanionPairingRecord, Error>
            do {
                let record = try CompanionSecureEnclaveEnrollment.rotate(
                    from: keyID,
                    to: replacementKeyID,
                    directory: directory
                )
                let carried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: record.keyID, directory: directory)
                result = .success(record)
                DispatchQueue.main.async {
                    self.keyID = record.keyID
                    pairingText = String(decoding: carried, as: UTF8.self)
                }
            } catch {
                result = .failure(error)
            }

            DispatchQueue.main.async {
                switch result {
                case .success(let record):
                    feedbackGenerator.notificationOccurred(.success)
                    rotateOutcome = .success("New key active (generation \(record.generation)). Old key revoked.")
                    keyState = .active(generation: record.generation)
                case .failure(let error):
                    feedbackGenerator.notificationOccurred(.error)
                    let (message, detail) = describeError(error, action: "rotate")
                    rotateOutcome = .failure(message: message, detail: detail)
                    refreshKeyState()
                }
            }
        }
    }

    private func showRequest() {
        feedbackGenerator.prepare()
        showOutcome = .inProgress
        signatureText = ""

        guard let data = packageText.data(using: .utf8) else {
            feedbackGenerator.notificationOccurred(.error)
            showOutcome = .failure(message: "Could not read the package text.", detail: "The text could not be encoded as UTF-8.")
            return
        }

        let preview = CompanionApprovalPreview.parse(data)
        lines = preview.lines
        fields = preview.fields

        if fields != nil {
            feedbackGenerator.notificationOccurred(.success)
            showOutcome = .success("Request decoded. Review it above, then sign.")
        } else {
            feedbackGenerator.notificationOccurred(.warning)
            showOutcome = .failure(message: preview.refusal.isEmpty ? "Could not parse the request." : preview.refusal, detail: "Ensure you pasted a complete RSBA2 package from the Mac.")
        }
    }

    private func signPackage() {
        guard let fields else {
            signOutcome = .failure(message: "No request to sign.", detail: "Use 'Show request' first to decode a package.")
            return
        }

        feedbackGenerator.prepare()
        signOutcome = .inProgress
        signatureText = ""

        DispatchQueue.global(qos: .userInitiated).async {
            let result: Result<Data, Error>
            do {
                let signature = try CompanionSecureEnclaveEnrollment.signDisplayed(
                    packageText: packageText,
                    displayed: fields,
                    directory: directory
                )
                result = .success(signature)
            } catch {
                result = .failure(error)
            }

            DispatchQueue.main.async {
                switch result {
                case .success(let signature):
                    feedbackGenerator.notificationOccurred(.success)
                    signatureText = signature.base64EncodedString()
                    signOutcome = .success("Signed. Copy the signature and carry it back to the Mac.")
                case .failure(let error):
                    feedbackGenerator.notificationOccurred(.error)
                    let (message, detail) = describeError(error, action: "sign")
                    signOutcome = .failure(message: message, detail: detail)
                }
            }
        }
    }

    private func describeError(_ error: Error, action: String) -> (message: String, detail: String?) {
        if let refusal = error as? CompanionHardwareRefusal {
            switch refusal {
            case .automationRefused:
                return ("Cancelled.", "You cancelled Face ID or it was interrupted by the system.")
            case .missing:
                return ("No key found.", "Enroll a key with this ID first.")
            case .malformed(let detail):
                return ("Something went wrong.", "Internal error: \(detail)")
            case .staleRequest:
                return ("The request changed.", "Use 'Show request' again with the current package.")
            case .alreadyEnrolled:
                return ("A key with this ID already exists.", "Revoke the existing key first, or use a different ID.")
            }
        }
        return ("Unexpected error.", error.localizedDescription)
    }
}
