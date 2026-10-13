import XCTest
@testable import RunSpecimenApp

final class ConsumerCopyTests: XCTestCase {
    func testPhaseHeadlinesAreEverydayLanguage() {
        XCTAssertEqual(ConsumerCopy.phaseHeadline("none"), "Ready when you are")
        XCTAssertEqual(ConsumerCopy.phaseHeadline("approved"), "You approved this")
        XCTAssertEqual(ConsumerCopy.phaseHeadline("running"), "Running now")
        XCTAssertEqual(ConsumerCopy.phaseHeadline("failed"), "Didn’t finish as planned")
        XCTAssertEqual(ConsumerCopy.phaseHeadline("postflighted"), "Results checked")
    }

    func testNextStepAfterApprovalIsGetReady() {
        let step = ConsumerNextStep.current(
            phase: "approved",
            doctorOK: true,
            hasCertificate: false,
            isBusy: false,
            leaseBusy: false
        )
        XCTAssertEqual(step.action, .preflight)
        XCTAssertEqual(step.action?.consumerTitle, "Get ready")
        XCTAssertFalse(step.title.contains("Preflight"))
    }

    func testResultHeroForIntactPostflightIsAllGood() {
        let status = RunStatus(
            phase: "postflighted",
            campaignID: "demo",
            runID: "run-001",
            workspace: "/tmp",
            eventCount: 4,
            eventChainOK: true,
            eventChainMessage: "",
            leaseHeldByOther: false,
            certificateID: "cert-1",
            eventHead: "abc",
            approvalExpiresUnix: nil,
            argv: ["python3", "work/compute.py"],
            contractHash: "aa",
            sourceHash: "bb",
            runtimeID: "cc",
            exitCode: 0,
            postflightOK: true,
            rawJSON: "{}"
        )
        let result = ConsumerResult.from(status: status)
        XCTAssertEqual(result.kind, .success)
        XCTAssertEqual(result.title, "All good")
    }

    func testBrokenHistoryIsSomethingChanged() {
        let status = RunStatus(
            phase: "postflighted",
            campaignID: "demo",
            runID: "run-001",
            workspace: "/tmp",
            eventCount: 4,
            eventChainOK: false,
            eventChainMessage: "mismatch",
            leaseHeldByOther: false,
            certificateID: "cert-1",
            eventHead: "abc",
            approvalExpiresUnix: nil,
            argv: [],
            contractHash: "aa",
            sourceHash: "bb",
            runtimeID: "cc",
            exitCode: 0,
            postflightOK: true,
            rawJSON: "{}"
        )
        let result = ConsumerResult.from(status: status)
        XCTAssertEqual(result.kind, .problem)
        XCTAssertEqual(result.title, "Something changed")
    }

    func testApproveConfirmationStillRefusesToTypeApprove() {
        XCTAssertTrue(LifecycleAction.run.consumerConfirmationMessage.contains("will not type APPROVE"))
        XCTAssertEqual(LifecycleAction.approve.consumerTitle, "Review & approve")
        XCTAssertEqual(LifecycleAction.approve.title, "Approve…")
    }
}
