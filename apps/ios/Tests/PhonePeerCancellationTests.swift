import Foundation

@MainActor
final class HoldingPeer: PhonePeerTransport {
    let hold: FetchHold
    var holdFetch = true
    var holdBeforePost = false
    var holdDuringPost = false
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
        verification ?? PhoneHolderVerification(verified: false, consumed: false, invalidated: false)
    }
}

final class CountingSigner: PhoneChallengeSigning {
    var signs = 0
    var commits = 0
    func sign(message: Data) throws -> (publicKey: String, signature: String) {
        signs += 1
        return ("cHVibGlj", "c2ln")
    }
    func commitEnrollment() throws {
        commits += 1
    }
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
            try await testPhoneKeyCommitsOnlyAfterHolderVerification()
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

@MainActor
func testPhoneKeyCommitsOnlyAfterHolderVerification() async throws {
    let peer = HoldingPeer(hold: FetchHold())
    peer.holdFetch = false
    let signer = CountingSigner()
    let session = CompanionSession()
    let task = Task { await session.signPhonePeerChallenge(signer: signer, peer: peer) }
    await task.value
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 0 {
        throw TestFailure.mailboxAcceptanceEnrolled
    }
    peer.verification = PhoneHolderVerification(verified: true, consumed: false, invalidated: false)
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 0 {
        throw TestFailure.mailboxAcceptanceEnrolled
    }
    peer.verification = PhoneHolderVerification(verified: true, consumed: true, invalidated: false)
    await session.commitPhoneKeyAfterHolderVerification(signer: signer, peer: peer)
    if signer.commits != 1 {
        throw TestFailure.holderVerificationDidNotEnroll
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
