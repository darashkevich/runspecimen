# RunSpecimen agent adapter

This plugin teaches Codex, Cursor, Claude Code, Grok Build, Gemini CLI, Junie,
and Windsurf to put consequential local commands behind the RunSpecimen
lifecycle.

**Prerequisite:** the `runspecimen` CLI must be on `PATH` (`command -v
runspecimen`). Install the engine first (`pip install .` or
`sh scripts/bootstrap_dev.sh` from this repo). The plugin is only an adapter; it
does not ship the enforcement binary.

## Install paths

- **Codex marketplace / plugin directory:** install the `runspecimen` plugin from
  the Codex plugin listing (package root `plugins/runspecimen`, skill under
  `skills/runspecimen/`). After install, confirm `runspecimen` remains on `PATH`
  in the environment Codex uses.
- **Cursor (local):** symlink this directory to
  `~/.cursor/plugins/local/runspecimen`, reload Cursor, and confirm that the
  RunSpecimen skill and rule appear in Customize. Repo marketplace metadata lives
  at `.cursor-plugin/marketplace.json`.
- **Claude Code:** add this repository as a marketplace
  (`/plugin marketplace add darashkevich/runspecimen` or a local checkout), then
  install `runspecimen`. Or symlink this directory under `~/.claude/plugins/` /
  a skills-directory plugin path. Manifest: `.claude-plugin/plugin.json`. Repo
  marketplace catalog: `.claude-plugin/marketplace.json`.
- **Grok Build (xAI):** Grok reads Claude Code plugins. Symlink this directory to
  `~/.grok/plugins/runspecimen` (see `grok/README.md`), or enable Claude compat
  discovery. Optional project instructions: copy `grok/AGENTS.md`.
- **Gemini CLI:** `gemini extensions link` / `install` this directory (see
  `gemini/README.md`). Manifest: `gemini-extension.json`.
- **JetBrains Junie:** add this repo as a marketplace (`.junie-extension/` or
  `.claude-plugin/`) and install `runspecimen` (see `jetbrains/README.md`).
  IntelliJ scaffold: `jetbrains/intellij-plugin/` (no in-IDE Approve).
- **Windsurf:** symlink `windsurf/skills/runspecimen` and
  `windsurf/rules/runspecimen.md` into `.windsurf/` or
  `~/.codeium/windsurf/` (see `windsurf/README.md`).

## Boundary

The plugin is an adapter, not the enforcement boundary. It cannot approve a
run, weaken a contract, or replace operating-system sandboxing. A human must
complete `runspecimen approve --workspace … --contract …` in a real terminal
before an agent can continue. Receipt checks use:

```bash
runspecimen verify --workspace … --contract … \
  --campaign-id … --run-id …
```

Approve-safety layers in this package:

1. Skill / rules / commands instruct agents to pause for human TTY approve.
2. `scripts/runspecimen_adapter.py` and `scripts/runspecimen_mcp.py` omit
   `approve` (and remote-confirm settle) from their allow-lists.
3. `hooks/hooks.json` + `scripts/block_approve_gate.py` deny Bash/shell or MCP
   tool calls that look like typing `APPROVE`, running `runspecimen approve`,
   or settling remote-confirm (Claude `PreToolUse` + Gemini `BeforeTool`).
4. JetBrains `ide_actions.py` / IntelliJ scaffold expose `request-approval`
   handoff only — never an Approve action.

## MCP (Claude / Gemini / Junie / Desktop / Grok / Windsurf)

`.mcp.json` (and Gemini/Junie mirrors) starts a local stdio MCP server
(`scripts/runspecimen_mcp.py`) that exposes only: `about`, `doctor`,
`validate`, `status`, `preflight`, `run`, `postflight`, `verify`, `dashboard`.
No network phone-home. For hosts outside a plugin install, point an MCP server
entry at the same script with an absolute path.

## Local dashboard

When launching a visual view, use only:

```bash
runspecimen dashboard --workspace … --contract … --open
```

`dashboard` is blocking (`serve_forever`). Agents must background or detach it
(or run it in another terminal) so they can continue lifecycle commands. It is
loopback-only and read-only; it cannot replace real-TTY approval.
