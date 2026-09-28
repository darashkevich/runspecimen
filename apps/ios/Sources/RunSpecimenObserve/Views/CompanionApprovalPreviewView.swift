import SwiftUI

/// Shows a carried approval package. There is no sign button.
struct CompanionApprovalPreviewView: View {
    @State private var packageText = ""
    @State private var lines: [String] = []
    @State private var message = CompanionApprovalPreview.refusalText

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                BoundaryBanner(text: message)
                Text("Paste the package a person carried from the Mac. This screen only displays it.")
                    .font(.footnote)
                    .foregroundStyle(RSTheme.muted)
                TextEditor(text: $packageText)
                    .font(.system(.footnote, design: .monospaced))
                    .frame(minHeight: 160)
                    .accessibilityLabel("Carried approval package")
                Button("Show request") {
                    guard let data = packageText.data(using: .utf8) else { return }
                    let preview = CompanionApprovalPreview.parse(data)
                    lines = preview.lines
                    message = preview.refusal
                }
                .accessibilityHint("Displays the request. Does not call Face ID.")
                ForEach(lines, id: \.self) { line in
                    Text(line)
                        .font(.system(.footnote, design: .monospaced))
                        .foregroundStyle(RSTheme.ink)
                        .textSelection(.enabled)
                }
            }
            .padding(20)
        }
        .background(RSTheme.bg)
        .navigationTitle("Carried approval")
        .navigationBarTitleDisplayMode(.inline)
    }
}
