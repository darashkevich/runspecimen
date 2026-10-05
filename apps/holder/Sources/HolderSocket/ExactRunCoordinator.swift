import Foundation

/// One issued exact run. Continue uses this value and does not issue again.
public struct RetainedExactRun: Equatable {
    public var nonce: String
    public var bound: Data
    public var policy: String
    public var generation: Int
    public var keyGeneration: Int
    public var expiry: Int
    public var enrolledMacPublicKey: Data

    public init(
        nonce: String,
        bound: Data,
        policy: String,
        generation: Int,
        keyGeneration: Int,
        expiry: Int,
        enrolledMacPublicKey: Data
    ) {
        self.nonce = nonce
        self.bound = bound
        self.policy = policy
        self.generation = generation
        self.keyGeneration = keyGeneration
        self.expiry = expiry
        self.enrolledMacPublicKey = enrolledMacPublicKey
    }
}

public struct ExactRunLiveSession: Equatable {
    public var policy: String
    public var generation: Int
    public var keyGeneration: Int

    public init(policy: String, generation: Int, keyGeneration: Int) {
        self.policy = policy
        self.generation = generation
        self.keyGeneration = keyGeneration
    }
}

/// The phone response is accepted only when it names the retained nonce.
public struct BoundPhoneExactSignature: Equatable {
    public var nonce: String
    public var signature: String

    public init(nonce: String, signature: String) {
        self.nonce = nonce
        self.signature = signature
    }
}

public protocol ExactRunTransport {
    func issue(
        policy: String,
        workspace: String,
        files: [[String]],
        binding: [String: Any]
    ) async throws -> RetainedExactRun
    func liveSession() async throws -> ExactRunLiveSession
    func authorize(nonce: String, policy: String, signatures: [String: String]) async throws
    func execute(nonce: String, signatures: [String: String]) async throws -> String
}

public protocol ExactRunPhoneMailbox {
    func publish(run: RetainedExactRun) async throws
    func collect(nonce: String) async throws -> BoundPhoneExactSignature
}

public protocol ReloadedMacSigner {
    func sign(message: Data, enrolledPublicKey: Data) throws -> Data
}

public enum ExactRunCoordinatorError: Error, Equatable {
    case missingPrepare
    case expired
    case generationChanged
    case policyRefused
    case phoneNotBound
    case missingPhone
    case missingMacKey
}

/// Prepare displays and sends one challenge. Continue accepts and executes that same challenge.
public final class ExactRunCoordinator: @unchecked Sendable {
    public private(set) var issueCount = 0
    public private(set) var displayedBound: Data?
    public private(set) var publishedNonce: String?
    private var retained: RetainedExactRun?

    public init() {}

    public func prepare(
        policy: String,
        workspace: String,
        files: [[String]],
        binding: [String: Any],
        transport: any ExactRunTransport,
        mailbox: any ExactRunPhoneMailbox
    ) async throws -> RetainedExactRun {
        let trimmed = policy.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed == "local" || trimmed == "companion" || trimmed == "dual" else {
            throw ExactRunCoordinatorError.policyRefused
        }
        let issued = try await transport.issue(
            policy: trimmed,
            workspace: workspace,
            files: files,
            binding: binding
        )
        guard issued.policy == trimmed, !issued.nonce.isEmpty, !issued.bound.isEmpty else {
            throw ExactRunCoordinatorError.policyRefused
        }
        issueCount += 1
        retained = issued
        displayedBound = issued.bound
        publishedNonce = nil
        if trimmed == "companion" || trimmed == "dual" {
            try await mailbox.publish(run: issued)
            publishedNonce = issued.nonce
        }
        return issued
    }

    /// Authorize and execute the retained challenge. This method does not call issue.
    public func continueRun(
        now: Int,
        transport: any ExactRunTransport,
        mailbox: any ExactRunPhoneMailbox,
        signer: any ReloadedMacSigner
    ) async throws -> String {
        let prepared = retained
        let issuesBefore = issueCount
        guard let prepared else { throw ExactRunCoordinatorError.missingPrepare }
        if now > prepared.expiry { throw ExactRunCoordinatorError.expired }
        let live = try await transport.liveSession()
        if live.policy != prepared.policy { throw ExactRunCoordinatorError.policyRefused }
        if live.generation != prepared.generation || live.keyGeneration != prepared.keyGeneration {
            throw ExactRunCoordinatorError.generationChanged
        }
        var signatures: [String: String] = [:]
        if prepared.policy == "local" || prepared.policy == "dual" {
            guard !prepared.enrolledMacPublicKey.isEmpty else {
                throw ExactRunCoordinatorError.missingMacKey
            }
            let raw = try signer.sign(message: prepared.bound, enrolledPublicKey: prepared.enrolledMacPublicKey)
            signatures["mac"] = raw.base64EncodedString()
        }
        if prepared.policy == "companion" || prepared.policy == "dual" {
            let response = try await mailbox.collect(nonce: prepared.nonce)
            guard response.nonce == prepared.nonce else { throw ExactRunCoordinatorError.phoneNotBound }
            let signature = response.signature.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !signature.isEmpty else { throw ExactRunCoordinatorError.missingPhone }
            signatures["phone"] = signature
        }
        if issueCount != issuesBefore { throw ExactRunCoordinatorError.policyRefused }
        try await transport.authorize(nonce: prepared.nonce, policy: prepared.policy, signatures: signatures)
        return try await transport.execute(nonce: prepared.nonce, signatures: signatures)
    }
}

public struct HeldSessionKey {
    public let role: String
    public let publicKey: Data
    public let accessPolicy: String
    public let sign: (Data) throws -> Data

    public init(role: String, publicKey: Data, accessPolicy: String, sign: @escaping (Data) throws -> Data) {
        self.role = role
        self.publicKey = publicKey
        self.accessPolicy = accessPolicy
        self.sign = sign
    }
}

public protocol CommittedCustodySource {
    func committedPublicKey() throws -> Data
    func sign(message: Data) throws -> Data
}

public enum CustodyReloadError: Error, Equatable {
    case missingCustody
    case identityMismatch
    case policyRefused
}

/// In-memory keys win. After restart the committed record signs, and only when it is the enrolled key.
public final class ReloadingSessionCustody: @unchecked Sendable {
    private var memory: [String: HeldSessionKey] = [:]
    private let source: any CommittedCustodySource
    private let lock = NSLock()
    public static let eachSignature = "biometry-current-set-on-each-signature"

    public init(source: any CommittedCustodySource) {
        self.source = source
    }

    public func keep(_ key: HeldSessionKey) {
        lock.lock()
        memory[key.role] = key
        lock.unlock()
    }

    public func sign(role: String, message: Data, enrolledPublicKey: Data) throws -> Data {
        guard !enrolledPublicKey.isEmpty else { throw CustodyReloadError.identityMismatch }
        lock.lock()
        let held = memory[role]
        lock.unlock()
        if let held {
            guard held.publicKey == enrolledPublicKey else { throw CustodyReloadError.identityMismatch }
            guard held.accessPolicy == Self.eachSignature else { throw CustodyReloadError.policyRefused }
            return try held.sign(message)
        }
        let committed: Data
        do {
            committed = try source.committedPublicKey()
        } catch {
            throw CustodyReloadError.missingCustody
        }
        guard committed == enrolledPublicKey else { throw CustodyReloadError.identityMismatch }
        return try source.sign(message: message)
    }
}
