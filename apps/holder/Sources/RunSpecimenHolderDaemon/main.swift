import Foundation

/// Root LaunchDaemon entry. Owns holder state under
/// /Library/Application Support/com.darashkevich.runspecimen.holder and
/// execs the Python holder protocol with software-test-double OFF.
/// Administrator or root can still defeat this holder.

let support = URL(fileURLWithPath: "/Library/Application Support/com.darashkevich.runspecimen.holder")
let state = support.appendingPathComponent("state", isDirectory: true)
let secretFile = support.appendingPathComponent("bootstrap.secret")

func die(_ message: String) -> Never {
    FileHandle.standardError.write(Data("\(message)\n".utf8))
    exit(1)
}

if geteuid() != 0 {
    die("RunSpecimenHolderDaemon must run as root")
}

let fm = FileManager.default
try? fm.createDirectory(at: support, withIntermediateDirectories: true)
try? fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: support.path)
try? fm.createDirectory(at: state, withIntermediateDirectories: true)
try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: state.path)

if !fm.fileExists(atPath: secretFile.path) {
    var bytes = [UInt8](repeating: 0, count: 32)
    let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
    if status != errSecSuccess {
        die("failed to create bootstrap secret")
    }
    let hex = bytes.map { String(format: "%02x", $0) }.joined()
    do {
        try hex.write(to: secretFile, atomically: true, encoding: .utf8)
        try fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: secretFile.path)
    } catch {
        die("failed to write bootstrap secret: \(error)")
    }
}

let secret: String
do {
    let raw = try String(contentsOf: secretFile, encoding: .utf8)
    secret = raw.trimmingCharacters(in: .whitespacesAndNewlines)
} catch {
    die("bootstrap secret unreadable: \(error)")
}
if secret.count < 32 {
    die("bootstrap secret missing or too short")
}

let execURL = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
// .../RunSpecimen Holder.app/Contents/MacOS/RunSpecimenHolderDaemon
let contents = execURL.deletingLastPathComponent().deletingLastPathComponent()
let resources = contents.appendingPathComponent("Resources")
let pythonRoot = resources.appendingPathComponent("Python")
let python = ProcessInfo.processInfo.environment["RS_HOLDER_PYTHON"]
    ?? "/opt/homebrew/bin/python3.12"

setenv("RS_HOLDER_BOOTSTRAP_SECRET", secret, 1)
setenv("PYTHONPATH", pythonRoot.path, 1)
setenv("PYTHONDONTWRITEBYTECODE", "1", 1)

let args = [
    python,
    "-m", "runspecimen.holder_daemon",
    "--support-dir", support.path,
]
let executable = args[0]
let argv = args.map { strdup($0) } + [nil]
execv(executable, argv)
die("execv failed for \(executable)")
