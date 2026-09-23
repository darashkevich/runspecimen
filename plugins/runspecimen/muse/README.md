# Meta Muse Code v1 adapter

Skill + MCP allow-list for [Muse Code](https://dev.meta.ai/docs/muse-code/extending/).
Reuses the Claude skill/MCP patterns from the parent plugin. **No approve tool.**
Never auto-type `APPROVE`.

**Marketplace / gallery:** not submitted. Local install only.

## Prerequisite

`runspecimen` on `PATH` (`command -v runspecimen`).

## Install

### Skill (stable)

Muse discovers project skills under `.agents/skills/` (also imports Claude/Codex
skill roots). From a checkout:

```bash
mkdir -p .agents/skills
ln -sfn "$(pwd)/plugins/runspecimen/muse/skills/runspecimen" \
  .agents/skills/runspecimen
# or:
muse skills install "$(pwd)/plugins/runspecimen/muse/skills/runspecimen" --scope project
muse skills validate "$(pwd)/plugins/runspecimen/muse/skills/runspecimen"
```

Alternatively: `muse skills import --from claude` after the Claude plugin skill
is available, then keep the same TTY-approve rules.

### MCP allow-list (stable)

Merge `examples/mcp_settings.fragment.json` into your Muse settings
(`mcp_servers` block). Point `args` at an **absolute** path to
`plugins/runspecimen/scripts/runspecimen_mcp.py`. Mode `optional` so a missing
binary does not abort the session. The server never exposes `approve` or
remote-confirm settle.

### PreToolUse gate (**beta**)

Muse documents project hooks at `.muse/hooks.json` with Claude-shaped nested
`PreToolUse` matchers. Hook trust, enablement, and deny-output details still
move across Muse builds — treat this gate as **beta**.

```bash
mkdir -p .muse
# Copy and edit the command to an absolute path:
cp "$(pwd)/plugins/runspecimen/muse/examples/hooks.beta.json" .muse/hooks.json
```

The example calls:

```text
python3 /ABS/plugins/runspecimen/scripts/block_approve_gate.py --format claude
```

Deny output uses Claude `hookSpecificOutput.permissionDecision`. If your Muse
build ignores that shape, keep the skill + MCP layers and report the mismatch;
do not weaken the CLI TTY boundary.

## Approve-safety

1. Skill instructs pause for human TTY `approve` only.
2. MCP omit `approve` / settle.
3. Beta PreToolUse gate denies approve-like Bash/MCP when hooks are trusted.
4. **Cloud / remote Muse threads** cannot settle local TTY `APPROVE` — they are
   outside the trust boundary.
5. **Multi-agent / worktrees / subagents:** one approved run, one exclusive
   lease — not one approval for a swarm.
6. **Not compatible** with Muse `--yolo` or `--disable-approval` as a
   RunSpecimen substitute. Those flags bypass Muse's own guardrails; they do
   not authorize agents to type `APPROVE` or settle remote-confirm.
7. Companion `can_approve` stays false (no remote approve from plugins).
8. Local-only; no telemetry phone-home.
