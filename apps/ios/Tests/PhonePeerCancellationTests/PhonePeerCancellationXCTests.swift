import XCTest
@testable import RunSpecimenObserve

final class PhonePeerCancellationXCTests: XCTestCase {

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
