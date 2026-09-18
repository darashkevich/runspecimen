import SwiftUI

extension View {
    /// Center a readable column on iPad / landscape without stretching form fields.
    func rsReadableWidth(_ max: CGFloat = 720) -> some View {
        frame(maxWidth: max, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .center)
    }
}

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
