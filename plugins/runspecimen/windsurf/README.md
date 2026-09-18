# Windsurf (Cascade) adapter

Windsurf's Cascade agent uses VS Code–compatible packaging plus Windsurf-native
skills and rules. Reuse the same RunSpecimen skill/rule content as Cursor; install
into Windsurf paths below.

## Prerequisite

`runspecimen` on `PATH`. This adapter does not ship the enforcement binary.

## Install — skills (recommended)

Workspace (commit with the project):

```bash
mkdir -p .windsurf/skills
ln -sfn /absolute/path/to/runspecimen/plugins/runspecimen/windsurf/skills/runspecimen \
  .windsurf/skills/runspecimen
```

Or copy the folder instead of symlinking.

Global (all workspaces):

```bash
mkdir -p ~/.codeium/windsurf/skills
ln -sfn /absolute/path/to/runspecimen/plugins/runspecimen/windsurf/skills/runspecimen \
  ~/.codeium/windsurf/skills/runspecimen
```

Invoke with `@runspecimen` in Cascade, or let Cascade match the skill
description.

## Install — rules

Workspace rules (modern Wave 8+ format):

```bash
mkdir -p .windsurf/rules
ln -sfn /absolute/path/to/runspecimen/plugins/runspecimen/windsurf/rules/runspecimen.md \
  .windsurf/rules/runspecimen.md
```

Optional legacy root file (only if your Windsurf build still prefers it):

```bash
cp plugins/runspecimen/windsurf/rules/runspecimen.md .windsurfrules
```

## MCP (optional)

Cascade supports MCP servers. Point a local stdio server at the shared adapter
(no `approve` tool):

```json
{
  "mcpServers": {
    "runspecimen": {
      "command": "python3",
      "args": ["/absolute/path/to/runspecimen/plugins/runspecimen/scripts/runspecimen_mcp.py"]
    }
  }
}
```

## Cursor / VS Code extension reuse

The Cursor plugin package (`plugins/runspecimen` + `.cursor-plugin/`) remains the
primary VS Code–family marketplace artifact. Windsurf can import VS Code/Cursor
extensions during onboarding; treat that as optional discovery, not a separate
binary. This folder is the **Windsurf-native** skill/rule path.

## Approve-safety

- Skill + rule instruct agents to pause for human TTY `approve`.
- MCP allow-list omits `approve` / settle (shared `runspecimen_mcp.py`).
- No Windsurf workflow or button that types `APPROVE` or settles remote-confirm.
- Local-only; no telemetry phone-home.

## Marketplace / store

Windsurf / Open VSX / VS Marketplace listing for a dedicated RunSpecimen UI
extension is **not submitted**. Prefer PR + install docs until Yahor publishes.
