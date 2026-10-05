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

    /// Passes the access value into key creation. Tests call this with stand-ins and do not use the hardware APIs.
    public static func bindAccessForExplicitHandoff<Access, Key>(
        acknowledgePrivilegedHardwareTrial: Bool,
        makeAccess: () -> Access?,
        makeKey: (Access) throws -> Key
    ) throws -> Key {
        guard acknowledgePrivilegedHardwareTrial else {
            throw DaemonKeyCreationError.handoffRequired
        }
        guard let access = makeAccess() else {
            throw DaemonKeyCreationError.handoffRequired
        }
        return try makeKey(access)
    }

    /// Later human handoff only. Tests and unattended code must pass `false` or not call this.
    public static func createKeyForExplicitHumanHandoff(acknowledgePrivilegedHardwareTrial: Bool) throws {
        guard acknowledgePrivilegedHardwareTrial else {
            throw DaemonKeyCreationError.handoffRequired
        }
        hardwareCallsiteReached += 1
        _ = try bindAccessForExplicitHandoff(
            acknowledgePrivilegedHardwareTrial: acknowledgePrivilegedHardwareTrial,
            makeAccess: {
                SecAccessControlCreateWithFlags(
                    kCFAllocatorDefault,
                    kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
                    [.privateKeyUsage, .biometryCurrentSet],
                    nil
                )
            },
            makeKey: { access in
                try SecureEnclave.P256.Signing.PrivateKey(accessControl: access)
            }
        )
    }
}
