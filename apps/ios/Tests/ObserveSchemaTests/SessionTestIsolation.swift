import XCTest
import Security
@testable import RunSpecimenObserve

/// Pairing fixtures must not inherit another simulator installation's credentials.
class IsolatedCompanionSessionTests: XCTestCase {
    private var savedPairing: Any?
    private var savedHolder: Any?

    override func setUp() async throws {
        try await super.setUp()
        await MainActor.run {
            savedPairing = UserDefaults.standard.object(forKey: "rs.observe.pairing")
            savedHolder = UserDefaults.standard.object(forKey: "rs.observe.pinnedHolderId")
            UserDefaults.standard.removeObject(forKey: "rs.observe.pairing")
            UserDefaults.standard.removeObject(forKey: "rs.observe.pinnedHolderId")
            CompanionSession.testTokenRead = { nil }
            CompanionSession.testTokenWrite = { _ in errSecSuccess }
            CompanionSession.testTokenDelete = {}
        }
    }

    override func tearDown() async throws {
        await MainActor.run {
            UserDefaults.standard.set(savedPairing, forKey: "rs.observe.pairing")
            UserDefaults.standard.set(savedHolder, forKey: "rs.observe.pinnedHolderId")
            CompanionSession.testTokenRead = nil
            CompanionSession.testTokenWrite = nil
            CompanionSession.testTokenDelete = nil
        }
        try await super.tearDown()
    }
}
