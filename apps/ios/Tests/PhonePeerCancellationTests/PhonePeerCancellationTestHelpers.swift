import CryptoKit
import Foundation
@testable import RunSpecimenObserve

func testPublicKey(_ suffix: String) -> Data {
    var data = Data(repeating: 0x04, count: 65)
    let suffixBytes = Array(suffix.utf8)
    for (i, byte) in suffixBytes.prefix(32).enumerated() {
        data[1 + i] = byte
    }
    return data
}

@MainActor
final class HoldingPeer: PhonePeerTransport {
    let hold: FetchHold
    var holdFetch = true
    var holdBeforePost = false
    var holdDuringPost = false
    var holdVerification = false
    var posts = 0
    var invalidations = 0
    var published = false
    var verification: PhoneHolderVerification?

    init(hold: FetchHold) {
        self.hold = hold
    }

    func fetchPhonePeerChallenge() async throws -> PhonePeerChallengeMessage {
        if holdFetch {
            try await hold.enter()
        }
        return PhonePeerChallengeMessage(
            challengeId: "nonce-1",
            challenge: "Y2hhbGxlbmdl",
            generation: 1,
            holderId: "holder",
            expiry: 1,
            role: "phone"
        )
    }

    func willSubmitPhonePeerSignature() async throws {
        if holdBeforePost {
            try await hold.enter()
        }
    }

    func submitPhonePeerSignature(
        challengeId: String,
        challenge: String,
        publicKey: String,
        signature: String
    ) async throws {
        posts += 1
        published = true
        if holdDuringPost {
            try await hold.enter()
        }
    }

    func invalidatePhonePeerChallenge(challengeId: String) async throws {
        invalidations += 1
        verification = PhoneHolderVerification(verified: false, consumed: false, invalidated: true)
    }

    func fetchHolderVerification(challengeId: String) async throws -> PhoneHolderVerification {
        if holdVerification {
            try await hold.enter()
        }
        return verification ?? PhoneHolderVerification(verified: false, consumed: false, invalidated: false)
    }
}

final class CountingSigner: PhoneChallengeSigning {
    var signs = 0
    var committedSigns = 0
    var commits = 0
    var failCommits = 0
    var refuseCommitted = false
    var lastMessage = Data()
    func sign(message: Data) throws -> (publicKey: String, signature: String) {
        signs += 1
        lastMessage = message
        return ("cHVibGlj", "c2ln")
    }
    func signCommitted(message: Data) throws -> (publicKey: String, signature: String) {
        if refuseCommitted {
            throw CompanionClientError.transport("phone session key is not enrolled")
        }
        committedSigns += 1
        lastMessage = message
        return ("cHVibGlj", "c2ln")
    }
    func commitEnrollment(ownedBy challengeId: String, publicKey: String) throws {
        if failCommits > 0 {
            failCommits -= 1
            throw CompanionClientError.transport("phone custody commit failed")
        }
        commits += 1
    }
}

final class RecordingExactPeer: ExactRunPhoneSigningTransport {
    var fetched: FetchedExactRun
    var replacement: FetchedExactRun?
    var fetches = 0
    var submittedNonce = ""
    var submittedSignature = ""
    var submissions = 0
    var hold: FetchHold?
    init(fetched: FetchedExactRun, hold: FetchHold? = nil) {
        self.fetched = fetched
        self.hold = hold
    }
    func fetchRetainedExactRun() async throws -> FetchedExactRun {
        fetches += 1
        if let hold, fetches == 1 {
            try await hold.enter()
        }
        if fetches > 1, let replacement {
            return replacement
        }
        return fetched
    }
    func submitRetainedExactRunSignature(challengeId: String, signature: String) async throws {
        submissions += 1
        submittedNonce = challengeId
        submittedSignature = signature
    }
}

func sampleFetchedExactRun(policy: String = "companion", nonce: String = "nonce-kept", expiry: Int = 1_800_000_000) -> FetchedExactRun {
    let digest = String(repeating: "ab", count: 32)
    let bound = canonicalExactRunBound(
        holderId: "holder-a",
        payloadDigest: digest,
        launchArgv: ["/usr/bin/true", "script"],
        nonce: nonce,
        policy: policy,
        generation: 3,
        keyGeneration: 1,
        expiry: expiry
    )
    return FetchedExactRun(
        challengeId: nonce,
        bound: bound,
        policy: policy,
        generation: 3,
        keyGeneration: 1,
        expiry: expiry
    )
}

actor FetchHold {
    private var waiters: [CheckedContinuation<Void, any Error>] = []
    private(set) var entered = false
    private var cancellationObserved = false
    private var cancellationWaiters: [CheckedContinuation<Void, Never>] = []

    func enter() async throws {
        entered = true
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                waiters.append(continuation)
            }
        } onCancel: {
            Task { await self.signalCancellationObserved() }
        }
    }

    private func signalCancellationObserved() {
        cancellationObserved = true
        let pending = cancellationWaiters
        cancellationWaiters = []
        for waiter in pending {
            waiter.resume()
        }
    }

    func waitForCancellationObserved() async {
        if cancellationObserved {
            return
        }
        await withCheckedContinuation { continuation in
            cancellationWaiters.append(continuation)
        }
    }

    func resetCancellationState() {
        cancellationObserved = false
        cancellationWaiters = []
    }

    func cancelAllWaiters() {
        let pending = waiters
        waiters = []
        for continuation in pending {
            continuation.resume(throwing: CancellationError())
        }
    }

    func release() {
        let pending = waiters
        waiters = []
        for continuation in pending {
            continuation.resume(returning: ())
        }
    }
}


@MainActor
func testDelayedFetchThenCancelDoesNotSignOrPost() async throws {
    let hold = FetchHold()
    let peer = HoldingPeer(hold: hold)
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    let task = Task { await session.signPhonePeerChallenge(signer: signer, peer: peer) }
    while await hold.entered == false {
        await Task.yield()
    }
    await session.cancelPhonePeerChallenge()
    await hold.release()
    await task.value
    if signer.signs != 0 || peer.posts != 0 {
        throw TestFailure.cancelledPathSignedOrPosted
    }
}

@MainActor
func testCancelBeforePostDoesNotPublish() async throws {
    let hold = FetchHold()
    let peer = HoldingPeer(hold: hold)
    peer.holdFetch = false
    peer.holdBeforePost = true
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    let task = Task { await session.signPhonePeerChallenge(signer: signer, peer: peer) }
    while await hold.entered == false {
        await Task.yield()
    }
    await session.cancelPhonePeerChallenge()
    await hold.release()
    await task.value
    if peer.posts != 0 || signer.commits != 0 {
        throw TestFailure.cancelBeforePostStillPublished
    }
    if session.phonePeerNote != "Phone peer challenge cancelled before a signature was returned." {
        throw TestFailure.wrongCancellationNote
    }
}

@MainActor
func testPostThatAlreadyLeftIsCancellationTooLate() async throws {
    let hold = FetchHold()
    let peer = HoldingPeer(hold: hold)
    peer.holdFetch = false
    peer.holdDuringPost = true
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    let task = Task { await session.signPhonePeerChallenge(signer: signer, peer: peer) }
    while peer.published == false {
        await Task.yield()
    }
    await session.cancelPhonePeerChallenge()
    await hold.release()
    await task.value
    if peer.posts != 1 || peer.invalidations != 1 || signer.commits != 0 {
        throw TestFailure.lateCancelEnrolled
    }
    if session.phonePeerNote != "Phone peer challenge cancellation was too late. The signature left the device and must not enroll." {
        throw TestFailure.lateCancelLookedLikeNoSignature
    }
}

func signedPhoneReceipt(
    key: P256.Signing.PrivateKey,
    challenge: PhonePeerChallengeMessage,
    phonePublic: String,
    generation: Int? = nil,
    challengeId: String? = nil
) throws -> PhoneHolderVerification {
    let mac = key.publicKey.x963Representation.base64EncodedString()
    let canonical = phoneReceiptCanonical(
        challenge: challenge.challenge,
        challengeId: challengeId ?? challenge.challengeId,
        generation: generation ?? challenge.generation,
        holderId: challenge.holderId,
        macPublicKey: mac,
        phoneFingerprint: phoneKeyFingerprint(phonePublic)
    )
    let signature = try key.signature(for: Data(canonical.utf8)).rawRepresentation.base64EncodedString()
    return PhoneHolderVerification(
        verified: true,
        consumed: true,
        invalidated: false,
        challengeId: challengeId ?? challenge.challengeId,
        receipt: Data(canonical.utf8).base64EncodedString(),
        signature: signature,
        macPublicKey: mac,
        phoneFingerprint: phoneKeyFingerprint(phonePublic),
        holderId: challenge.holderId,
        generation: generation ?? challenge.generation,
        outcome: "verified-consumed"
    )
}

@MainActor
func testForgedFlagsWrongKeyChallengeReplayCancelAndStaleDoNotCommit() async throws {
    let peer = HoldingPeer(hold: FetchHold())
    peer.holdFetch = false
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    let task = Task { await session.signPhonePeerChallenge(signer: signer, peer: peer) }
    await task.value
    guard let challenge = session.phoneChallenge else { throw TestFailure.holderVerificationDidNotEnroll }
    let mac = P256.Signing.PrivateKey()
    session.macSessionPublicKey = mac.publicKey.x963Representation.base64EncodedString()
    peer.verification = PhoneHolderVerification(verified: true, consumed: true, invalidated: false)
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 0 { throw TestFailure.mailboxAcceptanceEnrolled }
    let wrong = P256.Signing.PrivateKey()
    peer.verification = try signedPhoneReceipt(key: wrong, challenge: challenge, phonePublic: "cHVibGlj")
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 0 { throw TestFailure.mailboxAcceptanceEnrolled }
    peer.verification = try signedPhoneReceipt(
        key: mac, challenge: challenge, phonePublic: "cHVibGlj", challengeId: "other-challenge"
    )
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 0 { throw TestFailure.mailboxAcceptanceEnrolled }
    peer.verification = try signedPhoneReceipt(
        key: mac, challenge: challenge, phonePublic: "cHVibGlj", generation: 99
    )
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 0 { throw TestFailure.mailboxAcceptanceEnrolled }
    var cancelled = try signedPhoneReceipt(key: mac, challenge: challenge, phonePublic: "cHVibGlj")
    cancelled.invalidated = true
    peer.verification = cancelled
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 0 { throw TestFailure.mailboxAcceptanceEnrolled }
    let good = try signedPhoneReceipt(key: mac, challenge: challenge, phonePublic: "cHVibGlj")
    peer.verification = good
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 1 { throw TestFailure.holderVerificationDidNotEnroll }
    session.phoneChallenge = challenge
    peer.verification = good
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 1 { throw TestFailure.mailboxAcceptanceEnrolled }
}

@MainActor
func testDelayedReceiptThenCancelDoesNotCommit() async throws {
    let hold = FetchHold()
    let peer = HoldingPeer(hold: hold)
    peer.holdFetch = false
    peer.holdVerification = true
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    let mac = P256.Signing.PrivateKey()
    session.macSessionPublicKey = mac.publicKey.x963Representation.base64EncodedString()
    let challenge = PhonePeerChallengeMessage(
        challengeId: "nonce-1",
        challenge: "Y2hhbGxlbmdl",
        generation: 1,
        holderId: "holder",
        expiry: 1,
        role: "phone"
    )
    session.phoneChallenge = challenge
    session.signedPhonePublicKey = "cHVibGlj"
    peer.verification = try signedPhoneReceipt(key: mac, challenge: challenge, phonePublic: "cHVibGlj")
    let task = Task { await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer) }
    while await hold.entered == false {
        await Task.yield()
    }
    await session.cancelPhonePeerChallenge()
    await hold.release()
    await task.value
    if signer.commits != 0 {
        throw TestFailure.lateCancelEnrolled
    }
}

@MainActor
func testDelayedReceiptThenNewChallengeDoesNotCommit() async throws {
    let hold = FetchHold()
    let peer = HoldingPeer(hold: hold)
    peer.holdVerification = true
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    let mac = P256.Signing.PrivateKey()
    session.macSessionPublicKey = mac.publicKey.x963Representation.base64EncodedString()
    let challenge = PhonePeerChallengeMessage(
        challengeId: "nonce-1",
        challenge: "Y2hhbGxlbmdl",
        generation: 1,
        holderId: "holder",
        expiry: 1,
        role: "phone"
    )
    session.phoneChallenge = challenge
    session.signedPhonePublicKey = "cHVibGlj"
    peer.verification = try signedPhoneReceipt(key: mac, challenge: challenge, phonePublic: "cHVibGlj")
    let task = Task { await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer) }
    while await hold.entered == false {
        await Task.yield()
    }
    peer.holdFetch = false
    let newer = Task { await session.signPhonePeerChallenge(signer: signer, peer: peer) }
    await newer.value
    await hold.release()
    await task.value
    if signer.commits != 0 {
        throw TestFailure.lateCancelEnrolled
    }
}

@MainActor
func testFailedCommitThenRetryEnrolls() async throws {
    let peer = HoldingPeer(hold: FetchHold())
    let signer = CountingSigner()
    signer.failCommits = 1
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    let mac = P256.Signing.PrivateKey()
    session.macSessionPublicKey = mac.publicKey.x963Representation.base64EncodedString()
    let challenge = PhonePeerChallengeMessage(
        challengeId: "nonce-1",
        challenge: "Y2hhbGxlbmdl",
        generation: 1,
        holderId: "holder",
        expiry: 1,
        role: "phone"
    )
    session.phoneChallenge = challenge
    session.signedPhonePublicKey = "cHVibGlj"
    peer.verification = try signedPhoneReceipt(key: mac, challenge: challenge, phonePublic: "cHVibGlj")
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 0 || session.phoneChallenge == nil {
        throw TestFailure.injectedCommitFailureDidNotStop
    }
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 1 {
        throw TestFailure.holderVerificationDidNotEnroll
    }
}

@MainActor
func testExactRunSignatureUsesTheFetchedNonce() async throws {
    let fetched = sampleFetchedExactRun()
    let peer = RecordingExactPeer(fetched: fetched)
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    session.pinnedHolderId = "holder-a"
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    if session.reviewedExactRunLines.contains("policy companion") == false
        || session.reviewedExactRunLines.contains("holder holder-a") == false
        || session.reviewedExactRunArgv != ["/usr/bin/true", "script"] {
        throw TestFailure.holderVerificationDidNotEnroll
    }
    await session.approveReviewedExactRun(signer: signer, peer: peer)
    if peer.submittedNonce != "nonce-kept" || signer.lastMessage != fetched.bound || signer.committedSigns != 1 || signer.signs != 0 {
        throw TestFailure.holderVerificationDidNotEnroll
    }
}

@MainActor
func testExactRunCancelDuringReviewDoesNotSign() async throws {
    let hold = FetchHold()
    let peer = RecordingExactPeer(fetched: sampleFetchedExactRun(), hold: hold)
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    session.pinnedHolderId = "holder-a"
    let task = Task { await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer) }
    while await hold.entered == false {
        await Task.yield()
    }
    session.cancelExactRunReview()
    await hold.release()
    await task.value
    await session.approveReviewedExactRun(signer: signer, peer: peer)
    let lines = session.reviewedExactRunLines
    if signer.committedSigns != 0 || signer.signs != 0 || peer.submissions != 0 || lines.isEmpty == false {
        throw TestFailure.lateCancelEnrolled
    }
}

@MainActor
func testExactRunReplacementDoesNotSubmit() async throws {
    let peer = RecordingExactPeer(fetched: sampleFetchedExactRun())
    peer.replacement = sampleFetchedExactRun(nonce: "nonce-other")
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    session.pinnedHolderId = "holder-a"
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    await session.approveReviewedExactRun(signer: signer, peer: peer)
    if peer.submissions != 0 || signer.committedSigns != 1 {
        throw TestFailure.lateCancelEnrolled
    }
}

@MainActor
func testExactRunMalformedBoundDoesNotSign() async throws {
    let fetched = FetchedExactRun(
        challengeId: "nonce-kept",
        bound: Data("not-canonical".utf8),
        policy: "companion",
        generation: 3,
        keyGeneration: 1,
        expiry: 1_800_000_000
    )
    let peer = RecordingExactPeer(fetched: fetched)
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    session.pinnedHolderId = "holder-a"
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    await session.approveReviewedExactRun(signer: signer, peer: peer)
    if signer.signs != 0 || signer.committedSigns != 0 || peer.submissions != 0 {
        throw TestFailure.lateCancelEnrolled
    }
}

@MainActor
func testExactRunMissingKeyDoesNotSubmit() async throws {
    let peer = RecordingExactPeer(fetched: sampleFetchedExactRun(policy: "dual"))
    let signer = CountingSigner()
    signer.refuseCommitted = true
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    session.pinnedHolderId = "holder-a"
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    await session.approveReviewedExactRun(signer: signer, peer: peer)
    if signer.committedSigns != 0 || signer.signs != 0 || peer.submissions != 0 {
        throw TestFailure.lateCancelEnrolled
    }
}

@MainActor
func testExactRunExpiryBeforeApproveDoesNotSign() async throws {
    let peer = RecordingExactPeer(fetched: sampleFetchedExactRun(expiry: 1_800_000_000))
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    session.pinnedHolderId = "holder-a"
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    await session.approveReviewedExactRun(signer: signer, peer: peer, now: { 1_800_000_000 })
    if signer.committedSigns != 0 || signer.signs != 0 || peer.submissions != 0 {
        throw TestFailure.lateCancelEnrolled
    }
}

@MainActor
func testExactRunExpiryAfterWaitDoesNotSubmit() async throws {
    let peer = RecordingExactPeer(fetched: sampleFetchedExactRun(expiry: 1_800_000_000))
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    session.pinnedHolderId = "holder-a"
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    var calls = 0
    await session.approveReviewedExactRun(signer: signer, peer: peer, now: {
        calls += 1
        return calls == 1 ? 1_700_000_000 : 1_900_000_000
    })
    if signer.committedSigns != 1 || peer.submissions != 0 {
        throw TestFailure.lateCancelEnrolled
    }
}

@MainActor
func testExactRunCancellationBeforeSignDoesNotSign() async throws {
    let hold = FetchHold()
    let peer = RecordingExactPeer(fetched: sampleFetchedExactRun())
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    session.pinnedHolderId = "holder-a"
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    let task = Task {
        await session.approveReviewedExactRun(signer: signer, peer: peer, now: { 1_700_000_000 }, beforeSign: {
            try? await hold.enter()
        })
    }
    while await hold.entered == false {
        await Task.yield()
    }
    task.cancel()
    await hold.waitForCancellationObserved()
    await hold.release()
    await task.value
    if signer.committedSigns != 0 || signer.signs != 0 || peer.submissions != 0 {
        throw TestFailure.cancelledPathSignedOrPosted
    }
}

@MainActor
func testExactRunCancellationBeforeSubmitDoesNotSubmit() async throws {
    let peer = RecordingExactPeer(fetched: sampleFetchedExactRun())
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    session.pinnedHolderId = "holder-a"
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    await session.approveReviewedExactRun(signer: signer, peer: peer, now: { 1_700_000_000 }, beforeSubmit: {
        session.cancelExactRunReview()
    })
    if signer.committedSigns != 1 || peer.submissions != 0 {
        throw TestFailure.cancelledPathSignedOrPosted
    }
}

@MainActor
func testExactRunUnpinnedHolderDoesNotSign() async throws {
    let peer = RecordingExactPeer(fetched: sampleFetchedExactRun())
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    await session.approveReviewedExactRun(signer: signer, peer: peer, now: { 1_700_000_000 })
    if signer.committedSigns != 0 || peer.submissions != 0 || session.reviewedExactRunLines.isEmpty == false {
        throw TestFailure.mailboxAcceptanceEnrolled
    }
}

@MainActor
func testExactRunSubstitutedHolderDoesNotSign() async throws {
    let peer = RecordingExactPeer(fetched: sampleFetchedExactRun())
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    session.pinnedHolderId = "holder-b"
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    await session.approveReviewedExactRun(signer: signer, peer: peer, now: { 1_700_000_000 })
    if signer.committedSigns != 0 || peer.submissions != 0 || session.reviewedExactRunLines.isEmpty == false {
        throw TestFailure.mailboxAcceptanceEnrolled
    }
}

func testPhoneKeyOwnershipRejectsADifferentChallenge() throws {
    let directory = URL(fileURLWithPath: "/private/tmp/rs-qa-own-phone-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let stage = PhoneKeyStage(directory: directory)
    let publicKey = testPublicKey("public-a")
    try stage.stage(handle: Data("handle-a".utf8), publicKey: publicKey, challengeId: "nonce-a")
    do {
        try stage.commit(ownedBy: "nonce-b", publicKey: publicKey)
        throw TestFailure.lateCancelEnrolled
    } catch {
    }
    if FileManager.default.fileExists(atPath: directory.appendingPathComponent("custody.json").path) {
        throw TestFailure.lateCancelEnrolled
    }
    try stage.commit(ownedBy: "nonce-a", publicKey: publicKey)
    let generation = try stage.committedGeneration()
    let committed = try stage.committedPublicKey()
    if generation != 1 || committed != publicKey {
        throw TestFailure.rollbackLostPreviousKey
    }
}

func testPhoneKeyCommitFailureKeepsThePreviousGeneration() throws {
    let directory = URL(fileURLWithPath: "/private/tmp/rs-qa-bind-phone-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let stage = PhoneKeyStage(directory: directory)
    let pubKeyA = testPublicKey("public-a")
    let pubKeyB = testPublicKey("public-b")
    try stage.stage(handle: Data("previous".utf8), publicKey: pubKeyA)
    try stage.commit()
    let generation = try stage.committedGeneration()
    let publicKey = try stage.committedPublicKey()
    if generation != 1 || publicKey != pubKeyA {
        throw TestFailure.rollbackLostPreviousKey
    }
    try stage.rotate(handle: Data("next".utf8), publicKey: pubKeyB)
    do {
        try stage.commit(failAfterFirstWrite: true)
        throw TestFailure.injectedCommitFailureDidNotStop
    } catch {
    }
    if try stage.committedGeneration() != 1 {
        throw TestFailure.rollbackLostPreviousKey
    }
    let handle = try stage.committedHandle()
    let keptPublic = try stage.committedPublicKey()
    if handle != Data("previous".utf8) || keptPublic != pubKeyA {
        throw TestFailure.rollbackLostPreviousKey
    }
}

func testPhoneKeyStageRollsBackAndRevokes() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    let stage = PhoneKeyStage(directory: directory)
    let pubKeyA = testPublicKey("public-a")
    let pubKeyB = testPublicKey("public-b")
    try stage.stage(handle: Data("previous".utf8), publicKey: pubKeyA)
    try stage.commit()
    try stage.rotate(handle: Data("next".utf8), publicKey: pubKeyB)
    stage.discard()
    let reloaded = try stage.committedHandle()
    if reloaded != Data("previous".utf8) {
        throw TestFailure.rollbackLostPreviousKey
    }
    try stage.revoke()
    do {
        _ = try stage.committedHandle()
        throw TestFailure.revokedKeyStillReloaded
    } catch {
        return
    }
}

@MainActor
func testRevokePhonePeerKeyClearsExactRunState() async throws {
    let session = CompanionSession()
    session.reviewedExactRunLines = ["test line"]
    session.reviewedExactRunArgv = ["/usr/bin/test"]
    
    let previousGeneration = session.testExactRunGeneration
    
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("revoke-exact-clear-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    
    do {
        try session.revokePhonePeerKey()
    } catch {
    }
    
    if session.testExactRunGeneration <= previousGeneration {
        throw TestFailure.exactRunNotCleared
    }
    if !session.reviewedExactRunLines.isEmpty || !session.reviewedExactRunArgv.isEmpty {
        throw TestFailure.exactRunNotCleared
    }
}

@MainActor
func testRotatePhonePeerKeyClearsExactRunState() async throws {
    let session = CompanionSession()
    session.reviewedExactRunLines = ["test line"]
    session.reviewedExactRunArgv = ["/usr/bin/test"]
    
    let previousGeneration = session.testExactRunGeneration
    
    do {
        try session.rotatePhonePeerKey()
    } catch {
    }
    
    if session.testExactRunGeneration <= previousGeneration {
        throw TestFailure.exactRunNotCleared
    }
    if !session.reviewedExactRunLines.isEmpty || !session.reviewedExactRunArgv.isEmpty {
        throw TestFailure.exactRunNotCleared
    }
}

@MainActor
func testCancelAllTasksCancelsInFlightPhonePeerOperation() async throws {
    let hold = FetchHold()
    let peer = HoldingPeer(hold: hold)
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    
    let task = Task {
        await session.signPhonePeerChallenge(signer: signer, peer: peer)
    }
    
    while await hold.entered == false {
        await Task.yield()
    }
    
    session.cancelAllTasks()
    await hold.release()
    await task.value
    
    if signer.signs != 0 || peer.posts != 0 {
        throw TestFailure.cancelAllTasksDidNotCancelOperation
    }
}

@MainActor
func testDisconnectCancelsInFlightPhonePeerOperation() async throws {
    let hold = FetchHold()
    let peer = HoldingPeer(hold: hold)
    let signer = CountingSigner()
    let session = CompanionSession()
    session.isPaired = true
    session.capabilities = CompanionCapabilities(
        product: "test",
        mode: "observe",
        canApprove: false,
        canExecute: false,
        canMutateLifecycle: false,
        canRemoteConfirm: true,
        boundary: "test"
    )
    
    let task = Task {
        await session.signPhonePeerChallenge(signer: signer, peer: peer)
    }
    
    while await hold.entered == false {
        await Task.yield()
    }
    
    session.disconnect()
    await hold.release()
    await task.value
    
    if signer.signs != 0 || peer.posts != 0 {
        throw TestFailure.disconnectDidNotCancelOperation
    }
}

enum TestFailure: Error {
    case cancelledPathSignedOrPosted
    case rollbackLostPreviousKey
    case revokedKeyStillReloaded
    case cancelBeforePostStillPublished
    case wrongCancellationNote
    case lateCancelEnrolled
    case lateCancelLookedLikeNoSignature
    case mailboxAcceptanceEnrolled
    case holderVerificationDidNotEnroll
    case injectedCommitFailureDidNotStop
    case exactRunNotCleared
    case cancelAllTasksDidNotCancelOperation
    case disconnectDidNotCancelOperation
}
