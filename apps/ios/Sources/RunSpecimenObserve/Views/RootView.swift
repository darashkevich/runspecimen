import SwiftUI
import os

#if DEBUG
private let launchLogger = Logger(subsystem: "com.darashkevich.runspecimen.observe", category: "launch")
#endif

struct RootView: View {
    @EnvironmentObject private var session: CompanionSession
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        #if DEBUG
        let _ = launchLogger.info("RootView.body evaluated, isPaired=\(session.isPaired), scenePhase=\(String(describing: scenePhase))")
        #endif
        NavigationStack {
            Group {
                if session.isPaired {
                    StatusObserveView()
                } else {
                    PairingView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(RSTheme.bg.ignoresSafeArea())
            .toolbar {
                ToolbarItem(placement: .principal) {
                    HStack(spacing: 8) {
                        Image("BrandMark")
                            .resizable()
                            .scaledToFit()
                            .frame(width: 22, height: 22)
                            .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
                        Text("RunSpecimen")
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(RSTheme.ink)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                    }
                }
            }
        }
        .tint(RSTheme.cyan)
        #if DEBUG
        .onAppear {
            launchLogger.info("RootView.onAppear fired")
        }
        .onChange(of: scenePhase) { oldPhase, newPhase in
            launchLogger.info("Scene phase changed: \(String(describing: oldPhase)) -> \(String(describing: newPhase))")
        }
        #endif
    }
}
