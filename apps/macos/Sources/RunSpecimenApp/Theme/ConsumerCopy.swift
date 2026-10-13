import Foundation

/// Everyday labels for the consumer macOS surface.
/// Engine commands, JSON, and exact bind phrases stay unchanged.
enum ConsumerCopy {
    static let productName = "RunSpecimen"
    static let tagline = "You approve what may run.\nThen you get a receipt you can keep."
    static let emptyLede =
        "When an assistant or a script is about to do something that matters, a green “done” is not enough. You review a short plan, you type APPROVE yourself, and you get a receipt of what actually ran."
    static let staysLocal = "Stays on this Mac. No account. No telemetry."
    static let notASandbox =
        "This does not lock the rest of your Mac. It records what you allowed and whether that is what ran."
    static let approveInvariant =
        "Only you can approve. Assistants cannot type APPROVE, and this app will not type it for you."

    static func phaseHeadline(_ phase: String) -> String {
        switch phase {
        case "none", "": return "Ready when you are"
        case "approved": return "You approved this"
        case "preflighted": return "Ready to run"
        case "running": return "Running now"
        case "completed": return "Finished — check the results"
        case "failed": return "Didn’t finish as planned"
        case "postflighted": return "Results checked"
        default: return phase.capitalized
        }
    }

    static func railLabel(at index: Int) -> String {
        ["You approve", "Get ready", "It runs", "Check results", "Receipt"][index]
    }

    static func railEngineName(at index: Int) -> String {
        ["Approve", "Preflight", "Run", "Postflight", "Verify"][index]
    }
}

struct ConsumerNextStep: Equatable {
    enum Tone: Equatable {
        case calm, action, success, warning, danger
    }

    var title: String
    var body: String
    var action: LifecycleAction?
    var tone: Tone

    static func current(
        phase: String,
        doctorOK: Bool?,
        hasCertificate: Bool,
        isBusy: Bool,
        leaseBusy: Bool
    ) -> ConsumerNextStep {
        if isBusy {
            return ConsumerNextStep(
                title: "Working…",
                body: "Hang on — this step is in progress.",
                action: nil,
                tone: .calm
            )
        }
        if leaseBusy {
            return ConsumerNextStep(
                title: "This folder is busy",
                body: "Another step is using this folder. Wait until it finishes, then try again.",
                action: nil,
                tone: .warning
            )
        }
        if doctorOK == false {
            return ConsumerNextStep(
                title: "The engine needs a moment",
                body: "Check the plan to see what is missing. Nothing will run until this is resolved.",
                action: .validate,
                tone: .warning
            )
        }
        switch phase {
        case "none", "":
            return ConsumerNextStep(
                title: "Next: Review & approve",
                body: "Read what may run, then type APPROVE yourself. Nothing starts until you do.",
                action: .approve,
                tone: .action
            )
        case "approved":
            return ConsumerNextStep(
                title: "Next: Get ready",
                body: "A last check that your yes is still valid and nothing in the plan has changed.",
                action: .preflight,
                tone: .action
            )
        case "preflighted":
            return ConsumerNextStep(
                title: "Next: Start the run",
                body: "This starts the command you already approved — once, not in the background.",
                action: .run,
                tone: .action
            )
        case "running":
            return ConsumerNextStep(
                title: "Running now",
                body: "The approved command is in progress. We’ll check the results when it finishes.",
                action: nil,
                tone: .warning
            )
        case "completed":
            return ConsumerNextStep(
                title: "Next: Check the results",
                body: "Make sure the run did what you allowed. This does not run it again.",
                action: .postflight,
                tone: .action
            )
        case "failed":
            return ConsumerNextStep(
                title: "Didn’t finish as planned",
                body: "Check the results to record what happened. You can read the details without starting anything.",
                action: .postflight,
                tone: .danger
            )
        case "postflighted":
            return ConsumerNextStep(
                title: hasCertificate ? "All good — get the receipt" : "Next: Get the receipt",
                body: "Open the checkable history of this run. Looking does not approve or start anything.",
                action: .verify,
                tone: hasCertificate ? .success : .action
            )
        default:
            return ConsumerNextStep(
                title: "Check where this run stands",
                body: "Refresh to see the latest status. Looking does not approve or start anything.",
                action: .validate,
                tone: .calm
            )
        }
    }
}

struct ConsumerResult: Equatable {
    enum Kind: Equatable {
        case empty, success, warning, problem
    }

    var kind: Kind
    var title: String
    var body: String

    static func from(status: RunStatus?) -> ConsumerResult {
        guard let status else {
            return ConsumerResult(
                kind: .empty,
                title: "Nothing has run yet",
                body: "Check the plan, then review and approve. A receipt appears after the run is recorded."
            )
        }
        if status.eventCount > 0 && !status.eventChainOK {
            return ConsumerResult(
                kind: .problem,
                title: "Something changed",
                body: "The history of this run no longer matches. Open details for the exact fingerprints — nothing was auto-approved."
            )
        }
        if let ok = status.postflightOK, !ok {
            return ConsumerResult(
                kind: .problem,
                title: "Something changed",
                body: "The results did not match what you allowed. The details below keep the full record."
            )
        }
        if status.phase == "failed" {
            return ConsumerResult(
                kind: .problem,
                title: "Didn’t finish as planned",
                body: "The command stopped before it completed. Check the results to keep a record of what happened."
            )
        }
        if status.phase == "postflighted", status.postflightOK == true, status.eventChainOK {
            return ConsumerResult(
                kind: .success,
                title: "All good",
                body: "This run matches what you allowed. The receipt below is a checkable history on this Mac."
            )
        }
        if status.phase == "running" {
            return ConsumerResult(
                kind: .warning,
                title: "Running now",
                body: "The approved command is in progress. This screen is not the receipt yet."
            )
        }
        if status.phase == "completed" {
            return ConsumerResult(
                kind: .warning,
                title: "Finished — check the results",
                body: "The command finished. Check the results to confirm it did what you allowed."
            )
        }
        if !status.hasEvidenceFields {
            return ConsumerResult(
                kind: .empty,
                title: "No receipt yet",
                body: "This run is at “\(ConsumerCopy.phaseHeadline(status.phase))”. A receipt appears after the results are checked."
            )
        }
        return ConsumerResult(
            kind: .warning,
            title: ConsumerCopy.phaseHeadline(status.phase),
            body: "Looking at this history does not approve or start anything."
        )
    }
}

extension LifecycleAction {
    var consumerTitle: String {
        switch self {
        case .validate: return "Check the plan"
        case .approve: return "Review & approve"
        case .preflight: return "Get ready"
        case .run: return "Start the run"
        case .postflight: return "Check results"
        case .verify: return "Get the receipt"
        case .dashboard: return "Open the timeline"
        }
    }

    var consumerConfirmationTitle: String {
        switch self {
        case .run: return "Start this run?"
        case .postflight: return "Check the results now?"
        default: return confirmationTitle
        }
    }

    var consumerConfirmationMessage: String {
        switch self {
        case .run:
            return "This starts the task you already approved. The app will not type APPROVE for you."
        case .postflight:
            return "This checks that the run did what you allowed. It does not run the task again."
        default:
            return confirmationMessage
        }
    }
}
