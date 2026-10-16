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
                if session.rotationRecoveryError != nil && session.rotationRecoveryDismissed {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Key recovery") { session.showRotationRecoveryNotice() }
                    }
                }
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
            .safeAreaInset(edge: .top) {
                if let error = session.rotationRecoveryError, !session.rotationRecoveryDismissed {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(error).font(.callout)
                        Button(session.rotationRecoveryInProgress ? "Retrying recovery…" : "Retry key recovery") {
                            Task { await session.recoverHardwareRotation() }
                        }
                        .disabled(session.rotationRecoveryInProgress)
                        ShareLink("Export recovery diagnostics", item: session.rotationRecoveryDiagnostics)
                        Button("Dismiss notice") { session.dismissRotationRecoveryNotice() }
                    }
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.orange.opacity(0.2))
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier("rotationRecoveryFailure")
                }
            }
        .tint(RSTheme.cyan)
        .onDisappear { session.cancelAllTasks() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { session.cancelAllTasks() }
        }
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
