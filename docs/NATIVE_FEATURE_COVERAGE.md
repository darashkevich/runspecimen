# Native feature coverage

This matrix is for the integrated successor on this branch. It is not a description of the Mac App Store binary Apple already has.

Published engine **`0.2.0rc14`** does not include these commands. The submitted package **0.1.4 (9)** (SHA-256 `584f68684deb4700cde59b8fb57701c825ea5445d11c0bd451aacb3d380f4c1d`, Apple build `51a18894-02e3-4846-86f5-29cc345567f0`) excludes this work. A separate local package that reused the label 0.1.4 (9) and SHA-256 `758f8d4651ccc4240410d9618a906fdc9cbbb9974c5c53976b9abb646138cf7f` is not that submission.

The successor candidate is marketing version **0.1.5**, build **10**. It is not uploaded.

Store builds keep the browser dashboard and `com.apple.security.network.server` out. The standalone CLI dashboard remains. No native control types `APPROVE`.

| Feature | Engine | Tests | Native entry | Store sandbox | Authorization |
| --- | --- | --- | --- | --- | --- |
| Requirements report | `requirements report` reads a stored evidence report | `tests/test_evidence_expansion.py` | Evidence pane → Refresh read-only | Reads files inside the bookmarked workspace. No listening socket | Read-only. `requirements check` can run checks and is not in the native pane |
| Freshness report | `freshness show` reads a stored report. `freshness check` recomputes and writes | `tests/test_freshness_show.py` | Same refresh, `freshness show` only | Read-only show. Check writes a report and is not a native button | Show does not approve or run |
| Config inspect | `config inspect` | expansion tests | Same refresh | Read-only diagnostics | `config apply`, `export`, and `rollback` change files and are not native buttons |
| Decisions list | `decisions list` | expansion tests | Same refresh | Read-only | `decisions capture` is explicit and not in the native pane |
| Usage summary | `usage summarize` | expansion tests | Same refresh | Read-only | `usage import` writes and is not a native button |
| Snapshots | `snapshot create`, `preview-restore`, `restore`, `compare` | expansion tests | None yet | Restore must target a directory outside the workspace | Not native. Restore is consequential |
| Coordination | `coordination validate`, `readiness` | expansion tests | None yet | Plan files only; no network | Not native. No auto-merge |
| Evaluations | `eval run`, `eval compare` | expansion tests | None yet | `eval run` uses disposable workspaces | Not native. Running a suite is consequential |
| Scenes | `runspecimen scenes` | expansion tests | None yet | Writes under `.runspecimen/scenes-demo` | Not native. Prints APPROVE instructions and never types the phrase |

Bundled engine code without one of the native entries above is not a usable Mac feature.
