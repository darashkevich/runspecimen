import XCTest
import Security
@testable import RunSpecimenObserve

/// Each test owns its preferences domain and an in-memory pairing token.
/// Even tests that remove an error-injection hook never reach the real Keychain.
class IsolatedCompanionSessionTests: XCTestCase {
    private var suiteName: String!

    override func setUp() async throws {
        try await super.setUp()
        await MainActor.run {
            suiteName = "rs.observe.tests." + UUID().uuidString
            CompanionSession.testDefaults = UserDefaults(suiteName: suiteName)!
            CompanionSession.testIsolatedKeychain = true
            CompanionSession.testPairingToken = nil
            CompanionSession.testTokenRead = nil
            CompanionSession.testTokenWrite = nil
            CompanionSession.testTokenDelete = nil
        }
    }

    override func tearDown() async throws {
        await MainActor.run {
            CompanionSession.testDefaults?.removePersistentDomain(forName: suiteName)
            CompanionSession.testDefaults = nil
            CompanionSession.testPairingToken = nil
            CompanionSession.testIsolatedKeychain = false
            CompanionSession.testTokenRead = nil
            CompanionSession.testTokenWrite = nil
            CompanionSession.testTokenDelete = nil
        }
        try await super.tearDown()
    }
}
