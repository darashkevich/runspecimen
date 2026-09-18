# RunSpecimen (Gemini CLI)

Use the installed `runspecimen` CLI on `PATH` as the enforcement boundary. This
extension is an adapter only: it cannot approve a run, weaken a contract, or
replace OS sandboxing.

## Hard rules

- Never type or pipe `APPROVE`.
- Never run `runspecimen approve` or settle remote-confirm for the user.
- Never call companion `/v1/approve`.
- Pause after validate and ask the human to approve in a **real terminal**.

## Workflow

1. `runspecimen doctor --workspace <workspace>`
2. Author or edit a version-1 JSON contract only when the user asked for it.
3. `runspecimen validate --workspace <workspace> --contract <contract>`
4. Show the exact command, outputs, timeout, and major limitations.
5. Ask the user to run:

```bash
runspecimen approve --workspace <workspace> --contract <contract>
```

6. After the human confirms approval, run sequentially:
   `preflight` → `run` → `postflight` →
   `verify --campaign-id … --run-id …`. Stop on the first refusal.
7. RunSpecimen is not an OS sandbox. Recommend a container for untrusted
   payloads.

## MCP tools

The bundled MCP server exposes only: about, doctor, validate, status,
preflight, run, postflight, verify, dashboard. There is no `approve` tool.

## Local dashboard

`runspecimen dashboard --workspace … --contract … --open` is loopback-only,
read-only, and blocking — background or detach it. It cannot replace TTY
approval.
