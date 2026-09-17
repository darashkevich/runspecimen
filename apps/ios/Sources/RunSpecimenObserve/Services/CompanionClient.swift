import Foundation

enum CompanionClientError: LocalizedError {
    case notPaired
    case http(Int, String)
    case decoding
    case transport(String)

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
        }
    }
}

/// HTTP client for the Mac-side observation endpoint only.
/// Intentionally has no approve/run methods.
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
        do {
            let (data, response) = try await URLSession.shared.data(for: req)
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
}
