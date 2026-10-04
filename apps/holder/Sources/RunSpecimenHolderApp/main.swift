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
    @State private var callerId = ""
    @State private var callerSecret = ""
    @State private var companionURL = ""
    @State private var pairingToken = ""
    @State private var exactPayload = ""
    @State private var exactLaunch = ""
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
                TextField("Exact-run payload digest", text: $exactPayload)
                TextField("Exact-run launch argv", text: $exactLaunch)
                Button("Enroll with Secure Enclave") {
                    Task { await enrollLocalFromPerson() }
                }
                Button("Sign with session key") {
                    Task { await signReloadedFromPerson() }
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

    /// A digest field is not a snapshot-bound run. This control does not sign.
    private func signReloadedFromPerson() async {
        statusText = "Exact run is not snapshot-bound from this control. E2 is not closed."
        detail = "A digest and launch string do not reach consume or execute. A biometric press does not finish missing implementation."
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
            try await ObserveMailbox.recordHolderVerification(
                challengeId: issued.nonce,
                baseURL: companionURL,
                pairingToken: pairingToken
            )
            pendingPhone = nil
            statusText = "Holder verified the phone signature and consumed the challenge. E2 is not closed."
            detail = receipt
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

final class UserSessionKeyCustody {
    private var keys: [String: SessionHeldKey] = [:]

    func keep(_ key: SessionHeldKey) {
        keys[key.role] = key
    }

    func sign(role: String, message: Data) throws -> Data {
        guard let key = keys[role] else { throw HolderEnrollmentError.missingCustody }
        guard key.accessPolicy == BiometricAccessPolicy.eachSignature else {
            throw HolderEnrollmentError.policyRefused
        }
        return try key.sign(message)
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

    static func recordHolderVerification(challengeId: String, baseURL: String, pairingToken: String) async throws {
        let payload: [String: Any] = [
            "challenge_id": challengeId,
            "verified": true,
            "consumed": true,
            "enrolled": false,
        ]
        let body = try await request(
            baseURL: baseURL,
            pairingToken: pairingToken,
            path: "/v1/phone-peer-verification",
            method: "POST",
            payload: payload
        )
        guard body["verified"] as? Bool == true, body["consumed"] as? Bool == true, body["enrolled"] as? Bool == false else {
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

