import SwiftUI
import UIKit
import UniformTypeIdentifiers

enum CompanionHardwareHints {
    static let revoke = "Asks for Face ID and revokes this iPhone key. If Face ID is cancelled, nothing changes. Does not approve a Mac run."
    static let rotate = "Asks for Face ID once, then creates a replacement key and revokes the current key. If Face ID is cancelled or any step fails, the old key stays active and nothing changes. Does not approve a Mac run."
}

enum KeyState: Equatable {
    case unknown
    case noKey
    case active(generation: Int, macUpdatePending: Bool)
    case revoked(generation: Int, macUpdatePending: Bool)

    var statusLabel: String {
        switch self {
        case .unknown: return "Checking…"
        case .noKey: return "No key enrolled"
        case .active(let gen, let pending):
            return pending ? "Active (gen \(gen)) · Mac update needed" : "Active (generation \(gen))"
        case .revoked(let gen, let pending):
            return pending ? "Revoked (gen \(gen)) · Mac update needed" : "Revoked (generation \(gen))"
        }
    }

    var statusColor: Color {
        switch self {
        case .unknown: return RSTheme.muted
        case .noKey: return RSTheme.muted
        case .active(_, let pending): return pending ? RSTheme.amber : RSTheme.signal
        case .revoked: return RSTheme.danger
        }
    }

    var statusIcon: String {
        switch self {
        case .unknown: return "questionmark.circle"
        case .noKey: return "key.slash"
        case .active(_, let pending): return pending ? "exclamationmark.shield" : "checkmark.shield.fill"
        case .revoked: return "xmark.shield.fill"
        }
    }

    var isActive: Bool {
        if case .active = self { return true }
        return false
    }

    var isRevoked: Bool {
        if case .revoked = self { return true }
        return false
    }
}

enum ActionOutcome: Equatable {
    case none
    case inProgress
    case success(String)
    case failure(message: String, detail: String?)
}

struct CompanionHardwareApprovalView: View {
    @AppStorage("rs.observe.selectedKeyID") private var keyID = "iphone-companion"
    @State private var replacementKeyID = "iphone-companion-2"
    @State private var packageText = ""
    @State private var lines: [String] = []
    @State private var fields: RSBA2Package.Fields?
    @State private var pairingText = ""
    @State private var revokedPairingText = ""
    @State private var signatureText = ""
    @State private var keyState: KeyState = .unknown
    @State private var allKeys: [CompanionPairingRecord] = []

    @State private var enrollOutcome: ActionOutcome = .none
    @State private var revokeOutcome: ActionOutcome = .none
    @State private var rotateOutcome: ActionOutcome = .none
    @State private var showOutcome: ActionOutcome = .none
    @State private var signOutcome: ActionOutcome = .none

    @State private var showRevokeConfirmation = false
    @State private var showRotateConfirmation = false
    @State private var showImportPicker = false

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
        .onAppear {
            refreshKeyState()
            loadAllKeys()
        }
        .onChange(of: keyID) { oldValue, newValue in
            if oldValue != newValue {
                refreshKeyState()
            }
        }
        .onChange(of: packageText) { _, _ in
            lines = []
            fields = nil
            signatureText = ""
            showOutcome = .none
            signOutcome = .none
        }
        .confirmationDialog(
            "Revoke key '\(keyID)'?",
            isPresented: $showRevokeConfirmation,
            titleVisibility: .visible
        ) {
            Button("Revoke Key", role: .destructive) { revokeKey() }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("This permanently revokes the key. On the Mac, re-import the revoked pairing file to sync the state. Signatures already issued remain valid until their expiry.")
        }
        .confirmationDialog(
            "Rotate to '\(replacementKeyID)'?",
            isPresented: $showRotateConfirmation,
            titleVisibility: .visible
        ) {
            Button("Rotate Key", role: .destructive) { rotateKey() }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("Creates a new key '\(replacementKeyID)' and revokes '\(keyID)'. On the Mac, import both the new pairing file and the revoked pairing file. Face ID is required once.")
        }
        .fileImporter(
            isPresented: $showImportPicker,
            allowedContentTypes: [.json, .plainText],
            allowsMultipleSelection: false
        ) { result in
            handleImportedFile(result)
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

            if !allKeys.isEmpty {
                Picker("Select key", selection: $keyID) {
                    ForEach(allKeys, id: \.keyID) { record in
                        HStack {
                            Text(record.keyID)
                            if record.state == CompanionSecureEnclaveEnrollment.revoked {
                                Text("(revoked)")
                                    .foregroundStyle(RSTheme.danger)
                            }
                        }
                        .tag(record.keyID)
                    }
                }
                .pickerStyle(.menu)
                .tint(RSTheme.cyan)
            }

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
                exportCard(title: "Active key", json: pairingText, isRevoked: false)
            }

            Text("Creates a Secure Enclave key. Face ID protects signing, not enrollment.")
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

            if keyState.isRevoked {
                exportButton(title: "Export revoked record for Mac", isRevoked: true)
            }

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

            if !revokedPairingText.isEmpty {
                exportCard(title: "Revoked key (share with Mac)", json: revokedPairingText, isRevoked: true)
            }

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

            Text("Revoke permanently disables the key. Rotate creates a replacement and revokes the old key. Both require Face ID and produce a revocation record to share with the Mac.")
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

            Text("Paste or import a carried approval package from the Mac, then review and sign it.")
                .font(.caption)
                .foregroundStyle(RSTheme.muted)

            HStack(spacing: 8) {
                Button {
                    showImportPicker = true
                } label: {
                    Label("Import", systemImage: "doc.badge.plus")
                        .font(.subheadline.weight(.medium))
                }
                .buttonStyle(.bordered)
                .tint(RSTheme.cyan)

                Button {
                    if let clipboard = UIPasteboard.general.string {
                        packageText = clipboard
                    }
                } label: {
                    Label("Paste", systemImage: "doc.on.clipboard")
                        .font(.subheadline.weight(.medium))
                }
                .buttonStyle(.bordered)
                .tint(RSTheme.cyan)

                Spacer()
            }

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
                    ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
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
                        feedbackGenerator.notificationOccurred(.success)
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

    @ViewBuilder
    private func exportCard(title: String, json: String, isRevoked: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: isRevoked ? "xmark.shield" : "checkmark.shield")
                    .foregroundStyle(isRevoked ? RSTheme.danger : RSTheme.signal)
                Text(title)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(isRevoked ? RSTheme.danger : RSTheme.signal)
            }

            HStack(spacing: 12) {
                Button {
                    UIPasteboard.general.string = json
                    feedbackGenerator.notificationOccurred(.success)
                } label: {
                    Label("Copy", systemImage: "doc.on.doc")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                }
                .buttonStyle(.bordered)
                .tint(isRevoked ? RSTheme.danger : RSTheme.cyan)

                ShareLink(item: json) {
                    Label("Share", systemImage: "square.and.arrow.up")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                }
                .buttonStyle(.bordered)
                .tint(isRevoked ? RSTheme.danger : RSTheme.cyan)
            }

            DisclosureGroup("Show record") {
                Text(json)
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

    @ViewBuilder
    private func exportButton(title: String, isRevoked: Bool) -> some View {
        Button {
            exportCurrentKey()
        } label: {
            HStack {
                Image(systemName: "square.and.arrow.up")
                Text(title)
            }
            .font(.subheadline.weight(.medium))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
        }
        .buttonStyle(.bordered)
        .tint(isRevoked ? RSTheme.danger : RSTheme.cyan)
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
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(RSTheme.muted)
                            .textSelection(.enabled)
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

    private func loadAllKeys() {
        do {
            allKeys = try CompanionSecureEnclaveEnrollment.listKeys(directory: directory)
        } catch {
            allKeys = []
        }
    }

    private func refreshKeyState() {
        keyState = .unknown
        pairingText = ""
        revokedPairingText = ""
        do {
            let record = try CompanionSecureEnclaveEnrollment.inspect(keyID: keyID, directory: directory)
            if record.state == CompanionSecureEnclaveEnrollment.active {
                keyState = .active(generation: record.generation, macUpdatePending: record.macUpdatePending)
                let carried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: keyID, directory: directory)
                pairingText = String(decoding: carried, as: UTF8.self)
            } else {
                keyState = .revoked(generation: record.generation, macUpdatePending: record.macUpdatePending)
                let carried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: keyID, directory: directory)
                revokedPairingText = String(decoding: carried, as: UTF8.self)
            }
        } catch CompanionHardwareRefusal.missing {
            keyState = .noKey
        } catch {
            keyState = .noKey
        }
        loadAllKeys()
    }

    private func exportCurrentKey() {
        do {
            let carried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: keyID, directory: directory)
            revokedPairingText = String(decoding: carried, as: UTF8.self)
        } catch {
            revokeOutcome = .failure(message: "Could not export key.", detail: error.localizedDescription)
        }
    }

    private func handleImportedFile(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            guard url.startAccessingSecurityScopedResource() else {
                showOutcome = .failure(message: "Could not access file.", detail: nil)
                return
            }
            defer { url.stopAccessingSecurityScopedResource() }
            do {
                let data = try Data(contentsOf: url)
                packageText = String(decoding: data, as: UTF8.self)
            } catch {
                showOutcome = .failure(message: "Could not read file.", detail: error.localizedDescription)
            }
        case .failure(let error):
            showOutcome = .failure(message: "Import failed.", detail: error.localizedDescription)
        }
    }

    private func enroll() {
        feedbackGenerator.prepare()
        enrollOutcome = .inProgress
        signatureText = ""
        pairingText = ""
        revokedPairingText = ""

        Task {
            do {
                let record = try CompanionSecureEnclaveEnrollment.enroll(keyID: keyID, directory: directory)
                let carried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: record.keyID, directory: directory)
                await MainActor.run {
                    pairingText = String(decoding: carried, as: UTF8.self)
                    feedbackGenerator.notificationOccurred(.success)
                    enrollOutcome = .success("Key enrolled (generation \(record.generation)). Share the pairing record with the Mac.")
                    keyState = .active(generation: record.generation, macUpdatePending: record.macUpdatePending)
                    loadAllKeys()
                }
            } catch {
                await MainActor.run {
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
        revokedPairingText = ""

        Task {
            do {
                let revokedRecord = try await CompanionSecureEnclaveEnrollment.revoke(keyID: keyID, directory: directory)
                let carried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: keyID, directory: directory)
                await MainActor.run {
                    revokedPairingText = String(decoding: carried, as: UTF8.self)
                    feedbackGenerator.notificationOccurred(.success)
                    revokeOutcome = .success("Key revoked (generation \(revokedRecord.generation)). Share the revoked record with the Mac.")
                    refreshKeyState()
                }
            } catch {
                await MainActor.run {
                    feedbackGenerator.notificationOccurred(.error)
                    let (message, detail) = describeError(error, action: "revoke")
                    revokeOutcome = .failure(message: message, detail: detail)
                    refreshKeyState()
                }
            }
        }
    }

    private func rotateKey() {
        feedbackGenerator.prepare()
        rotateOutcome = .inProgress
        signatureText = ""
        pairingText = ""
        revokedPairingText = ""

        Task {
            do {
                let (newRecord, revokedRecord) = try await CompanionSecureEnclaveEnrollment.rotate(
                    from: keyID,
                    to: replacementKeyID,
                    directory: directory
                )
                let newCarried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: newRecord.keyID, directory: directory)
                let revokedCarried = try CompanionSecureEnclaveEnrollment.carriedPairing(keyID: revokedRecord.keyID, directory: directory)
                await MainActor.run {
                    keyID = newRecord.keyID
                    pairingText = String(decoding: newCarried, as: UTF8.self)
                    revokedPairingText = String(decoding: revokedCarried, as: UTF8.self)
                    feedbackGenerator.notificationOccurred(.success)
                    rotateOutcome = .success("New key active (generation \(newRecord.generation)). Share both records with the Mac.")
                    keyState = .active(generation: newRecord.generation, macUpdatePending: newRecord.macUpdatePending)
                    loadAllKeys()
                }
            } catch {
                await MainActor.run {
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

        Task {
            do {
                let signature = try CompanionSecureEnclaveEnrollment.signDisplayed(
                    packageText: packageText,
                    displayed: fields,
                    directory: directory
                )
                await MainActor.run {
                    feedbackGenerator.notificationOccurred(.success)
                    signatureText = signature.base64EncodedString()
                    signOutcome = .success("Signed. Copy the signature and carry it back to the Mac.")
                }
            } catch {
                await MainActor.run {
                    feedbackGenerator.notificationOccurred(.error)
                    let (message, detail) = describeError(error, action: "sign")
                    signOutcome = .failure(message: message, detail: detail)
                }
            }
        }
    }

    private func describeError(_ error: Error, action: String) -> (message: String, detail: String?) {
        if let refusal = error as? CompanionHardwareRefusal {
            return (refusal.userMessage, refusal.technicalDetail)
        }
        return ("Unexpected error.", error.localizedDescription)
    }
}
