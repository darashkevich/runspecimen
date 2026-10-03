import XCTest
import RunSpecimenCore
@testable import RunSpecimenApp

@MainActor
final class AppModelWorkflowContextTests: XCTestCase {
    func testContractAndWorkspaceHandlersDropPendingWork() {
        let model = AppModel()
        model.noteWorkspaceSelection(URL(fileURLWithPath: "/ws"))
        model.noteContractSelection(URL(fileURLWithPath: "/ws/contract.json"))
        model.stageWorkflow(retain(out: "/dest-a"))
        XCTAssertEqual(model.pendingWorkflow?.workspacePath, "/ws")
        XCTAssertEqual(model.pendingWorkflow?.contractPath, "/ws/contract.json")
        XCTAssertEqual(model.pendingWorkflow?.arguments, ["retain", "--out", "/dest-a"])

        model.noteContractSelection(URL(fileURLWithPath: "/ws/other.json"))
        XCTAssertNil(model.pendingWorkflow)
        XCTAssertEqual(model.contractURL?.path, "/ws/other.json")

        model.noteContractSelection(URL(fileURLWithPath: "/ws/contract.json"))
        model.stageWorkflow(retain(out: "/dest-a"))
        model.noteWorkspaceSelection(URL(fileURLWithPath: "/other"))
        XCTAssertNil(model.pendingWorkflow)
        XCTAssertNil(model.contractURL)
        XCTAssertEqual(model.workspaceURL?.path, "/other")
    }

    func testClaimRefusesARequestWhoseContextNoLongerMatches() {
        let model = AppModel()
        model.workspaceURL = URL(fileURLWithPath: "/ws")
        model.contractURL = URL(fileURLWithPath: "/ws/contract.json")
        model.stageWorkflow(retain(out: "/dest-a"))
        let id = try! XCTUnwrap(model.pendingWorkflow?.id)
        model.contractURL = URL(fileURLWithPath: "/ws/other.json")
        XCTAssertNil(model.claimConfirmedWorkflow(matching: id))
        XCTAssertNil(model.pendingWorkflow)
    }

    func testAClaimDoesNotRunAfterTheWorkspaceChanges() async {
        let model = AppModel()
        model.noteWorkspaceSelection(URL(fileURLWithPath: "/ws"))
        model.noteContractSelection(URL(fileURLWithPath: "/ws/contract.json"))
        model.stageWorkflow(retain(out: "/dest-a"))
        let id = try! XCTUnwrap(model.pendingWorkflow?.id)
        let claimed = model.claimConfirmedWorkflow(matching: id)
        XCTAssertEqual(claimed?.arguments, ["retain", "--out", "/dest-a"])
        model.noteWorkspaceSelection(URL(fileURLWithPath: "/other"))
        await model.performClaimedWorkflow(claimed!)
        XCTAssertEqual(
            model.expansionReadout,
            "The workspace or contract changed before this workflow ran. Nothing was written."
        )
        XCTAssertNil(model.pendingWorkflow)
    }

    private func retain(out: String) -> WorkflowRequest {
        WorkflowRequest(
            title: "Retain incident pack",
            detail: "Copies into \(out). Cancel copies nothing.",
            arguments: ["retain", "--out", out]
        )
    }
}
