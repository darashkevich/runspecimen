# RunSpecimen agent adapter

This plugin teaches Codex and Cursor to put consequential local commands behind
the RunSpecimen lifecycle. It requires the `runspecimen` CLI on `PATH`.

The plugin is an adapter, not the enforcement boundary. It cannot approve a
run, weaken a contract, or replace operating-system sandboxing. A human must
complete `runspecimen approve` in a real terminal before an agent can continue.

For local Cursor testing, symlink this directory to
`~/.cursor/plugins/local/runspecimen`, reload Cursor, and confirm that the
RunSpecimen skill and rule appear in Customize.
