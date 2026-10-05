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

public struct ExactRunInputs: Equatable, Sendable {
    public var policy: String
    public var workspace: String
    public var scriptDigest: String
    public var contractHash: String
    public var executable: String

    public init(policy: String, workspace: String, scriptDigest: String, contractHash: String, executable: String) {
        self.policy = policy
        self.workspace = workspace
        self.scriptDigest = scriptDigest
        self.contractHash = contractHash
        self.executable = executable
    }
}

public enum ExactRunCoordinatorError: Error, Equatable {
    case missingPrepare
    case expired
    case generationChanged
    case policyRefused
    case phoneNotBound
    case missingPhone
    case missingMacKey
    case busy
    case inputsChanged
    /// Authorize already consumed the nonce. The uncertain lease stays held. This is not permission to execute or to consume again.
    case leaseUncertain
}

/// Prepare displays and sends one challenge. Continue accepts and executes that same challenge.
/// The actor serializes Prepare and Continue. A changed signed input drops the pending request.
public actor ExactRunCoordinator {
    public private(set) var issueCount = 0
    public private(set) var displayedBound: Data?
    public private(set) var publishedNonce: String?
    private var retained: RetainedExactRun?
    private var retainedInputs: ExactRunInputs?
    private var busy = false
    private var epoch = 0
    /// Nonces whose authorize succeeded and whose execute did not. Invalidation does not release these.
    private var uncertainNonces: Set<String> = []

    public init() {}

    public func invalidate() {
        epoch += 1
        retained = nil
        retainedInputs = nil
        displayedBound = nil
        publishedNonce = nil
    }

    public func prepare(
        policy: String,
        workspace: String,
        files: [[String]],
        binding: [String: Any],
        inputs: ExactRunInputs,
        transport: any ExactRunTransport,
        mailbox: any ExactRunPhoneMailbox
    ) async throws -> RetainedExactRun {
        guard !busy else { throw ExactRunCoordinatorError.busy }
        busy = true
        defer { busy = false }
        let trimmed = policy.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed == "local" || trimmed == "companion" || trimmed == "dual" else {
            throw ExactRunCoordinatorError.policyRefused
        }
        guard inputs.policy == trimmed else { throw ExactRunCoordinatorError.inputsChanged }
        let epochAtStart = epoch
        let issued = try await transport.issue(
            policy: trimmed,
            workspace: workspace,
            files: files,
            binding: binding
        )
        guard epoch == epochAtStart else { throw ExactRunCoordinatorError.inputsChanged }
        guard issued.policy == trimmed, !issued.nonce.isEmpty, !issued.bound.isEmpty else {
            throw ExactRunCoordinatorError.policyRefused
        }
        issueCount += 1
        retained = issued
        retainedInputs = inputs
        displayedBound = issued.bound
        publishedNonce = nil
        if trimmed == "companion" || trimmed == "dual" {
            do {
                try await mailbox.publish(run: issued)
            } catch {
                retained = nil
                retainedInputs = nil
                displayedBound = nil
                publishedNonce = nil
                throw error
            }
            guard epoch == epochAtStart, retained?.nonce == issued.nonce, retainedInputs == inputs else {
                retained = nil
                retainedInputs = nil
                displayedBound = nil
                publishedNonce = nil
                throw ExactRunCoordinatorError.inputsChanged
            }
            publishedNonce = issued.nonce
        }
        guard epoch == epochAtStart, retained?.nonce == issued.nonce else {
            throw ExactRunCoordinatorError.inputsChanged
        }
        return issued
    }

    /// Authorize and execute the retained challenge. This method does not call issue.
    public func continueRun(
        now: Int,
        inputs: ExactRunInputs,
        transport: any ExactRunTransport,
        mailbox: any ExactRunPhoneMailbox,
        signer: any ReloadedMacSigner
    ) async throws -> String {
        guard !busy else { throw ExactRunCoordinatorError.busy }
        busy = true
        defer { busy = false }
        guard let prepared = retained else { throw ExactRunCoordinatorError.missingPrepare }
        if uncertainNonces.contains(prepared.nonce) { throw ExactRunCoordinatorError.leaseUncertain }
        guard retainedInputs == inputs else { throw ExactRunCoordinatorError.inputsChanged }
        let epochAtStart = epoch
        let nonce = prepared.nonce
        let bound = prepared.bound
        if now > prepared.expiry { throw ExactRunCoordinatorError.expired }
        let live = try await transport.liveSession()
        try requireSameRequest(epochAtStart: epochAtStart, nonce: nonce, inputs: inputs)
        if live.policy != prepared.policy { throw ExactRunCoordinatorError.policyRefused }
        if live.generation != prepared.generation || live.keyGeneration != prepared.keyGeneration {
            throw ExactRunCoordinatorError.generationChanged
        }
        var signatures: [String: String] = [:]
        if prepared.policy == "local" || prepared.policy == "dual" {
            guard !prepared.enrolledMacPublicKey.isEmpty else {
                throw ExactRunCoordinatorError.missingMacKey
            }
            let raw = try signer.sign(message: bound, enrolledPublicKey: prepared.enrolledMacPublicKey)
            try requireSameRequest(epochAtStart: epochAtStart, nonce: nonce, inputs: inputs)
            signatures["mac"] = raw.base64EncodedString()
        }
        if prepared.policy == "companion" || prepared.policy == "dual" {
            let response = try await mailbox.collect(nonce: nonce)
            try requireSameRequest(epochAtStart: epochAtStart, nonce: nonce, inputs: inputs)
            guard response.nonce == nonce else { throw ExactRunCoordinatorError.phoneNotBound }
            let signature = response.signature.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !signature.isEmpty else { throw ExactRunCoordinatorError.missingPhone }
            signatures["phone"] = signature
        }
        try requireSameRequest(epochAtStart: epochAtStart, nonce: nonce, inputs: inputs)
        try await transport.authorize(nonce: nonce, policy: prepared.policy, signatures: signatures)
        if epoch != epochAtStart || retained?.nonce != nonce || retainedInputs != inputs {
            uncertainNonces.insert(nonce)
            throw ExactRunCoordinatorError.leaseUncertain
        }
        return try await transport.execute(nonce: nonce, signatures: signatures)
    }

    private func requireSameRequest(epochAtStart: Int, nonce: String, inputs: ExactRunInputs) throws {
        guard epoch == epochAtStart, retained?.nonce == nonce, retained?.bound != nil, retainedInputs == inputs else {
            throw ExactRunCoordinatorError.inputsChanged
        }
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
public final class ReloadingSessionCustody {
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
