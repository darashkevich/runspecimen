import CryptoKit
import Foundation
import LocalAuthentication
import os
import Security
import SwiftUI

#if DEBUG
private let launchLogger = Logger(subsystem: "com.darashkevich.runspecimen.observe", category: "launch")
#endif

@MainActor
final class CompanionSession: ObservableObject {
    @Published var baseURLString: String = ""
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
    @Published var exactRunNote: String = "No exact run is waiting for review. Phone approval is not physical presence at the Mac."
    @Published var reviewedExactRunLines: [String] = []
    @Published var reviewedExactRunArgv: [String] = []
    @Published var macSessionPublicKey: String = ""
    /// Entered by the person from the Mac. A holder id inside a mailbox request is not this pin.
    @Published var pinnedHolderId: String = ""
    @Published var phonePeerKeyState: PhonePeerKeyState = .unknown
    var phoneChallenge: PhonePeerChallengeMessage?
    var signedPhonePublicKey: String?
    private var phoneSignGeneration = 0
    private var exactRunGeneration = 0
    private var reviewedExactRun: ParsedExactRun?
    private var acceptedReceiptSignatures: Set<String> = []

    private var activeRefreshTask: Task<Void, Never>?
    private var activePhonePeerTask: Task<Void, Never>?
    private var activeExactRunTask: Task<Void, Never>?
    private var activeRemoteConfirmTask: Task<Void, Never>?

    private var cachedClient: CompanionClient?
    private var cachedClientConfig: PairingConfig?

    private let defaultsKey = "rs.observe.pairing"
    private let holderPinKey = "rs.observe.pinnedHolderId"

    enum PhonePeerKeyState: Equatable {
        case unknown
        case noKey
        case enrolled(generation: Int)
        case error(String)

        var isEnrolled: Bool {
            if case .enrolled = self { return true }
            return false
        }
    }

    init(deferPhoneKeyState: Bool = false) {
        #if DEBUG
        let start = CFAbsoluteTimeGetCurrent()
        launchLogger.info("CompanionSession.init() START, deferPhoneKeyState=\(deferPhoneKeyState)")
        #endif

        load()
        pinnedHolderId = UserDefaults.standard.string(forKey: holderPinKey) ?? ""

        if !deferPhoneKeyState {
            refreshPhonePeerKeyState()
        }

        #if DEBUG
        let end = CFAbsoluteTimeGetCurrent()
        launchLogger.info("CompanionSession.init() END, duration: \((end - start) * 1000, format: .fixed(precision: 1))ms")
        #endif
    }

    func refreshPhonePeerKeyState() {
        #if DEBUG
        let start = CFAbsoluteTimeGetCurrent()
        launchLogger.info("refreshPhonePeerKeyState() START (sync)")
        #endif

        let signer = LivePhoneSecureEnclaveSigner()
        do {
            let generation = try signer.stage.committedGeneration()
            phonePeerKeyState = .enrolled(generation: generation)
        } catch {
            phonePeerKeyState = .noKey
        }

        #if DEBUG
        let end = CFAbsoluteTimeGetCurrent()
        launchLogger.info("refreshPhonePeerKeyState() END, duration: \((end - start) * 1000, format: .fixed(precision: 1))ms, state: \(String(describing: self.phonePeerKeyState))")
        #endif
    }

    func refreshPhonePeerKeyStateAsync() async {
        #if DEBUG
        let start = CFAbsoluteTimeGetCurrent()
        launchLogger.info("refreshPhonePeerKeyStateAsync() START")
        #endif

        let result: PhonePeerKeyState = await Task.detached(priority: .userInitiated) {
            let signer = LivePhoneSecureEnclaveSigner()
            do {
                let generation = try signer.stage.committedGeneration()
                return .enrolled(generation: generation)
            } catch {
                return .noKey
            }
        }.value

        phonePeerKeyState = result

        #if DEBUG
        let end = CFAbsoluteTimeGetCurrent()
        launchLogger.info("refreshPhonePeerKeyStateAsync() END, duration: \((end - start) * 1000, format: .fixed(precision: 1))ms, state: \(String(describing: self.phonePeerKeyState))")
        #endif
    }

    func revokePhonePeerKey() throws {
        exactRunGeneration += 1
        reviewedExactRun = nil
        reviewedExactRunLines = []
        reviewedExactRunArgv = []
        let signer = LivePhoneSecureEnclaveSigner()
        try signer.revokeEnrollment()
        phonePeerKeyState = .noKey
        phoneChallenge = nil
        signedPhonePublicKey = nil
        phonePeerNote = "Phone-peer key revoked. Re-enroll by signing a new challenge."
    }

    func rotatePhonePeerKey() throws {
        exactRunGeneration += 1
        reviewedExactRun = nil
        reviewedExactRunLines = []
        reviewedExactRunArgv = []
        let signer = LivePhoneSecureEnclaveSigner()
        try signer.rotateEnrollment()
        try signer.stage.commit()
        refreshPhonePeerKeyState()
        phonePeerNote = "Phone-peer key rotated. The Mac must accept the new key."
    }

    func cancelAllTasks() {
        activeRefreshTask?.cancel()
        activePhonePeerTask?.cancel()
        activeExactRunTask?.cancel()
        activeRemoteConfirmTask?.cancel()
        activeRefreshTask = nil
        activePhonePeerTask = nil
        activeExactRunTask = nil
        activeRemoteConfirmTask = nil
    }

    func rememberPinnedHolderId() {
        UserDefaults.standard.set(pinnedHolderId, forKey: holderPinKey)
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
            switch CapabilityValidator.validateForPairing(capabilities: caps) {
            case .valid:
                break
            case .invalid(let reason):
                lastError = "Refusing pair: \(reason)"
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
        let fetchedStatus = try await client.fetchStatus()
        status = fetchedStatus
        if let caps = try? await client.fetchCapabilities() {
            capabilities = caps
        }
        switch CapabilityValidator.validateForRefresh(status: fetchedStatus) {
        case .valid:
            break
        case .invalid(let reason):
            lastError = "\(reason) Disconnecting."
            disconnect()
        }
    }

    func refresh() async {
        activeRefreshTask?.cancel()
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            self.lastError = nil
            do {
                guard !Task.isCancelled else { return }
                try await self.refreshStatus()
            } catch is CancellationError {
                return
            } catch {
                guard !Task.isCancelled else { return }
                self.lastError = error.localizedDescription
            }
            if self.activeRefreshTask?.isCancelled == false {
                self.activeRefreshTask = nil
            }
        }
        activeRefreshTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }

    func signPhonePeerChallenge(
        signer: PhoneChallengeSigning = LivePhoneSecureEnclaveSigner(),
        peer: (any PhonePeerTransport)? = nil
    ) async {
        activePhonePeerTask?.cancel()
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.signPhonePeerChallengeImpl(signer: signer, peer: peer)
            if self.activePhonePeerTask?.isCancelled == false {
                self.activePhonePeerTask = nil
            }
        }
        activePhonePeerTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func signPhonePeerChallengeImpl(
        signer: PhoneChallengeSigning,
        peer: (any PhonePeerTransport)?
    ) async {
        lastError = nil
        guard !Task.isCancelled else {
            phonePeerNote = "Phone peer challenge cancelled before a signature was returned."
            return
        }
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            lastError = "Action refused: \(reason)"
            return
        }
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
            guard !Task.isCancelled else { throw PhonePeerSignError.cancelled }
            let message = try await transport.fetchPhonePeerChallenge()
            try Task.checkCancellation()
            guard generation == phoneSignGeneration else { throw PhonePeerSignError.cancelled }
            guard !Task.isCancelled else { throw PhonePeerSignError.cancelled }
            phoneChallenge = message
            guard generation == phoneSignGeneration else { throw PhonePeerSignError.cancelled }
            let bytes = try boundPhoneChallengeBytes(message)
            try Task.checkCancellation()
            guard generation == phoneSignGeneration else { throw PhonePeerSignError.cancelled }
            guard !Task.isCancelled else { throw PhonePeerSignError.cancelled }
            let signed = try signer.sign(message: bytes)
            try Task.checkCancellation()
            guard generation == phoneSignGeneration else {
                signer.discardStagedEnrollment()
                throw PhonePeerSignError.cancelled
            }
            guard !Task.isCancelled else {
                signer.discardStagedEnrollment()
                throw PhonePeerSignError.cancelled
            }
            try await transport.willSubmitPhonePeerSignature()
            try Task.checkCancellation()
            guard generation == phoneSignGeneration else {
                signer.discardStagedEnrollment()
                throw PhonePeerSignError.cancelled
            }
            guard !Task.isCancelled else {
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
            guard !Task.isCancelled else {
                signer.discardStagedEnrollment()
                try? await transport.invalidatePhonePeerChallenge(challengeId: message.challengeId)
                throw PhonePeerSignError.cancellationTooLate
            }
            try signer.bindStagedOwnership(challengeId: message.challengeId, publicKey: signed.publicKey)
            signedPhonePublicKey = signed.publicKey
            phonePeerNote = "Mailbox accepted challenge \(message.challengeId). That is not holder verification and the key is not enrolled."
        } catch PhonePeerSignError.cancelled {
            phoneChallenge = nil
            signedPhonePublicKey = nil
            signer.discardStagedEnrollment()
            phonePeerNote = "Phone peer challenge cancelled before a signature was returned."
            lastError = nil
        } catch PhonePeerSignError.cancellationTooLate {
            signedPhonePublicKey = nil
            phonePeerNote = "Phone peer challenge cancellation was too late. The signature left the device and must not enroll."
            lastError = nil
        } catch is CancellationError {
            phoneChallenge = nil
            signedPhonePublicKey = nil
            signer.discardStagedEnrollment()
            phonePeerNote = "Phone peer challenge cancelled before a signature was returned."
            lastError = nil
        } catch {
            signer.discardStagedEnrollment()
            lastError = error.localizedDescription
        }
    }

    /// Enroll only after the phone verifies a holder receipt. Caller flags are ignored.
    func commitPhoneKeyAfterHolderVerification(
        signer: PhoneChallengeSigning = LivePhoneSecureEnclaveSigner(),
        peer: (any PhonePeerTransport)? = nil
    ) async {
        activePhonePeerTask?.cancel()
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.commitPhoneKeyAfterHolderVerificationImpl(signer: signer, peer: peer)
            if self.activePhonePeerTask?.isCancelled == false {
                self.activePhonePeerTask = nil
            }
        }
        activePhonePeerTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func commitPhoneKeyAfterHolderVerificationImpl(
        signer: PhoneChallengeSigning,
        peer: (any PhonePeerTransport)?
    ) async {
        guard !Task.isCancelled else {
            phonePeerNote = "Phone peer challenge cancelled before the holder receipt committed."
            return
        }
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            lastError = "Action refused: \(reason)"
            return
        }
        let transport: any PhonePeerTransport
        if let peer {
            transport = peer
        } else if let client = makeClient() {
            transport = client
        } else {
            lastError = CompanionClientError.notPaired.localizedDescription
            return
        }
        guard let message = phoneChallenge, let phonePublicKey = signedPhonePublicKey else {
            phonePeerNote = "Mailbox acceptance is not holder verification."
            return
        }
        let generation = phoneSignGeneration
        let challengeId = message.challengeId
        do {
            guard !Task.isCancelled else { throw CancellationError() }
            let record = try await transport.fetchHolderVerification(challengeId: challengeId)
            try Task.checkCancellation()
            guard generation == phoneSignGeneration, phoneChallenge?.challengeId == challengeId, signedPhonePublicKey == phonePublicKey else {
                phonePeerNote = "Phone peer challenge cancelled before the holder receipt committed."
                return
            }
            guard !Task.isCancelled else { throw CancellationError() }
            let decision = phoneReceiptAuthentic(
                record: record,
                challenge: message,
                phonePublicKey: phonePublicKey,
                pinnedMacPublicKey: macSessionPublicKey,
                seenSignatures: acceptedReceiptSignatures
            )
            guard decision == .accept, let signature = record.signature else {
                phonePeerNote = "A caller flag is not a holder receipt."
                return
            }
            guard generation == phoneSignGeneration, phoneChallenge?.challengeId == challengeId else {
                phonePeerNote = "Phone peer challenge cancelled before the holder receipt committed."
                return
            }
            guard !Task.isCancelled else { throw CancellationError() }
            try signer.commitEnrollment(ownedBy: challengeId, publicKey: phonePublicKey)
            guard !Task.isCancelled else { throw CancellationError() }
            acceptedReceiptSignatures.insert(signature)
            phoneChallenge = nil
            refreshPhonePeerKeyState()
            phonePeerNote = "Holder receipt verified for challenge \(challengeId). The phone key is enrolled."
        } catch PhonePeerSignError.cancelled {
            phonePeerNote = "Phone peer challenge cancelled before the holder receipt committed."
            lastError = nil
        } catch is CancellationError {
            phonePeerNote = "Phone peer challenge cancelled before the holder receipt committed."
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }

    /// Fetch one published exact run and show the fields inside its signed bytes. This does not sign.
    func reviewRetainedExactRun(
        now: Int = Int(Date().timeIntervalSince1970),
        peer: (any ExactRunPhoneSigningTransport)? = nil
    ) async {
        activeExactRunTask?.cancel()
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.reviewRetainedExactRunImpl(now: now, peer: peer)
            if self.activeExactRunTask?.isCancelled == false {
                self.activeExactRunTask = nil
            }
        }
        activeExactRunTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func reviewRetainedExactRunImpl(
        now: Int,
        peer: (any ExactRunPhoneSigningTransport)?
    ) async {
        lastError = nil
        guard !Task.isCancelled else {
            exactRunNote = "Exact run review was cancelled before a signature was returned."
            return
        }
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            lastError = "Action refused: \(reason)"
            return
        }
        exactRunGeneration += 1
        let generation = exactRunGeneration
        reviewedExactRun = nil
        reviewedExactRunLines = []
        reviewedExactRunArgv = []
        let transport: any ExactRunPhoneSigningTransport
        if let peer {
            transport = peer
        } else if let client = makeClient() {
            transport = client
        } else {
            lastError = CompanionClientError.notPaired.localizedDescription
            return
        }
        do {
            guard !Task.isCancelled else { throw CancellationError() }
            let fetched = try await transport.fetchRetainedExactRun()
            try Task.checkCancellation()
            guard generation == exactRunGeneration else {
                exactRunNote = "Exact run review was cancelled before a signature was returned."
                return
            }
            guard !Task.isCancelled else { throw CancellationError() }
            let pin = pinnedHolderId.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !pin.isEmpty else {
                exactRunNote = "Holder identity is not pinned. The mailbox holder id was not trusted."
                return
            }
            let parsed = try parseExactRun(fetched: fetched, now: now, pinnedHolderId: pin)
            guard generation == exactRunGeneration else {
                exactRunNote = "Exact run review was replaced before it could be shown."
                return
            }
            guard !Task.isCancelled else { throw CancellationError() }
            reviewedExactRun = parsed
            reviewedExactRunLines = parsed.lines
            reviewedExactRunArgv = parsed.launchArgv
            exactRunNote = "Review these bytes before signing. Signing uses the enrolled phone key and does not create one."
        } catch is CancellationError {
            reviewedExactRun = nil
            reviewedExactRunLines = []
            reviewedExactRunArgv = []
            exactRunNote = "Exact run review was cancelled before a signature was returned."
        } catch {
            if generation == exactRunGeneration {
                reviewedExactRun = nil
                reviewedExactRunLines = []
                reviewedExactRunArgv = []
                exactRunNote = "Exact run was not shown."
                lastError = error.localizedDescription
            }
        }
    }

    /// Sign the reviewed bytes with the committed phone key and return that signature for the same nonce.
    #if RUNSPECIMEN_TEST_HOOKS
    func approveReviewedExactRun(
        signer: PhoneChallengeSigning = LivePhoneSecureEnclaveSigner(),
        peer: (any ExactRunPhoneSigningTransport)? = nil,
        now: @MainActor @escaping () -> Int = { Int(Date().timeIntervalSince1970) },
        beforeSign: (@MainActor () async -> Void)? = nil,
        beforeSubmit: (@MainActor () async -> Void)? = nil
    ) async {
        activeExactRunTask?.cancel()
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.approveReviewedExactRunImpl(signer: signer, peer: peer, now: now, beforeSign: beforeSign, beforeSubmit: beforeSubmit)
            if self.activeExactRunTask?.isCancelled == false {
                self.activeExactRunTask = nil
            }
        }
        activeExactRunTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }
    #else
    func approveReviewedExactRun(
        signer: PhoneChallengeSigning = LivePhoneSecureEnclaveSigner(),
        peer: (any ExactRunPhoneSigningTransport)? = nil,
        now: @MainActor @escaping () -> Int = { Int(Date().timeIntervalSince1970) }
    ) async {
        activeExactRunTask?.cancel()
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.approveReviewedExactRunImpl(signer: signer, peer: peer, now: now, beforeSign: nil, beforeSubmit: nil)
            if self.activeExactRunTask?.isCancelled == false {
                self.activeExactRunTask = nil
            }
        }
        activeExactRunTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }
    #endif

    private func approveReviewedExactRunImpl(
        signer: PhoneChallengeSigning,
        peer: (any ExactRunPhoneSigningTransport)?,
        now: @MainActor @escaping () -> Int,
        beforeSign: (@MainActor () async -> Void)?,
        beforeSubmit: (@MainActor () async -> Void)?
    ) async {
        lastError = nil
        guard !Task.isCancelled else {
            exactRunNote = "Exact run was cancelled before a signature was returned."
            return
        }
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            lastError = "Action refused: \(reason)"
            return
        }
        guard let reviewed = reviewedExactRun else {
            exactRunNote = "Review the exact run before signing it."
            return
        }
        let generation = exactRunGeneration
        let transport: any ExactRunPhoneSigningTransport
        if let peer {
            transport = peer
        } else if let client = makeClient() {
            transport = client
        } else {
            lastError = CompanionClientError.notPaired.localizedDescription
            return
        }
        do {
            if let beforeSign {
                await beforeSign()
            }
            try Task.checkCancellation()
            guard !Task.isCancelled else { throw CancellationError() }
            let pin = pinnedHolderId.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !pin.isEmpty, reviewed.holderId == pin else {
                exactRunNote = "Holder identity is not the pinned holder. The signature was not returned."
                return
            }
            guard now() < reviewed.expiry else {
                reviewedExactRun = nil
                reviewedExactRunLines = []
                reviewedExactRunArgv = []
                exactRunNote = "Exact run expired before signing. The signature was not returned."
                return
            }
            guard generation == exactRunGeneration, reviewedExactRun?.bound == reviewed.bound, reviewedExactRun?.nonce == reviewed.nonce else {
                exactRunNote = "Exact run changed after review. The signature was not returned."
                return
            }
            guard !Task.isCancelled else { throw CancellationError() }
            let signed = try signer.signCommitted(message: reviewed.bound)
            try Task.checkCancellation()
            guard !Task.isCancelled else { throw CancellationError() }
            let again = try await transport.fetchRetainedExactRun()
            try Task.checkCancellation()
            guard !Task.isCancelled else { throw CancellationError() }
            guard now() < reviewed.expiry else {
                exactRunNote = "Exact run expired before the signature was returned."
                return
            }
            guard generation == exactRunGeneration, again.challengeId == reviewed.nonce, again.bound == reviewed.bound else {
                reviewedExactRun = nil
                reviewedExactRunLines = []
                reviewedExactRunArgv = []
                exactRunNote = "The Mac replaced the exact run. The signature was not returned."
                return
            }
            if let beforeSubmit {
                await beforeSubmit()
            }
            try Task.checkCancellation()
            guard !Task.isCancelled else { throw CancellationError() }
            guard generation == exactRunGeneration, reviewedExactRun?.bound == reviewed.bound, reviewedExactRun?.nonce == reviewed.nonce else {
                exactRunNote = "Exact run was cancelled before the signature was returned."
                return
            }
            guard !Task.isCancelled else { throw CancellationError() }
            try await transport.submitRetainedExactRunSignature(challengeId: reviewed.nonce, signature: signed.signature)
            guard generation == exactRunGeneration else {
                exactRunNote = "Exact run was cancelled after the signature left the phone."
                return
            }
            exactRunNote = "Exact-run signature returned for challenge \(reviewed.nonce). This is not physical presence at the Mac."
        } catch PhonePeerSignError.cancelled {
            exactRunNote = "Exact run was cancelled before a signature was returned."
            lastError = nil
        } catch is CancellationError {
            exactRunNote = "Exact run was cancelled before a signature was returned."
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }

    func cancelExactRunReview() {
        activeExactRunTask?.cancel()
        activeExactRunTask = nil
        exactRunGeneration += 1
        reviewedExactRun = nil
        reviewedExactRunLines = []
        reviewedExactRunArgv = []
        exactRunNote = "Exact run review was cancelled before a signature was returned."
        lastError = nil
    }

    func cancelPhonePeerChallenge() async {
        activePhonePeerTask?.cancel()
        activePhonePeerTask = nil
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
        activeRemoteConfirmTask?.cancel()
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.submitRemoteConfirmImpl()
            if self.activeRemoteConfirmTask?.isCancelled == false {
                self.activeRemoteConfirmTask = nil
            }
        }
        activeRemoteConfirmTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func submitRemoteConfirmImpl() async {
        lastError = nil
        lastRemoteConfirmNote = nil
        guard !Task.isCancelled else { return }
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            lastError = "Action refused: \(reason)"
            return
        }
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
            guard !Task.isCancelled else { return }
            let result = try await client.submitRemoteConfirm(challenge: challenge, phrase: phrase)
            guard !Task.isCancelled else { return }
            if result.isAmbiguous {
                lastError = "Server returned ambiguous confirm response. Refresh status to check state."
                return
            }
            guard result.confirmedSuccessfully else {
                lastError = result.note ?? "Confirm was not accepted by the server."
                return
            }
            guard !Task.isCancelled else { return }
            lastRemoteConfirmNote = result.note
                ?? "Remote human confirm settled. This is not equivalent to local TTY APPROVE."
            challengeInput = ""
            approvePhraseInput = ""
            try await refreshStatus()
        } catch is CancellationError {
            return
        } catch {
            lastError = error.localizedDescription
        }
    }

    func submitRemoteRefuse() async {
        activeRemoteConfirmTask?.cancel()
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.submitRemoteRefuseImpl()
            if self.activeRemoteConfirmTask?.isCancelled == false {
                self.activeRemoteConfirmTask = nil
            }
        }
        activeRemoteConfirmTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func submitRemoteRefuseImpl() async {
        lastError = nil
        lastRemoteConfirmNote = nil
        guard !Task.isCancelled else { return }
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            lastError = "Action refused: \(reason)"
            return
        }
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
            guard !Task.isCancelled else { return }
            let result = try await client.submitRemoteRefuse(challenge: challenge, reason: reason)
            guard !Task.isCancelled else { return }
            if result.isAmbiguous {
                lastError = "Server returned ambiguous refuse response. Refresh status to check state."
                return
            }
            guard result.refusedSuccessfully else {
                lastError = result.note ?? "Refuse was not accepted by the server."
                return
            }
            guard !Task.isCancelled else { return }
            lastRemoteConfirmNote = result.note
                ?? "Pending refused. Re-arm or use local TTY APPROVE. Not an approval."
            challengeInput = ""
            approvePhraseInput = ""
            refuseReasonInput = ""
            try await refreshStatus()
        } catch is CancellationError {
            return
        } catch {
            lastError = error.localizedDescription
        }
    }

    func disconnect() {
        cancelAllTasks()
        invalidateCachedClient()
        isPaired = false
        capabilities = nil
        status = nil
        challengeInput = ""
        approvePhraseInput = ""
        refuseReasonInput = ""
        phoneSignGeneration += 1
        exactRunGeneration += 1
        phoneChallenge = nil
        signedPhonePublicKey = nil
        reviewedExactRun = nil
        reviewedExactRunLines = []
        reviewedExactRunArgv = []
        lastError = nil
        lastAttentionNote = nil
        lastRemoteConfirmNote = nil
        phonePeerNote = "No phone-peer signature has been returned. Signing uses the published challenge. It does not approve a run."
        exactRunNote = "No exact run is waiting for review. Phone approval is not physical presence at the Mac."
        UserDefaults.standard.removeObject(forKey: defaultsKey)
    }

    private func makeClient() -> CompanionClient? {
        guard isPaired,
              let url = URL(string: baseURLString),
              !pairingToken.isEmpty
        else { return nil }
        let fingerprint = tlsFingerprint.trimmingCharacters(in: .whitespacesAndNewlines)
        let config = PairingConfig(
            baseURL: url,
            pairingToken: pairingToken,
            tlsFingerprint: fingerprint.isEmpty ? nil : fingerprint
        )
        if let cached = cachedClient, let cachedConfig = cachedClientConfig,
           cachedConfig.baseURL == config.baseURL,
           cachedConfig.pairingToken == config.pairingToken,
           cachedConfig.tlsFingerprint == config.tlsFingerprint {
            return cached
        }
        let client = CompanionClient(config: config)
        cachedClient = client
        cachedClientConfig = config
        return client
    }

    func invalidateCachedClient() {
        cachedClient = nil
        cachedClientConfig = nil
    }

    #if DEBUG
    func testMakeClient() -> CompanionClient? {
        makeClient()
    }

    var testExactRunGeneration: Int {
        exactRunGeneration
    }
    #endif

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
    var challengeId: String? = nil
    var receipt: String? = nil
    var signature: String? = nil
    var macPublicKey: String? = nil
    var phoneFingerprint: String? = nil
    var holderId: String? = nil
    var generation: Int? = nil
    var outcome: String? = nil
}

enum PhoneReceiptDecision: Equatable {
    case accept
    case reject
}

func phoneKeyFingerprint(_ publicKey: String) -> String {
    SHA256.hash(data: Data(publicKey.utf8)).map { String(format: "%02x", $0) }.joined()
}

func phoneReceiptCanonical(
    challenge: String,
    challengeId: String,
    generation: Int,
    holderId: String,
    macPublicKey: String,
    phoneFingerprint: String
) -> String {
    let domain = "holder-phone-receipt-v1"
    let outcome = "verified-consumed"
    return "{\"challenge\":\"\(challenge)\",\"challenge_id\":\"\(challengeId)\",\"domain\":\"\(domain)\",\"generation\":\(generation),\"holder_id\":\"\(holderId)\",\"mac_public_key\":\"\(macPublicKey)\",\"outcome\":\"\(outcome)\",\"phone_fingerprint\":\"\(phoneFingerprint)\"}"
}

/// A caller `verified` or `consumed` flag is not read. The pinned Mac key must sign the receipt.
func phoneReceiptAuthentic(
    record: PhoneHolderVerification,
    challenge: PhonePeerChallengeMessage,
    phonePublicKey: String,
    pinnedMacPublicKey: String,
    seenSignatures: Set<String>
) -> PhoneReceiptDecision {
    if record.invalidated || pinnedMacPublicKey.isEmpty || phonePublicKey.isEmpty {
        return .reject
    }
    guard let signatureText = record.signature, !signatureText.isEmpty, !seenSignatures.contains(signatureText) else {
        return .reject
    }
    let expected = phoneReceiptCanonical(
        challenge: challenge.challenge,
        challengeId: challenge.challengeId,
        generation: challenge.generation,
        holderId: challenge.holderId,
        macPublicKey: pinnedMacPublicKey,
        phoneFingerprint: phoneKeyFingerprint(phonePublicKey)
    )
    guard
        let receiptData = Data(base64Encoded: record.receipt ?? ""),
        String(data: receiptData, encoding: .utf8) == expected,
        let macKeyData = Data(base64Encoded: pinnedMacPublicKey),
        let signatureData = Data(base64Encoded: signatureText),
        let macKey = try? P256.Signing.PublicKey(x963Representation: macKeyData),
        let signature = try? P256.Signing.ECDSASignature(rawRepresentation: signatureData),
        macKey.isValidSignature(signature, for: Data(expected.utf8))
    else {
        return .reject
    }
    return .accept
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

struct FetchedExactRun: Equatable {
    var challengeId: String
    var bound: Data
    var policy: String
    var generation: Int
    var keyGeneration: Int
    var expiry: Int
}

struct ParsedExactRun: Equatable {
    var nonce: String
    var bound: Data
    var policy: String
    var holderId: String
    var payloadDigest: String
    var launchArgv: [String]
    var generation: Int
    var keyGeneration: Int
    var expiry: Int
    var lines: [String]
}

protocol ExactRunPhoneSigningTransport {
    func fetchRetainedExactRun() async throws -> FetchedExactRun
    func submitRetainedExactRunSignature(challengeId: String, signature: String) async throws
}

protocol PhoneChallengeSigning {
    func sign(message: Data) throws -> (publicKey: String, signature: String)
    func signCommitted(message: Data) throws -> (publicKey: String, signature: String)
    func bindStagedOwnership(challengeId: String, publicKey: String) throws
    func commitEnrollment(ownedBy challengeId: String, publicKey: String) throws
    func discardStagedEnrollment()
}

extension PhoneChallengeSigning {
    func signCommitted(message: Data) throws -> (publicKey: String, signature: String) {
        throw CompanionClientError.transport("phone session key is not enrolled")
    }
    func bindStagedOwnership(challengeId: String, publicKey: String) throws {}
    func commitEnrollment(ownedBy challengeId: String, publicKey: String) throws {}
    func discardStagedEnrollment() {}
}

func canonicalExactRunBound(
    holderId: String,
    payloadDigest: String,
    launchArgv: [String],
    nonce: String,
    policy: String,
    generation: Int,
    keyGeneration: Int,
    expiry: Int
) -> Data {
    let argv = "[" + launchArgv.map(jsonStringLiteral).joined(separator: ",") + "]"
    let text = "{\"domain\":\"holder-exact-run-v1\",\"expiry\":\(expiry),\"generation\":\(generation),\"holder_id\":\(jsonStringLiteral(holderId)),\"key_generation\":\(keyGeneration),\"launch_argv\":\(argv),\"nonce\":\(jsonStringLiteral(nonce)),\"payload_digest\":\(jsonStringLiteral(payloadDigest)),\"policy\":\(jsonStringLiteral(policy))}"
    return Data(text.utf8)
}

func jsonInt(_ value: Any?) -> Int? {
    if let number = value as? Int { return number }
    if let number = value as? NSNumber { return number.intValue }
    return nil
}

func jsonStringLiteral(_ value: String) -> String {
    var out = "\""
    for scalar in value.unicodeScalars {
        switch scalar.value {
        case 0x5C:
            out += "\\\\"
        case 0x22:
            out += "\\\""
        case 0x0A:
            out += "\\n"
        case 0x0D:
            out += "\\r"
        case 0x09:
            out += "\\t"
        case ..<0x20:
            out += String(format: "\\u%04x", scalar.value)
        default:
            out.append(Character(scalar))
        }
    }
    out += "\""
    return out
}

func parseExactRun(fetched: FetchedExactRun, now: Int, pinnedHolderId: String) throws -> ParsedExactRun {
    guard
        let object = try JSONSerialization.jsonObject(with: fetched.bound) as? [String: Any],
        Set(object.keys) == ["domain", "expiry", "generation", "holder_id", "key_generation", "launch_argv", "nonce", "payload_digest", "policy"]
    else {
        throw CompanionClientError.transport("exact run bytes are not the canonical request")
    }
    guard object["domain"] as? String == "holder-exact-run-v1" else {
        throw CompanionClientError.transport("exact run domain is not holder-exact-run-v1")
    }
    guard
        let holderId = object["holder_id"] as? String, !pinnedHolderId.isEmpty, holderId == pinnedHolderId,
        let digest = object["payload_digest"] as? String, digest.count == 64, digest.allSatisfy({ $0.isHexDigit }),
        let argvValues = object["launch_argv"] as? [Any], argvValues.allSatisfy({ $0 is String }),
        let nonce = object["nonce"] as? String, !nonce.isEmpty,
        let policy = object["policy"] as? String, policy == "companion" || policy == "dual",
        let generation = jsonInt(object["generation"]),
        let keyGeneration = jsonInt(object["key_generation"]),
        let expiry = jsonInt(object["expiry"])
    else {
        throw CompanionClientError.transport("exact run bytes are not the canonical request")
    }
    let launchArgv = argvValues.compactMap { $0 as? String }
    guard fetched.challengeId == nonce, fetched.policy == policy, fetched.generation == generation, fetched.keyGeneration == keyGeneration, fetched.expiry == expiry else {
        throw CompanionClientError.transport("exact run envelope does not match the signed bytes")
    }
    guard expiry > now else {
        throw CompanionClientError.transport("exact run has expired")
    }
    let rebuilt = canonicalExactRunBound(
        holderId: holderId,
        payloadDigest: digest,
        launchArgv: launchArgv,
        nonce: nonce,
        policy: policy,
        generation: generation,
        keyGeneration: keyGeneration,
        expiry: expiry
    )
    guard rebuilt == fetched.bound else {
        throw CompanionClientError.transport("exact run bytes are not the canonical request")
    }
    let lines = [
        "policy \(policy)",
        "nonce \(nonce)",
        "holder \(holderId)",
        "payload \(digest)",
        "generation \(generation)",
        "key generation \(keyGeneration)",
        "expiry \(expiry)",
    ]
    return ParsedExactRun(
        nonce: nonce,
        bound: fetched.bound,
        policy: policy,
        holderId: holderId,
        payloadDigest: digest,
        launchArgv: launchArgv,
        generation: generation,
        keyGeneration: keyGeneration,
        expiry: expiry,
        lines: lines
    )
}

/// Sealed key bytes in Application Support. This is not the Keychain and not
/// the Secure Enclave. A new key stays pending until commit.
struct PhoneKeyStage {
    let directory: URL

    func stage(handle: Data, publicKey: Data) throws {
        try stage(handle: handle, publicKey: publicKey, challengeId: "")
    }

    func stage(handle: Data, publicKey: Data, challengeId: String) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try handle.write(to: pendingHandle, options: .atomic)
        try publicKey.write(to: pendingPublic, options: .atomic)
        let owner: [String: String] = [
            "challengeId": challengeId,
            "publicKey": publicKey.base64EncodedString(),
        ]
        let encoded = try JSONSerialization.data(withJSONObject: owner)
        try encoded.write(to: pendingOwner, options: .atomic)
    }

    func bindOwner(challengeId: String, publicKey: Data) throws {
        let staged = try Data(contentsOf: pendingPublic)
        guard staged == publicKey else {
            throw CompanionClientError.transport("staged phone key belongs to another challenge")
        }
        let owner: [String: String] = [
            "challengeId": challengeId,
            "publicKey": publicKey.base64EncodedString(),
        ]
        let encoded = try JSONSerialization.data(withJSONObject: owner)
        try encoded.write(to: pendingOwner, options: .atomic)
    }

    func validateStagedParts() throws {
        guard FileManager.default.fileExists(atPath: pendingHandle.path) else {
            throw CompanionClientError.transport("phone key handle not staged (incomplete-stage)")
        }
        guard FileManager.default.fileExists(atPath: pendingPublic.path) else {
            throw CompanionClientError.transport("phone key public key not staged (incomplete-stage)")
        }
        let handle = try Data(contentsOf: pendingHandle)
        guard !handle.isEmpty else {
            throw CompanionClientError.transport("phone key handle is empty (incomplete-stage)")
        }
        let publicKey = try Data(contentsOf: pendingPublic)
        guard publicKey.count == 65 else {
            throw CompanionClientError.transport("phone key public key is malformed (incomplete-stage)")
        }
    }

    #if RUNSPECIMEN_TEST_HOOKS
    func commit(ownedBy challengeId: String, publicKey: Data, failAfterFirstWrite: Bool = false) throws {
        try validateOwnership(challengeId: challengeId, publicKey: publicKey)
        try commitInternal(failAfterFirstWrite: failAfterFirstWrite)
    }

    func commit(failAfterFirstWrite: Bool = false) throws {
        try commitInternal(failAfterFirstWrite: failAfterFirstWrite)
    }
    #else
    func commit(ownedBy challengeId: String, publicKey: Data) throws {
        try validateOwnership(challengeId: challengeId, publicKey: publicKey)
        try commitInternal(failAfterFirstWrite: false)
    }

    func commit() throws {
        try commitInternal(failAfterFirstWrite: false)
    }
    #endif

    private func validateOwnership(challengeId: String, publicKey: Data) throws {
        try validateStagedParts()
        guard FileManager.default.fileExists(atPath: pendingOwner.path) else {
            throw CompanionClientError.transport("staged phone key belongs to another challenge")
        }
        let ownerData = try Data(contentsOf: pendingOwner)
        guard
            let owner = try JSONSerialization.jsonObject(with: ownerData) as? [String: String],
            owner["challengeId"] == challengeId,
            owner["publicKey"] == publicKey.base64EncodedString()
        else {
            throw CompanionClientError.transport("staged phone key belongs to another challenge")
        }
        let staged = try Data(contentsOf: pendingPublic)
        guard staged == publicKey else {
            throw CompanionClientError.transport("staged phone key belongs to another challenge")
        }
    }

    /// One record. A failure after the next-file write leaves the previous generation.
    private func commitInternal(failAfterFirstWrite: Bool) throws {
        guard FileManager.default.fileExists(atPath: pendingHandle.path),
              FileManager.default.fileExists(atPath: pendingPublic.path)
        else { return }
        try validateStagedParts()
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
        try? FileManager.default.removeItem(at: pendingOwner)
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

    func revoke() throws {
        discard()
        var errors: [Error] = []
        do {
            if FileManager.default.fileExists(atPath: recordURL.path) {
                try FileManager.default.removeItem(at: recordURL)
            }
        } catch {
            errors.append(error)
        }
        do {
            if FileManager.default.fileExists(atPath: nextRecordURL.path) {
                try FileManager.default.removeItem(at: nextRecordURL)
            }
        } catch {
            errors.append(error)
        }
        if let first = errors.first {
            throw CompanionClientError.transport("Phone key revocation failed: \(first.localizedDescription)")
        }
    }

    private var pendingHandle: URL { directory.appendingPathComponent("phone-session-handle.pending") }
    private var pendingPublic: URL { directory.appendingPathComponent("phone-session-public.pending") }
    private var pendingOwner: URL { directory.appendingPathComponent("phone-session-owner.pending") }
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

    func signCommitted(message: Data) throws -> (publicKey: String, signature: String) {
        let token = try stage.committedHandle()
        let key = try SecureEnclave.P256.Signing.PrivateKey(dataRepresentation: token)
        let committed = try stage.committedPublicKey()
        guard key.publicKey.x963Representation == committed else {
            throw CompanionClientError.transport("phone session key is not enrolled")
        }
        let signature = try key.signature(for: message).rawRepresentation
        return (
            key.publicKey.x963Representation.base64EncodedString(),
            signature.base64EncodedString()
        )
    }

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

    func bindStagedOwnership(challengeId: String, publicKey: String) throws {
        guard let key = Data(base64Encoded: publicKey) else {
            throw CompanionClientError.transport("staged phone key belongs to another challenge")
        }
        try stage.bindOwner(challengeId: challengeId, publicKey: key)
    }

    func commitEnrollment(ownedBy challengeId: String, publicKey: String) throws {
        guard let key = Data(base64Encoded: publicKey) else {
            throw CompanionClientError.transport("staged phone key belongs to another challenge")
        }
        try stage.commit(ownedBy: challengeId, publicKey: key)
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

    func revokeEnrollment() throws {
        try stage.revoke()
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
