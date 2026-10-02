import Darwin
import Foundation
import Security

/// Root LaunchDaemon entry. Source-level protected runtime selection.
/// This pass does not modify the live /Applications install. Yahor must
/// separately authorize replacing that install with a root-owned runtime.
/// Administrator or root can still defeat this holder.

let support = URL(fileURLWithPath: "/Library/Application Support/com.darashkevich.runspecimen.holder")
let state = support.appendingPathComponent("state", isDirectory: true)
let snapshots = support.appendingPathComponent("run-snapshots", isDirectory: true)
let secretFile = support.appendingPathComponent("bootstrap.secret")
let logFile = support.appendingPathComponent("daemon.log")

func log(_ message: String) {
    let line = "\(ISO8601DateFormatter().string(from: Date())) \(message)\n"
    if let data = line.data(using: .utf8) {
        if FileManager.default.fileExists(atPath: logFile.path) {
            if let handle = try? FileHandle(forWritingTo: logFile) {
                defer { try? handle.close() }
                _ = try? handle.seekToEnd()
                try? handle.write(contentsOf: data)
            }
        } else {
            try? data.write(to: logFile)
            try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: logFile.path)
        }
    }
}

func die(_ message: String) -> Never {
    log("FATAL \(message)")
    FileHandle.standardError.write(Data("\(message)\n".utf8))
    exit(1)
}

func absoluteExecutableURL() -> URL {
    var bufSize = UInt32(PATH_MAX)
    var buf = [CChar](repeating: 0, count: Int(bufSize))
    let rc = _NSGetExecutablePath(&buf, &bufSize)
    if rc == 0 {
        return URL(fileURLWithFileSystemRepresentation: buf, isDirectory: false, relativeTo: nil)
            .resolvingSymlinksInPath()
    }
    return URL(fileURLWithPath: CommandLine.arguments[0]).absoluteURL.resolvingSymlinksInPath()
}

func isSymlink(_ path: String) -> Bool {
    guard let attrs = try? FileManager.default.attributesOfItem(atPath: path) else { return false }
    if let type = attrs[.type] as? FileAttributeType {
        return type == .typeSymbolicLink
    }
    return false
}

func assertTrustedPath(_ path: String) {
    if isSymlink(path) {
        die("refusing symlink in runtime path: \(path)")
    }
    guard let attrs = try? FileManager.default.attributesOfItem(atPath: path) else {
        die("cannot stat runtime path: \(path)")
    }
    let owner = (attrs[.ownerAccountID] as? NSNumber)?.intValue ?? -1
    if owner != 0 {
        die("runtime path is not root-owned: \(path)")
    }
    let posix = (attrs[.posixPermissions] as? NSNumber)?.uint16Value ?? 0
    if (posix & 0o002) != 0 || (posix & 0o020) != 0 {
        die("runtime path is group/world-writable: \(path)")
    }
}

if geteuid() != 0 {
    die("RunSpecimenHolderDaemon must run as root")
}
if getenv("RS_HOLDER_PYTHON") != nil {
    die("RS_HOLDER_PYTHON is refused for protected holder runtime")
}
if getenv("PYTHONPATH") != nil {
    die("PYTHONPATH is refused for protected holder runtime")
}

let fm = FileManager.default
let execURL = absoluteExecutableURL()
let contents = execURL.deletingLastPathComponent().deletingLastPathComponent()
let resources = contents.appendingPathComponent("Resources")
let embedded = resources.appendingPathComponent("Runtime/bin/python3")
let moduleRoot = resources.appendingPathComponent("Python")
let entry = moduleRoot.appendingPathComponent("runspecimen/holder_entry.py")

// The installed holder is assumed to be root-owned under /Applications.
// That is not the Store app. Trust the embedded interpreter before any
// support directory or bootstrap secret is created. /usr/bin/python3 is not
// a fallback.
assertTrustedPath(execURL.path)
assertTrustedPath(embedded.path)
assertTrustedPath(moduleRoot.path)
assertTrustedPath(entry.path)
let python = embedded.path

try? fm.createDirectory(at: support, withIntermediateDirectories: true)
try? fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: support.path)
try? fm.createDirectory(at: state, withIntermediateDirectories: true)
try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: state.path)
try? fm.createDirectory(at: snapshots, withIntermediateDirectories: true)
try? fm.setAttributes([.posixPermissions: 0o711], ofItemAtPath: snapshots.path)

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

if !fm.isReadableFile(atPath: entry.path) {
    die("holder_entry.py missing from protected module root")
}

log("exec=\(execURL.path) python=\(python) entry=\(entry.path)")

unsetenv("PYTHONPATH")
unsetenv("PYTHONHOME")
unsetenv("PYTHONUSERBASE")
unsetenv("RS_HOLDER_PYTHON")
unsetenv("RS_HOLDER_MODULE_ROOT")
setenv("RS_HOLDER_BOOTSTRAP_SECRET", secret, 1)
setenv("PYTHONDONTWRITEBYTECODE", "1", 1)

// Execute the isolated entrypoint by path. Do not use python -m: that cannot
// discover Resources/Python before import without a prior path mutation.
let args = [
    python,
    "-I",
    entry.path,
    "--support-dir", support.path,
]
let argv = args.map { strdup($0) } + [nil]
execv(python, argv)
die("execv failed for \(python): errno=\(errno)")
