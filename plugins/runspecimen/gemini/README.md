# Gemini CLI / Code Assist adapter

This directory's parent (`plugins/runspecimen`) is a **Gemini CLI extension**
as well as a Claude/Codex/Cursor plugin. Manifest: `gemini-extension.json`.

## Prerequisite

`runspecimen` on `PATH` (`command -v runspecimen`). The extension is an adapter
only; it does not ship the enforcement binary.

## Install

### Link (local development)

```bash
gemini extensions link /absolute/path/to/runspecimen/plugins/runspecimen
# restart gemini, then:
/extensions list
```

### Install from a clone

```bash
gemini extensions install /absolute/path/to/runspecimen/plugins/runspecimen
```

### Install from GitHub (after this branch is on a remote)

```bash
gemini extensions install https://github.com/darashkevich/runspecimen \
  --path plugins/runspecimen
```

(If your Gemini CLI build does not support `--path`, clone locally and
`gemini extensions install` / `link` the `plugins/runspecimen` directory.)

## What ships

| Piece | Path | Role |
| --- | --- | --- |
| Manifest | `gemini-extension.json` | Name, version, MCP, excludeTools |
| Context | `GEMINI.md` | Always-on TTY-approve policy |
| Skill | `skills/runspecimen/SKILL.md` | Lifecycle workflow |
| Commands | `commands/*.toml` | `/validate`, `/status`, `/request-approval`, `/verify` |
| Hooks | `hooks/hooks.json` → `BeforeTool` only | Deny approve / settle shell + MCP |
| Claude hooks (sibling) | `hooks/claude-hooks.json` → `PreToolUse` | Claude/Junie/Grok via plugin.json; not mixed into Gemini file |
| MCP | `scripts/runspecimen_mcp.py` | No `approve` tool |

## Approve-safety

1. `GEMINI.md` + skill instruct the agent to pause for human TTY approve.
2. MCP allow-list omits `approve` / settle.
3. `BeforeTool` hook runs `block_approve_gate.py --format gemini` from
   `hooks/hooks.json` (Gemini-only; Claude uses `hooks/claude-hooks.json`).
4. `excludeTools` additionally blocks obvious `runspecimen approve` /
   `remote-confirm` shell invocations.
5. Local-only; no telemetry phone-home.

Gemini CLI loads `hooks/hooks.json` from the extension root. Claude Code
rejects `BeforeTool` keys, so PreToolUse lives in a separate file pointed at by
`.claude-plugin/plugin.json`. Ensure hooks are enabled in Gemini settings
(`enableHooks`) if your build gates hook execution behind that flag.

## Gemini Code Assist (IDE)

There is no separate partner plugin SDK for Code Assist beyond MCP / project
instructions. Point the IDE MCP config at
`plugins/runspecimen/scripts/runspecimen_mcp.py` (absolute path) and keep the
same human-TTY approve rule in project instructions. Do not add an in-IDE
Approve control that bypasses the CLI.

## Gallery / store

**Not submitted** to the Gemini CLI extension gallery. Prefer PR + local
install docs until Yahor explicitly publishes.
