import CryptoKit
import Foundation
import Security

enum CompanionClientError: LocalizedError {
    case notPaired
    case http(Int, String)
    case decoding
    case transport(String)
    case tlsPinRequired
    case tlsPinMismatch

    var errorDescription: String? {
        switch self {
        case .notPaired:
            return "Pair with a Mac companion first."
        case let .http(code, message):
            return "HTTP \(code): \(message)"
        case .decoding:
            return "Could not decode companion response."
        case let .transport(message):
            return message
        case .tlsPinRequired:
            return "HTTPS companion URLs require the Mac TLS fingerprint from --print-token."
        case .tlsPinMismatch:
            return "TLS certificate fingerprint does not match the paired Mac value."
        }
    }
}

/// HTTP client for the Mac-side companion endpoint.
/// No plugin-style approve/run helpers — only observe + optional remote-confirm settle.
struct CompanionClient {
    var config: PairingConfig

    private func endpoint(_ path: String) throws -> URL {
        let root = config.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let suffix = path.hasPrefix("/") ? path : "/" + path
        guard let url = URL(string: root + suffix) else {
            throw CompanionClientError.transport("Invalid companion URL")
        }
        return url
    }

    private func makeSession() throws -> URLSession {
        let scheme = (config.baseURL.scheme ?? "").lowercased()
        if scheme == "https" {
            let pin = (config.tlsFingerprint ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !pin.isEmpty else { throw CompanionClientError.tlsPinRequired }
            let delegate = CompanionTLSPinningDelegate(expectedFingerprint: pin)
            return URLSession(configuration: .ephemeral, delegate: delegate, delegateQueue: nil)
        }
        if scheme == "http" {
            let host = (config.baseURL.host ?? "").lowercased()
            let loopback = host == "localhost" || host == "127.0.0.1" || host == "::1"
            if !loopback {
                throw CompanionClientError.transport(
                    "Cleartext HTTP is only allowed for loopback. Use HTTPS + TLS fingerprint for LAN/Tailscale."
                )
            }
        }
        return URLSession.shared
    }

    private func request(path: String, method: String = "GET", body: Data? = nil) async throws -> Data {
        var req = URLRequest(url: try endpoint(path))
        req.httpMethod = method
        req.setValue("Bearer \(config.pairingToken)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            req.httpBody = body
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        req.timeoutInterval = 8
        let session = try makeSession()
        do {
            let (data, response) = try await session.data(for: req)
            guard let http = response as? HTTPURLResponse else {
                throw CompanionClientError.transport("Non-HTTP response")
            }
            guard (200 ..< 300).contains(http.statusCode) else {
                let message = String(data: data, encoding: .utf8) ?? "error"
                throw CompanionClientError.http(http.statusCode, message)
            }
            return data
        } catch let error as CompanionClientError {
            throw error
        } catch {
            throw CompanionClientError.transport(error.localizedDescription)
        }
    }

    func fetchCapabilities() async throws -> CompanionCapabilities {
        let data = try await request(path: "/v1/capabilities")
        return try JSONDecoder().decode(CompanionCapabilities.self, from: data)
    }

    func fetchStatus() async throws -> CompanionStatus {
        let data = try await request(path: "/v1/status")
        return try JSONDecoder().decode(CompanionStatus.self, from: data)
    }

    func requestAttention(message: String) async throws {
        let payload = try JSONSerialization.data(withJSONObject: [
            "message": message,
            "mutates_lifecycle": false,
        ])
        _ = try await request(path: "/v1/attention", method: "POST", body: payload)
    }

    func requestOpenDashboard() async throws {
        _ = try await request(path: "/v1/open-dashboard", method: "POST", body: Data("{}".utf8))
    }

    /// Settle a Mac-armed pending confirm. Requires typed challenge + APPROVE phrase.
    func submitRemoteConfirm(challenge: String, phrase: String) async throws -> RemoteConfirmResult {
        let payload = try JSONSerialization.data(withJSONObject: [
            "challenge": challenge,
            "phrase": phrase,
        ])
        let data = try await request(path: "/v1/remote-confirm", method: "POST", body: payload)
        return try JSONDecoder().decode(RemoteConfirmResult.self, from: data)
    }

    /// Consume a Mac-armed pending without writing approval. Requires typed challenge + reason.
    func submitRemoteRefuse(challenge: String, reason: String) async throws -> RemoteConfirmResult {
        let payload = try JSONSerialization.data(withJSONObject: [
            "challenge": challenge,
            "reason": reason,
        ])
        let data = try await request(path: "/v1/remote-confirm-refuse", method: "POST", body: payload)
        return try JSONDecoder().decode(RemoteConfirmResult.self, from: data)
    }
}

final class CompanionTLSPinningDelegate: NSObject, URLSessionDelegate {
    let expectedFingerprint: String

    init(expectedFingerprint: String) {
        self.expectedFingerprint = Self.normalize(expectedFingerprint)
        super.init()
    }

    static func normalize(_ value: String) -> String {
        value
            .uppercased()
            .filter { "0123456789ABCDEF".contains($0) }
            .lowercased()
    }

    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust
        else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        let cert: SecCertificate?
        if #available(iOS 15.0, *) {
            cert = SecTrustGetCertificateAtIndex(trust, 0)
        } else {
            cert = SecTrustGetCertificateAtIndex(trust, 0)
        }
        guard let cert else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }

        let data = SecCertificateCopyData(cert) as Data
        let digest = SHA256.hash(data: data)
        let compact = digest.map { String(format: "%02x", $0) }.joined()
        guard compact == expectedFingerprint else {
            completionHandler(.cancelAuthenticationChallenge, nil)
            return
        }
        completionHandler(.useCredential, URLCredential(trust: trust))
    }
}
