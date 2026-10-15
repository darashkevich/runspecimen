import SwiftUI
import os

private let appLogger = Logger(subsystem: "com.darashkevich.runspecimen.observe", category: "app")

@main
struct RunSpecimenObserveApp: App {
    @StateObject private var session = CompanionSession()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .preferredColorScheme(.dark)
                .task(priority: .background) {
                    recoverIncompleteRotationsAfterLaunch()
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
