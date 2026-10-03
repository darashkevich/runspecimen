import SwiftUI

/// Shows a carried approval package. It does not sign and it does not call Face ID.
struct CompanionApprovalPreviewView: View {
    @State private var packageText = ""
    @State private var lines: [String] = []
    @State private var message = CompanionApprovalPreview.refusalText
    @State private var fields: RSBA2Package.Fields?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                BoundaryBanner(text: message)
                Text("Paste the package a person carried from the Mac. Showing it does not approve a run and does not call Face ID.")
                    .font(.footnote)
                    .foregroundStyle(RSTheme.muted)
                TextEditor(text: $packageText)
                    .font(.system(.footnote, design: .monospaced))
                    .frame(minHeight: 160)
                    .accessibilityLabel("Carried approval package")
                    .accessibilityValue(fields == nil ? "No parsed request" : "Parsed request")
                Button("Show request") {
                    showRequest()
                }
                .accessibilityHint("Displays the request, including enrollment generations. Does not call Face ID.")
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
        .onChange(of: packageText) { _, _ in
            lines = []
            fields = nil
            message = CompanionApprovalPreview.refusalText
        }
    }

    private func showRequest() {
        guard let data = packageText.data(using: .utf8) else { return }
        let preview = CompanionApprovalPreview.parse(data)
        lines = preview.lines
        message = preview.refusal
        fields = preview.fields
    }
}
