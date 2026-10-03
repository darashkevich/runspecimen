import AppKit
import CryptoKit
import ServiceManagement
import SwiftUI

/// Separate Developer ID product. Registers an embedded SMAppService.daemon.
/// Does not modify the Mac App Store app. Root/admin can still defeat the holder.

@main
struct RunSpecimenHolderApp: App {
    @State private var statusText = "Starting…"
    @State private var detail = ""

    private let daemonPlist = "com.darashkevich.runspecimen.holder.daemon.plist"

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
                Text("Mechanism: SMAppService.daemon. State is root-owned. A same-user process must not rewrite enrollment, policy, nonces, or leases. Administrator or root can still defeat this holder. This is not human-only execution and not Store parity. An origin string is not production trust. E2 is not closed.")
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button("Enroll with Secure Enclave") {
                    enrollFromPerson(policy: "local")
                }
                Button("Enroll paired phone") {
                    enrollFromPerson(policy: "companion")
                }
            }
            .padding(24)
            .frame(minWidth: 520, minHeight: 280)
            .onAppear(perform: registerDaemon)
        }
    }

    /// The real Secure Enclave API runs only inside this button action.
    private func enrollFromPerson(policy: String) {
        do {
            let key = try HolderSecureEnclaveEnrollment.enroll(
                policy: policy,
                maker: LiveSecureEnclaveKeyMaker()
            )
            statusText = "Secure Enclave control returned a key. E2 is not closed."
            detail = "policy=\(policy) bytes=\(key.count). A biometric prompt is the human step."
        } catch {
            statusText = "Secure Enclave enrollment was not completed"
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

protocol HolderSecureEnclaveKeyMaking {
    func makePublicKey() throws -> Data
}

struct LiveSecureEnclaveKeyMaker: HolderSecureEnclaveKeyMaking {
    func makePublicKey() throws -> Data {
        let key = try SecureEnclave.P256.Signing.PrivateKey()
        return key.publicKey.x963Representation
    }
}

enum HolderEnrollmentError: Error {
    case emptyKey
    case policyRefused
}

enum HolderSecureEnclaveEnrollment {
    static func enroll(policy: String, maker: HolderSecureEnclaveKeyMaking) throws -> Data {
        guard policy == "local" || policy == "companion" || policy == "dual" else {
            throw HolderEnrollmentError.policyRefused
        }
        let key = try maker.makePublicKey()
        if key.isEmpty {
            throw HolderEnrollmentError.emptyKey
        }
        return key
    }
}
