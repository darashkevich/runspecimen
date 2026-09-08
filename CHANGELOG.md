# Changelog

## 0.2.0rc4 - 2026-09-07

- Harden lifecycle supervision so inherited output pipes, timeouts, and
  interruption all leave bounded captures and a terminal recorded state.
- Bind approvals and receipts to the exact parsed contract bytes, reject unsafe
  source-root symlinks, and recheck expiry at launch.
- Make the local dashboard honest about recorded evidence versus live receipt
  verification; reject cross-origin access, contract drift, and write requests.
- Add a dashboard About panel plus User guide / FAQ links, `docs/ABOUT.md`, and
  a `runspecimen about` command (docs URLs also appear in `doctor` and `--help`).
- Add a fresh `init-demo` onboarding command and a clean-install release gate
  for source archives, wheels, the dashboard, and the plugin package.

## 0.2.0rc3 - 2026-09-04

- Add a contract-scoped, loopback-only local dashboard that renders phase,
  evidence, and the exact lifecycle commands for Codex and Cursor users.
- Keep the dashboard read-only: it cannot approve or execute commands, so the
  real-TTY approval and CLI enforcement boundaries remain intact.
- Teach the Codex and Cursor adapters to launch the dashboard on request.

## 0.2.0rc2 - 2026-09-03

- Execute the exact absolute executable whose digest was approved, including
  correct resolution of relative `PATH` entries against the contract working directory.
- Reject unknown and duplicate contract fields so misspelled safety controls fail closed.
- Add a native Cursor plugin manifest, marketplace metadata, packaged rule, and local-test docs.
- Expand release checks to keep the Python, Codex, and Cursor package versions aligned.

## 0.2.0rc1 - 2026-09-01

- Bind approvals and receipts to the resolved executable SHA-256.
- Remove stale lease-owner metadata and make status report only active holders.
- Add `doctor` and `validate` readiness commands.
- Add Codex plugin and Cursor rule adapters that preserve the TTY approval gate.
- Add threat model, security policy, CI, release checks, and clean-install smoke tests.
- Declare Apache-2.0 licensing and Python 3.9+ support.

## 0.1.0 - 2026-08-24

- Initial bounded-run engine with TTY approval, workspace lease, atomic state,
  predecessor gating, postflight assertions, and tamper-evident receipts.
