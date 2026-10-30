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
        CompanionSession.storageDefaults.set("holder-a", forKey: "rs.observe.pinnedHolderId")
        var savedToken: String? = "secret-token"
        CompanionSession.storageDefaults.set(Data("saved-pairing".utf8), forKey: "rs.observe.pairing")
        CompanionSession.testTokenDelete = { savedToken = nil }
        defer { CompanionSession.testTokenDelete = nil }
        session.disconnect()
        XCTAssertNil(savedToken, "disconnect must delete the persisted keychain token")
        XCTAssertNil(CompanionSession.storageDefaults.object(forKey: "rs.observe.pairing"))
        XCTAssertEqual(session.pairingToken, "", "disconnect must forget the bearer token")
        XCTAssertEqual(session.baseURLString, "", "disconnect must clear the URL")
        XCTAssertEqual(session.tlsFingerprint, "", "disconnect must clear the pin")
        XCTAssertEqual(session.macSessionPublicKey, "", "disconnect must clear the Mac trust anchor")
        XCTAssertEqual(session.pinnedHolderId, "", "disconnect must clear the holder trust anchor")
        XCTAssertNil(CompanionSession.storageDefaults.object(forKey: "rs.observe.pinnedHolderId"))
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
                try Task.checkCancellation()
                return try await withCheckedThrowingContinuation { resume = $0; entered.fulfill() }
            }
            if request.url?.path == "/v1/remote-confirm-refuse" { XCTFail("must not send competing refusal") }
            throw CancellationError()
        }
        let confirm = Task { await session.submitRemoteConfirm() }
        let readiness = await XCTWaiter.fulfillment(of: [entered], timeout: 5)
        guard readiness == .completed, let continuation = resume else {
            confirm.cancel()
            resume?.resume(throwing: CancellationError())
            _ = await confirm.value
            XCTFail("confirm transport did not become ready")
            return
        }
        let refused = await session.submitRemoteRefuse()
        if case .failure = refused { /* expected: confirm still owns the request */ }
        else { XCTFail("competing settlement must be refused") }
        // Always resume and await the original task, including the red path.
        // Returning at the assertion would leave its continuation suspended.
        continuation.resume(returning: Data("{\"ok\":true,\"settled\":true}".utf8))
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


extension SettlementOutcomeRegressionTests {
    @MainActor
    func testRejectedRePairRetainsWorkingConnection() async throws {
        let session = qaSession()
        let previousStatus = session.status
        let previousCapabilities = session.capabilities
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { _ in throw CompanionClientError.transport("candidate unavailable") }
        await session.saveAndPair(client: client)
        XCTAssertTrue(session.isPaired)
        XCTAssertEqual(session.status, previousStatus)
        XCTAssertEqual(session.capabilities, previousCapabilities)
        XCTAssertEqual(session.baseURLString, "http://localhost")
        XCTAssertEqual(session.pairingToken, "fixture-token")
        XCTAssertNotNil(session.lastError)
    }
}


extension SettlementOutcomeRegressionTests {
    @MainActor
    func testRejectedCandidateNeverChangesLivePairingOrPins() async throws {
        let session = qaSession()
        session.macSessionPublicKey = "old-mac-key"
        session.pinnedHolderId = "old-holder"
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { _ in throw CompanionClientError.transport("candidate unavailable") }
        let candidate = PairingConfig(baseURL: URL(string: "https://candidate.invalid")!, pairingToken: "new-token", tlsFingerprint: "new-pin")
        await session.saveAndPair(candidate: candidate, client: client)
        XCTAssertTrue(session.isPaired)
        XCTAssertEqual(session.baseURLString, "http://localhost")
        XCTAssertEqual(session.pairingToken, "fixture-token")
        XCTAssertEqual(session.macSessionPublicKey, "old-mac-key")
        XCTAssertEqual(session.pinnedHolderId, "old-holder")
        XCTAssertNotEqual(session.tlsFingerprint, "new-pin")
    }
}


extension SettlementOutcomeRegressionTests {
    @MainActor
    func testVerifiedCandidateCommitsOnlyAfterValidation() async throws {
        let session = qaSession()
        session.challengeInput = "old-challenge"
        session.approvePhraseInput = "APPROVE"
        session.lastRemoteConfirmNote = "old result"
        session.reviewedExactRunLines = ["old request"]
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { request in
            if request.url?.path == "/v1/status" { return try JSONEncoder().encode(CompanionStatus(phase: "active")) }
            return try JSONEncoder().encode(CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
                canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture"))
        }
        let candidate = PairingConfig(baseURL: URL(string: "https://candidate.invalid")!, pairingToken: "new-token", tlsFingerprint: "new-pin")
        let paired = await session.saveAndPair(candidate: candidate, client: client)
        XCTAssertTrue(paired)
        XCTAssertEqual(session.challengeInput, "")
        XCTAssertEqual(session.approvePhraseInput, "")
        XCTAssertNil(session.lastRemoteConfirmNote)
        XCTAssertEqual(session.reviewedExactRunLines, [])
        XCTAssertEqual(session.baseURLString, candidate.baseURL.absoluteString)
        XCTAssertEqual(session.pairingToken, "new-token")
        XCTAssertEqual(session.tlsFingerprint, "new-pin")
    }
}


extension SettlementOutcomeRegressionTests {
    @MainActor
    func testInvalidatedPairingReturnsFailureWithoutReplacingConnection() async throws {
        let session = qaSession()
        let client = try XCTUnwrap(session.testMakeClient())
        client.testRequest = { request in
            if request.url?.path == "/v1/status" {
                session.cancelAllTasks()
                return try JSONEncoder().encode(CompanionStatus(phase: "active"))
            }
            return try JSONEncoder().encode(CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
                canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture"))
        }
        let candidate = PairingConfig(baseURL: URL(string: "https://candidate.invalid")!, pairingToken: "new-token", tlsFingerprint: "new-pin")
        let paired = await session.saveAndPair(candidate: candidate, client: client)
        XCTAssertFalse(paired)
        XCTAssertEqual(session.baseURLString, "http://localhost")
        XCTAssertEqual(session.pairingToken, "fixture-token")
    }
}

extension SettlementOutcomeRegressionTests {
    @MainActor
    func testGrokP3DirectRefreshFailureReplacesSuccess() async throws {
        let s = qaSession()
        s.refreshOutcome = .success(Date())
        let c = try XCTUnwrap(s.testMakeClient())
        c.testRequest = { _ in throw CompanionClientError.transport("offline fixture") }
        do { try await s.refreshStatus(); XCTFail("expected failure") } catch {}
        XCTAssertEqual(s.refreshOutcome, .failure("offline fixture"))
    }

    func testGrokN1LegacyBiometricErrorsUseHumanCopy() {
        XCTAssertEqual(CompanionHardwareErrorPresentation.describe(CompanionHardwareRefusal.automationRefused).message, "Authentication cancelled.")
        XCTAssertEqual(CompanionHardwareErrorPresentation.describe(CompanionHardwareRefusal.malformed("biometric--1")).message, "Authentication did not succeed. Try again when you are ready.")
    }

    @MainActor
    func testGrokN2FailedCandidateEndsObsoleteRefresh() async throws {
        let s = qaSession()
        s.refreshOutcome = .inProgress
        let c = try XCTUnwrap(s.testMakeClient())
        c.testRequest = { _ in throw CompanionClientError.transport("candidate refused") }
        let paired = await s.saveAndPair(client: c)
        XCTAssertFalse(paired)
        XCTAssertNotEqual(s.refreshOutcome, .inProgress)
    }

    @MainActor
    func testGrokN2CancelledConnectDoesNotPublishError() async throws {
        let s = qaSession()
        let c = try XCTUnwrap(s.testMakeClient())
        c.testRequest = { _ in throw CancellationError() }
        let paired = await s.saveAndPair(client: c)
        XCTAssertFalse(paired)
        XCTAssertNil(s.lastError)
    }

    @MainActor
    func testGrokN3CancelledTransportHasUnknownOutcomeAndClearsInputs() async throws {
        for refuse in [false, true] {
            let s = qaSession()
            s.challengeInput = "challenge"; s.approvePhraseInput = "APPROVE"; s.refuseReasonInput = "reason"
            let c = try XCTUnwrap(s.testMakeClient())
            c.testRequest = { _ in throw CancellationError() }
            let outcome = refuse ? await s.submitRemoteRefuse() : await s.submitRemoteConfirm()
            XCTAssertEqual(outcome, .failure("Request outcome is unknown. Refresh status before trying again."))
            XCTAssertNil(s.lastError)
            XCTAssertEqual(s.challengeInput, "")
            XCTAssertEqual(s.approvePhraseInput, "")
        }
    }

    @MainActor
    func testGrokN4VerifiedReplacementResetsOldMacNotesAndTrust() async throws {
        let s = qaSession()
        let baseline = qaSession()
        s.phonePeerNote = "old phone note"; s.exactRunNote = "old exact note"
        s.macSessionPublicKey = "old mac key"; s.pinnedHolderId = "old holder"
        let c = try XCTUnwrap(s.testMakeClient())
        c.testRequest = { r in
            if r.url?.path == "/v1/status" { return try JSONEncoder().encode(CompanionStatus(phase: "active")) }
            return try JSONEncoder().encode(CompanionCapabilities(product: "test", mode: "observe", canApprove: false, canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture"))
        }
        let paired = await s.saveAndPair(candidate: PairingConfig(baseURL: URL(string: "http://new-mac.invalid")!, pairingToken: "new-token", tlsFingerprint: nil), client: c)
        XCTAssertTrue(paired)
        XCTAssertEqual(s.phonePeerNote, baseline.phonePeerNote)
        XCTAssertEqual(s.exactRunNote, baseline.exactRunNote)
        XCTAssertEqual(s.macSessionPublicKey, "")
        XCTAssertEqual(s.pinnedHolderId, "")
        XCTAssertNil(s.lastError)
    }
}


extension SettlementOutcomeRegressionTests {
    @MainActor
    func testGrokN3CancelledTaskDoesNotPublishLateTransportError() async throws {
        for refuse in [false, true] {
            let s = qaSession()
            s.challengeInput = "challenge"; s.approvePhraseInput = "APPROVE"; s.refuseReasonInput = "reason"
            let entered = expectation(description: "settlement entered transport")
            var resume: CheckedContinuation<Data, Error>?
            let c = try XCTUnwrap(s.testMakeClient())
            c.testRequest = { _ in
                try Task.checkCancellation()
                return try await withCheckedThrowingContinuation { resume = $0; entered.fulfill() }
            }
            let task = Task { refuse ? await s.submitRemoteRefuse() : await s.submitRemoteConfirm() }
            let ready = await XCTWaiter.fulfillment(of: [entered], timeout: 5)
            guard ready == .completed, let continuation = resume else {
                task.cancel(); resume?.resume(throwing: CancellationError()); _ = await task.value
                XCTFail("transport never entered"); return
            }
            task.cancel()
            continuation.resume(throwing: CompanionClientError.transport("late network failure"))
            let outcome = await task.value
            XCTAssertEqual(outcome, .failure(CompanionSession.unknownSettlementMessage))
            XCTAssertNil(s.lastError)
            XCTAssertEqual(s.challengeInput, "")
            XCTAssertEqual(s.approvePhraseInput, "")
        }
    }
}


extension SettlementOutcomeRegressionTests {
    @MainActor
    func testP3CancelAllTasksClearsInterruptedSettlementFields() async throws {
        for refuse in [false, true] {
            let s = qaSession()
            s.challengeInput = "challenge"; s.approvePhraseInput = "APPROVE"; s.refuseReasonInput = "reason"
            let entered = expectation(description: "transport suspended")
            var resume: CheckedContinuation<Data, Error>?
            let c = try XCTUnwrap(s.testMakeClient())
            c.testRequest = { _ in try await withCheckedThrowingContinuation { resume = $0; entered.fulfill() } }
            let task = Task { refuse ? await s.submitRemoteRefuse() : await s.submitRemoteConfirm() }
            let ready = await XCTWaiter.fulfillment(of: [entered], timeout: 5)
            guard ready == .completed, let continuation = resume else {
                task.cancel(); resume?.resume(throwing: CancellationError()); _ = await task.value
                XCTFail("transport never entered"); return
            }
            s.cancelAllTasks()
            continuation.resume(throwing: CancellationError())
            _ = await task.value
            XCTAssertEqual(s.challengeInput, "")
            XCTAssertEqual(s.approvePhraseInput, "")
            XCTAssertEqual(s.refuseReasonInput, "")
        }
    }

    @MainActor
    func testP3VerifiedPairingFormDoesNotRestoreUneditedOldTrust() {
        let s = qaSession()
        s.applyVerifiedPairingTrustEdits(previousMacKey: "old-key", previousHolderID: "old-holder", macKey: "old-key", holderID: "old-holder")
        XCTAssertEqual(s.macSessionPublicKey, "")
        XCTAssertEqual(s.pinnedHolderId, "")
    }

    @MainActor
    func testP3VerifiedPairingFormKeepsOnlyDeliberatelyEditedPins() {
        let s = qaSession()
        s.applyVerifiedPairingTrustEdits(previousMacKey: "old-key", previousHolderID: "old-holder", macKey: "replacement-key", holderID: "old-holder")
        XCTAssertEqual(s.macSessionPublicKey, "replacement-key")
        XCTAssertEqual(s.pinnedHolderId, "")
        s.macSessionPublicKey = ""
        s.applyVerifiedPairingTrustEdits(previousMacKey: "old-key", previousHolderID: "old-holder", macKey: "old-key", holderID: "replacement-holder")
        XCTAssertEqual(s.macSessionPublicKey, "")
        XCTAssertEqual(s.pinnedHolderId, "replacement-holder")
        XCTAssertEqual(CompanionSession.storageDefaults.string(forKey: "rs.observe.pinnedHolderId"), "replacement-holder")
    }

    @MainActor
    func testIdleCancelPreservesUnsubmittedSettlementDraft() {
        let s = qaSession()
        s.challengeInput = "challenge"; s.approvePhraseInput = "APPROVE"; s.refuseReasonInput = "reason"
        s.cancelAllTasks()
        XCTAssertEqual(s.challengeInput, "challenge")
        XCTAssertEqual(s.approvePhraseInput, "APPROVE")
        XCTAssertEqual(s.refuseReasonInput, "reason")
    }

    @MainActor
    func testSchemaStorageIsNotStandardDefaults() {
        XCTAssertFalse(CompanionSession.storageDefaults === UserDefaults.standard)
    }
}

extension SettlementOutcomeRegressionTests {
    func testVerifiedPairingSuccessExplainsClearedTrustAndNextStep() {
        let message = PairingOutcome.successMessage
        XCTAssertTrue(message.contains("Mac session key and holder pin were cleared"))
        XCTAssertTrue(message.contains("Re-enter them"))
        XCTAssertTrue(message.contains("Advanced settings"))
    }
}


extension SettlementOutcomeRegressionTests {
    @MainActor
    func testQA2PostSendErrorsHaveUnknownSettlementAndClearInputs() async throws {
        let errors: [Error] = [URLError(.timedOut), URLError(.networkConnectionLost), CompanionClientError.http(502, "gateway")]
        for refuse in [false, true] {
            for index in 0...errors.count {
                let session = qaSession()
                session.challengeInput = "challenge"
                session.approvePhraseInput = "APPROVE"
                session.refuseReasonInput = "fixture refusal"
                let client = try XCTUnwrap(session.testMakeClient())
                client.testRequest = { _ in
                    if index < errors.count { throw errors[index] }
                    return Data("garbage 200 body".utf8)
                }
                let outcome = refuse ? await session.submitRemoteRefuse() : await session.submitRemoteConfirm()
                XCTAssertEqual(outcome, .failure(CompanionSession.unknownSettlementMessage))
                XCTAssertEqual(session.challengeInput, "")
                XCTAssertEqual(session.approvePhraseInput, "")
                XCTAssertEqual(session.refuseReasonInput, "")
            }
        }
    }
}


extension SettlementOutcomeRegressionTests {
    @MainActor
    func testQA2ReenteringSamePinsAfterRePairIsADeliberateEdit() {
        var draft = PairingTrustDraft()
        draft.synchronize(macKey: "old-key", holderID: "old-holder")
        let session = qaSession()
        session.macSessionPublicKey = ""
        session.pinnedHolderId = ""
        draft.synchronize(macKey: session.macSessionPublicKey, holderID: session.pinnedHolderId)
        XCTAssertEqual(draft.macKey, "")
        XCTAssertEqual(draft.holderID, "")
        draft.macKey = "old-key"
        draft.holderID = "old-holder"
        session.applyVerifiedPairingTrustEdits(previousMacKey: draft.initialMacKey, previousHolderID: draft.initialHolderID,
            macKey: draft.macKey, holderID: draft.holderID)
        XCTAssertEqual(session.macSessionPublicKey, "old-key")
        XCTAssertEqual(session.pinnedHolderId, "old-holder")
    }
}
