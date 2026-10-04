import CryptoKit
import Foundation
import LocalAuthentication
import Security
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
    @Published var phonePeerNote: String = "No phone-peer signature has been returned. Signing uses the published challenge. It does not approve a run."
    private var phoneChallenge: PhonePeerChallengeMessage?
    private var phoneSignGeneration = 0

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

    func signPhonePeerChallenge(
        signer: PhoneChallengeSigning = LivePhoneSecureEnclaveSigner(),
        peer: (any PhonePeerTransport)? = nil
    ) async {
        lastError = nil
        let transport: any PhonePeerTransport
        if let peer {
            transport = peer
        } else if let client = makeClient() {
            transport = client
        } else {
            lastError = CompanionClientError.notPaired.localizedDescription
            return
        }
        phoneSignGeneration += 1
        let generation = phoneSignGeneration
        do {
            let message = try await transport.fetchPhonePeerChallenge()
            try Task.checkCancellation()
            guard generation == phoneSignGeneration else { throw PhonePeerSignError.cancelled }
            phoneChallenge = message
            guard generation == phoneSignGeneration else { throw PhonePeerSignError.cancelled }
            let bytes = try boundPhoneChallengeBytes(message)
            try Task.checkCancellation()
            guard generation == phoneSignGeneration else { throw PhonePeerSignError.cancelled }
            let signed = try signer.sign(message: bytes)
            try Task.checkCancellation()
            guard generation == phoneSignGeneration else {
                signer.discardStagedEnrollment()
                throw PhonePeerSignError.cancelled
            }
            try await transport.willSubmitPhonePeerSignature()
            try Task.checkCancellation()
            guard generation == phoneSignGeneration else {
                signer.discardStagedEnrollment()
                throw PhonePeerSignError.cancelled
            }
            try await transport.submitPhonePeerSignature(
                challengeId: message.challengeId,
                challenge: message.challenge,
                publicKey: signed.publicKey,
                signature: signed.signature
            )
            guard generation == phoneSignGeneration else {
                signer.discardStagedEnrollment()
                try? await transport.invalidatePhonePeerChallenge(challengeId: message.challengeId)
                throw PhonePeerSignError.cancellationTooLate
            }
            phonePeerNote = "Mailbox accepted challenge \(message.challengeId). That is not holder verification and the key is not enrolled."
        } catch PhonePeerSignError.cancelled {
            phoneChallenge = nil
            signer.discardStagedEnrollment()
            phonePeerNote = "Phone peer challenge cancelled before a signature was returned."
            lastError = nil
        } catch PhonePeerSignError.cancellationTooLate {
            phonePeerNote = "Phone peer challenge cancellation was too late. The signature left the device and must not enroll."
            lastError = nil
        } catch is CancellationError {
            phoneChallenge = nil
            signer.discardStagedEnrollment()
            phonePeerNote = "Phone peer challenge cancelled before a signature was returned."
            lastError = nil
        } catch {
            signer.discardStagedEnrollment()
            lastError = error.localizedDescription
        }
    }

    /// Enroll only after the mailbox records holder verification and consumption.
    func commitPhoneKeyAfterHolderVerification(
        signer: PhoneChallengeSigning = LivePhoneSecureEnclaveSigner(),
        peer: (any PhonePeerTransport)? = nil
    ) async {
        let transport: any PhonePeerTransport
        if let peer {
            transport = peer
        } else if let client = makeClient() {
            transport = client
        } else {
            lastError = CompanionClientError.notPaired.localizedDescription
            return
        }
        guard let message = phoneChallenge else {
            phonePeerNote = "Mailbox acceptance is not holder verification."
            return
        }
        do {
            let record = try await transport.fetchHolderVerification(challengeId: message.challengeId)
            guard record.verified, record.consumed, !record.invalidated else {
                phonePeerNote = "Mailbox acceptance is not holder verification."
                return
            }
            try signer.commitEnrollment()
            phoneChallenge = nil
            phonePeerNote = "Holder verified and consumed challenge \(message.challengeId). The phone key is enrolled."
        } catch {
            lastError = error.localizedDescription
        }
    }

    func cancelPhonePeerChallenge() async {
        phoneSignGeneration += 1
        phoneChallenge = nil
        phonePeerNote = "Phone peer challenge cancelled before a signature was returned."
        lastError = nil
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

struct PhoneHolderVerification: Equatable {
    var verified: Bool
    var consumed: Bool
    var invalidated: Bool
}

protocol PhonePeerTransport {
    func fetchPhonePeerChallenge() async throws -> PhonePeerChallengeMessage
    func willSubmitPhonePeerSignature() async throws
    func submitPhonePeerSignature(
        challengeId: String,
        challenge: String,
        publicKey: String,
        signature: String
    ) async throws
    func invalidatePhonePeerChallenge(challengeId: String) async throws
    func fetchHolderVerification(challengeId: String) async throws -> PhoneHolderVerification
}

extension PhonePeerTransport {
    func willSubmitPhonePeerSignature() async throws {}
    func invalidatePhonePeerChallenge(challengeId: String) async throws {}
    func fetchHolderVerification(challengeId: String) async throws -> PhoneHolderVerification {
        PhoneHolderVerification(verified: false, consumed: false, invalidated: false)
    }
}

extension CompanionClient: PhonePeerTransport {}

enum PhonePeerSignError: Error {
    case cancelled
    case cancellationTooLate
}

protocol PhoneChallengeSigning {
    func sign(message: Data) throws -> (publicKey: String, signature: String)
    func commitEnrollment() throws
    func discardStagedEnrollment()
}

extension PhoneChallengeSigning {
    func commitEnrollment() throws {}
    func discardStagedEnrollment() {}
}

/// Sealed key bytes in Application Support. This is not the Keychain and not
/// the Secure Enclave. A new key stays pending until commit.
struct PhoneKeyStage {
    let directory: URL

    func stage(handle: Data, publicKey: Data) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try handle.write(to: pendingHandle, options: .atomic)
        try publicKey.write(to: pendingPublic, options: .atomic)
    }

    /// One record. A failure after the next-file write leaves the previous generation.
    func commit(failAfterFirstWrite: Bool = false) throws {
        guard FileManager.default.fileExists(atPath: pendingHandle.path),
              FileManager.default.fileExists(atPath: pendingPublic.path)
        else { return }
        let handle = try Data(contentsOf: pendingHandle)
        let publicKey = try Data(contentsOf: pendingPublic)
        let generation = ((try? committedGeneration()) ?? 0) + 1
        let record: [String: Any] = [
            "generation": generation,
            "handle": handle.base64EncodedString(),
            "publicKey": publicKey.base64EncodedString(),
        ]
        let encoded = try JSONSerialization.data(withJSONObject: record)
        try encoded.write(to: nextRecordURL, options: .atomic)
        if failAfterFirstWrite {
            throw CompanionClientError.transport("phone custody commit stopped after the first write")
        }
        if FileManager.default.fileExists(atPath: recordURL.path) {
            _ = try FileManager.default.replaceItemAt(recordURL, withItemAt: nextRecordURL)
        } else {
            try FileManager.default.moveItem(at: nextRecordURL, to: recordURL)
        }
        discard()
    }

    func discard() {
        try? FileManager.default.removeItem(at: pendingHandle)
        try? FileManager.default.removeItem(at: pendingPublic)
    }

    func committedGeneration() throws -> Int {
        let object = try readRecord()
        if let number = object["generation"] as? Int { return number }
        if let number = object["generation"] as? NSNumber { return number.intValue }
        throw CompanionClientError.transport("phone session key is not enrolled")
    }

    func committedHandle() throws -> Data {
        try decodedRecordField("handle")
    }

    func committedPublicKey() throws -> Data {
        try decodedRecordField("publicKey")
    }

    func rotate(handle: Data, publicKey: Data) throws {
        try stage(handle: handle, publicKey: publicKey)
    }

    func revoke() {
        discard()
        try? FileManager.default.removeItem(at: recordURL)
        try? FileManager.default.removeItem(at: nextRecordURL)
    }

    private var pendingHandle: URL { directory.appendingPathComponent("phone-session-handle.pending") }
    private var pendingPublic: URL { directory.appendingPathComponent("phone-session-public.pending") }
    private var recordURL: URL { directory.appendingPathComponent("custody.json") }
    private var nextRecordURL: URL { directory.appendingPathComponent("custody-next.json") }

    private func readRecord() throws -> [String: Any] {
        let data = try Data(contentsOf: recordURL)
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw CompanionClientError.transport("phone session key is not enrolled")
        }
        return object
    }

    private func decodedRecordField(_ name: String) throws -> Data {
        guard let text = try readRecord()[name] as? String, let data = Data(base64Encoded: text) else {
            throw CompanionClientError.transport("phone session key is not enrolled")
        }
        return data
    }
}

struct LivePhoneSecureEnclaveSigner: PhoneChallengeSigning {
    var stage = PhoneKeyStage(directory: LivePhoneSecureEnclaveSigner.support)

    func sign(message: Data) throws -> (publicKey: String, signature: String) {
        if let token = try? stage.committedHandle() {
            let key = try SecureEnclave.P256.Signing.PrivateKey(dataRepresentation: token)
            let signature = try key.signature(for: message).rawRepresentation
            return (
                key.publicKey.x963Representation.base64EncodedString(),
                signature.base64EncodedString()
            )
        }
        var error: Unmanaged<CFError>?
        guard let access = SecAccessControlCreateWithFlags(
            kCFAllocatorDefault,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            [.privateKeyUsage, .biometryCurrentSet],
            &error
        ) else {
            throw CompanionClientError.transport("biometric access policy was refused")
        }
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            accessControl: access,
            authenticationContext: LAContext()
        )
        try stage.stage(handle: key.dataRepresentation, publicKey: key.publicKey.x963Representation)
        let signature = try key.signature(for: message).rawRepresentation
        return (
            key.publicKey.x963Representation.base64EncodedString(),
            signature.base64EncodedString()
        )
    }

    func commitEnrollment() throws {
        try stage.commit()
    }

    func discardStagedEnrollment() {
        stage.discard()
    }

    func rotateEnrollment() throws {
        var error: Unmanaged<CFError>?
        guard let access = SecAccessControlCreateWithFlags(
            kCFAllocatorDefault,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            [.privateKeyUsage, .biometryCurrentSet],
            &error
        ) else {
            throw CompanionClientError.transport("biometric access policy was refused")
        }
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            accessControl: access,
            authenticationContext: LAContext()
        )
        try stage.rotate(handle: key.dataRepresentation, publicKey: key.publicKey.x963Representation)
    }

    func revokeEnrollment() {
        stage.revoke()
    }

    private static var support: URL {
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return root.appendingPathComponent("RunSpecimenObserve", isDirectory: true)
    }
}

func boundPhoneChallengeBytes(_ message: PhonePeerChallengeMessage) throws -> Data {
    guard let expiry = message.expiry else {
        throw CompanionClientError.transport("phone peer challenge is missing its expiry")
    }
    let role = message.role ?? "phone"
    let object = """
    {"challenge":"\(message.challenge)","domain":"holder-device-p256-v1","expiry":\(expiry),"generation":\(message.generation),"holder_id":"\(message.holderId)","nonce":"\(message.challengeId)","role":"\(role)"}
    """
    return Data(object.utf8)
}
