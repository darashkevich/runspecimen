import SwiftUI

struct RootView: View {
    @EnvironmentObject private var session: CompanionSession

    var body: some View {
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
    }
}
