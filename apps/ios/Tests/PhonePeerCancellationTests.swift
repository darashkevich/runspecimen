import CryptoKit
import Foundation

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
            await hold.enter()
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
            await hold.enter()
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
            await hold.enter()
        }
    }

    func invalidatePhonePeerChallenge(challengeId: String) async throws {
        invalidations += 1
        verification = PhoneHolderVerification(verified: false, consumed: false, invalidated: true)
    }

    func fetchHolderVerification(challengeId: String) async throws -> PhoneHolderVerification {
        if holdVerification {
            await hold.enter()
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
            await hold.enter()
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
    private var waiters: [CheckedContinuation<Void, Never>] = []
    private(set) var entered = false

    func enter() async {
        entered = true
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func release() {
        let pending = waiters
        waiters = []
        for continuation in pending {
            continuation.resume()
        }
    }
}

@main
struct PhonePeerCancellationTests {
    static func main() async {
        do {
            try await testDelayedFetchThenCancelDoesNotSignOrPost()
            try await testCancelBeforePostDoesNotPublish()
            try await testPostThatAlreadyLeftIsCancellationTooLate()
            try await testForgedFlagsWrongKeyChallengeReplayCancelAndStaleDoNotCommit()
            try await testDelayedReceiptThenCancelDoesNotCommit()
            try await testDelayedReceiptThenNewChallengeDoesNotCommit()
            try await testFailedCommitThenRetryEnrolls()
            try await testExactRunSignatureUsesTheFetchedNonce()
            try await testExactRunCancelDuringReviewDoesNotSign()
            try await testExactRunReplacementDoesNotSubmit()
            try await testExactRunMalformedBoundDoesNotSign()
            try await testExactRunMissingKeyDoesNotSubmit()
            try testPhoneKeyOwnershipRejectsADifferentChallenge()
            try testPhoneKeyStageRollsBackAndRevokes()
            try testPhoneKeyCommitFailureKeepsThePreviousGeneration()
            print("PhonePeerCancellationTests passed")
        } catch {
            fputs("PhonePeerCancellationTests failed: \(error)\n", stderr)
            exit(1)
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
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    if session.reviewedExactRunLines.contains("policy companion") == false
        || session.reviewedExactRunLines.contains("holder holder-a") == false
        || session.reviewedExactRunLines.contains("argv /usr/bin/true script") == false {
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
    await session.reviewRetainedExactRun(now: 1_700_000_000, peer: peer)
    await session.approveReviewedExactRun(signer: signer, peer: peer)
    if signer.committedSigns != 0 || signer.signs != 0 || peer.submissions != 0 {
        throw TestFailure.lateCancelEnrolled
    }
}

func testPhoneKeyOwnershipRejectsADifferentChallenge() throws {
    let directory = URL(fileURLWithPath: "/private/tmp/rs-qa-own-phone-\(UUID().uuidString)", isDirectory: true)
    let stage = PhoneKeyStage(directory: directory)
    let publicKey = Data("public-a".utf8)
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
    let stage = PhoneKeyStage(directory: directory)
    try stage.stage(handle: Data("previous".utf8), publicKey: Data("public-a".utf8))
    try stage.commit()
    let generation = try stage.committedGeneration()
    let publicKey = try stage.committedPublicKey()
    if generation != 1 || publicKey != Data("public-a".utf8) {
        throw TestFailure.rollbackLostPreviousKey
    }
    try stage.rotate(handle: Data("next".utf8), publicKey: Data("public-b".utf8))
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
    if handle != Data("previous".utf8) || keptPublic != Data("public-a".utf8) {
        throw TestFailure.rollbackLostPreviousKey
    }
}

func testPhoneKeyStageRollsBackAndRevokes() throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    let stage = PhoneKeyStage(directory: directory)
    try stage.stage(handle: Data("previous".utf8), publicKey: Data("public-a".utf8))
    try stage.commit()
    try stage.rotate(handle: Data("next".utf8), publicKey: Data("public-b".utf8))
    stage.discard()
    let reloaded = try stage.committedHandle()
    if reloaded != Data("previous".utf8) {
        throw TestFailure.rollbackLostPreviousKey
    }
    stage.revoke()
    do {
        _ = try stage.committedHandle()
        throw TestFailure.revokedKeyStillReloaded
    } catch {
        return
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
}
