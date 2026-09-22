# Vertical contract templates

Copy a template into a workspace, point `argv` at a real program inside that
workspace, and approve it on a TTY. These files are examples, not a marketplace
listing.

| Template | Campaign |
| --- | --- |
| `research/contract.json` | One local analysis step, no confinement backend |
| `ml-eval/contract.json` | One evaluation step with an explicit `isolation.backend` of `none` |
| `security/contract.json` | One check step that names the shared policy in `shared-policy/` |

`shared-policy/policy.json` is a workspace-local file. Copy it to the workspace
root as `policy.json` before using `security/contract.json` (that contract's
`policy.path` is `policy.json`). The contract stores the file's SHA-256. There
is no policy server. `isolation.backend` of `none` means the workload is not
confined.
