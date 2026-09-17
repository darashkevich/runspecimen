# ASC kit status (honest)

Last packaging tip should match PR #6 / `cursor/macos-native-app`.

| Item | Status |
| --- | --- |
| Ad-hoc Archive + nested helper sandbox+inherit | Done (local) |
| Engine freeze **0.2.0rc10** | Done |
| PrivacyInfo + AppIcon | Done |
| Positive sandboxed e2e (bookmark / dashboard / PTY wait) | Done via `Scripts/test_mas_sandbox_e2e.sh` — requires **actual** `Type 'APPROVE' to bind…` prompt + session still waiting; never types APPROVE |
| Store export fail-closed without Apple Distribution | Done — `Scripts/assert_store_export_ready.sh` parses profile fields (exact app id, team, Mac platform, MAS type); `Scripts/test_store_export_gate.sh` negatives |
| Metadata / reviewer demo copy | Ready in this kit |
| ASC screenshot PNGs | **Pending** — 0 PNGs under `screenshots/` (see [screenshots/README.md](screenshots/README.md)) |
| Local e2e / gate evidence | [evidence/](evidence/) — PTY + store-export negatives (not Connect media) |
| Apple Distribution cert + MAS profile | **Pending** Yahor |
| `ExportOptions.mas.plist` teamID ≠ `TEAMID` | **Pending** Yahor |
| ASC app record + Upload | **Pending** Yahor |
| Submit for Review | **Blocked** until Codex QA + Yahor decision |
| App Review approval | **Not claimed** |

Do not merge/publish/submit from automation without Yahor’s release decision.
