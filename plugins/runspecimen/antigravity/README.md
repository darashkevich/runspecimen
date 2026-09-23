# Antigravity CLI (`agy`) adapter

Native Antigravity plugin layout for consumer `agy`, alongside the existing
**Gemini CLI** extension in the parent directory. Enterprise Gemini CLI keeps
using `gemini-extension.json` + `BeforeTool`. Consumer Antigravity uses this
folder + `PreToolUse`.

**Not submitted** to any Antigravity / Gemini gallery. Local install only.

## Prerequisite

`runspecimen` on `PATH` (`command -v runspecimen`). This plugin is an adapter
only; it does not ship the enforcement binary.

## Install paths (pick one)

### A. Native Antigravity plugin (preferred for `agy`)

```bash
agy plugin install "$(pwd)/plugins/runspecimen/antigravity"
agy plugin list
# inside agy TUI:
/hooks
/mcp
```

Workspace alternative (no global install):

```bash
mkdir -p .agents/plugins
ln -sfn "$(pwd)/plugins/runspecimen/antigravity" .agents/plugins/runspecimen
```

### B. Import legacy Gemini extension

If you already linked/installed the parent Gemini extension:

```bash
gemini extensions link "$(pwd)/plugins/runspecimen"   # enterprise Gemini CLI
# then, on Antigravity CLI:
agy plugin import gemini
```

After import, **replace** any converted hooks with this package's
`hooks.json` (Antigravity uses named `PreToolUse` handlers and a `toolCall`
stdin shape — Gemini `BeforeTool` does not map 1:1). Confirm
`block_approve_gate.py --format antigravity` is what `/hooks` runs.

### C. Workspace skills + MCP without a plugin

Per current Antigravity docs (skills under `.agents/skills/`, MCP under
`.agents/mcp_config.json`):

```bash
mkdir -p .agents/skills
ln -sfn "$(pwd)/plugins/runspecimen/antigravity/skills/runspecimen" \
  .agents/skills/runspecimen
cp "$(pwd)/plugins/runspecimen/antigravity/mcp_config.json" \
  .agents/mcp_config.json
# Edit mcp_config.json args to an absolute path to runspecimen_mcp.py if needed.
cp "$(pwd)/plugins/runspecimen/antigravity/hooks.json" .agents/hooks.json
# Point hook commands at an absolute path to scripts/block_approve_gate.py.
```

## What ships

| Piece | Path | Role |
| --- | --- | --- |
| Manifest | `plugin.json` | Antigravity plugin marker |
| MCP | `mcp_config.json` | stdio MCP; no `approve` tool |
| Hooks | `hooks.json` → `PreToolUse` | Deny approve / settle (`run_command` + MCP) |
| Skill | `skills/runspecimen/SKILL.md` | Lifecycle workflow |
| Rules | `rules/runspecimen.md` | Always-on TTY-approve policy |
| Scripts | `scripts/` | Gate + MCP (kept identical to parent `scripts/`) |

## Dual path: Gemini CLI vs `agy`

| Host | Layout | Gate event | Gate dialect |
| --- | --- | --- | --- |
| Enterprise Gemini CLI | Parent `gemini-extension.json` | `BeforeTool` in `hooks/hooks.json` | `--format gemini` |
| Consumer Antigravity (`agy`) | This `antigravity/` plugin | `PreToolUse` in `hooks.json` | `--format antigravity` |

Both deny the same patterns: typing `APPROVE`, `runspecimen approve`,
remote-confirm settle, companion `/v1/approve`. Honest status: **not** listed
in a gallery.

## Approve-safety

1. Skill + rules instruct the agent to pause for human TTY approve.
2. MCP allow-list omits `approve` / settle.
3. `PreToolUse` runs `block_approve_gate.py --format antigravity` (decision /
   reason output; reads Antigravity `toolCall` payloads).
4. Local-only; no telemetry phone-home.
5. Do not use host flags that disable approval/sandbox as a substitute for
   RunSpecimen TTY approve.
