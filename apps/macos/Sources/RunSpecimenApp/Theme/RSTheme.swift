import SwiftUI

enum RSTheme {
    static let bg = Color(red: 0.027, green: 0.039, blue: 0.059) // #070a0f
    static let bgElevated = Color(red: 0.051, green: 0.071, blue: 0.098) // #0d1219
    static let bgPanel = Color(red: 0.067, green: 0.094, blue: 0.129) // #111821
    static let ink = Color(red: 0.933, green: 0.953, blue: 0.973) // #eef3f8
    static let muted = Color(red: 0.604, green: 0.671, blue: 0.737) // #9aabbc
    static let soft = Color(red: 0.435, green: 0.506, blue: 0.580) // #6f8194
    static let line = Color(red: 0.604, green: 0.671, blue: 0.737).opacity(0.18)
    static let signal = Color(red: 0.608, green: 0.898, blue: 0.416) // #9be56a
    static let signalDeep = Color(red: 0.435, green: 0.749, blue: 0.271) // #6fbf45
    static let amber = Color(red: 0.910, green: 0.722, blue: 0.290) // #e8b84a
    static let cyan = Color(red: 0.431, green: 0.784, blue: 1.0) // #6ec8ff
    static let danger = Color(red: 0.95, green: 0.40, blue: 0.42)

    static let displayFont = Font.system(.largeTitle, design: .default).weight(.bold)
    static let titleFont = Font.system(.title2, design: .default).weight(.semibold)
    static let bodyFont = Font.system(.body, design: .default)
    static let mono = Font.system(.body, design: .monospaced)
    static let monoSmall = Font.system(.caption, design: .monospaced)
}

struct AtmosphericBackground: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            RSTheme.bg
            RadialGradient(
                colors: [
                    RSTheme.signal.opacity(0.12),
                    RSTheme.cyan.opacity(0.05),
                    .clear
                ],
                center: .topLeading,
                startRadius: 20,
                endRadius: 520
            )
            RadialGradient(
                colors: [
                    RSTheme.amber.opacity(0.08),
                    .clear
                ],
                center: UnitPoint(x: 0.85, y: 0.2),
                startRadius: 10,
                endRadius: 380
            )
            GridPattern()
                .opacity(reduceMotion ? 0.35 : 0.55)
        }
        .ignoresSafeArea()
    }
}

private struct GridPattern: View {
    var body: some View {
        Canvas { context, size in
            let step: CGFloat = 28
            var path = Path()
            stride(from: 0, through: size.width, by: step).forEach { x in
                path.move(to: CGPoint(x: x, y: 0))
                path.addLine(to: CGPoint(x: x, y: size.height))
            }
            stride(from: 0, through: size.height, by: step).forEach { y in
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
            }
            context.stroke(path, with: .color(RSTheme.line.opacity(0.55)), lineWidth: 0.5)
        }
        .allowsHitTesting(false)
    }
}
