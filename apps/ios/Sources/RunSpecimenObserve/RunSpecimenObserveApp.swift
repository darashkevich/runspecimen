import SwiftUI

@main
struct RunSpecimenObserveApp: App {
    @StateObject private var session = CompanionSession()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .preferredColorScheme(.dark)
        }
    }
}
