---
description: Validate a RunSpecimen contract (never approves)
---

Use the installed `runspecimen` CLI on `PATH`.

1. Confirm `command -v runspecimen`.
2. Run `runspecimen doctor --workspace <workspace>`.
3. Run `runspecimen validate --workspace <workspace> --contract <contract>`.
4. Show the user the exact argv, outputs, timeout, and limitations.
5. Do **not** type `APPROVE`, run `runspecimen approve`, or settle remote-confirm.
   Ask the human to approve in a real terminal when they are ready.
