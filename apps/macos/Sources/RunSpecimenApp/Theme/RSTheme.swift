import SwiftUI
import AppKit

enum RSTheme {
    static let bg = Color(rsLight: Color(red: 0.957, green: 0.941, blue: 0.910), // #F4F0E8
                          rsDark: Color(red: 0.086, green: 0.078, blue: 0.071)) // #161412
    static let bgElevated = Color(rsLight: Color(red: 1.0, green: 0.988, blue: 0.969), // #FFFCF7
                                  rsDark: Color(red: 0.133, green: 0.122, blue: 0.102)) // #221F1A
    static let bgPanel = Color(rsLight: Color.white,
                               rsDark: Color(red: 0.165, green: 0.149, blue: 0.129)) // #2A261F
    static let ink = Color(rsLight: Color(red: 0.110, green: 0.094, blue: 0.078), // #1C1814
                           rsDark: Color(red: 0.953, green: 0.933, blue: 0.902)) // #F3EEE6
    static let muted = Color(rsLight: Color(red: 0.361, green: 0.337, blue: 0.310), // #5C564F
                             rsDark: Color(red: 0.769, green: 0.733, blue: 0.659)) // #C4BBA8
    static let soft = Color(rsLight: Color(red: 0.541, green: 0.510, blue: 0.471), // #8A8278
                            rsDark: Color(red: 0.620, green: 0.580, blue: 0.520))
    static let line = ink.opacity(0.10)
    /// Brand teal — primary actions, current step.
    static let brand = Color(rsLight: Color(red: 0.122, green: 0.435, blue: 0.408), // #1F6F68
                             rsDark: Color(red: 0.490, green: 0.808, blue: 0.690)) // #7DCEB0
    static let brandOn = Color(rsLight: Color.white,
                               rsDark: Color(red: 0.063, green: 0.137, blue: 0.110))
    static let signal = Color(rsLight: Color(red: 0.180, green: 0.545, blue: 0.341), // #2E8B57
                              rsDark: Color(red: 0.561, green: 0.796, blue: 0.608))
    static let signalDeep = Color(rsLight: Color(red: 0.133, green: 0.435, blue: 0.275),
                                  rsDark: Color(red: 0.420, green: 0.690, blue: 0.480))
    static let amber = Color(rsLight: Color(red: 0.788, green: 0.537, blue: 0.102), // #C9891A
                             rsDark: Color(red: 0.878, green: 0.643, blue: 0.353))
    static let cyan = brand
    static let danger = Color(rsLight: Color(red: 0.788, green: 0.298, blue: 0.298), // #C94C4C
                              rsDark: Color(red: 0.941, green: 0.631, blue: 0.588))

    static let displayFont = Font.system(.largeTitle, design: .rounded).weight(.bold)
    static let titleFont = Font.system(.title2, design: .rounded).weight(.semibold)
    static let bodyFont = Font.system(.body, design: .default)
    static let mono = Font.system(.body, design: .monospaced)
    static let monoSmall = Font.system(.caption, design: .monospaced)

    static let cardRadius: CGFloat = 16
    static let buttonRadius: CGFloat = 12
}

extension Color {
    init(rsLight: Color, rsDark: Color) {
        self.init(nsColor: NSColor(name: nil, dynamicProvider: { appearance in
            let dark = appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            return NSColor(dark ? rsDark : rsLight)
        }))
    }
}

struct AtmosphericBackground: View {
    var body: some View {
        ZStack {
            RSTheme.bg
            RadialGradient(
                colors: [
                    RSTheme.brand.opacity(0.10),
                    RSTheme.amber.opacity(0.06),
                    .clear
                ],
                center: .topLeading,
                startRadius: 20,
                endRadius: 560
            )
            RadialGradient(
                colors: [
                    RSTheme.signal.opacity(0.06),
                    .clear
                ],
                center: UnitPoint(x: 0.92, y: 0.08),
                startRadius: 8,
                endRadius: 420
            )
        }
        .ignoresSafeArea()
    }
}

struct RSCard<Content: View>: View {
    var padding: CGFloat = 16
    @ViewBuilder var content: () -> Content

    var body: some View {
        content()
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: RSTheme.cardRadius, style: .continuous)
                    .fill(RSTheme.bgPanel.opacity(0.94))
                    .overlay(
                        RoundedRectangle(cornerRadius: RSTheme.cardRadius, style: .continuous)
                            .stroke(RSTheme.line, lineWidth: 1)
                    )
                    .shadow(color: Color.black.opacity(0.04), radius: 12, y: 4)
            )
    }
}

struct DetailsDisclosure<Content: View>: View {
    var title: String = "Show details"
    var accessibilityHint: String = "Shows fingerprints, paths, and exact engine terms. Does not approve or start a run."
    @ViewBuilder var content: () -> Content

    var body: some View {
        DisclosureGroup {
            content()
                .padding(.top, 8)
        } label: {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(RSTheme.brand)
        }
        .tint(RSTheme.brand)
        .accessibilityHint(accessibilityHint)
    }
}
