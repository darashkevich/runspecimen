import Foundation
import RunSpecimenCore

let arguments = CommandLine.arguments
if arguments.last == "preview" {
    let request = PolicyBoundApprovalRequest(
        policy: .companion,
        macID: "preview-mac",
        workspaceID: "preview-workspace",
        runID: "preview-run",
        contractSHA256: String(repeating: "ab", count: 32),
        inputsSHA256: String(repeating: "cd", count: 32),
        bounds: "timeout_seconds=1",
        nonce: String(repeating: "a", count: 64),
        expiryUnix: 1_700_000_000,
        companionKeyID: "preview-phone",
        companionGeneration: 1
    )
    for line in BiometricRequestPresentation.lines(for: request) {
        print(line)
    }
    print("Preview only. No Secure Enclave call and no approval was stored.")
    exit(0)
}

if let reason = TouchIDDiagnosticGate.refusal(arguments: arguments) {
    FileHandle.standardError.write(Data((reason + "\n").utf8))
    exit(2)
}

guard let directory = argumentValue("--directory"),
      let keyID = argumentValue("--key-id"),
      let command = arguments.last else {
    FileHandle.standardError.write(Data("The diagnostic gate accepted arguments that it could not read back.\n".utf8))
    exit(2)
}

let folder = URL(fileURLWithPath: directory, isDirectory: true)
let keychain = LocalSecureEnclaveEnrollment.diagnosticKeychainService
do {
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    switch command {
    case "enroll":
        let publicKey = try LocalSecureEnclaveEnrollment.enroll(keyID: keyID, directory: folder, keychainService: keychain)
        print("enrolled \(publicKey.base64EncodedString())")
    case "sign", "reload":
        let request = diagnosticRequest(keyID: keyID)
        printExactRequest(request)
        let signature = try LocalSecureEnclaveEnrollment.sign(request, directory: folder, keychainService: keychain)
        print("signed \(signature.base64EncodedString())")
    case "cancel":
        let request = diagnosticRequest(keyID: keyID)
        printExactRequest(request)
        FileHandle.standardError.write(Data("Answer the prompt by cancelling it. A cancel must not store an approval.\n".utf8))
        _ = try LocalSecureEnclaveEnrollment.sign(request, directory: folder, keychainService: keychain)
        FileHandle.standardError.write(Data("The prompt completed instead of cancelling.\n".utf8))
        exit(1)
    case "revoke":
        try LocalSecureEnclaveEnrollment.revoke(keyID: keyID, directory: folder, keychainService: keychain)
        print("revoked")
    default:
        FileHandle.standardError.write(Data("Unknown command.\n".utf8))
        exit(2)
    }
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8))
    exit(1)
}

func argumentValue(_ flag: String) -> String? {
    guard let index = arguments.firstIndex(of: flag), arguments.index(after: index) < arguments.endIndex else {
        return nil
    }
    return arguments[arguments.index(after: index)]
}

func printExactRequest(_ request: BiometricApprovalRequest) {
    print("Signing this request:")
    print("Mac: \(request.macID)")
    print("Workspace: \(request.workspaceID)")
    print("Run: \(request.runID)")
    print("Contract: \(request.contractSHA256)")
    print("Inputs: \(request.inputsSHA256)")
    print("Bounds: \(request.bounds)")
    print("Nonce: \(request.nonce)")
    print("Expiry unix: \(request.expiryUnix)")
    print("Key: \(request.keyID)")
    print("Policy: local")
}

func diagnosticRequest(keyID: String) -> BiometricApprovalRequest {
    BiometricApprovalRequest(
        macID: "touchid-diagnostic",
        workspaceID: "touchid-diagnostic",
        runID: "touchid-diagnostic",
        contractSHA256: String(repeating: "ab", count: 32),
        inputsSHA256: String(repeating: "cd", count: 32),
        bounds: "timeout_seconds=1",
        nonce: String(repeating: "a", count: 64),
        expiryUnix: Int(Date().timeIntervalSince1970) + 300,
        keyID: keyID
    )
}
