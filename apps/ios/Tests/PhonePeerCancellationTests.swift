import Foundation

@MainActor
final class HoldingPeer: PhonePeerTransport {
    let hold: FetchHold
    var posts = 0

    init(hold: FetchHold) {
        self.hold = hold
    }

    func fetchPhonePeerChallenge() async throws -> PhonePeerChallengeMessage {
        await hold.enter()
        return PhonePeerChallengeMessage(
            challengeId: "nonce-1",
            challenge: "Y2hhbGxlbmdl",
            generation: 1,
            holderId: "holder",
            expiry: 1,
            role: "phone"
        )
    }

    func submitPhonePeerSignature(
        challengeId: String,
        challenge: String,
        publicKey: String,
        signature: String
    ) async throws {
        posts += 1
    }
}

final class CountingSigner: PhoneChallengeSigning {
    var signs = 0
    func sign(message: Data) throws -> (publicKey: String, signature: String) {
        signs += 1
        return ("cHVibGlj", "c2ln")
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
            try testPhoneKeyStageRollsBackAndRevokes()
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
}
