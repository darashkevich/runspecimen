import CryptoKit
import Foundation
import Security

public enum DaemonKeyCreationError: Error, Equatable {
    /// The unattended process refused before any Secure Enclave or access-control call.
    case handoffRequired
}

/// Isolated feasibility record. This target is not installed, not registered, and not a daemon.
///
/// `unattendedAssessment` never reaches the hardware callsite. `createKeyForExplicitHumanHandoff`
/// contains that callsite for a later human trial and returns before it unless the caller
/// passes an explicit acknowledgement. Compile success is not evidence that creation works.
public enum DaemonKeyCreationHarness {
    public private(set) static var hardwareCallsiteReached = 0

    public struct Assessment: Equatable, Sendable {
        public var finding: String
        public var hardwareCallsiteReached: Int
        public var readOn: String
    }

    public static func unattendedAssessment() -> Assessment {
        Assessment(
            finding: "unsupported",
            hardwareCallsiteReached: hardwareCallsiteReached,
            readOn: "2026-10-05"
        )
    }

    /// Later human handoff only. Tests and unattended code must pass `false` or not call this.
    public static func createKeyForExplicitHumanHandoff(acknowledgePrivilegedHardwareTrial: Bool) throws {
        guard acknowledgePrivilegedHardwareTrial else {
            throw DaemonKeyCreationError.handoffRequired
        }
        hardwareCallsiteReached += 1
        guard let access = SecAccessControlCreateWithFlags(
            kCFAllocatorDefault,
            kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            [.privateKeyUsage, .biometryCurrentSet],
            nil
        ) else {
            throw DaemonKeyCreationError.handoffRequired
        }
        // The access-control value constrains the key only when this call receives it.
        // The parameterless initializer would apply a different default and ignore `access`.
        _ = try SecureEnclave.P256.Signing.PrivateKey(accessControl: access)
    }
}
