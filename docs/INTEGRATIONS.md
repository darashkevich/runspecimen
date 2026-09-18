# Integrations status and research

Central ledger for RunSpecimen agent-host adapters. Plugins are **adapters
only**; the CLI on `PATH` remains the enforcement boundary. No adapter may
auto-approve, type `APPROVE`, or settle remote-confirm.

## Status ledger

| Surface | Package / path | Status | Notes |
| --- | --- | --- | --- |
| Codex plugin | `plugins/runspecimen/.codex-plugin/` | Shipped in-repo; marketplace **not submitted** | Skill + adapter; see `docs/SUBMISSION.md` |
| Cursor plugin | `plugins/runspecimen/.cursor-plugin/` + `.cursor-plugin/marketplace.json` | Shipped in-repo; marketplace **not submitted** | Skill + rule + logo |
| Claude Code plugin | `plugins/runspecimen/.claude-plugin/` + `.claude-plugin/marketplace.json` | Shipped in-repo; community marketplace **not submitted** | Skills, commands, PreToolUse approve-gate, stdio MCP |
| Claude Desktop MCP | `plugins/runspecimen/.mcp.json` → `scripts/runspecimen_mcp.py` | Shipped (local stdio) | Same allow-list as adapter; no `approve` tool |
| Grok Build (xAI) | Claude-compat + `plugins/runspecimen/grok/` | Shipped via Claude-compat path | Symlink to `~/.grok/plugins/`; optional `AGENTS.md` |
| Homebrew tap | — | Not started | Roadmap Phase 4 |
| VS Code / Open VSX UI | — | Not started | Status/evidence UI later |
| iOS / macOS companion | `apps/ios`, `apps/macos-companion` | Observe + optional human remote-confirm | `can_approve` always false for plugins |

Honest claims only: orchestration, leases, provenance, receipts — **not** OS
sandboxing.

## Approve-safety checklist (all adapters)

- [x] Skill / commands tell the agent to pause for human TTY `approve`
- [x] CLI adapter allow-list excludes `approve`
- [x] MCP tool list excludes `approve` / settle
- [x] Claude/Grok PreToolUse hook denies approve-like Bash/MCP calls
- [x] Companion capabilities keep `can_approve: false`
- [x] No telemetry phone-home in plugin scripts

## Research brief — frontier labs next

Ranked by (a) agent coding traction, (b) extension/skill API maturity,
(c) fit with the TTY-approve model.

| Rank | Target | (a) Traction | (b) API maturity | (c) TTY-approve fit | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | **Google Gemini CLI / Gemini Code Assist** | High and rising for agentic coding | Skills/extensions + MCP emerging; Android Studio AI | Good if we ship skill + MCP + “human must approve in terminal” commands | **Next** |
| 2 | **JetBrains AI / Junie** | Strong in enterprise IDEs | Mature JetBrains plugin SDK | Medium — IDE-centric UX; still can shell out to CLI and refuse in-IDE approve | **Next** |
| 3 | **Windsurf (Cascade) / Codium** | High agent-coding usage | VS Code-compatible extension model | Good — mirror Cursor skill/rule pattern | Strong candidate |
| 4 | OpenAI beyond Codex (ChatGPT apps / custom GPTs) | Huge chat surface | Apps/GPT actions are remote-HTTP oriented | Weak for local TTY approve | Defer unless Apps SDK gains local stdio |
| 5 | Amazon Q Developer | Solid IDE installs | VS Code + JetBrains extensions | Medium — policy hooks exist; agent autonomy lower than Cursor/Claude | Later |
| 6 | Continue.dev / open harnesses | Growing | Skills + MCP common | Good for power users | Optional community port |
| 7 | Meta Llama coding stacks | Model traction, weak product plugin surface | Mostly API / third-party hosts | Poor first-party surface | Skip until a first-party agent IDE ships |
| 8 | Mistral / Codestral | Moderate | Limited agent plugin marketplace | Weak | Watch |
| 9 | Perplexity | High search, low local agent coding | No serious local TTY agent plugin API | Poor | Skip |

### Recommended next 2–3 targets

1. **Gemini CLI / Code Assist** — closest “missing big lab” after Anthropic/xAI;
   MCP + instruction packs map cleanly onto the existing adapter.
2. **JetBrains AI / Junie** — enterprise distribution; ship a thin plugin that
   shells to `runspecimen` and never exposes an Approve action.
3. **Windsurf** — low incremental cost if Cursor packaging stays healthy
   (same skill/rule ZIP story).

### Partner-API blockers observed this slice

- **Anthropic:** Claude Code plugin + community marketplace paths are public;
  official `claude-plugins-official` inclusion is invite/curation-only (no
  application that guarantees listing).
- **xAI:** Grok Build documents skills/plugins/marketplaces and Claude compat;
  there is no separate partner “Grok-only” plugin SDK beyond that. Ship
  Claude-shaped package + Grok install docs (done here).
- **Google / JetBrains / Windsurf:** no RunSpecimen partner status; build
  against public extension docs when prioritized.

## Related docs

- [USER_GUIDE.md](USER_GUIDE.md) — install and lifecycle
- [SUBMISSION.md](SUBMISSION.md) — human marketplace submission steps
- [MARKET_AND_DISTRIBUTION.md](MARKET_AND_DISTRIBUTION.md) — channel strategy
- [THREAT_MODEL.md](THREAT_MODEL.md) — adapter non-expansion of trust boundary
- [ADR-004](ADR-004-remote-human-confirm.md) — plugins cannot remote-approve
