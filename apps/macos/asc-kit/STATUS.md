# ASC kit status (honest)

Last packaging tip should match PR #6 / `cursor/macos-native-app`.

| Item | Status |
| --- | --- |
| Ad-hoc Archive + nested helper sandbox+inherit | Done (local) |
| Engine freeze **0.2.0rc10** | Done |
| PrivacyInfo + AppIcon | Done |
| Positive sandboxed e2e (bookmark / dashboard / PTY wait) | Done via `Scripts/test_mas_sandbox_e2e.sh` |
| Store export fail-closed without Apple Distribution | Done via `Scripts/assert_store_export_ready.sh` |
| Metadata / reviewer demo copy | Ready in this kit |
| ASC screenshot PNGs | **Pending** |
| Apple Distribution cert + MAS profile | **Pending** Yahor |
| `ExportOptions.mas.plist` teamID ≠ `TEAMID` | **Pending** Yahor |
| ASC app record + Upload | **Pending** Yahor |
| Submit for Review | **Blocked** until Codex QA + Yahor decision |
| App Review approval | **Not claimed** |

Do not merge/publish/submit from automation without Yahor’s release decision.
