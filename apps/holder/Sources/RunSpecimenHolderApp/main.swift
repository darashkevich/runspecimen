import AppKit
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
                Text("Mechanism: SMAppService.daemon. State is root-owned. A same-user process must not rewrite enrollment, policy, nonces, or leases. Administrator or root can still defeat this holder. This is not human-only execution and not Store parity.")
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(24)
            .frame(minWidth: 520, minHeight: 280)
            .onAppear(perform: registerDaemon)
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
