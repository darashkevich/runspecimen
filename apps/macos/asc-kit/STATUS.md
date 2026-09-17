# ASC kit status (honest)

Last packaging tip should match PR #6 / `cursor/macos-native-app`.

| Item | Status |
| --- | --- |
| Ad-hoc Archive + nested helper sandbox+inherit | Done (local) |
| Engine freeze **0.2.0rc10** | Done |
| PrivacyInfo + AppIcon | Done |
| Positive sandboxed e2e (bookmark / dashboard / PTY wait) | Done via `Scripts/test_mas_sandbox_e2e.sh` — requires **actual** `Type 'APPROVE' to bind…` prompt + session still waiting; never types APPROVE |
| Store export fail-closed without Apple Distribution | Done — requires `RS_ARCHIVE_APP` (app + nested helper Apple Distribution); profile field checks; `test_store_export_gate.sh` negatives prove ad-hoc/Developer ID refused before `xcodebuild -exportArchive` |
| Metadata / reviewer demo copy | Ready in this kit |
| ASC screenshot PNGs | **Captured** — 4 real app PNGs under [screenshots/](screenshots/) (ad-hoc MAS; e2e demo path; see caveats in screenshots README) |
| Local e2e / gate evidence | [evidence/](evidence/) — PTY + store-export negatives (not Connect media) |
| Apple Distribution cert + MAS profile | **Pending** Yahor |
| `ExportOptions.mas.plist` teamID ≠ `TEAMID` | **Pending** Yahor |
| ASC app record + Upload | **Pending** Yahor |
| Optional prettier showcase-path reshoot | Optional Yahor |
| Submit for Review | **Blocked** until Codex QA + Yahor decision |
| App Review approval | **Not claimed** |

Do not merge/publish/submit from automation without Yahor’s release decision.
