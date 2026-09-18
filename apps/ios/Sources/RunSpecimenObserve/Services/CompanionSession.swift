import Foundation
import SwiftUI

@MainActor
final class CompanionSession: ObservableObject {
    @Published var baseURLString: String = "http://127.0.0.1:8787/"
    @Published var pairingToken: String = ""
    @Published var tlsFingerprint: String = ""
    @Published var isPaired: Bool = false
    @Published var capabilities: CompanionCapabilities?
    @Published var status: CompanionStatus?
    @Published var lastError: String?
    @Published var lastAttentionNote: String?
    @Published var challengeInput: String = ""
    @Published var approvePhraseInput: String = ""
    @Published var refuseReasonInput: String = ""
    @Published var lastRemoteConfirmNote: String?

    private let defaultsKey = "rs.observe.pairing"

    init() {
        load()
    }

    var boundaryCopy: String {
        capabilities?.boundary
            ?? "Observation plus optional Mac-armed remote human confirm. "
            + "Local TTY APPROVE remains primary and is not equivalent to phone confirm. "
            + "Plugins cannot approve. This app is not an OS sandbox."
    }

    var remoteConfirmPending: Bool {
        status?.companion?.remoteConfirm?.pending == true
            || status?.companion?.canRemoteConfirm == true
            || capabilities?.canRemoteConfirm == true
    }

    func saveAndPair() async {
        lastError = nil
        guard let url = URL(string: baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)),
              !pairingToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            lastError = "Enter a companion URL and pairing token from the Mac."
            isPaired = false
            return
        }
        let scheme = (url.scheme ?? "").lowercased()
        let fingerprint = tlsFingerprint.trimmingCharacters(in: .whitespacesAndNewlines)
        if scheme == "https", fingerprint.isEmpty {
            lastError = "HTTPS requires the Mac tls_fingerprint_sha256 from companion --print-token."
            isPaired = false
            return
        }
        let config = PairingConfig(
            baseURL: url,
            pairingToken: pairingToken.trimmingCharacters(in: .whitespacesAndNewlines),
            tlsFingerprint: fingerprint.isEmpty ? nil : fingerprint
        )
        let client = CompanionClient(config: config)
        do {
            let caps = try await client.fetchCapabilities()
            if caps.canApprove || caps.canExecute || caps.canMutateLifecycle {
                lastError = "Refusing pair: companion advertised plugin-style approve/execute (violates ADR-004)."
                isPaired = false
                return
            }
            capabilities = caps
            persist(config)
            isPaired = true
            try await refreshStatus()
        } catch {
            lastError = error.localizedDescription
            isPaired = false
        }
    }

    func refreshStatus() async throws {
        guard let client = makeClient() else { throw CompanionClientError.notPaired }
        status = try await client.fetchStatus()
        if let caps = try? await client.fetchCapabilities() {
            capabilities = caps
        }
        if status?.companion?.canApprove == true || status?.companion?.canExecute == true {
            lastError = "Server claimed approve/execute capability; disconnecting."
            disconnect()
        }
    }

    func refresh() async {
        lastError = nil
        do {
            try await refreshStatus()
        } catch {
            lastError = error.localizedDescription
        }
    }

    func requestAttention() async {
        lastError = nil
        lastAttentionNote = nil
        guard let client = makeClient() else {
            lastError = CompanionClientError.notPaired.localizedDescription
            return
        }
        do {
            try await client.requestAttention(
                message: "Please check RunSpecimen on the Mac (TTY or remote-confirm)."
            )
            lastAttentionNote = "Attention requested. Lifecycle still requires Mac TTY or Mac-armed remote confirm."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func openDashboardOnMac() async {
        lastError = nil
        guard let client = makeClient() else {
            lastError = CompanionClientError.notPaired.localizedDescription
            return
        }
        do {
            try await client.requestOpenDashboard()
            lastAttentionNote = "Asked Mac to open the loopback read-only dashboard."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func submitRemoteConfirm() async {
        lastError = nil
        lastRemoteConfirmNote = nil
        guard remoteConfirmPending else {
            lastError = "No Mac-armed remote confirm is pending."
            return
        }
        let challenge = challengeInput.trimmingCharacters(in: .whitespacesAndNewlines)
        let phrase = approvePhraseInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !challenge.isEmpty else {
            lastError = "Enter the challenge shown on the Mac."
            return
        }
        guard phrase == "APPROVE" else {
            lastError = "Phrase must be exactly APPROVE (typed, not one-tap)."
            return
        }
        guard let client = makeClient() else {
            lastError = CompanionClientError.notPaired.localizedDescription
            return
        }
        do {
            let result = try await client.submitRemoteConfirm(challenge: challenge, phrase: phrase)
            lastRemoteConfirmNote = result.note
                ?? "Remote human confirm settled. This is not equivalent to local TTY APPROVE."
            challengeInput = ""
            approvePhraseInput = ""
            try await refreshStatus()
        } catch {
            lastError = error.localizedDescription
        }
    }

    func submitRemoteRefuse() async {
        lastError = nil
        lastRemoteConfirmNote = nil
        guard remoteConfirmPending else {
            lastError = "No Mac-armed remote confirm is pending."
            return
        }
        let challenge = challengeInput.trimmingCharacters(in: .whitespacesAndNewlines)
        let reason = refuseReasonInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !challenge.isEmpty else {
            lastError = "Enter the challenge shown on the Mac."
            return
        }
        guard (1 ... 240).contains(reason.count) else {
            lastError = "Refuse requires a reason (1–240 characters). This does not approve."
            return
        }
        guard let client = makeClient() else {
            lastError = CompanionClientError.notPaired.localizedDescription
            return
        }
        do {
            let result = try await client.submitRemoteRefuse(challenge: challenge, reason: reason)
            lastRemoteConfirmNote = result.note
                ?? "Pending refused. Re-arm or use local TTY APPROVE. Not an approval."
            challengeInput = ""
            approvePhraseInput = ""
            refuseReasonInput = ""
            try await refreshStatus()
        } catch {
            lastError = error.localizedDescription
        }
    }

    func disconnect() {
        isPaired = false
        capabilities = nil
        status = nil
        challengeInput = ""
        approvePhraseInput = ""
        refuseReasonInput = ""
        UserDefaults.standard.removeObject(forKey: defaultsKey)
    }

    private func makeClient() -> CompanionClient? {
        guard isPaired,
              let url = URL(string: baseURLString),
              !pairingToken.isEmpty
        else { return nil }
        let fingerprint = tlsFingerprint.trimmingCharacters(in: .whitespacesAndNewlines)
        return CompanionClient(
            config: PairingConfig(
                baseURL: url,
                pairingToken: pairingToken,
                tlsFingerprint: fingerprint.isEmpty ? nil : fingerprint
            )
        )
    }

    private func persist(_ config: PairingConfig) {
        baseURLString = config.baseURL.absoluteString
        pairingToken = config.pairingToken
        tlsFingerprint = config.tlsFingerprint ?? ""
        if let data = try? JSONEncoder().encode(config) {
            UserDefaults.standard.set(data, forKey: defaultsKey)
        }
    }

    private func load() {
        guard let data = UserDefaults.standard.data(forKey: defaultsKey),
              let config = try? JSONDecoder().decode(PairingConfig.self, from: data)
        else { return }
        baseURLString = config.baseURL.absoluteString
        pairingToken = config.pairingToken
        tlsFingerprint = config.tlsFingerprint ?? ""
        isPaired = true
    }
}
