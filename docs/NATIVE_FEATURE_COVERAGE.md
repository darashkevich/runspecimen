# Native feature coverage

This matrix describes the Mac candidate on this branch. It is not the Mac App Store binary Apple already has.

Published engine **`0.2.0rc14`** does not include the evidence-expansion commands. The submitted package **0.1.4 (9)** (SHA-256 `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`, Apple build `51a18894-02e3-4846-86f5-29cc345567f0`) excludes this work.

Local **0.1.5 (10)** zip `705ced0fa79ca98f951455f68e6fa4a8d08624b686c6579b60678b43e6aac8b0` is an earlier signed app from `b467c63`. Local **0.1.5 (11)** package `2452956fe1179a7e4e019f5de5b2c40aba460ecbc077a7d75af35458b67ce309` is source `3a0f483` and does not include the confirmation or pipe fixes. The next candidate is marketing **0.1.5**, build **12**. It is not uploaded. Digest, diff, and retain stay CLI-only on this candidate; native receipt controls live only on `cursor/native-receipt-parity`.

Store builds keep the browser dashboard and `com.apple.security.network.server` out. The standalone CLI still has `runspecimen dashboard`. No native control types `APPROVE`.

| Feature | Engine | Tests | Native entry | Store sandbox | Authorization |
| --- | --- | --- | --- | --- | --- |
| Requirements report | `requirements report` | `tests/test_evidence_expansion.py` | Evidence → Refresh read-only | Bookmarked workspace. No listening socket | Read-only. `requirements check` runs checks and is not a native button |
| Freshness | `freshness show` | `tests/test_freshness_show.py` | Same refresh | Read-only | `freshness check` writes a report and is not a native button |
| Config inspect | `config inspect` | expansion tests | Same refresh | Read-only | Inspect does not write |
| Config preview | `config preview` | expansion tests | Workspace → Workflows | Read-only | Shows the apply diff. Does not write |
| Config apply / export / rollback | matching CLI commands | expansion tests | Workflows, after confirmation | Writes only the chosen bundle, export file, or backup | Cancel writes nothing. No silent sync |
| Decisions list | `decisions list` | expansion tests | Refresh read-only | Read-only | Listing does not capture |
| Decision capture | `decisions capture` | expansion tests | Workflows, after confirmation | Writes one decision record | Human picks id, rationale, and classification. Does not approve |
| Usage summary | `usage summarize` | expansion tests | Refresh read-only | Read-only | Unknown stays unknown |
| Usage import | `usage import` | expansion tests | Workflows, after confirmation | Writes usage records | Idempotent import. Cancel imports nothing |
| Snapshot compare / preview | `snapshot compare`, `preview-restore` | expansion tests | Workflows | Preview does not write. Restore dest must be outside the workspace | Preview is not restore |
| Snapshot create / restore | `snapshot create`, `restore` | expansion tests | Workflows, after confirmation | Restore is refused inside the workspace | Does not approve or run |
| Coordination | `coordination validate`, `readiness` | expansion tests | Workflows | Plan file only. No network | No auto-merge |
| Evaluations | `eval compare` read-only; `eval run` writes a result | expansion tests | Workflows. Run asks first | Disposable workspaces | Running a suite does not approve the selected contract |
| Scenes | `runspecimen scenes` | expansion tests | Workflows → Prepare or Run checks, after confirmation | Writes `.runspecimen/scenes-demo` | Never types `APPROVE` |

`requirements check` and `freshness check` stay CLI-only because they execute or rewrite evidence. Digest, diff, and retain also stay CLI-only on this candidate. The browser dashboard stays in the standalone CLI and stays out of the Store build.
