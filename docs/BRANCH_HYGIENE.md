# Branch hygiene

The working tip is `cursor/evidence-expansion-coherence` after the evidence-branch lineage: PR #39 merge `e2a32166662ec06a7b47a89df6ccabb3058263a8`, PR #47 merge `329e08bf83ecb3a512f880b5833cd90df46af23e`, PR #49 merge `18ef46180141bdd6ac02a0aa31299e5b52d85433`, PR #50 merge `dd85691e42e49df7a25caaddd27fa313e3fdf728`, PR #52 merge `32cd6a2907c347b050a8ab67bc9e3547a55f44f6`. `cursor/integrated-release-candidate` is historical at pre-merge `a0dc23361856db8a68075471860bd4ab25af838c` (same tree as the #39 merge). Do not retarget work there. Current open items live in [READINESS_LEDGER.md](READINESS_LEDGER.md). This is not a merge plan and not a production sign-off. NEW-01 packaged-suite discovery remains `5f35cfcf401107648d61b84e29da5a2e8b45f708`.

## Pull requests

| PR | Purpose | Commits in the integrated tip? | Action |
| --- | --- | --- | --- |
| #39 | Integrated candidate (capture, receipts, holder packaging) | Merge `e2a3216` is the first evidence-branch parent | Merged into `cursor/evidence-expansion-coherence` |
| #47 | `.cursor/environment.json` from #35 | Merge `329e08b` is on the evidence tip | Merged. Env-file only |
| #49 | Diagnostic-root Swift fixture and CHANNEL_MATRIX hashes | Merge `18ef461` is the evidence tip before OPEN-SDIST | Merged |
| #50 | OPEN-SDIST byte-reproducible rc15 sdist | Merge `dd85691` is the EEC package-tree tip | Merged |
| #51 | Draft rc15 candidate onto `main` | Same tip as EEC | Open draft. Blocked on human/release gates. Do not merge |
| #52 | Readiness ledger, first-pass Swift, isolated holder CI | Merge `32cd6a2` is on the evidence tip. Evidence-only at merge; not a new engine/plugin/wheel identity | Merged into `cursor/evidence-expansion-coherence` |
| #34 | Evidence expansion onto `main` | Yes. `cursor/evidence-expansion-coherence` is contained | Closed as superseded |
| #38 | Eval fast path must not forge requirement results | Yes. `cursor/deterministic-fastpath` is contained | Closed as superseded |
| #35 | Cloud Agent `environment.json` | No, until restacked | Closed. Restacked as #47 |
| #46 | Independent QA report of an older head (draft) | No. Point-in-time report | Left open as a draft. Do not merge |
| #48 | Draft GM notes plus Swift diagnostic-root fixture | Dirty against IRC; GM notes already on the tip | Close. Fixture restacked in #49 |

## Other remote branches

Contained in the integrated tip, so they are not a second line of work: `main` (behind the candidate), `cursor/antigravity-muse-adapters`, `cursor/bwrap-isolation-gaps-915a`, `cursor/ci-actions-node24`, `cursor/contract-parser-adversarial-0448`, `cursor/dead-code-cleanup-c039`, `cursor/docs-path-shadow-faq`, `cursor/fix-mas-freeze-python`, `cursor/ios-observe-asc-prep`, `cursor/macos-native-app`, `cursor/macos-store-verify-and-rc11-contract`, `cursor/plugin-approve-boundary-e95f`, `cursor/stable-020-release-gate-6567`, `cursor/structure-efficiency-pass`. Leave the refs until someone deletes them. Do not merge them again.

Substantively already on the tip, even where `git cherry` still shows a different patch: `cursor/qa-daemon-accept-timeout-39`, `cursor/qa-expected-commit`, `cursor/qa-ios-release-symbols`, `cursor/qa-jsonpath-capture-failures`, `cursor/qa-status-inflight-note`, `cursor/claude-grok-plugins`. Leave. `cursor/qa-holder-socket-isolation` is not a restack: production `installed_socket_path()` still ignores `RS_HOLDER_SOCKET`, and that override was already refused.

Leave, do not restack onto this tip: `cursor/add-release-docs-43d7`, `cursor/ed25519-pubkey-receipts`, `cursor/gemini-jetbrains-windsurf`, `cursor/implement-missing-features-43d7`, `cursor/ios-companion-observe`, `cursor/marketplace-brand-icons`, `cursor/native-receipt-parity`, `cursor/next-dev-status`, `cursor/release-single-build-provenance`, `cursor/schema-compat-dashboard-ia`. They are older divergent histories. Rebasing them would reopen closed product decisions.

`cursor/release-docs-audit` is a local worktree only. Do not edit or push it from the tightening pass.

## Long-lived branches that should survive

| Branch | What it is for |
| --- | --- |
| `main` | Published history through the Mac freeze fix. Not the unpublished candidate |
| `cursor/evidence-expansion-coherence` | Working tip after #39/`e2a3216`, #47/`329e08b`, #49/`18ef461`, #50/`dd85691`, #52/`32cd6a2`. Unpublished `0.2.0rc15` engineering integration. Draft #51 targets `main` |
| `cursor/integrated-release-candidate` | Historical pre-merge tip `a0dc233`. Same tree as the #39 merge. Do not retarget work here |
| `cursor/cloud-agent-environment` | Merged as #47. Cloud Agent install snippet only |
| `cursor/ios-companion-observe` | Older iOS companion line. ADR-003/004 already exist on the tip; do not merge this ref as a second implementation |
| `cursor/native-receipt-parity` | Follow-up native receipt work that is not this candidate's Store path |
