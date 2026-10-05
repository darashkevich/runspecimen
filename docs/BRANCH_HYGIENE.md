# Branch hygiene

Recorded against the integrated tip after the tree-tightening pass. This is not a merge plan and not a production sign-off. Do not delete `cursor/evidence-expansion-coherence`: pull request #39 uses it as its base.

## Open pull requests

| PR | Purpose | Commits in the integrated tip? | Action |
| --- | --- | --- | --- |
| #39 | Integrated candidate (capture, receipts, holder packaging) | This is the tip | Leave open. Do not merge from this pass |
| #34 | Evidence expansion onto `main` | Yes. `cursor/evidence-expansion-coherence` is contained | Close. Superseded by the integrated tip. The branch stays because #39 targets it |
| #38 | Eval fast path must not forge requirement results | Yes. `cursor/deterministic-fastpath` is contained | Close. Superseded by the integrated tip |
| #35 | Cloud Agent `environment.json` | No. One commit, file absent here | Restack onto the integrated head as a small follow-up. Close #35 once that PR exists |
| #46 | Independent QA report of an older head (draft) | No. Point-in-time report | Leave draft. Do not merge. The reviewed SHA is not this tip |

## Other remote branches

Contained in the integrated tip, so they are not a second line of work: `main` (behind the candidate), `cursor/antigravity-muse-adapters`, `cursor/bwrap-isolation-gaps-915a`, `cursor/ci-actions-node24`, `cursor/contract-parser-adversarial-0448`, `cursor/dead-code-cleanup-c039`, `cursor/docs-path-shadow-faq`, `cursor/fix-mas-freeze-python`, `cursor/ios-observe-asc-prep`, `cursor/macos-native-app`, `cursor/macos-store-verify-and-rc11-contract`, `cursor/plugin-approve-boundary-e95f`, `cursor/stable-020-release-gate-6567`, `cursor/structure-efficiency-pass`. Leave the refs until someone deletes them. Do not merge them again.

Substantively already on the tip, even where `git cherry` still shows a different patch: `cursor/qa-daemon-accept-timeout-39`, `cursor/qa-expected-commit`, `cursor/qa-ios-release-symbols`, `cursor/qa-jsonpath-capture-failures`, `cursor/qa-status-inflight-note`, `cursor/claude-grok-plugins`. Leave. `cursor/qa-holder-socket-isolation` is not a restack: production `installed_socket_path()` still ignores `RS_HOLDER_SOCKET`, and that override was already refused.

Leave, do not restack onto this tip: `cursor/add-release-docs-43d7`, `cursor/ed25519-pubkey-receipts`, `cursor/gemini-jetbrains-windsurf`, `cursor/implement-missing-features-43d7`, `cursor/ios-companion-observe`, `cursor/marketplace-brand-icons`, `cursor/native-receipt-parity`, `cursor/next-dev-status`, `cursor/release-single-build-provenance`, `cursor/schema-compat-dashboard-ia`. They are older divergent histories. Rebasing them would reopen closed product decisions.

`cursor/release-docs-audit` is a local worktree only. Do not edit or push it from the tightening pass.

## Long-lived branches that should survive

| Branch | What it is for |
| --- | --- |
| `main` | Published history through the Mac freeze fix. Not the unpublished candidate |
| `cursor/evidence-expansion-coherence` | Base of pull request #39. Contained in the tip. Keep until #39 has another base |
| `cursor/integrated-release-candidate` | The one integrated tip. Unpublished `0.2.0rc15` |
| `cursor/ios-companion-observe` | Older iOS companion line. ADR-003/004 already exist on the tip; do not merge this ref as a second implementation |
| `cursor/native-receipt-parity` | Follow-up native receipt work that is not this candidate's Store path |
