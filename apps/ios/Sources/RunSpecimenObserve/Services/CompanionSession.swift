import Foundation
import SwiftUI

@MainActor
final class CompanionSession: ObservableObject {
    @Published var baseURLString: String = "http://127.0.0.1:8787/"
    @Published var pairingToken: String = ""
    @Published var isPaired: Bool = false
    @Published var capabilities: CompanionCapabilities?
    @Published var status: CompanionStatus?
    @Published var lastError: String?
    @Published var lastAttentionNote: String?

    private let defaultsKey = "rs.observe.pairing"

    init() {
        load()
    }

    var boundaryCopy: String {
        capabilities?.boundary
            ?? "Observation only. Approval is real-TTY APPROVE on the Mac. This app cannot approve or execute."
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
        let config = PairingConfig(
            baseURL: url,
            pairingToken: pairingToken.trimmingCharacters(in: .whitespacesAndNewlines)
        )
        let client = CompanionClient(config: config)
        do {
            let caps = try await client.fetchCapabilities()
            if caps.canApprove || caps.canExecute || caps.canMutateLifecycle {
                lastError = "Refusing pair: companion advertised lifecycle mutation (violates ADR-003)."
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
            try await client.requestAttention(message: "Please check RunSpecimen on the Mac (TTY approval still required).")
            lastAttentionNote = "Attention requested. A human must still approve on the Mac if action is needed."
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

    func disconnect() {
        isPaired = false
        capabilities = nil
        status = nil
        UserDefaults.standard.removeObject(forKey: defaultsKey)
    }

    private func makeClient() -> CompanionClient? {
        guard isPaired,
              let url = URL(string: baseURLString),
              !pairingToken.isEmpty
        else { return nil }
        return CompanionClient(config: PairingConfig(baseURL: url, pairingToken: pairingToken))
    }

    private func persist(_ config: PairingConfig) {
        baseURLString = config.baseURL.absoluteString
        pairingToken = config.pairingToken
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
        isPaired = true
    }
}
