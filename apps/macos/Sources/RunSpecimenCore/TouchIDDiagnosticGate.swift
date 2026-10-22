import Foundation
import Darwin

// Standalone diagnostic support. Excluded from the Xcode Store target.
public enum TouchIDDiagnosticGate {
    public static func refusal(arguments: [String]) -> String? {
        if arguments.last == "preview" {
            return nil
        }
        if !arguments.contains("--human-invoked") {
            return "Refusing to call Secure Enclave. Re-run only when you will answer the Touch ID prompt yourself, and pass --human-invoked."
        }
        guard let directory = value(after: "--directory", in: arguments) else {
            return "Pass --directory /private/tmp/rs-touchid-diag. The diagnostic will not use the app container."
        }
        if !isIsolated(directory) {
            return "The diagnostic directory must be /private/tmp/rs-touchid-diag or a directory inside it."
        }
        guard let keyID = value(after: "--key-id", in: arguments) else {
            return "Pass --key-id diag-... so this diagnostic cannot select another enrollment."
        }
        if !keyID.hasPrefix("diag-") || keyID.count > 64 {
            return "The key id must start with diag- and stay within 64 characters."
        }
        guard let command = arguments.last else {
            return "Pass one command: preview, enroll, sign, reload, cancel, or revoke."
        }
        if command == "preview" {
            return nil
        }
        guard ["enroll", "sign", "reload", "cancel", "revoke"].contains(command) else {
            return "Pass one command: preview, enroll, sign, reload, cancel, or revoke."
        }
        _ = command
        return nil
    }

    private static func value(after flag: String, in arguments: [String]) -> String? {
        guard let index = arguments.firstIndex(of: flag), arguments.index(after: index) < arguments.endIndex else {
            return nil
        }
        let value = arguments[arguments.index(after: index)]
        if value.hasPrefix("-") || value.isEmpty {
            return nil
        }
        return value
    }

    /// Canonical containment. A `..` segment or a symlink that leaves the diagnostic root is rejected.
    /// `/tmp` is a symlink to `/private/tmp`, including when the leaf directory does not exist yet.
    static let rootPath = "/private/tmp/rs-touchid-diag"
    static let hopLimit = 16

    static func isIsolated(_ path: String) -> Bool {
        guard let resolved = canonicalPath(path) else { return false }
        return contains(resolved)
    }

    /// Opens a directory the caller owns inside the diagnostic root.
    ///
    /// The walk uses `openat` and `AT_SYMLINK_NOFOLLOW`. A symlink is followed only
    /// by reading its target and continuing in filesystem order. Hop exhaustion,
    /// a path that leaves the root, and a directory someone else can write are refusals.
    public static func openOwnedDirectory(_ path: String) throws -> Int32 {
        guard isIsolated(path) else { throw BiometricApprovalError.malformed("directory") }
        let fd = try walk(path)
        var info = stat()
        guard fstat(fd, &info) == 0 else {
            close(fd)
            throw BiometricApprovalError.malformed("directory")
        }
        let type = info.st_mode & S_IFMT
        guard type == S_IFDIR, info.st_uid == getuid(), (info.st_mode & 0o022) == 0 else {
            close(fd)
            throw BiometricApprovalError.malformed("directory")
        }
        guard let opened = openedPath(of: fd), contains(opened) else {
            close(fd)
            throw BiometricApprovalError.malformed("directory")
        }
        return fd
    }

    static func writeExclusive(directoryFD: Int32, name: String, data: Data) throws {
        try validateComponent(name)
        let fd = openat(directoryFD, name, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw BiometricApprovalError.malformed("directory") }
        do {
            try DescriptorIO.writeAll(fd, data)
            close(fd)
        } catch {
            close(fd)
            _ = unlinkat(directoryFD, name, 0)
            throw error
        }
    }

    static func readExclusive(directoryFD: Int32, name: String) throws -> Data {
        try validateComponent(name)
        let fd = openat(directoryFD, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard fd >= 0 else { throw BiometricApprovalError.malformed("directory") }
        defer { close(fd) }
        var st = stat()
        guard fstat(fd, &st) == 0, (st.st_mode & S_IFMT) == S_IFREG else {
            throw BiometricApprovalError.malformed("directory")
        }
        guard st.st_size >= 0, st.st_size <= 65_536 else {
            throw BiometricApprovalError.malformed("directory")
        }
        return try DescriptorIO.readAll(fd, count: Int(st.st_size))
    }

    public static func openedPath(of fd: Int32) -> String? {
        var buffer = [CChar](repeating: 0, count: Int(PATH_MAX))
        let result = buffer.withUnsafeMutableBufferPointer { pointer -> Int32 in
            guard let base = pointer.baseAddress else { return -1 }
            return fcntl(fd, F_GETPATH, base)
        }
        guard result == 0 else { return nil }
        return String(cString: buffer)
    }

    /// Resolves in filesystem order. Returns nil on hop exhaustion, a missing
    /// intermediate, or an unreadable symlink. A missing final component is kept.
    static func canonicalPath(_ path: String) -> String? {
        guard path.hasPrefix("/"), !path.contains("\0") else { return nil }
        var components = path.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
        var resolved: [String] = []
        var index = 0
        var hops = 0
        while index < components.count {
            let part = components[index]
            if part == "." {
                index += 1
                continue
            }
            if part == ".." {
                guard !resolved.isEmpty else { return nil }
                resolved.removeLast()
                index += 1
                continue
            }
            let next = "/" + (resolved + [part]).joined(separator: "/")
            var info = stat()
            if lstat(next, &info) != 0 {
                guard index == components.count - 1 else { return nil }
                resolved.append(part)
                break
            }
            if (info.st_mode & S_IFMT) == S_IFLNK {
                hops += 1
                guard hops <= hopLimit else { return nil }
                guard let dest = readLink(at: next) else { return nil }
                let rest = Array(components[(index + 1)...])
                let destParts = dest.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
                if dest.hasPrefix("/") {
                    resolved.removeAll()
                }
                components = destParts + rest
                index = 0
                continue
            }
            resolved.append(part)
            index += 1
        }
        if resolved.isEmpty { return "/" }
        return "/" + resolved.joined(separator: "/")
    }

    private static func contains(_ resolved: String) -> Bool {
        if resolved == "/tmp" || resolved == "/private/tmp" || resolved == "/" {
            return false
        }
        return resolved == rootPath || resolved.hasPrefix(rootPath + "/")
    }

    private static func walk(_ path: String) throws -> Int32 {
        var components = path.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
        var fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC)
        guard fd >= 0 else { throw BiometricApprovalError.malformed("directory") }
        var index = 0
        var hops = 0
        while index < components.count {
            let part = components[index]
            if part == "." {
                index += 1
                continue
            }
            if part == ".." {
                let parent = openat(fd, "..", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
                guard parent >= 0 else {
                    close(fd)
                    throw BiometricApprovalError.malformed("directory")
                }
                close(fd)
                fd = parent
                index += 1
                continue
            }
            var info = stat()
            if fstatat(fd, part, &info, AT_SYMLINK_NOFOLLOW) != 0 {
                guard errno == ENOENT, index == components.count - 1, mkdirat(fd, part, 0o700) == 0 else {
                    close(fd)
                    throw BiometricApprovalError.malformed("directory")
                }
                guard let child = openChild(fd, part) else {
                    close(fd)
                    throw BiometricApprovalError.malformed("directory")
                }
                close(fd)
                return child
            }
            if (info.st_mode & S_IFMT) == S_IFLNK {
                hops += 1
                guard hops <= hopLimit else {
                    close(fd)
                    throw BiometricApprovalError.malformed("directory")
                }
                guard let dest = readLink(atDirectory: fd, name: part) else {
                    close(fd)
                    throw BiometricApprovalError.malformed("directory")
                }
                let rest = Array(components[(index + 1)...])
                let destParts = dest.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
                if dest.hasPrefix("/") {
                    close(fd)
                    fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC)
                    guard fd >= 0 else { throw BiometricApprovalError.malformed("directory") }
                }
                components = destParts + rest
                index = 0
                continue
            }
            guard (info.st_mode & S_IFMT) == S_IFDIR, let child = openChild(fd, part) else {
                close(fd)
                throw BiometricApprovalError.malformed("directory")
            }
            close(fd)
            fd = child
            index += 1
        }
        return fd
    }

    private static func openChild(_ directory: Int32, _ name: String) -> Int32? {
        let fd = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        return fd >= 0 ? fd : nil
    }

    private static func readLink(at path: String) -> String? {
        var buffer = [CChar](repeating: 0, count: Int(PATH_MAX))
        let count = buffer.withUnsafeMutableBufferPointer { pointer -> Int in
            guard let base = pointer.baseAddress else { return -1 }
            return readlink(path, base, pointer.count - 1)
        }
        guard count > 0 else { return nil }
        return String(decoding: buffer.prefix(count).map { UInt8(bitPattern: $0) }, as: UTF8.self)
    }

    private static func readLink(atDirectory directory: Int32, name: String) -> String? {
        var buffer = [CChar](repeating: 0, count: Int(PATH_MAX))
        let count = buffer.withUnsafeMutableBufferPointer { pointer -> Int in
            guard let base = pointer.baseAddress else { return -1 }
            return readlinkat(directory, name, base, pointer.count - 1)
        }
        guard count > 0 else { return nil }
        return String(decoding: buffer.prefix(count).map { UInt8(bitPattern: $0) }, as: UTF8.self)
    }

    private static func validateComponent(_ name: String) throws {
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
        guard (1...64).contains(name.count), !name.contains("/"), name.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
            throw BiometricApprovalError.malformed("directory")
        }
    }
}
