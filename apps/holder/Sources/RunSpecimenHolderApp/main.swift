import AppKit
import CryptoKit
import Darwin
import Foundation
import LocalAuthentication
import ServiceManagement
import SwiftUI

/// Separate Developer ID product. Registers an embedded SMAppService.daemon.
/// Does not modify the Mac App Store app. Root/admin can still defeat the holder.

@main
struct RunSpecimenHolderApp: App {
    @State private var statusText = "Starting…"
    @State private var detail = ""

    private let daemonPlist = "com.darashkevich.runspecimen.holder.daemon.plist"
    private let custody = UserSessionKeyCustody()
    private let holderClient = HolderSocketClient()
    private let exactRuns = ExactRunCoordinator()
    @State private var callerId = ""
    @State private var callerSecret = ""
    @State private var companionURL = ""
    @State private var pairingToken = ""
    @State private var exactPolicy = "local"
    @State private var exactWorkspace = ""
    @State private var exactScript = ""
    @State private var exactExecutable = ""
    @State private var pendingPhone: IssuedDeviceChallenge?

    var body: some Scene {
        WindowGroup("RunSpecimen Holder") {
            VStack(alignment: .leading, spacing: 12) {
                Text("RunSpecimen Holder")
                    .font(.title)
                Text(statusText)
                    .font(.headline)
                Text(detail)
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                Text("Mechanism: SMAppService.daemon. State is root-owned. A same-user process must not rewrite enrollment, policy, nonces, or leases. Administrator or root can still defeat this holder. This is not human-only execution and not Store parity. An origin string is not production trust. E2 is not closed. A biometric press does not finish missing implementation. The local button reaches the holder over authenticated IPC. The Observe screen returns the phone signature. A root-owned install is still unbuilt.")
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                TextField("Holder caller id", text: $callerId)
                TextField("Holder caller secret", text: $callerSecret)
                TextField("Observe companion URL", text: $companionURL)
                TextField("Observe pairing token", text: $pairingToken)
                TextField("Exact-run policy: local, companion, or dual", text: $exactPolicy)
                TextField("Exact-run workspace", text: $exactWorkspace)
                TextField("Exact-run script path", text: $exactScript)
                TextField("Exact-run executable", text: $exactExecutable)
                Text("Phone signature is collected for the prepared challenge. Continue does not issue another nonce.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Enroll with Secure Enclave") {
                    Task { await enrollLocalFromPerson() }
                }
                Button("Prepare exact run") {
                    Task { await prepareExactRunFromPerson() }
                }
                Button("Continue exact run") {
                    Task { await continueExactRunFromPerson() }
                }
                Button("Enroll paired phone") {
                    Task { await enrollPhoneFromPerson() }
                }
                Button("Accept phone signature") {
                    Task { await acceptPhoneFromPerson() }
                }
                Button("Cancel phone challenge") {
                    Task { await cancelPhoneFromPerson() }
                }
            }
            .padding(24)
            .frame(minWidth: 520, minHeight: 280)
            .onAppear(perform: registerDaemon)
        }
    }

    /// The local control creates the OS key and enrolls it over authenticated IPC.
    /// The Secure Enclave constructor runs only inside this button action.
    private func enrollLocalFromPerson() async {
        let maker = LiveSecureEnclaveKeyMaker()
        do {
            let held = try maker.stageSessionKey()
            let client = try authenticatedClient()
            let issued = try await client.issueChallenge(role: "mac")
            let signature = try held.sign(issued.bound)
            let receipt = try await client.enrollLocal(
                publicKey: held.publicKey,
                accessPolicy: held.accessPolicy,
                issued: issued,
                signature: signature
            )
            try maker.commitStagedSession()
            custody.keep(held)
            statusText = "Holder verified the local key over IPC. E2 is not closed."
            detail = "\(receipt). access=\(held.accessPolicy). A biometric press does not finish missing implementation. A root-owned install is still unbuilt."
        } catch {
            maker.discardStagedSession()
            statusText = "Secure Enclave enrollment was not completed"
            detail = "\(error)"
        }
    }

    /// Issue one snapshot challenge, show its bound bytes, and send that same challenge to the phone.
    private func prepareExactRunFromPerson() async {
        do {
            let prepared = try await exactRuns.prepare(
                policy: exactPolicy,
                workspace: exactWorkspace.trimmingCharacters(in: .whitespacesAndNewlines),
                files: try exactRunFiles(),
                binding: try exactRunBinding(),
                transport: try appExactTransport(),
                mailbox: appExactMailbox()
            )
            statusText = "Exact run is prepared. Continue uses this challenge."
            detail = "nonce=\(prepared.nonce) policy=\(prepared.policy) generation=\(prepared.generation) expiry=\(prepared.expiry) bound=\(prepared.bound.base64EncodedString())"
        } catch {
            statusText = "Exact run was not prepared."
            detail = "\(error)"
        }
    }

    /// Accept the phone response for the prepared challenge and execute it. This does not issue again.
    private func continueExactRunFromPerson() async {
        do {
            let executed = try await exactRuns.continueRun(
                now: Int(Date().timeIntervalSince1970),
                transport: try appExactTransport(),
                mailbox: appExactMailbox(),
                signer: custody
            )
            statusText = "Exact run reached snapshot-bound execute. Installed admission is still undecided."
            detail = "\(executed). run_integration_complete is false. A press does not admit a Secure Enclave key."
        } catch {
            statusText = "Exact run did not reach snapshot-bound execute."
            detail = "\(error)"
        }
    }

    private func exactRunFiles() throws -> [[String]] {
        let script = exactScript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !script.isEmpty else { throw HolderEnrollmentError.policyRefused }
        let scriptData = try Data(contentsOf: URL(fileURLWithPath: script))
        let digest = SHA256.hash(data: scriptData).map { String(format: "%02x", $0) }.joined()
        return [[script, digest]]
    }

    private func exactRunBinding() throws -> [String: Any] {
        let policy = exactPolicy.trimmingCharacters(in: .whitespacesAndNewlines)
        let workspace = exactWorkspace.trimmingCharacters(in: .whitespacesAndNewlines)
        let script = exactScript.trimmingCharacters(in: .whitespacesAndNewlines)
        let executable = exactExecutable.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !workspace.isEmpty, !script.isEmpty, !executable.isEmpty else {
            throw HolderEnrollmentError.policyRefused
        }
        return [
            "contract_hash": String(repeating: "c", count: 64),
            "workspace": workspace,
            "argv": [script] as [Any],
            "executable": script,
            "policy": policy,
            "cwd": workspace,
            "launch_argv": [executable, script] as [Any],
            "bounds": [
                "wall_timeout_sec": 10,
                "stdout_max_bytes": 65536,
                "stderr_max_bytes": 65536,
            ] as [String: Any],
        ]
    }

    private func appExactTransport() throws -> AppExactRunTransport {
        AppExactRunTransport(client: try authenticatedClient())
    }

    private func appExactMailbox() -> AppExactRunMailbox {
        AppExactRunMailbox(baseURL: companionURL, pairingToken: pairingToken)
    }

    /// Publishes a holder-issued challenge to RunSpecimenObserve. It does not enroll.
    private func enrollPhoneFromPerson() async {
        do {
            let client = try authenticatedClient()
            let issued = try await client.issuePhoneChallenge()
            try await ObserveMailbox.publish(
                issued: issued,
                baseURL: companionURL,
                pairingToken: pairingToken
            )
            pendingPhone = issued
            statusText = "Paired phone challenge is published to RunSpecimenObserve."
            detail = "challenge=\(issued.challenge.count) bytes on /v1/phone-peer-challenge. A local key was not created. The signature is accepted only after P-256 verification and the challenge is consumed. E2 is not closed. A root-owned install is still unbuilt."
        } catch {
            statusText = "Paired phone enrollment was not completed"
            detail = "\(error)"
        }
    }

    private func acceptPhoneFromPerson() async {
        do {
            guard let issued = pendingPhone else { throw HolderEnrollmentError.staleChallenge }
            let submission = try await ObserveMailbox.collect(baseURL: companionURL, pairingToken: pairingToken)
            guard submission.challenge == issued.challengeBase64 else {
                throw HolderEnrollmentError.tamperedChallenge
            }
            let receipt = try await authenticatedClient().submit(
                role: "phone",
                publicKeyBase64: submission.publicKey,
                issued: issued,
                signatureBase64: submission.signature
            )
            let prepared = try await authenticatedClient().preparePhoneReceipt(challengeId: issued.nonce)
            guard let enrolledMac = Data(base64Encoded: prepared.macPublicKey) else {
                throw HolderEnrollmentError.identityMismatch
            }
            let macSignature = try custody.sign(role: "mac", message: prepared.receipt, enrolledPublicKey: enrolledMac)
            let sealed = try await authenticatedClient().sealPhoneReceipt(
                challengeId: issued.nonce,
                signatureBase64: macSignature.base64EncodedString()
            )
            try await ObserveMailbox.recordHolderReceipt(
                sealed,
                baseURL: companionURL,
                pairingToken: pairingToken
            )
            pendingPhone = nil
            statusText = "Holder sealed a phone receipt. The mailbox flag is not enrollment. E2 is not closed."
            detail = "\(receipt). mac_public_key=\(sealed.macPublicKey)"
        } catch HolderEnrollmentError.staleChallenge {
            try? await authenticatedClient().cancel(role: "phone")
            pendingPhone = nil
            statusText = "Phone challenge was invalidated and was not enrolled."
            detail = "The mailbox challenge was cleared before holder verification."
        } catch {
            statusText = "Paired phone enrollment was not completed"
            detail = "\(error)"
        }
    }

    private func cancelPhoneFromPerson() async {
        do {
            guard let issued = pendingPhone else { throw HolderEnrollmentError.staleChallenge }
            try await authenticatedClient().cancel(role: "phone")
            pendingPhone = nil
            statusText = "Phone challenge was cancelled. It was not enrolled."
            detail = "nonce=\(issued.nonce)"
        } catch {
            statusText = "Phone challenge was not cancelled"
            detail = "\(error)"
        }
    }

    private func authenticatedClient() throws -> HolderSocketClient {
        try holderClient.authenticate(callerId: callerId, callerSecret: callerSecret)
        return holderClient
    }

    private func registerDaemon() {
        let service = SMAppService.daemon(plistName: daemonPlist)
        do {
            try service.register()
        } catch {
            let ns = error as NSError
            // kSMErrorAlreadyRegistered ~= already present
            if !(ns.domain == "SMAppServiceErrorDomain" && ns.code == 1) {
                statusText = "Registration error"
                detail = "\(error)"
                return
            }
        }
        switch service.status {
        case .enabled:
            statusText = "Daemon enabled"
            detail = "SMAppService status: enabled\nBundle: \(Bundle.main.bundleIdentifier ?? "?")"
        case .requiresApproval:
            statusText = "Waiting for System Settings approval"
            detail = """
            Open System Settings → General → Login Items & Extensions.
            Allow “RunSpecimen Holder” Background Items (or Login Items).
            An admin password prompt may appear — enter it yourself; the agent will not.
            Bundle: \(Bundle.main.bundleIdentifier ?? "?")
            """
        case .notRegistered:
            statusText = "Not registered"
            detail = "SMAppService status: notRegistered"
        case .notFound:
            statusText = "Daemon plist not found in bundle"
            detail = "Expected Contents/Library/LaunchDaemons/\(daemonPlist)"
        @unknown default:
            statusText = "Unknown SMAppService status"
            detail = "raw=\(service.status.rawValue)"
        }
    }
}

enum BiometricAccessPolicy {
    /// Each later signature with the live key requires the current biometric set.
    /// Unattended code does not evaluate this policy and does not prompt.
    static let eachSignature = "biometry-current-set-on-each-signature"
}

struct SessionHeldKey {
    let role: String
    let publicKey: Data
    let accessPolicy: String
    let sign: (Data) throws -> Data
}

final class UserSessionKeyCustody: ReloadedMacSigner {
    private let reloading = ReloadingSessionCustody(source: LiveCommittedMacKey())

    func keep(_ key: SessionHeldKey) {
        reloading.keep(HeldSessionKey(
            role: key.role,
            publicKey: key.publicKey,
            accessPolicy: key.accessPolicy,
            sign: key.sign
        ))
    }

    func sign(message: Data, enrolledPublicKey: Data) throws -> Data {
        try sign(role: "mac", message: message, enrolledPublicKey: enrolledPublicKey)
    }

    func sign(role: String, message: Data, enrolledPublicKey: Data) throws -> Data {
        do {
            return try reloading.sign(role: role, message: message, enrolledPublicKey: enrolledPublicKey)
        } catch CustodyReloadError.missingCustody {
            throw HolderEnrollmentError.missingCustody
        } catch CustodyReloadError.identityMismatch {
            throw HolderEnrollmentError.identityMismatch
        } catch CustodyReloadError.policyRefused {
            throw HolderEnrollmentError.policyRefused
        }
    }
}

/// Reloads the committed session file. The Secure Enclave prompt is on this sign call, not on launch.
struct LiveCommittedMacKey: CommittedCustodySource {
    func committedPublicKey() throws -> Data {
        try LiveSecureEnclaveKeyMaker().reloadPublicKey()
    }

    func sign(message: Data) throws -> Data {
        try LiveSecureEnclaveKeyMaker().reloadAndSign(message)
    }
}

struct AppExactRunTransport: ExactRunTransport {
    let client: HolderSocketClient

    func issue(
        policy: String,
        workspace: String,
        files: [[String]],
        binding: [String: Any]
    ) async throws -> RetainedExactRun {
        try await client.issueSnapshotExactRun(
            policy: policy,
            workspace: workspace,
            files: files,
            binding: binding
        )
    }

    func liveSession() async throws -> ExactRunLiveSession {
        try await client.exactRunLiveSession()
    }

    func authorize(nonce: String, policy: String, signatures: [String: String]) async throws {
        try await client.authorizeSnapshotExactRun(nonce: nonce, policy: policy, signatures: signatures)
    }

    func execute(nonce: String, signatures: [String: String]) async throws -> String {
        try await client.executeSnapshotExactRun(nonce: nonce, signatures: signatures)
    }
}

struct AppExactRunMailbox: ExactRunPhoneMailbox {
    let baseURL: String
    let pairingToken: String

    func publish(run: RetainedExactRun) async throws {
        try await ObserveMailbox.publishExactRun(run, baseURL: baseURL, pairingToken: pairingToken)
    }

    func collect(nonce: String) async throws -> BoundPhoneExactSignature {
        try await ObserveMailbox.collectExactRun(nonce: nonce, baseURL: baseURL, pairingToken: pairingToken)
    }
}

protocol HolderSecureEnclaveKeyMaking {
    func makeSessionKey() throws -> SessionHeldKey
}

struct LiveSecureEnclaveKeyMaker: HolderSecureEnclaveKeyMaking {
    /// Stages a sealed representation under Application Support. That file is not
    /// the Keychain and not the Secure Enclave. Commit happens only after the
    /// holder accepts the enrollment.
    func stageSessionKey() throws -> SessionHeldKey {
        let created = try createSessionKey()
        try StagedCustodyFiles(directory: Self.support).stage(
            handle: created.representation,
            publicKey: created.held.publicKey
        )
        return created.held
    }

    func makeSessionKey() throws -> SessionHeldKey {
        try createSessionKey().held
    }

    private func createSessionKey() throws -> (held: SessionHeldKey, representation: Data) {
        var error: Unmanaged<CFError>?
        guard let access = SecAccessControlCreateWithFlags(
            kCFAllocatorDefault,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            [.privateKeyUsage, .biometryCurrentSet],
            &error
        ) else {
            throw HolderEnrollmentError.policyRefused
        }
        let key = try SecureEnclave.P256.Signing.PrivateKey(
            accessControl: access,
            authenticationContext: LAContext()
        )
        let publicKey = key.publicKey.x963Representation
        let held = SessionHeldKey(
            role: "mac",
            publicKey: publicKey,
            accessPolicy: BiometricAccessPolicy.eachSignature,
            sign: { message in
                try key.signature(for: message).rawRepresentation
            }
        )
        return (held, key.dataRepresentation)
    }

    func commitStagedSession() throws {
        try StagedCustodyFiles(directory: Self.support).commit()
    }

    func discardStagedSession() {
        StagedCustodyFiles(directory: Self.support).discard()
    }

    func reloadPublicKey() throws -> Data {
        try StagedCustodyFiles(directory: Self.support).committedPublicKey()
    }

    /// Loads the sealed Application Support representation and signs. The prompt
    /// is on this call. The file is not the Keychain store.
    func reloadAndSign(_ message: Data) throws -> Data {
        let token = try StagedCustodyFiles(directory: Self.support).committedHandle()
        let key = try SecureEnclave.P256.Signing.PrivateKey(dataRepresentation: token)
        return try key.signature(for: message).rawRepresentation
    }

    private static var support: URL {
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let directory = root.appendingPathComponent("RunSpecimenHolder", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }
}

enum HolderEnrollmentError: Error {
    case emptyKey
    case policyRefused
    case missingCustody
    case identityMismatch
    case localKeyIsNotPhone
    case missingCaller
    case ipcFailed
    case staleChallenge
    case tamperedChallenge
    case observeUnavailable
}


enum ObserveMailbox {
    static func publish(issued: IssuedDeviceChallenge, baseURL: String, pairingToken: String) async throws {
        let payload: [String: Any] = [
            "challenge_id": issued.nonce,
            "generation": issued.generation,
            "holder_id": issued.holderId,
            "challenge": issued.challengeBase64,
            "expiry": issued.expiry,
            "role": "phone",
        ]
        _ = try await request(baseURL: baseURL, pairingToken: pairingToken, path: "/v1/phone-peer-challenge", method: "POST", payload: payload)
    }

    static func publishExactRun(_ run: RetainedExactRun, baseURL: String, pairingToken: String) async throws {
        let payload: [String: Any] = [
            "challenge_id": run.nonce,
            "bound": run.bound.base64EncodedString(),
            "policy": run.policy,
            "generation": run.generation,
            "key_generation": run.keyGeneration,
            "expiry": run.expiry,
        ]
        _ = try await request(baseURL: baseURL, pairingToken: pairingToken, path: "/v1/exact-peer-challenge", method: "POST", payload: payload)
    }

    static func collectExactRun(nonce: String, baseURL: String, pairingToken: String) async throws -> BoundPhoneExactSignature {
        let body = try await request(baseURL: baseURL, pairingToken: pairingToken, path: "/v1/exact-peer-signature", method: "GET", payload: nil)
        guard
            let returned = body["challenge_id"] as? String,
            let signature = body["signature"] as? String,
            returned == nonce
        else { throw HolderEnrollmentError.tamperedChallenge }
        return BoundPhoneExactSignature(nonce: returned, signature: signature)
    }

    static func collect(baseURL: String, pairingToken: String) async throws -> (challenge: String, publicKey: String, signature: String) {
        let body = try await request(baseURL: baseURL, pairingToken: pairingToken, path: "/v1/phone-peer-signature", method: "GET", payload: nil)
        guard
            let challenge = body["challenge"] as? String,
            let publicKey = body["public_key"] as? String,
            let signature = body["signature"] as? String,
            body["verified"] as? Bool == false
        else { throw HolderEnrollmentError.staleChallenge }
        return (challenge, publicKey, signature)
    }

    static func recordHolderReceipt(
        _ sealed: SealedPhoneReceipt,
        baseURL: String,
        pairingToken: String
    ) async throws {
        let payload: [String: Any] = [
            "challenge_id": sealed.challengeId,
            "receipt": sealed.receipt,
            "signature": sealed.signature,
            "mac_public_key": sealed.macPublicKey,
            "phone_fingerprint": sealed.phoneFingerprint,
            "holder_id": sealed.holderId,
            "generation": sealed.generation,
            "outcome": sealed.outcome,
        ]
        let body = try await request(
            baseURL: baseURL,
            pairingToken: pairingToken,
            path: "/v1/phone-peer-verification",
            method: "POST",
            payload: payload
        )
        guard body["accepted"] as? Bool == true,
              body["verified"] as? Bool == false,
              body["enrolled"] as? Bool == false
        else {
            throw HolderEnrollmentError.observeUnavailable
        }
    }

    private static func request(
        baseURL: String,
        pairingToken: String,
        path: String,
        method: String,
        payload: [String: Any]?
    ) async throws -> [String: Any] {
        let root = baseURL.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard pairingToken.count >= 16, let url = URL(string: root + path) else {
            throw HolderEnrollmentError.observeUnavailable
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("Bearer \(pairingToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let payload {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        request.timeoutInterval = 5
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw HolderEnrollmentError.observeUnavailable
        }
        if http.statusCode == 409 { throw HolderEnrollmentError.staleChallenge }
        guard (200 ..< 300).contains(http.statusCode),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { throw HolderEnrollmentError.observeUnavailable }
        return object
    }
}

