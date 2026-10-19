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
    @Published private(set) var rotationRecoveryError: String?
    @Published private(set) var rotationRecoveryInProgress = false
    @Published private(set) var rotationRecoveryDismissed = false
    @Published var lastError: String?
    @Published var lastSuccessfulRefresh: Date?
    @Published var refreshOutcome: RefreshOutcome = .notAttempted
    
    enum RefreshOutcome: Equatable {
        case notAttempted
        case inProgress
        case success(Date)
        case failure(String)
        case cancelled
    }
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
    @Published private(set) var phoneEnrollmentFeedback: PhoneEnrollmentOutcome?
    @Published var phonePeerKeyState: PhonePeerKeyState = .unknown {
        didSet { if oldValue != phonePeerKeyState { phoneEnrollmentFeedback = nil } }
    }
    var phoneChallenge: PhonePeerChallengeMessage?
    var signedPhonePublicKey: String?
    private var phoneSignGeneration = 0
    private var explicitlyCancelledSignGeneration: Int?
    private var postingSignGeneration: Int?
    private var phonePeerKeyStateRevision = 0
    private var exactRunGeneration = 0
    private var reviewedExactRun: ParsedExactRun?
    private var reviewedExactRunKeyGeneration: Int?
    private var acceptedReceiptSignatures: Set<String> = []

    private var activeKeyLifecycleTask: Task<Void, Error>?
    private var keyLifecycleGeneration = 0
    private var activeRefreshTask: Task<Void, Never>?
    private var activePhonePeerTask: Task<Void, Never>?
    private var activePhonePeerSigner: (any PhoneChallengeSigning)?
    private var activeExactRunTask: Task<Void, Never>?
    private var activeRemoteConfirmTask: Task<RemoteSettleOutcome, Never>?
    private var refreshTaskGeneration = 0
    private var phonePeerTaskGeneration = 0
    private var exactRunTaskGeneration = 0
    private var remoteConfirmTaskGeneration = 0

    private var cachedClient: CompanionClient?
    private var cachedClientConfig: PairingConfig?

    #if RUNSPECIMEN_TEST_HOOKS
    var testHardwareRecoveryDirectory: URL?
    var testPhoneKeyStateRead: (() async -> PhonePeerKeyState)?
    static var testTokenDelete: (() -> Void)?
    static var testTokenRead: (() -> String?)?
    static var testTokenWrite: ((String) -> OSStatus)?
    #endif

    private let phoneKeyStage: PhoneKeyStage

    private let defaultsKey = "rs.observe.pairing"
    private let keychainService = "com.darashkevich.runspecimen.observe.pairing"
    private let keychainAccount = "pairingToken"
    private let holderPinKey = "rs.observe.pinnedHolderId"

    enum PhonePeerKeyState: Equatable {
        case unknown
        case noKey
        case enrolled(generation: Int)
        case rotating(oldGeneration: Int, newPublicKey: String)
        case error(String)

        var isEnrolled: Bool {
            switch self {
            case .enrolled, .rotating:
                return true
            default:
                return false
            }
        }
        
        var isRotating: Bool {
            if case .rotating = self { return true }
            return false
        }
    }

    nonisolated static var hardwareEnrollmentDirectory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return base.appendingPathComponent("RunSpecimenObservePairing", isDirectory: true)
    }

    func recoverHardwareRotation(directory suppliedDirectory: URL? = nil) async {
        let directory: URL
        #if RUNSPECIMEN_TEST_HOOKS
        directory = suppliedDirectory ?? testHardwareRecoveryDirectory ?? Self.hardwareEnrollmentDirectory
        #else
        directory = suppliedDirectory ?? Self.hardwareEnrollmentDirectory
        #endif
        guard !rotationRecoveryInProgress else { return }
        rotationRecoveryInProgress = true
        defer { rotationRecoveryInProgress = false }
        do {
            try await CryptoWorker.shared.perform {
                try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
            }
            rotationRecoveryError = nil
            rotationRecoveryDismissed = false
        } catch {
            rotationRecoveryError = "Key recovery needs attention: \(error.localizedDescription)"
        }
    }

    func dismissRotationRecoveryNotice() { rotationRecoveryDismissed = true }
    func showRotationRecoveryNotice() { rotationRecoveryDismissed = false }

    var rotationRecoveryDiagnostics: String {
        "RunSpecimen key recovery\n" + (rotationRecoveryError ?? "No pending hardware-key recovery error.")
            + "\nRecovery evidence is retained. Retry after restoring storage access; do not delete key records or reset generation counters."
    }

    func repairPhoneKeyCounter() async throws {
        try await withKeyLifecycle { [self] in
            try await CompanionSecureEnclaveEnrollment.authenticateWithBiometrics(reason: "Authenticate to repair the saved phone key counter")
            let stage = phoneKeyStage
            try await CryptoWorker.shared.perform { try stage.repairGenerationReservation() }
            phonePeerKeyStateRevision += 1
            await refreshPhonePeerKeyStateAsync()
            phonePeerNote = "Saved key counter repaired from its recovery record. No key was replaced and no generation was reset."
        }
    }

    init(deferPhoneKeyState: Bool = false,
         phoneKeyStage: PhoneKeyStage = LivePhoneSecureEnclaveSigner().stage) {
        self.phoneKeyStage = phoneKeyStage
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

        phonePeerKeyStateRevision += 1
        phonePeerKeyState = Self.readPhoneKeyState(stage: phoneKeyStage)

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

        phonePeerKeyStateRevision += 1
        let capturedRevision = phonePeerKeyStateRevision

        let stage = phoneKeyStage
        let result: PhonePeerKeyState
        #if RUNSPECIMEN_TEST_HOOKS
        if let read = testPhoneKeyStateRead {
            result = await read()
        } else {
            result = await Task.detached { Self.readPhoneKeyState(stage: stage) }.value
        }
        #else
        result = await Task.detached { Self.readPhoneKeyState(stage: stage) }.value
        #endif

        guard capturedRevision == phonePeerKeyStateRevision else {
            #if DEBUG
            launchLogger.info("refreshPhonePeerKeyStateAsync() STALE - discarding result")
            #endif
            return
        }

        phonePeerKeyState = result

        #if DEBUG
        let end = CFAbsoluteTimeGetCurrent()
        launchLogger.info("refreshPhonePeerKeyStateAsync() END, duration: \((end - start) * 1000, format: .fixed(precision: 1))ms, state: \(String(describing: self.phonePeerKeyState))")
        #endif
    }

    nonisolated private static func readPhoneKeyState(stage: PhoneKeyStage) -> PhonePeerKeyState {
        do {
            try stage.checkGenerationReservation()
            let generation: Int
            do { generation = try stage.committedGeneration() }
            catch let error as CocoaError where error.code == .fileReadNoSuchFile { generation = 0 }
            if stage.hasAnyStagedParts() {
                return .rotating(oldGeneration: generation, newPublicKey: try stage.stagedPublicKey().base64EncodedString())
            }
            return generation == 0 ? .noKey : .enrolled(generation: generation)
        } catch {
            return .error(error.localizedDescription)
        }
    }

    private func withKeyLifecycle(_ operation: @escaping @MainActor () async throws -> Void) async throws {
        activeKeyLifecycleTask?.cancel()
        keyLifecycleGeneration += 1
        let generation = keyLifecycleGeneration
        let task = Task { @MainActor in try await operation() }
        activeKeyLifecycleTask = task
        defer { if generation == keyLifecycleGeneration { activeKeyLifecycleTask = nil } }
        try await withTaskCancellationHandler {
            try await task.value
        } onCancel: { task.cancel() }
    }

    private func invalidatePhonePeerOperation() {
        phoneEnrollmentFeedback = nil
        explicitlyCancelledSignGeneration = nil
        activePhonePeerTask?.cancel()
        if activePhonePeerTask != nil { activePhonePeerSigner?.discardStagedEnrollment() }
        activePhonePeerTask = nil
        activePhonePeerSigner = nil
        phonePeerTaskGeneration += 1
        phoneSignGeneration += 1
        phoneChallenge = nil
        signedPhonePublicKey = nil
    }

    func revokePhonePeerKey() async throws {
        try await withKeyLifecycle { [self] in
            invalidatePhonePeerOperation()
            phonePeerKeyStateRevision += 1
            exactRunGeneration += 1
            reviewedExactRun = nil
            reviewedExactRunLines = []
            reviewedExactRunArgv = []
            reviewedExactRunKeyGeneration = nil
            try await CompanionSecureEnclaveEnrollment.authenticateWithBiometrics(reason: "Authenticate to revoke this phone-peer key")
            let stage = phoneKeyStage
            try await CryptoWorker.shared.perform { try stage.revoke() }
            phonePeerKeyState = .noKey
            phoneChallenge = nil
            signedPhonePublicKey = nil
            phonePeerNote = "Phone-peer key revoked. Re-enroll by signing a new challenge."
        }
    }

    func rotatePhonePeerKey() async throws {
        try await withKeyLifecycle { [self] in
            invalidatePhonePeerOperation()
            phonePeerKeyStateRevision += 1
            exactRunGeneration += 1
            reviewedExactRun = nil
            reviewedExactRunLines = []
            reviewedExactRunArgv = []
            reviewedExactRunKeyGeneration = nil
            try await CompanionSecureEnclaveEnrollment.authenticateWithBiometrics(reason: "Authenticate to rotate this phone-peer key")
            let signer = LivePhoneSecureEnclaveSigner(stage: phoneKeyStage)
            try await signer.rotateEnrollmentAsync()
            await refreshPhonePeerKeyStateAsync()
            phonePeerNote = "Phone-peer key rotation staged. Sign its challenge, then verify the Mac holder receipt to complete."
        }
    }

    func completePhonePeerKeyRotation(signer: (any PhoneChallengeSigning)? = nil, peer: (any PhonePeerTransport)? = nil) async throws {
        try await withKeyLifecycle { [self] in
            phonePeerKeyStateRevision += 1
            let stage = phoneKeyStage
            let stagedPublicKey = try await CryptoWorker.shared.perform { try stage.stagedPublicKey() }
            guard let publicKey = signedPhonePublicKey,
                  publicKey == stagedPublicKey.base64EncodedString(), phoneChallenge != nil else {
                throw CompanionClientError.transport("Sign the staged replacement challenge and verify its holder receipt before completing rotation")
            }
            let outcome = await commitPhoneKeyAfterHolderVerification(
                signer: signer ?? LivePhoneSecureEnclaveSigner(stage: phoneKeyStage), peer: peer)
            switch outcome {
            case .enrolled: phonePeerNote = "Phone-peer key rotation completed after biometric and holder-receipt verification."
            case .cancelled: throw CancellationError()
            case .refused(let reason): throw CompanionClientError.transport(reason)
            }
        }
    }

    func cancelPhonePeerKeyRotation() async throws {
        try await withKeyLifecycle { [self] in
            invalidatePhonePeerOperation()
            phonePeerKeyStateRevision += 1
            let stage = phoneKeyStage
            try await CryptoWorker.shared.perform { stage.discard() }
            await refreshPhonePeerKeyStateAsync()
            phonePeerNote = "Phone-peer key rotation cancelled. The old key is still active."
        }
    }

    func cancelAllTasks() {
        keyLifecycleGeneration += 1
        activeKeyLifecycleTask?.cancel()
        activeKeyLifecycleTask = nil
        // Clean the current stage before invalidating its generation. A stale
        // completion must never clean a successor's shared stage directory.
        if activePhonePeerTask != nil { activePhonePeerSigner?.discardStagedEnrollment() }
        activePhonePeerSigner = nil
        refreshTaskGeneration += 1
        phonePeerTaskGeneration += 1
        exactRunTaskGeneration += 1
        remoteConfirmTaskGeneration += 1
        phoneSignGeneration += 1
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

    enum ConnectionState: Equatable {
        case offline, checking, stale, connected
    }

    var connectionState: ConnectionState {
        guard isPaired else { return .offline }
        if case .inProgress = refreshOutcome { return .checking }
        guard status != nil, capabilities != nil else { return .stale }
        switch refreshOutcome {
        case .failure, .cancelled: return .stale
        default: return .connected
        }
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

    func saveAndPair(client suppliedClient: CompanionClient? = nil) async {
        refreshTaskGeneration += 1
        let generation = refreshTaskGeneration
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
        let client = suppliedClient ?? CompanionClient(config: config)
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
            let verifiedStatus = try await client.fetchStatus()
            switch CapabilityValidator.validateForAction(capabilities: caps, status: verifiedStatus) {
            case .valid: break
            case .invalid(let reason): throw CompanionClientError.transport(reason)
            }
            try Task.checkCancellation()
            guard generation == refreshTaskGeneration else { throw CancellationError() }
            // A rejected candidate must never replace the saved pairing.
            try persist(config)
            status = verifiedStatus
            capabilities = caps
            isPaired = true
            let now = Date()
            lastSuccessfulRefresh = now
            refreshOutcome = .success(now)
        } catch {
            guard generation == refreshTaskGeneration else { return }
            capabilities = nil
            status = nil
            lastError = error.localizedDescription
            isPaired = false
        }
    }

    func refreshStatus() async throws {
        guard let client = makeClient() else { throw CompanionClientError.notPaired }
        let generation = refreshTaskGeneration
        do {
            let fetchedStatus = try await client.fetchStatus()
            try Task.checkCancellation()
            guard isPaired, generation == refreshTaskGeneration else { throw CancellationError() }
            let fetchedCapabilities = try await client.fetchCapabilities()
            try Task.checkCancellation()
            guard isPaired, generation == refreshTaskGeneration else { throw CancellationError() }
            switch CapabilityValidator.validateForAction(capabilities: fetchedCapabilities, status: fetchedStatus) {
            case .valid:
                status = fetchedStatus
                capabilities = fetchedCapabilities
                let now = Date()
                lastSuccessfulRefresh = now
                refreshOutcome = .success(now)
            case .invalid(let reason):
                disconnect()
                lastError = reason
                // Disconnect invalidates refresh tasks; publish the refusal after
                // that reset so the initiating refresh cannot erase the reason.
                refreshOutcome = .failure(reason)
                throw CompanionClientError.transport(reason)
            }
        } catch {
            if isPaired, generation == refreshTaskGeneration, !Task.isCancelled {
                capabilities = nil
            }
            throw error
        }
    }

    func refresh() async {
        activeRefreshTask?.cancel()
        refreshTaskGeneration += 1
        let myGeneration = refreshTaskGeneration
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            guard self.refreshTaskGeneration == myGeneration else { return }
            self.lastError = nil
            self.refreshOutcome = .inProgress
            do {
                guard !Task.isCancelled, self.isPaired, self.refreshTaskGeneration == myGeneration else {
                    if self.refreshTaskGeneration != myGeneration { return }
                    self.refreshOutcome = .cancelled
                    return
                }
                try await self.refreshStatus()
                guard !Task.isCancelled, self.isPaired, self.refreshTaskGeneration == myGeneration else {
                    if self.refreshTaskGeneration != myGeneration { return }
                    self.refreshOutcome = .cancelled
                    return
                }
                let now = Date()
                self.lastSuccessfulRefresh = now
                self.refreshOutcome = .success(now)
            } catch is CancellationError {
                guard self.refreshTaskGeneration == myGeneration else { return }
                self.refreshOutcome = .cancelled
                return
            } catch {
                guard !Task.isCancelled, self.isPaired, self.refreshTaskGeneration == myGeneration else {
                    if self.refreshTaskGeneration != myGeneration { return }
                    self.refreshOutcome = .cancelled
                    return
                }
                self.lastError = error.localizedDescription
                self.refreshOutcome = .failure(error.localizedDescription)
            }
            if self.refreshTaskGeneration == myGeneration {
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
        phoneEnrollmentFeedback = nil
        explicitlyCancelledSignGeneration = nil
        activePhonePeerTask?.cancel()
        if activePhonePeerTask != nil { activePhonePeerSigner?.discardStagedEnrollment() }
        activePhonePeerSigner = signer
        phonePeerTaskGeneration += 1
        let myGeneration = phonePeerTaskGeneration
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.signPhonePeerChallengeImpl(signer: signer, peer: peer)
            if self.phonePeerTaskGeneration == myGeneration {
                self.activePhonePeerTask = nil
                self.activePhonePeerSigner = nil
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
            let signed = try await signer.signAsync(message: bytes)
            try Task.checkCancellation()
            guard generation == phoneSignGeneration else {
                throw PhonePeerSignError.cancelled
            }
            guard !Task.isCancelled else {
                if generation == phoneSignGeneration { signer.discardStagedEnrollment() }
                throw PhonePeerSignError.cancelled
            }
            try await transport.willSubmitPhonePeerSignature()
            try Task.checkCancellation()
            guard generation == phoneSignGeneration else {
                throw PhonePeerSignError.cancelled
            }
            guard !Task.isCancelled else {
                if generation == phoneSignGeneration { signer.discardStagedEnrollment() }
                throw PhonePeerSignError.cancelled
            }
            postingSignGeneration = generation
            try await transport.submitPhonePeerSignature(
                challengeId: message.challengeId,
                challenge: message.challenge,
                publicKey: signed.publicKey,
                signature: signed.signature
            )
            guard generation == phoneSignGeneration else {
                try? await transport.invalidatePhonePeerChallenge(challengeId: message.challengeId)
                throw PhonePeerSignError.cancellationTooLate
            }
            guard !Task.isCancelled else {
                if generation == phoneSignGeneration { signer.discardStagedEnrollment() }
                try? await transport.invalidatePhonePeerChallenge(challengeId: message.challengeId)
                throw PhonePeerSignError.cancellationTooLate
            }
            try signer.bindStagedOwnership(challengeId: message.challengeId, publicKey: signed.publicKey)
            signedPhonePublicKey = signed.publicKey
            phonePeerNote = "Mailbox accepted challenge \(message.challengeId). That is not holder verification and the key is not enrolled."
        } catch PhonePeerSignError.cancelled {
            guard generation == phoneSignGeneration else { return }
            phoneChallenge = nil
            signedPhonePublicKey = nil
            signer.discardStagedEnrollment()
            phonePeerNote = "Phone peer challenge cancelled before a signature was returned."
            lastError = nil
        } catch PhonePeerSignError.cancellationTooLate {
            guard generation == phoneSignGeneration || explicitlyCancelledSignGeneration == generation else { return }
            signedPhonePublicKey = nil
            phonePeerNote = "Phone peer challenge cancellation was too late. The signature left the device and must not enroll."
            lastError = nil
        } catch is CancellationError {
            guard generation == phoneSignGeneration else { return }
            phoneChallenge = nil
            signedPhonePublicKey = nil
            signer.discardStagedEnrollment()
            phonePeerNote = "Phone peer challenge cancelled before a signature was returned."
            lastError = nil
        } catch {
            guard generation == phoneSignGeneration else { return }
            signer.discardStagedEnrollment()
            lastError = error.localizedDescription
        }
    }

    /// Enroll only after the phone verifies a holder receipt. Caller flags are ignored.
    enum PhoneEnrollmentOutcome: Equatable {
        case enrolled, cancelled
        case refused(String)
    }

    @discardableResult
    func commitPhoneKeyAfterHolderVerification(
        signer: PhoneChallengeSigning = LivePhoneSecureEnclaveSigner(),
        peer: (any PhonePeerTransport)? = nil
    ) async -> PhoneEnrollmentOutcome {
        phoneEnrollmentFeedback = nil
        activePhonePeerTask?.cancel()
        phonePeerTaskGeneration += 1
        let myGeneration = phonePeerTaskGeneration
        var outcome: PhoneEnrollmentOutcome = .cancelled
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            outcome = await self.commitPhoneKeyAfterHolderVerificationImpl(signer: signer, peer: peer)
            if self.phonePeerTaskGeneration == myGeneration {
                self.activePhonePeerTask = nil
            }
        }
        activePhonePeerTask = task
        await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
        if outcome == .enrolled {
            if myGeneration == phonePeerTaskGeneration || (isPaired && phoneChallenge == nil) { phoneEnrollmentFeedback = outcome }
            return outcome
        }
        guard !task.isCancelled, myGeneration == phonePeerTaskGeneration else { return .cancelled }
        phoneEnrollmentFeedback = outcome
        return outcome
    }

    private func commitPhoneKeyAfterHolderVerificationImpl(
        signer: PhoneChallengeSigning,
        peer: (any PhonePeerTransport)?
    ) async -> PhoneEnrollmentOutcome {
        guard !Task.isCancelled else {
            phonePeerNote = "Phone peer challenge cancelled before the holder receipt committed."
            return .refused(lastError ?? phonePeerNote)
        }
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            lastError = "Action refused: \(reason)"
            return .refused(lastError ?? phonePeerNote)
        }
        let transport: any PhonePeerTransport
        if let peer {
            transport = peer
        } else if let client = makeClient() {
            transport = client
        } else {
            lastError = CompanionClientError.notPaired.localizedDescription
            return .refused(lastError ?? phonePeerNote)
        }
        guard let message = phoneChallenge, let phonePublicKey = signedPhonePublicKey else {
            let reason = "Sign a phone peer challenge first, then verify it on the Mac before enrolling."
            phonePeerNote = reason
            lastError = reason
            return .refused(reason)
        }
        let generation = phoneSignGeneration
        let challengeId = message.challengeId
        do {
            guard !Task.isCancelled else { throw CancellationError() }
            let record = try await transport.fetchHolderVerification(challengeId: challengeId)
            try Task.checkCancellation()
            guard generation == phoneSignGeneration, phoneChallenge?.challengeId == challengeId, signedPhonePublicKey == phonePublicKey else {
                phonePeerNote = "Phone peer challenge cancelled before the holder receipt committed."
                return .refused(lastError ?? phonePeerNote)
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
                return .refused(lastError ?? phonePeerNote)
            }
            guard generation == phoneSignGeneration, phoneChallenge?.challengeId == challengeId else {
                phonePeerNote = "Phone peer challenge cancelled before the holder receipt committed."
                return .refused(lastError ?? phonePeerNote)
            }
            guard !Task.isCancelled else { throw CancellationError() }
            try await CompanionSecureEnclaveEnrollment.authenticateWithBiometrics(reason: "Authenticate to enroll the holder-verified phone-peer key")
            try Task.checkCancellation()
            guard generation == phoneSignGeneration, phoneChallenge?.challengeId == challengeId,
                  signedPhonePublicKey == phonePublicKey else { return .cancelled }
            phonePeerKeyStateRevision += 1
            try await signer.commitEnrollmentAsync(ownedBy: challengeId, publicKey: phonePublicKey)
            // A successful durable commit is the outcome, even if cancellation
            // arrived during the final write. Never leave its receipt reusable.
            acceptedReceiptSignatures.insert(signature)
            if phoneChallenge?.challengeId == challengeId { phoneChallenge = nil; signedPhonePublicKey = nil }
            if generation == phoneSignGeneration || (isPaired && phoneChallenge == nil) {
                await Task { @MainActor in await self.refreshPhonePeerKeyStateAsync() }.value
                phonePeerNote = "Holder receipt verified for challenge \(challengeId). The phone key is enrolled."
                lastError = nil
            }
            return .enrolled
        } catch PhonePeerSignError.cancelled {
            phonePeerNote = "Phone peer challenge cancelled before the holder receipt committed."
            lastError = nil
            return .cancelled
        } catch is CancellationError {
            phonePeerNote = "Phone peer challenge cancelled before the holder receipt committed."
            lastError = nil
            return .cancelled
        } catch {
            lastError = error.localizedDescription
            return .refused(error.localizedDescription)
        }
    }

    /// Fetch one published exact run and show the fields inside its signed bytes. This does not sign.
    func reviewRetainedExactRun(
        now: Int = Int(Date().timeIntervalSince1970),
        peer: (any ExactRunPhoneSigningTransport)? = nil
    ) async {
        activeExactRunTask?.cancel()
        exactRunTaskGeneration += 1
        let myGeneration = exactRunTaskGeneration
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.reviewRetainedExactRunImpl(now: now, peer: peer)
            if self.exactRunTaskGeneration == myGeneration {
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
        reviewedExactRunKeyGeneration = nil
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
            let capturedKeyGen: Int?
            if case .enrolled(let gen) = phonePeerKeyState {
                capturedKeyGen = gen
            } else {
                capturedKeyGen = nil
            }
            reviewedExactRun = parsed
            reviewedExactRunLines = parsed.lines
            reviewedExactRunArgv = parsed.launchArgv
            reviewedExactRunKeyGeneration = capturedKeyGen
            exactRunNote = "Review these bytes before signing. Signing uses the enrolled phone key and does not create one."
        } catch is CancellationError {
            reviewedExactRun = nil
            reviewedExactRunLines = []
            reviewedExactRunArgv = []
            reviewedExactRunKeyGeneration = nil
            exactRunNote = "Exact run review was cancelled before a signature was returned."
        } catch {
            if generation == exactRunGeneration {
                reviewedExactRun = nil
                reviewedExactRunLines = []
                reviewedExactRunArgv = []
                reviewedExactRunKeyGeneration = nil
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
        exactRunTaskGeneration += 1
        let myGeneration = exactRunTaskGeneration
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.approveReviewedExactRunImpl(signer: signer, peer: peer, now: now, beforeSign: beforeSign, beforeSubmit: beforeSubmit)
            if self.exactRunTaskGeneration == myGeneration {
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
        exactRunTaskGeneration += 1
        let myGeneration = exactRunTaskGeneration
        let task = Task { @MainActor [weak self] in
            guard let self else { return }
            await self.approveReviewedExactRunImpl(signer: signer, peer: peer, now: now, beforeSign: nil, beforeSubmit: nil)
            if self.exactRunTaskGeneration == myGeneration {
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
            let currentKeyGen: Int?
            if case .enrolled(let gen) = phonePeerKeyState {
                currentKeyGen = gen
            } else {
                currentKeyGen = nil
            }
            guard currentKeyGen == reviewedExactRunKeyGeneration else {
                reviewedExactRun = nil
                reviewedExactRunLines = []
                reviewedExactRunArgv = []
                reviewedExactRunKeyGeneration = nil
                exactRunNote = "Phone-peer key changed after review. The signature was not returned."
                return
            }
            guard !Task.isCancelled else { throw CancellationError() }
            let signed = try await signer.signCommittedAsync(message: reviewed.bound)
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
        reviewedExactRunKeyGeneration = nil
        exactRunNote = "Exact run review was cancelled before a signature was returned."
        lastError = nil
    }

    func cancelPhonePeerChallenge() async {
        phoneEnrollmentFeedback = nil
        activePhonePeerTask?.cancel()
        activePhonePeerTask = nil
        activePhonePeerSigner?.discardStagedEnrollment()
        activePhonePeerSigner = nil
        explicitlyCancelledSignGeneration = phoneSignGeneration
        let mayHavePublished = postingSignGeneration == phoneSignGeneration
        phoneSignGeneration += 1
        phoneChallenge = nil
        signedPhonePublicKey = nil
        phonePeerNote = mayHavePublished
            ? "Phone peer challenge cancellation was too late. The signature left the device and must not enroll."
            : "Phone peer challenge cancelled before a signature was returned."
        lastError = nil
    }

    func requestAttention() async {
        lastError = nil
        lastAttentionNote = nil
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            lastError = "Action refused: \(reason)"
            return
        }
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
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            lastError = "Action refused: \(reason)"
            return
        }
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

    enum RemoteSettleOutcome: Equatable {
        case confirmed
        case refused
        case cancelled
        case failure(String)
    }

    @discardableResult
    func submitRemoteConfirm() async -> RemoteSettleOutcome {
        guard !Task.isCancelled else { return .cancelled }
        guard activeRemoteConfirmTask == nil else {
            return .failure("A remote settlement is already in progress.")
        }
        remoteConfirmTaskGeneration += 1
        let myGeneration = remoteConfirmTaskGeneration
        let task = Task<RemoteSettleOutcome, Never> { @MainActor [weak self] in
            guard let self else { return .cancelled }
            let outcome = await self.submitRemoteConfirmImpl()
            if self.remoteConfirmTaskGeneration == myGeneration {
                self.activeRemoteConfirmTask = nil
            }
            // A validated server acknowledgement survives later local cancellation
            // or a newer request. Only unacknowledged work can become cancelled.
            if outcome == .confirmed || outcome == .refused { return outcome }
            guard !Task.isCancelled, self.remoteConfirmTaskGeneration == myGeneration else { return .cancelled }
            return outcome
        }
        activeRemoteConfirmTask = task
        return await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func submitRemoteConfirmImpl() async -> RemoteSettleOutcome {
        lastError = nil
        lastRemoteConfirmNote = nil
        guard !Task.isCancelled else { return .cancelled }
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            return settlementFailure("Action refused: \(reason)")
        }
        guard remoteConfirmPending else {
            return settlementFailure("No Mac-armed remote confirm is pending.")
        }
        let challenge = challengeInput.trimmingCharacters(in: .whitespacesAndNewlines)
        let phrase = approvePhraseInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !challenge.isEmpty else {
            return settlementFailure("Enter the challenge shown on the Mac.")
        }
        guard phrase == "APPROVE" else {
            return settlementFailure("Phrase must be exactly APPROVE (typed, not one-tap).")
        }
        guard let client = makeClient() else {
            return settlementFailure(CompanionClientError.notPaired.localizedDescription)
        }
        do {
            guard !Task.isCancelled else { return .cancelled }
            let result = try await client.submitRemoteConfirm(challenge: challenge, phrase: phrase)
            if result.isAmbiguous {
                return settlementFailure("Server returned ambiguous confirm response. Refresh status to check state.")
            }
            guard result.confirmedSuccessfully else {
                return settlementFailure(result.note ?? "Confirm was not accepted by the server.")
            }
            lastRemoteConfirmNote = result.note
                ?? "Remote human confirm settled. This is not equivalent to local TTY APPROVE."
            challengeInput = ""
            approvePhraseInput = ""
            // Settlement is already acknowledged; refresh cannot change its outcome.
            do { try await refreshStatus() } catch { }
            return .confirmed
        } catch is CancellationError {
            return .cancelled
        } catch {
            return settlementFailure(error.localizedDescription)
        }
    }

    @discardableResult
    func submitRemoteRefuse() async -> RemoteSettleOutcome {
        guard !Task.isCancelled else { return .cancelled }
        guard activeRemoteConfirmTask == nil else {
            return .failure("A remote settlement is already in progress.")
        }
        remoteConfirmTaskGeneration += 1
        let myGeneration = remoteConfirmTaskGeneration
        let task = Task<RemoteSettleOutcome, Never> { @MainActor [weak self] in
            guard let self else { return .cancelled }
            let outcome = await self.submitRemoteRefuseImpl()
            if self.remoteConfirmTaskGeneration == myGeneration {
                self.activeRemoteConfirmTask = nil
            }
            // A validated server acknowledgement survives later local cancellation
            // or a newer request. Only unacknowledged work can become cancelled.
            if outcome == .confirmed || outcome == .refused { return outcome }
            guard !Task.isCancelled, self.remoteConfirmTaskGeneration == myGeneration else { return .cancelled }
            return outcome
        }
        activeRemoteConfirmTask = task
        return await withTaskCancellationHandler {
            await task.value
        } onCancel: {
            task.cancel()
        }
    }

    private func submitRemoteRefuseImpl() async -> RemoteSettleOutcome {
        lastError = nil
        lastRemoteConfirmNote = nil
        guard !Task.isCancelled else { return .cancelled }
        switch CapabilityValidator.validateForAction(capabilities: capabilities, status: status) {
        case .valid:
            break
        case .invalid(let reason):
            return settlementFailure("Action refused: \(reason)")
        }
        guard remoteConfirmPending else {
            return settlementFailure("No Mac-armed remote confirm is pending.")
        }
        let challenge = challengeInput.trimmingCharacters(in: .whitespacesAndNewlines)
        let reason = refuseReasonInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !challenge.isEmpty else {
            return settlementFailure("Enter the challenge shown on the Mac.")
        }
        guard (1 ... 240).contains(reason.count) else {
            return settlementFailure("Refuse requires a reason (1–240 characters). This does not approve.")
        }
        guard let client = makeClient() else {
            return settlementFailure(CompanionClientError.notPaired.localizedDescription)
        }
        do {
            guard !Task.isCancelled else { return .cancelled }
            let result = try await client.submitRemoteRefuse(challenge: challenge, reason: reason)
            if result.isAmbiguous {
                return settlementFailure("Server returned ambiguous refuse response. Refresh status to check state.")
            }
            guard result.refusedSuccessfully else {
                return settlementFailure(result.note ?? "Refuse was not accepted by the server.")
            }
            lastRemoteConfirmNote = result.note
                ?? "Pending refused. Re-arm or use local TTY APPROVE. Not an approval."
            challengeInput = ""
            approvePhraseInput = ""
            refuseReasonInput = ""
            // Settlement is already acknowledged; refresh cannot change its outcome.
            do { try await refreshStatus() } catch { }
            return .refused
        } catch is CancellationError {
            return .cancelled
        } catch {
            return settlementFailure(error.localizedDescription)
        }
    }

    private func settlementFailure(_ message: String) -> RemoteSettleOutcome {
        lastError = message
        return .failure(message)
    }

    func disconnect() {
        phoneEnrollmentFeedback = nil
        cancelAllTasks()
        invalidateCachedClient()
        isPaired = false
        pairingToken = ""
        baseURLString = ""
        tlsFingerprint = ""
        macSessionPublicKey = ""
        pinnedHolderId = ""
        UserDefaults.standard.removeObject(forKey: holderPinKey)
        lastSuccessfulRefresh = nil
        refreshOutcome = .notAttempted
        capabilities = nil
        status = nil
        challengeInput = ""
        approvePhraseInput = ""
        refuseReasonInput = ""
        phoneSignGeneration += 1
        exactRunGeneration += 1
        phonePeerKeyStateRevision += 1
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
        deletePairingTokenFromKeychain()
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
    
    var testPhonePeerKeyStateRevision: Int {
        phonePeerKeyStateRevision
    }
    
    var testReviewedExactRunKeyGeneration: Int? {
        reviewedExactRunKeyGeneration
    }
    
    var testActiveRefreshTask: Task<Void, Never>? {
        activeRefreshTask
    }
    #endif

    func persist(_ config: PairingConfig) throws {
        var publicConfig = config
        publicConfig.pairingToken = ""
        let publicData = try JSONEncoder().encode(publicConfig)
        let status = savePairingTokenToKeychain(config.pairingToken)
        guard status == errSecSuccess else {
            throw CompanionClientError.transport("Could not save pairing token (Keychain status \(status)). Previous pairing retained.")
        }
        UserDefaults.standard.set(publicData, forKey: defaultsKey)
        baseURLString = config.baseURL.absoluteString
        pairingToken = config.pairingToken
        tlsFingerprint = config.tlsFingerprint ?? ""
    }

    private func load() {
        if let keychainToken = loadPairingTokenFromKeychain(), !keychainToken.isEmpty {
            if let data = UserDefaults.standard.data(forKey: defaultsKey),
               let config = try? JSONDecoder().decode(PairingConfig.self, from: data) {
                baseURLString = config.baseURL.absoluteString
                pairingToken = keychainToken
                tlsFingerprint = config.tlsFingerprint ?? ""
                isPaired = true
                return
            }
        }

        if let data = UserDefaults.standard.data(forKey: defaultsKey),
           let config = try? JSONDecoder().decode(PairingConfig.self, from: data),
           !config.pairingToken.isEmpty {
            baseURLString = config.baseURL.absoluteString
            pairingToken = config.pairingToken
            tlsFingerprint = config.tlsFingerprint ?? ""
            isPaired = true
            let migrationStatus = savePairingTokenToKeychain(config.pairingToken)
            guard migrationStatus == errSecSuccess else {
                lastError = "Pairing token migration failed (Keychain status \(migrationStatus)). Legacy token retained for retry."
                return
            }
            var sanitized = config
            sanitized.pairingToken = ""
            if let sanitizedData = try? JSONEncoder().encode(sanitized) {
                UserDefaults.standard.set(sanitizedData, forKey: defaultsKey)
            }
        }
    }

    @discardableResult
    private func savePairingTokenToKeychain(_ token: String) -> OSStatus {
        #if RUNSPECIMEN_TEST_HOOKS
        if let write = Self.testTokenWrite { return write(token) }
        #endif
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
        ]
        guard !token.isEmpty, let data = token.data(using: .utf8) else { return errSecParam }
        let updateStatus = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        guard updateStatus == errSecItemNotFound else { return updateStatus }
        let addQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        ]
        return SecItemAdd(addQuery as CFDictionary, nil)
    }

    private func loadPairingTokenFromKeychain() -> String? {
        #if RUNSPECIMEN_TEST_HOOKS
        if let read = Self.testTokenRead { return read() }
        #endif
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func deletePairingTokenFromKeychain() {
        #if RUNSPECIMEN_TEST_HOOKS
        if let delete = Self.testTokenDelete { delete(); return }
        #endif
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: keychainAccount,
        ]
        SecItemDelete(query as CFDictionary)
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
    func signAsync(message: Data) async throws -> (publicKey: String, signature: String)
    func signCommittedAsync(message: Data) async throws -> (publicKey: String, signature: String)
    func commitEnrollmentAsync(ownedBy challengeId: String, publicKey: String) async throws
    func signCommitted(message: Data) throws -> (publicKey: String, signature: String)
    func bindStagedOwnership(challengeId: String, publicKey: String) throws
    func commitEnrollment(ownedBy challengeId: String, publicKey: String) throws
    func discardStagedEnrollment()
}

extension PhoneChallengeSigning {
    func signAsync(message: Data) async throws -> (publicKey: String, signature: String) {
        try await CryptoWorker.shared.perform { try self.sign(message: message) }
    }
    func signCommittedAsync(message: Data) async throws -> (publicKey: String, signature: String) {
        try await CryptoWorker.shared.perform { try self.signCommitted(message: message) }
    }
    func commitEnrollmentAsync(ownedBy challengeId: String, publicKey: String) async throws {
        try await CryptoWorker.shared.performCommit { try self.commitEnrollment(ownedBy: challengeId, publicKey: publicKey) }
    }
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
    #if RUNSPECIMEN_TEST_HOOKS
    var testPublicKeyForHandle: ((Data) throws -> Data)? = nil
    #endif

    private func validateKey(handle: Data, publicKey: Data) throws {
        do { _ = try P256.Signing.PublicKey(x963Representation: publicKey) }
        catch { throw CompanionClientError.transport("phone key public key is malformed (incomplete-stage)") }
        let actual: Data
        #if RUNSPECIMEN_TEST_HOOKS
        if let resolve = testPublicKeyForHandle { actual = try resolve(handle) }
        else { actual = try Self.enclavePublicKey(handle) }
        #else
        actual = try Self.enclavePublicKey(handle)
        #endif
        guard actual == publicKey else {
            throw CompanionClientError.transport("phone key handle/public key mismatch")
        }
    }

    private static func enclavePublicKey(_ handle: Data) throws -> Data {
        let context = LAContext()
        defer { context.invalidate() }
        return try SecureEnclave.P256.Signing.PrivateKey(dataRepresentation: handle,
            authenticationContext: context).publicKey.x963Representation
    }

    private struct CustodyRecord: Codable {
        let generation: Int
        let handle: Data
        let publicKey: Data
    }

    func stage(handle: Data, publicKey: Data) throws {
        try stage(handle: handle, publicKey: publicKey, challengeId: "")
    }

    func stage(handle: Data, publicKey: Data, challengeId: String, operationID: String? = nil) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try handle.write(to: pendingHandle, options: .atomic)
        try publicKey.write(to: pendingPublic, options: .atomic)
        var owner: [String: String] = [
            "challengeId": challengeId,
            "publicKey": publicKey.base64EncodedString(),
        ]
        owner["operationID"] = operationID
        let encoded = try JSONSerialization.data(withJSONObject: owner)
        try encoded.write(to: pendingOwner, options: .atomic)
    }

    func bindOwner(challengeId: String, publicKey: Data) throws {
        let staged = try Data(contentsOf: pendingPublic)
        guard staged == publicKey else {
            throw CompanionClientError.transport("staged phone key belongs to another challenge")
        }
        var owner: [String: String] = [
            "challengeId": challengeId,
            "publicKey": publicKey.base64EncodedString(),
        ]
        if let existing = try JSONSerialization.jsonObject(with: Data(contentsOf: pendingOwner)) as? [String: String] {
            owner["operationID"] = existing["operationID"]
        }
        let encoded = try JSONSerialization.data(withJSONObject: owner)
        try encoded.write(to: pendingOwner, options: .atomic)
    }

    @discardableResult
    func claimOperation(_ operationID: String) throws -> (handle: Data, publicKey: Data) {
        let parts = try validateStagedParts()
        guard var owner = try JSONSerialization.jsonObject(with: Data(contentsOf: pendingOwner)) as? [String: String] else {
            throw CompanionClientError.transport("staged phone key owner is malformed")
        }
        owner["operationID"] = operationID
        try JSONSerialization.data(withJSONObject: owner).write(to: pendingOwner, options: .atomic)
        return parts
    }

    func discard(ownedByOperation operationID: String) {
        guard let bytes = try? Data(contentsOf: pendingOwner),
              let owner = try? JSONSerialization.jsonObject(with: bytes) as? [String: String],
              owner["operationID"] == operationID else { return }
        discard()
    }

    @discardableResult
    func validateStagedParts() throws -> (handle: Data, publicKey: Data) {
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
        try validateKey(handle: handle, publicKey: publicKey)
        return (handle, publicKey)
    }

    #if RUNSPECIMEN_TEST_HOOKS
    func commit(ownedBy challengeId: String, publicKey: Data, failAfterFirstWrite: Bool = false) throws {
        let parts = try validateStagedParts()
        try validateOwnership(challengeId: challengeId, publicKey: publicKey, stagedPublicKey: parts.publicKey)
        try commitInternal(failAfterFirstWrite: failAfterFirstWrite, validatedParts: parts)
    }

    func commit(failAfterFirstWrite: Bool = false) throws {
        try commitInternal(failAfterFirstWrite: failAfterFirstWrite)
    }
    #else
    func commit(ownedBy challengeId: String, publicKey: Data) throws {
        let parts = try validateStagedParts()
        try validateOwnership(challengeId: challengeId, publicKey: publicKey, stagedPublicKey: parts.publicKey)
        try commitInternal(failAfterFirstWrite: false, validatedParts: parts)
    }

    func commit() throws {
        try commitInternal(failAfterFirstWrite: false)
    }
    #endif

    private func validateOwnership(challengeId: String, publicKey: Data, stagedPublicKey: Data) throws {
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
        guard stagedPublicKey == publicKey else {
            throw CompanionClientError.transport("staged phone key belongs to another challenge")
        }
    }

    /// One record. A failure after the next-file write leaves the previous generation.
    private func commitInternal(failAfterFirstWrite: Bool, validatedParts: (handle: Data, publicKey: Data)? = nil) throws {
        guard FileManager.default.fileExists(atPath: pendingHandle.path),
              FileManager.default.fileExists(atPath: pendingPublic.path)
        else {
            throw CompanionClientError.transport("phone key not staged (incomplete-stage)")
        }
        let (handle, publicKey) = try validatedParts ?? validateStagedParts()
        let previousGeneration: Int
        do { previousGeneration = try readRecord().generation }
        catch let error as CocoaError where error.code == .fileReadNoSuchFile { previousGeneration = 0 }
        let highestGeneration = max(previousGeneration, try reservedGeneration())
        guard highestGeneration < Int.max else { throw CompanionClientError.transport("phone key generation overflow") }
        let record = CustodyRecord(generation: highestGeneration + 1, handle: handle, publicKey: publicKey)
        let encoded = try JSONEncoder().encode(record)
        try Task.checkCancellation()
        try encoded.write(to: nextRecordURL, options: .atomic)
        if failAfterFirstWrite {
            throw CompanionClientError.transport("phone custody commit stopped after the first write")
        }
        try Task.checkCancellation()
        // Reserve before publishing custody. A failed publish may skip a number,
        // but revocation or a crash can never reissue an earlier generation.
        try reserveGeneration(record.generation)
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

    func committedGeneration() throws -> Int { try readRecord().generation }
    func committedHandle() throws -> Data { try readRecord().handle }
    func committedPublicKey() throws -> Data { try readRecord().publicKey }
    func stagedHandle() throws -> Data {
        try validateStagedParts().handle
    }
    func hasAnyStagedParts() -> Bool {
        [pendingHandle, pendingPublic, pendingOwner].contains { FileManager.default.fileExists(atPath: $0.path) }
    }

    func rotate(handle: Data, publicKey: Data) throws {
        try stage(handle: handle, publicKey: publicKey)
    }

    func revoke() throws {
        let generation: Int
        do { generation = try readRecord().generation }
        catch let error as CocoaError where error.code == .fileReadNoSuchFile { generation = 0 }
        let highestGeneration = max(generation, try reservedGeneration())
        if highestGeneration > 0 { try reserveGeneration(highestGeneration) }
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

    func hasStagedKey() -> Bool {
        FileManager.default.fileExists(atPath: pendingHandle.path) &&
        FileManager.default.fileExists(atPath: pendingPublic.path)
    }
    
    func stagedPublicKey() throws -> Data {
        guard hasStagedKey() else {
            throw CompanionClientError.transport("no staged key")
        }
        return try validateStagedParts().publicKey
    }

    private var pendingHandle: URL { directory.appendingPathComponent("phone-session-handle.pending") }
    private var pendingPublic: URL { directory.appendingPathComponent("phone-session-public.pending") }
    private var pendingOwner: URL { directory.appendingPathComponent("phone-session-owner.pending") }
    private var recordURL: URL { directory.appendingPathComponent("custody.json") }
    private var nextRecordURL: URL { directory.appendingPathComponent("custody-next.json") }

    private var generationURL: URL { directory.appendingPathComponent("custody-generation.json") }

    enum CounterRecoveryError: LocalizedError, Equatable {
        case damagedReservation
        case noTrustedRecovery
        var errorDescription: String? {
            switch self {
            case .damagedReservation:
                return "Saved phone key counter is damaged. Use Repair saved key counter; enrollment is paused to prevent generation reuse."
            case .noTrustedRecovery:
                return "No trustworthy counter recovery record is available. Export diagnostics and restore the original app data with support. The counter cannot safely be reset."
            }
        }
    }

    private var recoveryGenerationURL: URL { directory.appendingPathComponent("custody-generation-recovery.json") }

    private func readGeneration(_ url: URL) throws -> Int {
        let generation = try JSONDecoder().decode(Int.self, from: Data(contentsOf: url))
        guard generation > 0 else { throw CounterRecoveryError.damagedReservation }
        return generation
    }

    private func reservedGeneration() throws -> Int {
        let generation: Int
        do { generation = try readGeneration(generationURL) }
        catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            // Once recovery evidence exists, a missing primary is damage, not a
            // fresh installation. Require explicit authenticated repair.
            guard !FileManager.default.fileExists(atPath: recoveryGenerationURL.path) else {
                throw CounterRecoveryError.damagedReservation
            }
            return 0
        }
        catch { throw CounterRecoveryError.damagedReservation }
        // A recovery write can be ahead after a failed primary publication.
        do { return max(generation, try readGeneration(recoveryGenerationURL)) }
        catch let error as CocoaError where error.code == .fileReadNoSuchFile { return generation }
        catch { throw CounterRecoveryError.noTrustedRecovery }
    }

    private func reserveGeneration(_ generation: Int) throws {
        let encoded = try JSONEncoder().encode(generation)
        // This independent high-water record always leads the primary write and
        // survives custody revocation. It contains no private key material.
        try encoded.write(to: recoveryGenerationURL, options: .atomic)
        try encoded.write(to: generationURL, options: .atomic)
    }

    func checkGenerationReservation() throws { _ = try reservedGeneration() }

    func repairGenerationReservation() throws {
        let floor: Int
        do { floor = try readGeneration(recoveryGenerationURL) }
        catch { throw CounterRecoveryError.noTrustedRecovery }
        // Never lower a readable primary (including migrated legacy data).
        let primary: Int
        do { primary = try readGeneration(generationURL) }
        catch { primary = 0 }
        try Task.checkCancellation()
        try reserveGeneration(max(floor, primary))
    }

    private func readRecord() throws -> CustodyRecord {
        let record = try JSONDecoder().decode(CustodyRecord.self, from: Data(contentsOf: recordURL))
        guard record.generation > 0, !record.handle.isEmpty else {
            throw CompanionClientError.transport("phone custody record is malformed")
        }
        try validateKey(handle: record.handle, publicKey: record.publicKey)
        return record
    }
}

/// An operation owns its context until completion. Cancellation can invalidate
/// it from outside the serial crypto executor while a biometric prompt is open.
final class CryptoOperationContext: @unchecked Sendable {
    let context = LAContext()
    private let lock = NSLock()
    private var invalidated = false
    #if RUNSPECIMEN_TEST_HOOKS
    static var testDidInvalidate: (() -> Void)?
    #endif
    func invalidate() {
        lock.lock()
        guard !invalidated else { lock.unlock(); return }
        invalidated = true
        lock.unlock()
        context.invalidate()
        #if RUNSPECIMEN_TEST_HOOKS
        Self.testDidInvalidate?()
        #endif
    }
}

actor CryptoWorker {
    static let shared = CryptoWorker()

    /// Commit operations enforce cancellation before starting; once their
    /// durable write succeeds, cancellation cannot turn success into failure.
    func performCommit<T>(_ operation: @Sendable () throws -> T) throws -> T {
        try Task.checkCancellation()
        return try operation()
    }

    func perform<T>(_ operation: @Sendable () throws -> T) throws -> T {
        try Task.checkCancellation()
        do {
            let result = try operation()
            try Task.checkCancellation()
            return result
        } catch {
            try Task.checkCancellation()
            throw error
        }
    }

    nonisolated static func withContext<T>(_ operation: @escaping @Sendable (LAContext) throws -> T) async throws -> T {
        let owner = CryptoOperationContext()
        defer { owner.invalidate() }
        return try await withTaskCancellationHandler {
            try await shared.perform { try operation(owner.context) }
        } onCancel: {
            owner.invalidate()
        }
    }
}

struct LivePhoneSecureEnclaveSigner: PhoneChallengeSigning {
    private let operationID = UUID().uuidString
    var stage: PhoneKeyStage
    init(stage: PhoneKeyStage = PhoneKeyStage(directory: LivePhoneSecureEnclaveSigner.support)) {
        self.stage = stage
    }

    func signCommitted(message: Data) throws -> (publicKey: String, signature: String) {
        let context = LAContext()
        defer { context.invalidate() }
        return try signCommitted(message: message, context: context)
    }

    private func signCommitted(message: Data, context: LAContext) throws -> (publicKey: String, signature: String) {
        let token = try stage.committedHandle()
        let key = try SecureEnclave.P256.Signing.PrivateKey(dataRepresentation: token, authenticationContext: context)
        guard key.publicKey.x963Representation == (try stage.committedPublicKey()) else {
            throw CompanionClientError.transport("phone session key is not enrolled")
        }
        return (key.publicKey.x963Representation.base64EncodedString(), try key.signature(for: message).rawRepresentation.base64EncodedString())
    }

    func sign(message: Data) throws -> (publicKey: String, signature: String) {
        let context = LAContext()
        defer { context.invalidate() }
        return try sign(message: message, context: context)
    }

    private func sign(message: Data, context: LAContext) throws -> (publicKey: String, signature: String) {
        if stage.hasAnyStagedParts() {
            let parts = try stage.claimOperation(operationID)
            let key = try SecureEnclave.P256.Signing.PrivateKey(dataRepresentation: parts.handle, authenticationContext: context)
            return (key.publicKey.x963Representation.base64EncodedString(), try key.signature(for: message).rawRepresentation.base64EncodedString())
        }
        do { return try signCommitted(message: message, context: context) }
        catch let error as CocoaError where error.code == .fileReadNoSuchFile { }
        let key = try makeKey(context: context)
        try stage.stage(handle: key.dataRepresentation, publicKey: key.publicKey.x963Representation, challengeId: "", operationID: operationID)
        return (key.publicKey.x963Representation.base64EncodedString(), try key.signature(for: message).rawRepresentation.base64EncodedString())
    }

    private func makeKey(context: LAContext) throws -> SecureEnclave.P256.Signing.PrivateKey {
        var error: Unmanaged<CFError>?
        guard let access = SecAccessControlCreateWithFlags(kCFAllocatorDefault,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly, [.privateKeyUsage, .biometryCurrentSet], &error) else {
            throw CompanionClientError.transport("biometric access policy was refused")
        }
        return try SecureEnclave.P256.Signing.PrivateKey(accessControl: access, authenticationContext: context)
    }

    private func cleanupCancelledStage() async {
        // Cleanup gets its own uncancelled task and checks ownership on the same
        // worker that serializes creation, so it cannot erase a newer stage.
        _ = await Task.detached { [self] in
            try? await CryptoWorker.shared.perform { self.stage.discard(ownedByOperation: self.operationID) }
        }.value
    }

    func signAsync(message: Data) async throws -> (publicKey: String, signature: String) {
        do { return try await CryptoWorker.withContext { try self.sign(message: message, context: $0) } }
        catch {
            await cleanupCancelledStage()
            throw error
        }
    }

    func signCommittedAsync(message: Data) async throws -> (publicKey: String, signature: String) {
        try await CryptoWorker.withContext { try self.signCommitted(message: message, context: $0) }
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
        stage.discard(ownedByOperation: operationID)
    }

    func rotateEnrollment() throws {
        let context = LAContext()
        defer { context.invalidate() }
        try rotateEnrollment(context: context)
    }

    private func rotateEnrollment(context: LAContext) throws {
        let key = try makeKey(context: context)
        try stage.stage(handle: key.dataRepresentation, publicKey: key.publicKey.x963Representation, challengeId: "", operationID: operationID)
    }

    func rotateEnrollmentAsync() async throws {
        do { try await CryptoWorker.withContext { try self.rotateEnrollment(context: $0) } }
        catch { await cleanupCancelledStage(); throw error }
    }

    func revokeEnrollment() throws {
        try stage.revoke()
    }

    static var support: URL {
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
