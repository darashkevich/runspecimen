import Foundation

/// A consequential command waiting for an explicit human confirmation.
public struct WorkflowRequest: Equatable, Sendable, Identifiable {
    public let id: UUID
    public var title: String
    public var detail: String
    public var arguments: [String]

    public init(id: UUID = UUID(), title: String, detail: String, arguments: [String]) {
        self.id = id
        self.title = title
        self.detail = detail
        self.arguments = arguments
    }
}

/// Holds one unconfirmed workflow and the single claim that may execute it.
///
/// `confirm()` takes the request synchronously. A later `cancel()` — the dialog
/// dismissing — does not revoke that claim. `cancel()` before `confirm()` leaves
/// nothing to run. A second confirm, or a confirm while an execution is busy,
/// returns nil.
public struct WorkflowConfirmationGate {
    public private(set) var pending: WorkflowRequest?
    public private(set) var isExecuting = false
    public private(set) var completedExecutions = 0
    private var claimed: WorkflowRequest?

    public init() {}

    public mutating func present(_ request: WorkflowRequest) {
        guard !isExecuting, claimed == nil else { return }
        pending = request
    }

    /// Returns the pending request once. The caller must pass that value into
    /// the later execution; do not read `pending` again after an await.
    public mutating func confirm() -> WorkflowRequest? {
        guard !isExecuting, claimed == nil, let pending else { return nil }
        claimed = pending
        self.pending = nil
        return pending
    }

    public mutating func cancel() {
        pending = nil
    }

    /// Starts the claimed execution once. A second call, or a different request, does nothing.
    public mutating func beginExecution(of request: WorkflowRequest) -> Bool {
        guard !isExecuting, let claimed, claimed == request else { return false }
        isExecuting = true
        return true
    }

    public mutating func finishExecution() {
        guard isExecuting else { return }
        isExecuting = false
        claimed = nil
        completedExecutions += 1
    }

    /// Drops a claim that must not be counted, for example when the app is already busy.
    public mutating func abandonExecution() {
        guard isExecuting else { return }
        isExecuting = false
        claimed = nil
    }
}
