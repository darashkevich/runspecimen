import XCTest
@testable import RunSpecimenObserve

// Regression cases derived from the independent final QA reproductions.
final class SettlementOutcomeRegressionTests: IsolatedCompanionSessionTests {
    @MainActor
    private func qaSession() -> CompanionSession {
        let session = CompanionSession(deferPhoneKeyState: true)
        session.baseURLString = "http://localhost"
        session.pairingToken = "fixture-token"
        session.isPaired = true
        session.status = CompanionStatus(phase: "active")
        session.capabilities = CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
            canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture")
        return session
    }

    @MainActor
    func testQAAcknowledgedConfirmThenCancellationStaysConfirmed() async throws {
        CompanionSession.testTokenDelete = {}
        defer { CompanionSession.testTokenDelete = nil }
        let session = qaSession()
        session.challengeInput = "challenge"
        session.approvePhraseInput = "APPROVE"
        let client = try XCTUnwrap(session.testMakeClient())
        let entered = expectation(description: "post-ack refresh suspended")
        var resume: CheckedContinuation<Data, Error>?
        client.testRequest = { request in
            if request.url?.path == "/v1/remote-confirm" {
                return Data("{\"ok\":true,\"settled\":true}".utf8)
            }
            if request.url?.path == "/v1/status" {
                return try await withCheckedThrowingContinuation { continuation in
                    resume = continuation
                    entered.fulfill()
                }
            }
            return try JSONEncoder().encode(CompanionCapabilities(product: "test", mode: "observe",
                canApprove: false, canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture"))
        }
        let task = Task { @MainActor in await session.submitRemoteConfirm() }
        await fulfillment(of: [entered], timeout: 5)
        task.cancel()
        try XCTUnwrap(resume).resume(returning: try JSONEncoder().encode(CompanionStatus(phase: "active")))
        let outcome = await task.value
        XCTAssertNotNil(session.lastRemoteConfirmNote, "the server acknowledged settlement")
        XCTAssertEqual(outcome, .confirmed, "acknowledged settlement must not be reported as cancelled")
    }

    @MainActor
    func testQAAcknowledgedRefuseThenCancellationStaysRefused() async throws {
        CompanionSession.testTokenDelete = {}
        defer { CompanionSession.testTokenDelete = nil }
        let session = qaSession()
        session.challengeInput = "challenge"
        session.refuseReasonInput = "fixture refusal"
        let client = try XCTUnwrap(session.testMakeClient())
        let entered = expectation(description: "post-ack refresh suspended")
        var resume: CheckedContinuation<Data, Error>?
        client.testRequest = { request in
            if request.url?.path == "/v1/remote-confirm-refuse" {
                return Data("{\"ok\":true,\"refused\":true}".utf8)
            }
            if request.url?.path == "/v1/status" {
                return try await withCheckedThrowingContinuation { continuation in
                    resume = continuation
                    entered.fulfill()
                }
            }
            return try JSONEncoder().encode(CompanionCapabilities(product: "test", mode: "observe",
                canApprove: false, canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture"))
        }
        let task = Task { @MainActor in await session.submitRemoteRefuse() }
        await fulfillment(of: [entered], timeout: 5)
        task.cancel()
        try XCTUnwrap(resume).resume(returning: try JSONEncoder().encode(CompanionStatus(phase: "active")))
        let outcome = await task.value
        XCTAssertNotNil(session.lastRemoteConfirmNote, "the server acknowledged settlement")
        XCTAssertEqual(outcome, .refused, "acknowledged settlement must not be reported as cancelled")
    }

    @MainActor
    func testQAValidationFailureIsNotReportedAsRefreshCancellation() async throws {
        CompanionSession.testTokenDelete = {}
        defer { CompanionSession.testTokenDelete = nil }
        let session = qaSession()
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { request in
            if request.url?.path == "/v1/status" {
                return try JSONEncoder().encode(CompanionStatus(phase: "active"))
            }
            // Advertised plugin-style execution is refused by CapabilityValidator.
            return try JSONEncoder().encode(CompanionCapabilities(product: "test", mode: "execute",
                canApprove: false, canExecute: true, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture"))
        }
        await session.refresh()
        XCTAssertNotNil(session.lastError)
        if case .failure = session.refreshOutcome {
            // expected: a server-policy refusal is a failure, not a cancellation
        } else {
            XCTFail("server-policy refusal reported as \(session.refreshOutcome), connectionState=\(session.connectionState)")
        }
    }
}

extension SettlementOutcomeRegressionTests {
    @MainActor
    func testQADisconnectClearsPairingSecrets() {
        let session = CompanionSession(deferPhoneKeyState: true)
        session.baseURLString = "https://mac.example:8787"
        session.pairingToken = "secret-token"
        session.tlsFingerprint = "aabbcc"
        session.macSessionPublicKey = "mac-public-key"
        session.pinnedHolderId = "holder-a"
        UserDefaults.standard.set("holder-a", forKey: "rs.observe.pinnedHolderId")
        var savedToken: String? = "secret-token"
        UserDefaults.standard.set(Data("saved-pairing".utf8), forKey: "rs.observe.pairing")
        CompanionSession.testTokenDelete = { savedToken = nil }
        defer { CompanionSession.testTokenDelete = nil }
        session.disconnect()
        XCTAssertNil(savedToken, "disconnect must delete the persisted keychain token")
        XCTAssertNil(UserDefaults.standard.object(forKey: "rs.observe.pairing"))
        XCTAssertEqual(session.pairingToken, "", "disconnect must forget the bearer token")
        XCTAssertEqual(session.baseURLString, "", "disconnect must clear the URL")
        XCTAssertEqual(session.tlsFingerprint, "", "disconnect must clear the pin")
        XCTAssertEqual(session.macSessionPublicKey, "", "disconnect must clear the Mac trust anchor")
        XCTAssertEqual(session.pinnedHolderId, "", "disconnect must clear the holder trust anchor")
        XCTAssertNil(UserDefaults.standard.object(forKey: "rs.observe.pinnedHolderId"))
    }
    @MainActor
    func testCancelledRefreshPreservesSuccessfulTimestamp() async throws {
        let session = qaSession()
        let previous = Date(timeIntervalSince1970: 100)
        session.lastSuccessfulRefresh = previous
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { _ in throw CancellationError() }
        await session.refresh()
        XCTAssertEqual(session.lastSuccessfulRefresh, previous)
        XCTAssertEqual(session.refreshOutcome, .cancelled)
    }

    @MainActor
    func testRecoveryExportContainsActualFailureAndRetentionGuidance() async throws {
        let session = CompanionSession(deferPhoneKeyState: true)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try Data("corrupt-journal".utf8).write(to: directory.appendingPathComponent(".rotation-state.json"))
        await session.recoverHardwareRotation(directory: directory)
        let failure = try XCTUnwrap(session.rotationRecoveryError)
        XCTAssertFalse(failure.isEmpty)
        let exported = session.rotationRecoveryDiagnostics
        XCTAssertTrue(exported.contains(failure), exported)
        XCTAssertTrue(exported.hasPrefix("RunSpecimen key recovery\n"), exported)
        XCTAssertTrue(exported.contains("do not delete key records or reset generation counters"), exported)
    }

    @MainActor
    func testEnrollmentRefusalFeedbackClearsWhenKeyStateChanges() async {
        let session = qaSession()
        let result = await session.commitPhoneKeyAfterHolderVerification()
        guard case .refused = result else { return XCTFail("missing challenge must refuse") }
        XCTAssertEqual(session.phoneEnrollmentFeedback, result)
        session.phonePeerKeyState = .noKey
        XCTAssertNil(session.phoneEnrollmentFeedback)
        session.disconnect()
        XCTAssertNil(session.phoneEnrollmentFeedback)
    }

}

extension SettlementOutcomeRegressionTests {
    @MainActor
    func testGrokCancellationAtAcknowledgementKeepsSettlement() async throws {
        for refuse in [false, true] {
            let session = qaSession()
            session.challengeInput = "challenge"
            session.approvePhraseInput = "APPROVE"
            session.refuseReasonInput = "reason"
            let client = try XCTUnwrap(session.testMakeClient())
            client.testRequest = { request in
                if request.url?.path.contains("remote-confirm") == true {
                    withUnsafeCurrentTask { $0?.cancel() }
                    return Data((refuse ? "{\"ok\":true,\"refused\":true}" : "{\"ok\":true,\"settled\":true}").utf8)
                }
                throw CancellationError()
            }
            let outcome = refuse ? await session.submitRemoteRefuse() : await session.submitRemoteConfirm()
            XCTAssertEqual(outcome, refuse ? .refused : .confirmed)
            XCTAssertEqual(session.challengeInput, "")
        }
    }

    @MainActor
    func testGrokRefuseDoesNotCancelInFlightConfirm() async throws {
        let session = qaSession()
        session.challengeInput = "challenge"
        session.approvePhraseInput = "APPROVE"
        session.refuseReasonInput = "reason"
        let entered = expectation(description: "confirm in flight")
        var resume: CheckedContinuation<Data, Error>?
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { request in
            if request.url?.path == "/v1/remote-confirm" {
                return try await withCheckedThrowingContinuation { resume = $0; entered.fulfill() }
            }
            if request.url?.path == "/v1/remote-confirm-refuse" { XCTFail("must not send competing refusal") }
            throw CancellationError()
        }
        let confirm = Task { await session.submitRemoteConfirm() }
        await fulfillment(of: [entered], timeout: 5)
        let refused = await session.submitRemoteRefuse()
        if case .failure = refused { /* expected: confirm still owns the request */ }
        else { XCTFail("competing settlement must be refused") }
        // Always resume and await the original task, including the red path.
        // Returning at the assertion would leave its continuation suspended.
        try XCTUnwrap(resume).resume(returning: Data("{\"ok\":true,\"settled\":true}".utf8))
        let result = await confirm.value
        XCTAssertEqual(result, .confirmed)
    }

    @MainActor
    func testGrokSettlementRefreshUpdatesFreshness() async throws {
        let session = qaSession()
        session.challengeInput = "challenge"; session.approvePhraseInput = "APPROVE"
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { request in
            if request.url?.path == "/v1/remote-confirm" { return Data("{\"ok\":true,\"settled\":true}".utf8) }
            if request.url?.path == "/v1/status" { return try JSONEncoder().encode(CompanionStatus(phase: "active")) }
            return try JSONEncoder().encode(session.capabilities)
        }
        _ = await session.submitRemoteConfirm()
        XCTAssertNotNil(session.lastSuccessfulRefresh)
    }

    @MainActor
    func testGrokCancelClearsEnrollmentRefusal() async {
        let session = qaSession()
        _ = await session.commitPhoneKeyAfterHolderVerification()
        XCTAssertNotNil(session.phoneEnrollmentFeedback)
        await session.cancelPhonePeerChallenge()
        XCTAssertNil(session.phoneEnrollmentFeedback)
    }
}


extension SettlementOutcomeRegressionTests {
    @MainActor
    func testDeviceExpiredArmOverridesAdvertisedCapability() throws {
        let session = qaSession()
        session.status = try JSONDecoder().decode(CompanionStatus.self, from: Data("{\"phase\":\"active\",\"companion\":{\"can_remote_confirm\":true,\"remote_confirm\":{\"pending\":true,\"expires_at_unix\":1}}}".utf8))
        XCTAssertFalse(session.remoteConfirmPending)
    }

    @MainActor
    func testDeviceSettledArmOverridesAdvertisedCapability() throws {
        let session = qaSession()
        session.status = try JSONDecoder().decode(CompanionStatus.self, from: Data("{\"phase\":\"active\",\"companion\":{\"can_remote_confirm\":true,\"remote_confirm\":{\"pending\":false}}}".utf8))
        XCTAssertFalse(session.remoteConfirmPending)
    }
}


extension SettlementOutcomeRegressionTests {
    @MainActor
    func testDeviceCountdownAdvancesWithoutRefreshAndHidesAtDeadline() async throws {
        let session = qaSession()
        session.status = try JSONDecoder().decode(CompanionStatus.self, from: Data("{\"phase\":\"active\",\"companion\":{\"remote_confirm\":{\"pending\":true,\"expires_at_unix\":1000,\"chips\":{\"expiry\":\"588s\"}}}}".utf8))
        XCTAssertEqual(session.remoteConfirmExpiry(at: Date(timeIntervalSince1970: 412)), "588s")
        XCTAssertEqual(session.remoteConfirmExpiry(at: Date(timeIntervalSince1970: 413)), "587s")
        XCTAssertTrue(session.remoteConfirmPending(at: Date(timeIntervalSince1970: 999)))
        XCTAssertFalse(session.remoteConfirmPending(at: Date(timeIntervalSince1970: 1000)))
        XCTAssertEqual(session.remoteConfirmExpiry(at: Date(timeIntervalSince1970: 1001)), "0s")
        session.challengeInput = "challenge"
        session.approvePhraseInput = "APPROVE"
        var requests = 0
        session.testMakeClient()?.testRequest = { _ in requests += 1; return Data() }
        let result = await session.submitRemoteConfirm()
        if case .failure = result {} else { XCTFail("Expired arm must fail") }
        XCTAssertEqual(requests, 0)
    }
}
