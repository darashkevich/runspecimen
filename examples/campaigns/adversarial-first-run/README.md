# Adversarial first run

This campaign shows the lease, not a product tour.

1. Approve `contract.json` in a real terminal (`runspecimen approve`).
2. Start `runspecimen run` for `first-run/run-001`. The job sleeps, then writes
   `outputs/result.json`.
3. While it is running, start a second `runspecimen run` for any contract in
   the same workspace.

The second command must fail because the workspace already holds the execution
lease. A second worker is not a queue. Do not type `APPROVE` from an agent
shell. `isolation.backend` is `none`: this demo does not confine the process.
