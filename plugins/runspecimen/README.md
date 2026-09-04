# RunSpecimen agent adapter

This plugin teaches Codex and Cursor to put consequential local commands behind
the RunSpecimen lifecycle.

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

## Boundary

The plugin is an adapter, not the enforcement boundary. It cannot approve a
run, weaken a contract, or replace operating-system sandboxing. A human must
complete `runspecimen approve --workspace … --contract …` in a real terminal
before an agent can continue. Receipt checks use:

```bash
runspecimen verify --workspace … --contract … \
  --campaign-id … --run-id …
```
