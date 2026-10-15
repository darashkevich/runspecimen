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

        _session = StateObject(wrappedValue: CompanionSession(deferPhoneKeyState: true))

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
                .task(priority: .background) {
                    recoverIncompleteRotationsAfterLaunch()
                }
                .task {
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

    private func recoverIncompleteRotationsAfterLaunch() {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let directory = base.appendingPathComponent("RunSpecimenObservePairing", isDirectory: true)

        do {
            try CompanionSecureEnclaveEnrollment.recoverIncompleteRotation(directory: directory)
            appLogger.info("Rotation recovery check completed after launch")
        } catch {
            appLogger.error("Rotation recovery failed after launch: \(error.localizedDescription, privacy: .public)")
        }
    }
}
