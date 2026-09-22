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
| Gemini CLI / Code Assist | `gemini-extension.json` + `GEMINI.md` + `gemini/` | Shipped in-repo; gallery **not submitted** | Skills, TOML commands, BeforeTool gate, MCP; Code Assist via MCP + instructions |
| JetBrains Junie | `.junie-extension/marketplace.json` + `extension.json` + `jetbrains/` | Shipped in-repo; JetBrains marketplace **not submitted** | Claude-compat + native Junie catalog; guidelines + MCP |
| JetBrains IntelliJ scaffold | `jetbrains/intellij-plugin/` | Scaffold + local install docs | Tools menu shells to CLI; **no** in-IDE Approve |
| Windsurf (Cascade) | `plugins/runspecimen/windsurf/` | Shipped in-repo; store **not submitted** | Skills + rules for `.windsurf/` / `~/.codeium/windsurf/`; optional MCP |
| Homebrew formula | `packaging/homebrew/runspecimen.rb` | In repo; installs `0.2.0rc13` | Not a tap. Default backend `none` is unconfined |
| VS Code / Open VSX UI | — | Not started | Status/evidence UI later; Windsurf reuses Cursor skill/rule story |
| iOS / macOS companion | `apps/ios`, `apps/macos-companion` | Observe + optional human remote-confirm | `can_approve` always false for plugins |

Honest claims only: orchestration, leases, provenance, receipts. Opt-in
`sandbox-exec` / `bwrap` confine writes (and network, when the contract denies
it). They are not an OS sandbox. Default `none` confines nothing.

## Approve-safety checklist (all adapters)

- [x] Skill / commands tell the agent to pause for human TTY `approve`
- [x] CLI adapter allow-list excludes `approve`
- [x] MCP tool list excludes `approve` / settle
- [x] Claude/Grok/Junie PreToolUse hook denies approve-like Bash/MCP calls
      (`hooks/claude-hooks.json` via `.claude-plugin/plugin.json`)
- [x] Gemini BeforeTool hook denies approve-like shell/MCP (`hooks/hooks.json`
      + `--format gemini`; kept separate so Claude schema stays valid)
- [x] JetBrains IDE actions omit Approve; `request-approval` is handoff-only
- [x] Companion capabilities keep `can_approve: false`
- [x] No telemetry phone-home in plugin scripts

## Research brief — frontier labs next

Ranked by (a) agent coding traction, (b) extension/skill API maturity,
(c) fit with the TTY-approve model.

| Rank | Target | (a) Traction | (b) API maturity | (c) TTY-approve fit | Verdict |
| --- | --- | --- | --- | --- | --- |
| 1 | **Google Gemini CLI / Gemini Code Assist** | High and rising for agentic coding | Skills/extensions + MCP + hooks | Good — extension + BeforeTool gate shipped | **Done (in-repo)** |
| 2 | **JetBrains AI / Junie** | Strong in enterprise IDEs | Junie extensions + Claude-compat marketplaces | Good — Junie catalog + IntelliJ scaffold; no in-IDE Approve | **Done (in-repo)** |
| 3 | **Windsurf (Cascade) / Codium** | High agent-coding usage | VS Code-compatible + `.windsurf` skills/rules | Good — skill/rule pack shipped | **Done (in-repo)** |
| 4 | OpenAI beyond Codex (ChatGPT apps / custom GPTs) | Huge chat surface | Apps/GPT actions are remote-HTTP oriented | Weak for local TTY approve | Defer unless Apps SDK gains local stdio |
| 5 | Amazon Q Developer | Solid IDE installs | VS Code + JetBrains extensions | Medium — policy hooks exist; agent autonomy lower than Cursor/Claude | Later |
| 6 | Continue.dev / open harnesses | Growing | Skills + MCP common | Good for power users | Optional community port |
| 7 | Meta Llama coding stacks | Model traction, weak product plugin surface | Mostly API / third-party hosts | Poor first-party surface | Skip until a first-party agent IDE ships |
| 8 | Mistral / Codestral | Moderate | Limited agent plugin marketplace | Weak | Watch |
| 9 | Perplexity | High search, low local agent coding | No serious local TTY agent plugin API | Poor | Skip |

### Shipped this slice (Gemini → JetBrains → Windsurf)

1. **Gemini CLI** — `gemini-extension.json`, `GEMINI.md`, TOML commands,
   BeforeTool approve-gate in `hooks/hooks.json` (Gemini-only file), shared
   MCP; Code Assist documented as MCP + instructions (no separate partner
   SDK). Claude PreToolUse lives in `hooks/claude-hooks.json` so Claude's
   hook schema is not polluted with `BeforeTool`.
2. **JetBrains / Junie** — `.junie-extension/marketplace.json`, native
   `extension.json`, guidelines, MCP mirror, IntelliJ Tools-menu scaffold +
   `ide_actions.py` (request-approval handoff only).
3. **Windsurf** — `windsurf/skills` + `windsurf/rules` + install docs; Cursor
   package remains the VS Code–family artifact.

### Partner-API blockers observed

- **Anthropic:** Claude Code plugin + community marketplace paths are public;
  official `claude-plugins-official` inclusion is invite/curation-only (no
  application that guarantees listing).
- **xAI:** Grok Build documents skills/plugins/marketplaces and Claude compat;
  there is no separate partner “Grok-only” plugin SDK beyond that.
- **Google:** Gemini CLI extension format is public; gallery listing is a
  separate publish step (not done here). Code Assist has no distinct plugin
  marketplace beyond MCP / project instructions.
- **JetBrains:** Junie accepts Claude-compat + native marketplaces; official
  JetBrains curated catalog and IntelliJ Marketplace are separate submissions
  (not done here).
- **Windsurf:** Skills/rules are filesystem-based; no dedicated partner SDK.
  VS Marketplace / Open VSX UI extension remains optional later work.

## Related docs

- [USER_GUIDE.md](USER_GUIDE.md) — install and lifecycle
- [SUBMISSION.md](SUBMISSION.md) — human marketplace submission steps
- [MARKET_AND_DISTRIBUTION.md](MARKET_AND_DISTRIBUTION.md) — channel strategy
- [THREAT_MODEL.md](THREAT_MODEL.md) — adapter non-expansion of trust boundary
- [ADR-004](ADR-004-remote-human-confirm.md) — plugins cannot remote-approve
