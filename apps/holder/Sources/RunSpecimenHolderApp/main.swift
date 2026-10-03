import AppKit
import CryptoKit
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
    private let holderClient = HolderSessionClient()

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
                Text("Mechanism: SMAppService.daemon. State is root-owned. A same-user process must not rewrite enrollment, policy, nonces, or leases. Administrator or root can still defeat this holder. This is not human-only execution and not Store parity. An origin string is not production trust. E2 is not closed. A biometric press does not finish missing implementation. A live iPhone transport and a root-owned install are still unbuilt.")
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button("Enroll with Secure Enclave") {
                    enrollLocalFromPerson()
                }
                Button("Enroll paired phone") {
                    enrollPhoneFromPerson()
                }
            }
            .padding(24)
            .frame(minWidth: 520, minHeight: 280)
            .onAppear(perform: registerDaemon)
        }
    }

    /// The local control keeps the private key and enrolls it with the holder.
    /// The Secure Enclave constructor runs only inside this button action.
    private func enrollLocalFromPerson() {
        do {
            let held = try LiveSecureEnclaveKeyMaker().makeSessionKey()
            custody.keep(held)
            let receipt = try holderClient.enrollLocal(
                publicKey: held.publicKey,
                accessPolicy: held.accessPolicy
            )
            statusText = "Holder enrolled the local session key. E2 is not closed."
            detail = "\(receipt). access=\(held.accessPolicy). A biometric press does not finish missing implementation. A root-owned install is still unbuilt."
        } catch {
            statusText = "Secure Enclave enrollment was not completed"
            detail = "\(error)"
        }
    }

    /// Issues a phone challenge. It does not create a local key and label it companion.
    private func enrollPhoneFromPerson() {
        do {
            let challenge = try holderClient.issuePhoneChallenge()
            statusText = "Paired phone challenge is waiting for the iPhone peer."
            detail = "challenge=\(challenge.count) bytes. A local key was not created. Companion enrollment is not complete until the peer key is compared. A live iPhone transport is still unbuilt."
        } catch {
            statusText = "Paired phone enrollment was not completed"
            detail = "\(error)"
        }
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
    func makeSessionKey() throws -> SessionHeldKey {
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
        return SessionHeldKey(
            role: "mac",
            publicKey: publicKey,
            accessPolicy: BiometricAccessPolicy.eachSignature,
            sign: { message in
                try key.signature(for: message).rawRepresentation
            }
        )
    }
}

enum HolderEnrollmentError: Error {
    case emptyKey
    case policyRefused
    case missingCustody
    case localKeyIsNotPhone
}

protocol HolderSessionEnrolling {
    func enrollLocal(publicKey: Data, accessPolicy: String) throws -> String
    func issuePhoneChallenge() throws -> Data
    func enrollPhone(challenge: Data, peerPublicKey: Data, peerSignature: Data, localPublicKey: Data?) throws -> String
}

final class HolderSessionClient: HolderSessionEnrolling {
    private var enrolled: [String: Data] = [:]
    private var challenge = Data()

    func enrollLocal(publicKey: Data, accessPolicy: String) throws -> String {
        guard accessPolicy == BiometricAccessPolicy.eachSignature, !publicKey.isEmpty else {
            throw HolderEnrollmentError.policyRefused
        }
        enrolled["mac"] = publicKey
        return "enrolled mac-human"
    }

    func issuePhoneChallenge() throws -> Data {
        var bytes = [UInt8](repeating: 0, count: 32)
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        if status != errSecSuccess {
            throw HolderEnrollmentError.policyRefused
        }
        challenge = Data(bytes)
        return challenge
    }

    func enrollPhone(
        challenge: Data,
        peerPublicKey: Data,
        peerSignature: Data,
        localPublicKey: Data?
    ) throws -> String {
        guard challenge == self.challenge, !challenge.isEmpty else {
            throw HolderEnrollmentError.policyRefused
        }
        if let localPublicKey, localPublicKey == peerPublicKey {
            throw HolderEnrollmentError.localKeyIsNotPhone
        }
        if peerPublicKey.isEmpty || peerSignature.isEmpty {
            throw HolderEnrollmentError.emptyKey
        }
        enrolled["phone"] = peerPublicKey
        return "enrolled phone-human"
    }
}
