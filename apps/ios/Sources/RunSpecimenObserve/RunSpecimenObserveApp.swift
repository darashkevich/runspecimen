import SwiftUI
import os

private let appLogger = Logger(subsystem: "com.darashkevich.runspecimen.observe", category: "app")

#if DEBUG
private let launchLogger = Logger(subsystem: "com.darashkevich.runspecimen.observe", category: "launch")
#endif

@main
struct RunSpecimenObserveApp: App {
    @StateObject private var session: CompanionSession

    init() {
        #if DEBUG
        let initStart = CFAbsoluteTimeGetCurrent()
        launchLogger.info("App.init() START at \(initStart, format: .fixed(precision: 3))")
        #endif

        let session = CompanionSession(deferPhoneKeyState: true)
        #if RUNSPECIMEN_TEST_HOOKS
        if ProcessInfo.processInfo.environment["RUNSPECIMEN_UI_RECOVERY_TEST"] == "1" {
            session.testHardwareRecoveryDirectory = Self.testRecoveryFixtureDirectory()
        }
        #endif
        #if RUNSPECIMEN_TEST_HOOKS
        if let scenario = ProcessInfo.processInfo.environment["RUNSPECIMEN_UI_REFRESH_TEST"] {
            session.baseURLString = "http://localhost"
            session.pairingToken = "ui-fixture-only"
            session.isPaired = true
            session.status = CompanionStatus(phase: "active")
            session.capabilities = CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
                canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "UI fixture")
            var fixtureRequests = 0
            session.testMakeClient()?.testRequest = { request in
                fixtureRequests += 1
                if scenario == "cancelled" { throw CancellationError() }
                if scenario == "recover", fixtureRequests > 1 {
                    if request.url?.path == "/v1/status" {
                        return try JSONEncoder().encode(CompanionStatus(phase: "active", campaignId: "button-refresh"))
                    }
                    return try JSONEncoder().encode(CompanionCapabilities(product: "test", mode: "observe", canApprove: false,
                        canExecute: false, canMutateLifecycle: false, canRemoteConfirm: true, boundary: "UI fixture"))
                }
                throw CompanionClientError.transport("Fixture Mac is unreachable")
            }
        }
        #endif
        _session = StateObject(wrappedValue: session)

        #if DEBUG
        let initEnd = CFAbsoluteTimeGetCurrent()
        launchLogger.info("App.init() END at \(initEnd, format: .fixed(precision: 3)), duration: \((initEnd - initStart) * 1000, format: .fixed(precision: 1))ms")
        #endif
    }

    var body: some Scene {
        #if DEBUG
        let _ = launchLogger.info("App.body evaluated")
        #endif
        WindowGroup {
            RootView()
                .environmentObject(session)
                .preferredColorScheme(.dark)
                .task(priority: .userInitiated) {
                    await session.recoverHardwareRotation()
                    #if DEBUG
                    launchLogger.info("RootView .task starting deferred phone key state refresh")
                    let start = CFAbsoluteTimeGetCurrent()
                    #endif
                    await session.refreshPhonePeerKeyStateAsync()
                    #if DEBUG
                    let end = CFAbsoluteTimeGetCurrent()
                    launchLogger.info("Phone key state refresh completed in \((end - start) * 1000, format: .fixed(precision: 1))ms")
                    #endif
                }
        }
    }

    #if RUNSPECIMEN_TEST_HOOKS
    private static func testRecoveryFixtureDirectory() -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("ui-recovery-" + UUID().uuidString)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try Data("corrupt-journal".utf8).write(to: directory.appendingPathComponent(".rotation-state.json"), options: .atomic)
        } catch { preconditionFailure("Could not prepare recovery UI fixture") }
        return directory
    }
    #endif

}
