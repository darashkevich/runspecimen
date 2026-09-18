import Foundation

/// Minimum CLI the native app expects (PyPI 0.2.0rc9+ / matching repo tree).
public enum CLIVersionGate {
    /// Comparable tuple: (major, minor, patch, preKind, preNum)
    /// preKind: 0 = rc/a/b, 1 = final (no pre-release). Higher is newer.
    public static let minimum = ParsedVersion(major: 0, minor: 2, patch: 0, preKind: 0, preNum: 9)

    public struct ParsedVersion: Comparable, Equatable, Sendable {
        public var major: Int
        public var minor: Int
        public var patch: Int
        /// 0 = pre-release (rc/a/b), 1 = final
        public var preKind: Int
        public var preNum: Int

        public init(major: Int, minor: Int, patch: Int, preKind: Int, preNum: Int) {
            self.major = major
            self.minor = minor
            self.patch = patch
            self.preKind = preKind
            self.preNum = preNum
        }

        public static func < (lhs: ParsedVersion, rhs: ParsedVersion) -> Bool {
            let l = [lhs.major, lhs.minor, lhs.patch, lhs.preKind, lhs.preNum]
            let r = [rhs.major, rhs.minor, rhs.patch, rhs.preKind, rhs.preNum]
            return l.lexicographicallyPrecedes(r)
        }

        public var displayMinimum: String { "0.2.0rc9" }

        public var display: String {
            if preKind == 0 {
                return "\(major).\(minor).\(patch)rc\(preNum)"
            }
            return "\(major).\(minor).\(patch)"
        }
    }

    public enum Evaluation: Equatable, Sendable {
        case ok(ParsedVersion)
        case tooOld(found: ParsedVersion, required: ParsedVersion, raw: String)
        case unparseable(raw: String)
    }

    public static func parse(from versionOutput: String) -> ParsedVersion? {
        // Accept "runspecimen 0.2.0rc9", "0.2.0rc9", "0.2.0-rc.9", "0.2.0"
        let lowered = versionOutput.lowercased()
        let pattern = #"(\d+)\.(\d+)\.(\d+)(?:[-.]?(?:rc|a|b|alpha|beta)\.?(\d+))?"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        let range = NSRange(lowered.startIndex..<lowered.endIndex, in: lowered)
        guard let match = regex.firstMatch(in: lowered, range: range) else { return nil }

        func group(_ i: Int) -> String? {
            let r = match.range(at: i)
            guard r.location != NSNotFound, let swift = Range(r, in: lowered) else { return nil }
            return String(lowered[swift])
        }

        guard let major = Int(group(1) ?? ""),
              let minor = Int(group(2) ?? ""),
              let patch = Int(group(3) ?? "") else { return nil }

        if let pre = group(4), let preNum = Int(pre) {
            return ParsedVersion(major: major, minor: minor, patch: patch, preKind: 0, preNum: preNum)
        }
        return ParsedVersion(major: major, minor: minor, patch: patch, preKind: 1, preNum: 0)
    }

    public static func evaluate(versionOutput: String) -> Evaluation {
        let raw = versionOutput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parsed = parse(from: raw) else {
            return .unparseable(raw: raw)
        }
        if parsed < minimum {
            return .tooOld(found: parsed, required: minimum, raw: raw)
        }
        return .ok(parsed)
    }

    public static func failureMessage(for evaluation: Evaluation) -> String? {
        switch evaluation {
        case .ok:
            return nil
        case .tooOld(let found, let required, let raw):
            return """
            CLI version mismatch: found \(found.display) (from “\(raw)”), need \(required.displayMinimum)+.
            Upgrade: python3 -m pip install --upgrade 'runspecimen==0.2.0rc10'
            Or select a newer binary via Open panel / Settings.
            """
        case .unparseable(let raw):
            return """
            Could not parse runspecimen version from:
            \(raw.isEmpty ? "(empty)" : raw)
            Install \(minimum.displayMinimum)+ then re-select the binary.
            """
        }
    }
}

/// Where the active CLI binary came from (discovery order in ADR-002).
public enum CLIResolutionSource: String, Equatable, Sendable {
    case bookmark
    case bundledHelper
    case pathProbe
    case manual

    public var label: String {
        switch self {
        case .bookmark: return "Saved bookmark"
        case .bundledHelper: return "Bundled Helpers"
        case .pathProbe: return "PATH / install probe"
        case .manual: return "User selected"
        }
    }
}
