import SwiftUI

struct BoundaryBanner: View {
    var text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Safety boundary")
                .font(.caption.weight(.semibold))
                .foregroundStyle(RSTheme.amber)
            Text(text)
                .font(.footnote)
                .foregroundStyle(RSTheme.ink.opacity(0.92))
                .fixedSize(horizontal: false, vertical: true)
            Text("Remote human confirm ≠ local TTY APPROVE · plugins cannot approve · not an OS sandbox")
                .font(.caption2.monospaced())
                .foregroundStyle(RSTheme.muted)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RSTheme.panel)
        .overlay(
            RoundedRectangle(cornerRadius: 4, style: .continuous)
                .stroke(RSTheme.amber.opacity(0.45), lineWidth: 1)
        )
    }
}
