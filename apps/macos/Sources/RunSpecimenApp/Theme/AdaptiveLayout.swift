import SwiftUI

/// Horizontal if it fits, otherwise stacks so buttons and chrome survive split / 13".
struct FitHStack<Content: View>: View {
    var spacing: CGFloat = 12
    var alignment: VerticalAlignment = .center
    @ViewBuilder var content: () -> Content

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: alignment, spacing: spacing, content: content)
            VStack(alignment: .leading, spacing: spacing, content: content)
        }
    }
}

extension View {
    func rsReadableColumn(maxWidth: CGFloat = 720) -> some View {
        frame(maxWidth: maxWidth, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}
