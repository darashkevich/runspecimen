import Foundation

/// Documents the security boundary between the sandboxed SwiftUI shell,
/// the bundled/user-selected CLI helper, and the payload under test.
///
/// Important: App Sandbox on the UI process does **not** by itself put the
/// payload command under an OS sandbox. Enforcement stays in the CLI
/// (lease, TTY APPROVE, contract hashes). Never auto-type APPROVE.
public enum SecurityBoundary: Sendable {
    public static let neverAutoApprove = true

    public static let confinedByAppSandbox: [String] = [
        "SwiftUI shell file access (user-selected bookmarks only)",
        "Network from the app process (client/server entitlements as declared)",
        "Child helper when spawned with com.apple.security.inherit",
        "Open-panel / security-scoped bookmark lifetime for workspace + CLI"
    ]

    public static let notConfinedByAppUISandboxAlone: [String] = [
        "Payload argv under test (contract command) — not an OS sandbox by virtue of the app UI",
        "Host tools invoked by the payload outside the lease model",
        "User-selected CLI binaries outside Contents/Helpers (still gated by basename + version probe)",
        "Anything claimed as “digital signature” — receipts remain hash-chained / HMAC"
    ]

    public static let humanApprovalRules: [String] = [
        "Approve uses a real PTY so engine isatty gates hold",
        "Human must type APPROVE; the app never auto-types or coerces it",
        "No agent / plugin / remote API may approve"
    ]

    /// Static assertion surface for unit tests / smoke greps.
    public static func assertsInvariants() -> Bool {
        neverAutoApprove
            && !confinedByAppSandbox.isEmpty
            && !notConfinedByAppUISandboxAlone.isEmpty
            && humanApprovalRules.contains(where: { $0.localizedCaseInsensitiveContains("never auto-types")
                || $0.localizedCaseInsensitiveContains("never auto-type")
                || $0.localizedCaseInsensitiveContains("must type APPROVE") })
    }
}
