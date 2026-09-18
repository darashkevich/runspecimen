# JetBrains AI / Junie adapter

RunSpecimen for JetBrains hosts: **Junie CLI** (preferred; Claude-compatible
extension + native marketplace) and a **minimal IntelliJ plugin scaffold** that
shells out to the `runspecimen` CLI. No in-IDE Approve button that bypasses
TTY.

## Prerequisite

`runspecimen` on `PATH`. Adapters never ship the enforcement binary.

## Junie CLI (recommended)

Junie discovers Claude-compatible plugins **and** native
`.junie-extension/marketplace.json` catalogs.

### Option A — Local marketplace (this repo)

In Junie CLI:

```text
/extensions
→ Marketplaces → Add marketplace → /absolute/path/to/runspecimen
→ Install `runspecimen` (user or project scope)
```

Repo catalogs:

- Native: `.junie-extension/marketplace.json`
- Claude-compat: `.claude-plugin/marketplace.json` (also works for Junie)

### Option B — Symlink Claude-shaped package

```bash
# Junie also accepts Claude plugin layout via marketplace / cache.
# For quick local testing, install from the Claude marketplace path:
# /extensions → Add marketplace → /absolute/path/to/runspecimen
```

### What Junie gets

Same package as Claude/Grok under `plugins/runspecimen`:

- Skill + slash commands (validate / status / request-approval / verify)
- PreToolUse approve-gate (`scripts/block_approve_gate.py`)
- Stdio MCP without `approve`
- Native `extension.json` for Junie metadata

**Do not** register a `PermissionRequest` hook that exits 0 without an explicit
deny — Junie treats that as auto-allow. Our gate only runs on `PreToolUse` /
tool matchers and denies approve-like calls.

## IntelliJ / AI Assistant scaffold

Path: `jetbrains/intellij-plugin/`

Minimal Gradle IntelliJ plugin that exposes Tools → RunSpecimen actions:

| Action | Behavior |
| --- | --- |
| Validate | Runs `runspecimen_adapter.py validate …` |
| Status | Runs adapter `status …` |
| Request approval | Copies/shows the **human** `runspecimen approve …` command; does **not** type APPROVE |
| Verify | Runs adapter `verify …` |

There is **no** Approve action and **no** remote-confirm settle action.

Build (optional, developer machine with JDK 17+):

```bash
cd plugins/runspecimen/jetbrains/intellij-plugin
./gradlew buildPlugin
```

Install the generated ZIP via Settings → Plugins → Install from Disk. The
plugin requires `runspecimen` on the IDE's PATH (or set
`runspecimen.path` in the plugin settings once implemented).

**Marketplace:** JetBrains Marketplace **not submitted**. Ship as scaffold +
local install until Yahor publishes.

## IDE action helper (tested)

`scripts/ide_actions.py` maps named IDE/Junie actions onto the shared adapter
allow-list. Used by tests and by the IntelliJ scaffold's ProcessBuilder calls.

```bash
python3 plugins/runspecimen/jetbrains/scripts/ide_actions.py \
  request-approval --workspace . --contract contract.json
```

`approve` is rejected by the allow-list.

## Boundary

- Adapter only — CLI remains the enforcement boundary.
- Never auto-approve, type `APPROVE`, or settle remote-confirm.
- Local-only; no telemetry phone-home.
- Honest claim: orchestration + evidence, **not** an OS sandbox.
