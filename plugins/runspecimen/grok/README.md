# Grok Build / xAI adapter notes

Grok Build reads Claude Code plugins with zero extra configuration. The same
`plugins/runspecimen` package (skill, commands, hooks, MCP) therefore covers
**Claude Code** and **Grok Build**.

## Install (Grok Build)

Prerequisite: `runspecimen` on `PATH`.

### Option A — Claude-compatible plugin dir (recommended)

```bash
mkdir -p ~/.grok/plugins
ln -sfn /absolute/path/to/runspecimen/plugins/runspecimen \
  ~/.grok/plugins/runspecimen
```

Then in Grok Build: `/plugins` → enable `runspecimen`, or:

```bash
grok plugin validate ~/.grok/plugins/runspecimen
grok inspect --json   # confirm skill / hooks / MCP discovery
```

### Option B — Project plugin path

Add to `~/.grok/config.toml` or project `.grok/config.toml`:

```toml
[plugins]
paths = ["/absolute/path/to/runspecimen/plugins/runspecimen"]
enabled = ["runspecimen"]
```

### Option C — Marketplace source (self-hosted)

Point a marketplace source at this repository (root contains
`.claude-plugin/marketplace.json`). Grok's Claude compat layer discovers that
catalog; treat listing status as **not submitted** until Yahor publishes it.

## Boundary (same as Codex / Cursor / Claude)

- Adapter only — CLI remains the enforcement boundary.
- Never auto-approve, type `APPROVE`, or settle remote-confirm.
- MCP tools exclude `approve` entirely (`scripts/runspecimen_mcp.py`).
- PreToolUse hook (`scripts/block_approve_gate.py`) denies Bash / MCP attempts
  that look like approval or settle.
- Local-only; no telemetry phone-home.
- Honest claim: orchestration + evidence, **not** an OS sandbox.

## Optional AGENTS.md snippet

Copy `grok/AGENTS.md` into a project root (or merge into an existing
`AGENTS.md`) when you want Grok to load the policy even without the plugin
enabled.
