import XCTest
@testable import RunSpecimenObserve

final class PhonePeerCancellationXCTests: IsolatedCompanionSessionTests {

    @MainActor
    func testQA2CancellationTargetUsesIsolatedStorage() {
        XCTAssertFalse(CompanionSession.storageDefaults === UserDefaults.standard)
        XCTAssertTrue(CompanionSession.testIsolatedKeychain)
    }

    override func setUp() {
        super.setUp()
        executionTimeAllowance = 60
        CompanionSecureEnclaveEnrollment.testAuthenticator = { _ in }
    }

    override func tearDown() {
        CompanionSecureEnclaveEnrollment.testAuthenticator = nil
        super.tearDown()
    }

    @MainActor
    func test_DelayedFetchThenCancelDoesNotSignOrPost() async throws {
        try await testDelayedFetchThenCancelDoesNotSignOrPost()
    }

    @MainActor
    func test_CancelBeforePostDoesNotPublish() async throws {
        try await testCancelBeforePostDoesNotPublish()
    }

    @MainActor
    func test_PostThatAlreadyLeftIsCancellationTooLate() async throws {
        try await testPostThatAlreadyLeftIsCancellationTooLate()
    }

    @MainActor
    func test_ForgedFlagsWrongKeyChallengeReplayCancelAndStaleDoNotCommit() async throws {
        try await testForgedFlagsWrongKeyChallengeReplayCancelAndStaleDoNotCommit()
    }

    @MainActor
    func test_DelayedReceiptThenCancelDoesNotCommit() async throws {
        try await testDelayedReceiptThenCancelDoesNotCommit()
    }

    @MainActor
    func test_DelayedReceiptThenNewChallengeDoesNotCommit() async throws {
        try await testDelayedReceiptThenNewChallengeDoesNotCommit()
    }

    @MainActor
    func test_FailedCommitThenRetryEnrolls() async throws {
        try await testFailedCommitThenRetryEnrolls()
    }

    @MainActor
    func test_ExactRunSignatureUsesTheFetchedNonce() async throws {
        try await testExactRunSignatureUsesTheFetchedNonce()
    }

    @MainActor
    func test_ExactRunCancelDuringReviewDoesNotSign() async throws {
        try await testExactRunCancelDuringReviewDoesNotSign()
    }

    @MainActor
    func test_ExactRunReplacementDoesNotSubmit() async throws {
        try await testExactRunReplacementDoesNotSubmit()
    }

    @MainActor
    func test_ExactRunMalformedBoundDoesNotSign() async throws {
        try await testExactRunMalformedBoundDoesNotSign()
    }

    @MainActor
    func test_ExactRunMissingKeyDoesNotSubmit() async throws {
        try await testExactRunMissingKeyDoesNotSubmit()
    }

    @MainActor
    func test_ExactRunExpiryBeforeApproveDoesNotSign() async throws {
        try await testExactRunExpiryBeforeApproveDoesNotSign()
    }

    @MainActor
    func test_ExactRunExpiryAfterWaitDoesNotSubmit() async throws {
        try await testExactRunExpiryAfterWaitDoesNotSubmit()
    }

    @MainActor
    func test_ExactRunCancellationBeforeSignDoesNotSign() async throws {
        try await testExactRunCancellationBeforeSignDoesNotSign()
    }

    @MainActor
    func test_ExactRunCancellationBeforeSubmitDoesNotSubmit() async throws {
        try await testExactRunCancellationBeforeSubmitDoesNotSubmit()
    }

    @MainActor
    func test_ExactRunUnpinnedHolderDoesNotSign() async throws {
        try await testExactRunUnpinnedHolderDoesNotSign()
    }

    @MainActor
    func test_ExactRunSubstitutedHolderDoesNotSign() async throws {
        try await testExactRunSubstitutedHolderDoesNotSign()
    }

    func test_PhoneKeyOwnershipRejectsADifferentChallenge() throws {
        try testPhoneKeyOwnershipRejectsADifferentChallenge()
    }

    func test_PhoneKeyStageRollsBackAndRevokes() throws {
        try testPhoneKeyStageRollsBackAndRevokes()
    }

    func test_PhoneKeyCommitFailureKeepsThePreviousGeneration() throws {
        try testPhoneKeyCommitFailureKeepsThePreviousGeneration()
    }

    @MainActor
    func test_RevokePhonePeerKeyClearsExactRunState() async throws {
        try await testRevokePhonePeerKeyClearsExactRunState()
    }

    @MainActor
    func test_RotatePhonePeerKeyClearsExactRunState() async throws {
        try await testRotatePhonePeerKeyClearsExactRunState()
    }

    @MainActor
    func test_CancelAllTasksCancelsInFlightPhonePeerOperation() async throws {
        try await testCancelAllTasksCancelsInFlightPhonePeerOperation()
    }

    @MainActor
    func test_DisconnectCancelsInFlightPhonePeerOperation() async throws {
        try await testDisconnectCancelsInFlightPhonePeerOperation()
    }
}

extension PhonePeerCancellationXCTests {
    @MainActor
    func testIOSQA610SupersededTaskCannotDiscardNewStageOrClearNewResult() async throws {
        let session = CompanionSession(deferPhoneKeyState: true)
        session.isPaired = true
        session.status = CompanionStatus(phase: "active")
        session.capabilities = CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
            canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "fixture")
        let signer = CountingSigner()
        let oldHold = FetchHold()
        let entered = expectation(description: "Old operation suspended after signing")
        await oldHold.observeEntry { entered.fulfill() }
        let oldPeer = HoldingPeer(hold: oldHold)
        oldPeer.holdFetch = false
        oldPeer.holdBeforePost = true
        let old = Task { @MainActor in await session.signPhonePeerChallenge(signer: signer, peer: oldPeer) }
        await fulfillment(of: [entered], timeout: 3)
        let newPeer = HoldingPeer(hold: FetchHold())
        newPeer.holdFetch = false
        await session.signPhonePeerChallenge(signer: signer, peer: newPeer)
        XCTAssertEqual(signer.signs, 2)
        XCTAssertEqual(newPeer.posts, 1)
        let newPublicKey = session.signedPhonePublicKey
        XCTAssertNotNil(newPublicKey)
        XCTAssertEqual(signer.discards, 1, "Only the superseded stage is cleaned before the new sign")
        await oldHold.release()
        await old.value
        XCTAssertEqual(signer.discards, 1, "The late old completion cannot discard the new stage")
        XCTAssertEqual(session.signedPhonePublicKey, newPublicKey)
        XCTAssertEqual(oldPeer.posts, 0)
    }
}
